"""Rescue command center.

Flow:  POST /incident  ->  selected AI plans mission  ->  safety check  ->  POST /dispatch (or auto)
       -> drone flies to target  ->  search loop (frame -> detector -> AI -> safety -> command)
       -> SUBJECT LOCATED broadcast to dashboard.

Run:   uvicorn app:app --host 0.0.0.0 --port 8000
Docs:  ../docs/PROTOCOL.md for the drone WebSocket contract.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import ai_backends
import detector
import geometry
import planner
import safety
import watch_alerts
import telemetry_display
from watch_alerts import WatchAlert
from models import DroneState, FallEvent, MissionPlan, SearchStep
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

AUTO_DISPATCH = os.environ.get("AUTO_DISPATCH", "0") == "1"
ARRIVAL_RADIUS_M = 4.0

app = FastAPI(title="Rescue Command Center")


class State:
    def __init__(self) -> None:
        self.watch = watch_alerts.AlertStore()
        self.watch_event_id: str | None = None
        self.watch_plan_task: asyncio.Task | None = None
        self.planning = False
        self.plan_epoch = 0
        self.incident: FallEvent | None = None
        self.plan: MissionPlan | None = None
        self.plan_verdict: safety.Verdict | None = None
        self.drone: DroneState | None = None
        self.aircraft_readout: dict | None = None
        self.aircraft_readout_at = 0.0
        self.home: tuple[float, float] | None = None  # iPhone ground anchor; simulator falls back to first fix
        self.phase = "idle"  # idle | planned | dispatched | searching | found | aborted
        self.log: list[dict] = []
        self.history: list[str] = []
        self.latest_frame: bytes | None = None
        self.latest_detection: dict | None = None
        self.found: dict | None = None
        self.last_step: dict | None = None  # latest AI decision incl. candidates, for dashboard overlays
        self.step_frame: bytes | None = None  # the exact JPEG that decision was made on (evidence frame)
        self.drone_ws: WebSocket | None = None
        self.dash: set[WebSocket] = set()
        self.pending_acks: dict[str, asyncio.Future] = {}
        self.search_task: asyncio.Task | None = None
        self.telemetry_updates = telemetry_display.LatestTelemetry(self.dash, self.telemetry_payload)

    def display_readout(self) -> dict | None:
        return telemetry_display.age_readout(self.aircraft_readout, time.monotonic()-self.aircraft_readout_at)

    def telemetry_payload(self) -> dict:
        return {"type": "telemetry", "drone": self.drone.model_dump() if self.drone else None,
                "aircraft": self.display_readout(), "navigation_age_ms": self.navigation_age_ms()}

    def navigation_age_ms(self) -> float | None:
        received = getattr(self, "telemetry_at", 0.0)
        return max(0, time.monotonic()-received)*1000 if received else None

    def snapshot(self) -> dict:
        return {
            "watch_alerts": self.watch.recent(),
            "phase": self.phase,
            "planning": self.planning,
            "ai": planner.status(),
            "incident": self.incident.model_dump() if self.incident else None,
            "plan": self.plan.model_dump() if self.plan else None,
            "plan_ok": self.plan_verdict.ok if self.plan_verdict else None,
            "plan_reason": self.plan_verdict.reason if self.plan_verdict else None,
            "drone": self.drone.model_dump() if self.drone else None,
            "aircraft": self.display_readout(),
            "navigation_age_ms": self.navigation_age_ms(),
            "drone_connected": self.drone_ws is not None,
            "detector": detector.available(),
            "found": self.found,
            "last_step": self.last_step,
            "log": self.log[-40:],
        }


S = State()


def log(msg: str, **extra: Any) -> None:
    entry = {"t": time.time(), "msg": msg, **extra}
    S.log.append(entry)
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
    asyncio.get_event_loop().create_task(broadcast({"type": "log", "entry": entry}))


async def broadcast(payload: dict) -> None:
    dead = []
    for ws in list(S.dash):
        try:
            await asyncio.wait_for(ws.send_text(json.dumps(payload)), 1.0)
        except Exception:  # noqa: BLE001
            dead.append(ws)
    for ws in dead:
        S.dash.discard(ws)


async def push_state() -> None:
    await broadcast({"type": "state", "state": S.snapshot()})


# ---------- drone command channel ----------


# Guardian Angel iPhone integration v1
async def iphone_stop(reason: str) -> None:
    """Release app flight control. Does not cancel DJI RTH or stop motors."""
    ws = S.drone_ws
    if ws is not None:
        try:
            await asyncio.wait_for(ws.send_text(json.dumps({
                "type": "cmd", "cmd_id": uuid.uuid4().hex[:8], "action": "stop",
            })), 2.0)
        except Exception as exc:
            log(f"stop delivery failed; pilot intervention required: {exc}")
    log(f"AI control release requested: {reason}")


async def iphone_cancel_mission() -> None:
    task = S.search_task
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def iphone_fresh_frame(after: float) -> float:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        received = getattr(S, "latest_frame_at", 0.0)
        if received > after and time.monotonic() - received < 3.0:
            return received
        await asyncio.sleep(0.1)
    raise RuntimeError("no fresh camera frame after the last action")


def iphone_telemetry_ready() -> bool:
    return S.drone is not None and time.monotonic() - getattr(S, "telemetry_at", 0.0) < 3.0

async def send_cmd(action: str, timeout: float = 25.0, **params: Any) -> dict:
    ws = S.drone_ws
    if ws is None:
        raise RuntimeError("no drone connected")
    cmd_id = uuid.uuid4().hex[:8]
    fut = asyncio.get_running_loop().create_future()
    S.pending_acks[cmd_id] = fut
    try:
        await asyncio.wait_for(ws.send_text(json.dumps({
            "type": "cmd", "cmd_id": cmd_id, "action": action,
            "expires_at_ms": int((time.time() + 5.0) * 1000), **params,
        })), 3.0)
        log(f"→ drone {action} {params}", cmd_id=cmd_id)
        return await asyncio.wait_for(fut, timeout)
    except Exception:
        if action != "rtl":
            await iphone_stop(f"{action} failed or timed out")
        raise
    finally:
        S.pending_acks.pop(cmd_id, None)


# ---------- HTTP ----------

class AIConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["codex", "claude_code", "openai_api", "anthropic_api"]
    model: str = Field("", max_length=120)


@app.get("/ai")
async def ai_status() -> dict:
    return planner.status()


@app.post("/ai/config")
async def ai_config(config: AIConfiguration) -> dict:
    if S.phase != "idle" or S.planning or (S.search_task and not S.search_task.done()) or S.pending_acks:
        raise HTTPException(409, "Reset and wait for active planning/commands before changing AI provider")
    try:
        result = planner.configure(config.provider, config.model)
    except ai_backends.AIError as exc:
        raise HTTPException(400, str(exc)) from exc
    log(f"AI selected: {result['label']} / {result['effective_model']}")
    await push_state()
    return result


def begin_incident(fall: FallEvent, watch_event_id: str | None = None) -> int:
    if S.planning or (S.search_task and not S.search_task.done()) or S.pending_acks:
        raise HTTPException(409, "planning/search/command already in progress")
    S.watch.update(S.watch_event_id, "cancelled", "Superseded by a new operator incident")
    S.plan_epoch += 1
    S.planning = True
    S.watch_event_id = watch_event_id
    S.plan = S.plan_verdict = None
    S.incident, S.found, S.last_step, S.step_frame, S.history = fall, None, None, None, []
    S.phase = "planned"
    log(f"HELP INCIDENT at {fall.latitude:.6f},{fall.longitude:.6f} ±{fall.accuracy}m ({fall.source})")
    return S.plan_epoch


async def complete_incident(fall: FallEvent, epoch: int) -> dict:
    await push_state()
    try:
        proposed = await asyncio.wait_for(asyncio.to_thread(planner.plan_mission, fall), planner.plan_timeout())
    except Exception as e:
        if isinstance(e, TimeoutError):
            e = ai_backends.AIError("AI mission planning exceeded the 60-second deadline")
        log(f"planner failed: {e}")
        raise HTTPException(502, f"planner failed: {e}") from e
    finally:
        S.planning = False
        await push_state()
    if epoch != S.plan_epoch:
        raise HTTPException(409, "Incident planning was cancelled or reset")
    # Navigation uses measured incident coordinates, never an AI-invented target.
    S.plan = proposed.model_copy(update={"target_lat": fall.latitude, "target_lng": fall.longitude})
    home = S.home or (fall.latitude, fall.longitude)
    S.plan_verdict = safety.check_mission(S.plan, *home, S.drone)
    S.watch.update(S.watch_event_id, "planned" if S.plan_verdict.ok else "rejected",
                   "Plan ready for operator dispatch" if S.plan_verdict.ok else S.plan_verdict.reason)
    log(f"mission planned: r={S.plan.search_radius_m}m alt={S.plan.altitude_m}m {S.plan.pattern} "
        f"| safety={'OK' if S.plan_verdict.ok else 'REJECTED: ' + S.plan_verdict.reason}")
    await push_state()
    if epoch != S.plan_epoch or S.plan is None:
        raise HTTPException(409, "Incident planning was cancelled or reset")
    if AUTO_DISPATCH and S.plan_verdict.ok:
        await dispatch()
    return {"ok": True, "plan": S.plan.model_dump(), "safety": S.plan_verdict.__dict__}


@app.post("/incident")
async def incident(fall: FallEvent) -> dict:
    """Legacy Shortcut/dashboard endpoint, waits for planning as before."""
    epoch = begin_incident(fall)
    return await complete_incident(fall, epoch)


@app.get("/watch/status")
async def watch_status() -> dict:
    return {"protocol": 1, "server_session": S.watch.session,
            "max_event_age_seconds": watch_alerts.MAX_EVENT_AGE,
            "max_location_age_seconds": watch_alerts.MAX_LOCATION_AGE,
            "max_accuracy_m": watch_alerts.MAX_LOCATION_ACCURACY,
            "auto_dispatch": AUTO_DISPATCH}


@app.get("/watch/alerts/{event_id}")
async def watch_alert_status(event_id: str) -> dict:
    S.watch.prune()
    record = S.watch.records.get(event_id)
    if not record:
        raise HTTPException(404, "Alert not found in this server session")
    return S.watch.public(record)


async def complete_watch_incident(fall: FallEvent, epoch: int, event_id: str):
    try:
        await complete_incident(fall, epoch)
    except HTTPException as exc:
        S.watch.update(event_id, "cancelled" if epoch != S.plan_epoch else "failed", str(exc.detail))
    except asyncio.CancelledError:
        S.watch.update(event_id, "cancelled", "Planning cancelled")
        raise
    except Exception:
        S.watch.update(event_id, "failed", "Planning failed; check the server log")
        log("Watch incident planning failed unexpectedly")
    finally:
        await push_state()


@app.post("/watch/alerts", status_code=202)
async def watch_alert(event: WatchAlert) -> dict:
    """Acknowledge receipt immediately; model calls run in a separate task."""
    if str(event.server_session) != S.watch.session:
        raise HTTPException(409, "Server restarted or changed; discard this alert, reconnect and send a new one")
    S.watch.prune()
    event_id = str(event.event_id)
    existing = S.watch.records.get(event_id)
    if existing:
        if existing["event"] != event.model_dump(mode="json"):
            raise HTTPException(409, "Event ID already used for a different alert")
        return {"accepted": True, "duplicate": True, **S.watch.public(existing)}
    if not -watch_alerts.FUTURE_TOLERANCE <= event.age() <= watch_alerts.MAX_EVENT_AGE:
        raise HTTPException(422, "Alert is too old or its clock is ahead; send a new alert")
    problem = event.location_problem()
    busy = S.phase != "idle" or S.planning or (S.search_task and not S.search_task.done()) or S.pending_acks
    if event.test_mode:
        status, message = "test_received", "Test alert received; no mission created"
    elif problem:
        status, message = "location_rejected", problem
    elif busy:
        status, message = "busy", "Help alert received; current mission preserved. No mission queued"
    else:
        status, message = "planning", "Help alert received; preparing an operator-reviewed plan"
    try:
        record = S.watch.add(event, status, message)
    except ValueError as exc:
        raise HTTPException(429, str(exc)) from exc
    log(f"Watch {'TEST' if event.test_mode else 'HELP'} received ({event.source}): {message}")
    if status == "planning":
        fall = FallEvent(event="help_requested", latitude=event.latitude, longitude=event.longitude, accuracy=event.accuracy,
                         timestamp=event.timestamp.isoformat(), source=event.source)
        epoch = begin_incident(fall, event_id)
        S.watch_plan_task = asyncio.create_task(complete_watch_incident(fall, epoch, event_id))
    # Never wait on a slow dashboard socket before acknowledging the Watch.
    asyncio.create_task(broadcast({"type": "watch_alert", "alert": S.watch.public(record)}))
    asyncio.create_task(push_state())
    return {"accepted": True, "duplicate": False, **S.watch.public(record)}


@app.post("/dispatch")
async def dispatch() -> dict:
    """Operator hits the button (or AUTO_DISPATCH=1)."""
    if not S.plan or not S.plan_verdict or not S.plan_verdict.ok:
        raise HTTPException(400, "no approved mission")
    if S.drone_ws is None:
        raise HTTPException(503, "no drone connected")
    if S.search_task and not S.search_task.done():
        raise HTTPException(409, "already dispatched")
    if not iphone_telemetry_ready():
        raise HTTPException(409, "fresh aircraft telemetry required")
    if S.home is None or not (5 <= S.plan.altitude_m <= 30) or safety.haversine_m(*S.home, S.plan.target_lat, S.plan.target_lng) > 35:
        raise HTTPException(400, "iPhone demo requires target within 35 m of launch and altitude 5..30 m")
    verdict = safety.check_mission(S.plan, *S.home, S.drone)
    if not verdict.ok:
        raise HTTPException(400, verdict.reason)
    if S.watch_event_id:
        record = S.watch.records.get(S.watch_event_id)
        if not record or time.monotonic() - record["received_monotonic"] > watch_alerts.MAX_DISPATCH_AGE:
            raise HTTPException(409, "Watch destination expired; reset and send a fresh alert")
        if record["status"] != "planned" or record["event"]["test_mode"]:
            raise HTTPException(409, "This Watch alert cannot be dispatched")
        if (S.plan.target_lat, S.plan.target_lng) != (record["event"]["latitude"], record["event"]["longitude"]):
            raise HTTPException(400, "Destination must match the Watch location")
    S.watch.update(S.watch_event_id, "dispatched", "Mission dispatched; pilot supervision required")
    S.phase = "dispatched"
    S.search_task = asyncio.create_task(run_mission())
    await push_state()
    return {"ok": True}


@app.post("/abort")
async def abort() -> dict:
    S.watch.update(S.watch_event_id, "cancelled", "Operator aborted this mission")
    S.plan_epoch += 1
    await iphone_cancel_mission()
    S.phase = "aborted"
    try:
        # iPhone acknowledges actual landing, not just SDK acceptance.
        await send_cmd("rtl", timeout=180)
    except Exception as exc:
        log(f"abort: return not completed ({exc}); pilot must intervene")
        await push_state()
        return {"ok": False, "error": str(exc)}
    await push_state()
    return {"ok": True}


@app.post("/frame")
async def frame(request: Request) -> dict:
    """Publish a matched frame/detection pair, ordered by receive time."""
    if S.drone_ws is None:
        raise HTTPException(409, "no connected drone")
    epoch = getattr(S, "frame_epoch", 0)
    received = time.monotonic()
    data = await request.body()
    if not data or len(data) > 2_000_000:
        raise HTTPException(400, "expected JPEG under 2 MB")
    detection = await asyncio.to_thread(detector.detect, data)
    if S.drone_ws is None or epoch != getattr(S, "frame_epoch", 0):
        raise HTTPException(409, "frame belongs to an old connection or reset")
    if received > getattr(S, "latest_frame_at", 0.0):
        S.latest_frame, S.latest_detection = data, detection
        S.latest_frame_at = received
        await broadcast({"type": "frame", "detection": detection})
    return {"ok": True, "detection": detection}


@app.get("/frame.jpg")
async def frame_jpg():
    from fastapi.responses import Response
    if not S.latest_frame:
        raise HTTPException(404)
    return Response(S.latest_frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/step.jpg")
async def step_jpg():
    """The frame the last AI decision was based on — the evidence an operator reviews on 'found'."""
    from fastapi.responses import Response
    if not S.step_frame:
        raise HTTPException(404)
    return Response(S.step_frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/state")
async def state() -> dict:
    return S.snapshot()


@app.post("/dev/cmd")
async def dev_cmd(body: dict) -> dict:
    """Bench harness: send ONE raw command to the connected bridge, bypassing the mission runner.

    Enabled only with DEV_COMMANDS=1. Intended for props-off checks (gimbal, hold, stop) where GPS is
    unavailable and a full dispatch would be refused, plus a single short `move` for supervised
    flight-test hops. A move runs through the same safety.check_step guard as a mission step
    (0–5 m, inside the 35 m home geofence, battery floor) and still needs the pilot's local
    flight enable on the iPhone.
    """
    if os.environ.get("DEV_COMMANDS", "0") != "1":
        raise HTTPException(403, "set DEV_COMMANDS=1 to enable the bench command endpoint")
    if S.search_task and not S.search_task.done():
        raise HTTPException(409, "mission active; dev commands disabled")
    action = str(body.get("action", ""))
    allowed = {"gimbal", "hold", "stop", "yaw", "move"}
    if action not in allowed:
        raise HTTPException(400, f"action must be one of {sorted(allowed)}")
    params = {k: v for k, v in body.items() if k != "action"}
    if action == "gimbal" and not (isinstance(params.get("pitch"), (int, float)) and -90 <= params["pitch"] <= 0):
        raise HTTPException(400, "gimbal needs pitch -90..0")
    if action == "yaw" and not (isinstance(params.get("deg"), (int, float)) and -180 <= params["deg"] <= 180):
        raise HTTPException(400, "yaw needs deg -180..180")
    if action == "move":
        bearing, dist = params.get("bearing"), params.get("dist")
        if not (isinstance(bearing, (int, float)) and isinstance(dist, (int, float))):
            raise HTTPException(400, "move needs bearing 0..<360 and dist 0..5")
        if S.drone is None or S.home is None:
            raise HTTPException(409, "move needs live telemetry and a ground anchor (home)")
        step = SearchStep(action="move", move_bearing_deg=float(bearing), move_distance_m=float(dist),
                          observation="dev bench move")
        verdict = safety.check_step(step, S.drone, *S.home, 0)
        if not verdict.ok:
            raise HTTPException(400, f"move refused: {verdict.reason}")
        params = {"bearing": float(bearing), "dist": float(dist)}
    try:
        ack = await send_cmd(action, timeout=25, **params)
    except Exception as e:  # noqa: BLE001
        log(f"dev cmd {action} failed: {e}")
        return {"ok": False, "error": str(e)}
    log(f"dev cmd {action} {params} acked")
    return {"ok": True, "ack": ack}


@app.post("/reset")
async def reset() -> dict:
    S.watch.update(S.watch_event_id, "cancelled", "Operator reset this mission")
    S.watch_event_id = None
    S.plan_epoch += 1
    S.frame_epoch = getattr(S, "frame_epoch", 0) + 1
    await iphone_cancel_mission()
    await iphone_stop("mission reset")
    S.incident = S.plan = S.plan_verdict = S.found = S.last_step = S.step_frame = None
    S.history, S.phase = [], "idle"
    S.latest_frame = S.latest_detection = None
    S.latest_frame_at = 0.0
    await push_state()
    return {"ok": True, "note": "AI control release requested; re-enable locally"}


# ---------- mission runner ----------

def describe_candidates(step: SearchStep, frame_dims: tuple[int, int] | None,
                        drone: DroneState, plan: MissionPlan) -> list[dict]:
    """Candidates as the AI reported them, plus a ground-projected position for each box."""
    out = []
    for i, c in enumerate(step.candidates):
        item = {"index": i, **c.model_dump(), "chosen": i == step.chosen_index,
                "est_north_m": None, "est_east_m": None, "est_range_m": None,
                "est_lat": None, "est_lng": None, "est_distance_from_report_m": None}
        hit = None
        if frame_dims and len(c.bbox) == 4:
            hit = geometry.locate(c.bbox, *frame_dims, drone_lat=drone.latitude, drone_lng=drone.longitude,
                                  altitude_m=drone.altitude_m, heading_deg=drone.heading_deg,
                                  gimbal_pitch_deg=drone.gimbal_pitch_deg,
                                  report_lat=plan.target_lat, report_lng=plan.target_lng)
        if hit:
            item.update(est_north_m=hit.north_m, est_east_m=hit.east_m, est_range_m=hit.range_m,
                        est_lat=hit.lat, est_lng=hit.lng, est_distance_from_report_m=hit.distance_from_report_m)
        out.append(item)
    return out


def summarize_candidates(candidates: list[dict], chosen: int | None) -> str:
    """Compact one-liner for the step history the AI reads back (lets it track people across steps)."""
    if not candidates:
        return "0 people in frame"
    parts = []
    for c in candidates:
        d = c.get("est_distance_from_report_m")
        parts.append(f"#{c['index'] + 1}{'*' if c['chosen'] else ''} {c['posture']}"
                     f"{' moving' if c['is_moving'] else ' still'} bbox={c['bbox']}"
                     f"{'' if d is None else f' ~{d}m from report'} p={c['subject_confidence']:.2f}")
    who = "no subject chosen" if chosen is None or chosen >= len(candidates) else f"subject=#{chosen + 1}"
    return f"{len(candidates)} people in frame, {who}: " + "; ".join(parts)


async def run_mission() -> None:
    plan = S.plan
    assert plan is not None
    try:
        await send_cmd("goto", lat=plan.target_lat, lng=plan.target_lng, alt=plan.altitude_m, timeout=120)
        await send_cmd("gimbal", pitch=plan.gimbal_pitch_deg)
        S.phase = "searching"
        await push_state()
        home = S.home or (plan.target_lat, plan.target_lng)
        for step_no in range(safety.LIMITS["max_search_steps"]):
            frame_at = await iphone_fresh_frame(time.monotonic())
            if not iphone_telemetry_ready():
                raise RuntimeError("lost telemetry")
            judged_frame = S.latest_frame
            step: SearchStep = await asyncio.wait_for(asyncio.to_thread(
                planner.next_search_step, S.drone, judged_frame, S.latest_detection,
                S.history, plan.target_lat, plan.target_lng,
            ), planner.search_timeout())
            if not iphone_telemetry_ready() or time.monotonic() - frame_at > planner.search_timeout() + 5.0:
                raise RuntimeError("planner result based on stale frame/telemetry")
            verdict = safety.check_step(step, S.drone, *home, step_no)
            frame_dims = geometry.frame_size(judged_frame)
            S.step_frame = judged_frame
            candidates = describe_candidates(step, frame_dims, S.drone, plan)
            desc = (f"step {step_no + 1}: {step.action} "
                    f"{step.model_dump(exclude_none=True, exclude={'action', 'observation', 'candidates', 'chosen_index'})} "
                    f"[{summarize_candidates(candidates, step.chosen_index)}] — {step.observation}")
            S.history.append(desc)
            log(("✓ " if verdict.ok else f"✗ ({verdict.reason}) ") + desc)
            S.last_step = {"step": step.model_dump(), "candidates": candidates, "frame": frame_dims,
                           "ok": verdict.ok, "reason": verdict.reason}
            await broadcast({"type": "step", **S.last_step})
            if not verdict.ok:
                continue
            if step.action == "found":
                pick = candidates[step.chosen_index]
                S.found = {
                    "lat": S.drone.latitude, "lng": S.drone.longitude,
                    "confidence": step.confidence,
                    "distance_from_report_m": round(safety.haversine_m(
                        plan.target_lat, plan.target_lng, S.drone.latitude, S.drone.longitude), 1),
                    "observation": step.observation,
                    # Subject-level estimate: chosen bbox projected onto the ground (null if the ray missed).
                    "people_in_frame": len(candidates),
                    "subject": pick,
                    "subject_lat": pick.get("est_lat"), "subject_lng": pick.get("est_lng"),
                    "subject_distance_from_report_m": pick.get("est_distance_from_report_m"),
                    "candidates": candidates,
                }
                S.phase = "found"
                S.watch.update(S.watch_event_id, "found", "Visual candidate found; operator review required")
                subject_d = pick.get("est_distance_from_report_m")
                log(f"SUBJECT LOCATED — {len(candidates)} in frame, subject {pick['posture']}"
                    f"{'' if subject_d is None else f' ~{subject_d}m from report'} "
                    f"(aircraft {S.found['distance_from_report_m']}m), conf {step.confidence:.2f}")
                await send_cmd("hold")
                await push_state()
                return
            if step.action == "abort":
                break
            if step.action == "yaw":
                await send_cmd("yaw", deg=step.yaw_deg)
            elif step.action == "gimbal":
                await send_cmd("gimbal", pitch=step.gimbal_pitch_deg)
            elif step.action == "move":
                await send_cmd("move", bearing=step.move_bearing_deg, dist=step.move_distance_m)
        S.phase = "aborted"
        S.watch.update(S.watch_event_id, "aborted", "Search ended without a find")
        log("search ended without a find — returning home")
        await send_cmd("rtl", timeout=180)
    except asyncio.CancelledError:
        log("mission cancelled")
        raise
    except Exception as e:  # noqa: BLE001
        S.phase = "aborted"
        if isinstance(e, TimeoutError):
            e = ai_backends.AIError("AI search or command response exceeded its deadline")
        S.watch.update(S.watch_event_id, "failed", "Mission failed; pilot intervention required")
        log(f"mission error: {e}")
        await iphone_stop("mission failed")
    finally:
        await push_state()


# ---------- WebSockets ----------

@app.websocket("/ws/drone")
async def ws_drone(ws: WebSocket) -> None:
    await ws.accept()
    if S.drone_ws is not None:
        await ws.close(code=1008, reason="one drone connection allowed")
        return
    S.frame_epoch = getattr(S, "frame_epoch", 0) + 1
    S.drone = None
    S.aircraft_readout = None
    S.aircraft_readout_at = 0.0
    S.telemetry_at = 0.0
    S.latest_frame = S.latest_detection = None
    S.latest_frame_at = 0.0
    S.drone_ws = ws
    log("drone connected")
    await push_state()
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            t = msg.get("type")
            if t in ("telemetry", "aircraft_status") and isinstance(msg.get("aircraft"), dict):
                S.aircraft_readout = telemetry_display.clean_readout(msg["aircraft"])
                S.aircraft_readout_at = time.monotonic()
            if t == "aircraft_status":
                # A GPS-less observation is display-only: do not create DroneState,
                # record a home point or refresh navigation readiness.
                S.telemetry_updates.publish()
            elif t == "telemetry":
                S.telemetry_at = time.monotonic()
                S.drone = DroneState(**{k: v for k, v in msg.items() if k != "type"})
                if S.home is None:
                    S.home = (float(msg.get("home_latitude", S.drone.latitude)), float(msg.get("home_longitude", S.drone.longitude)))
                    log(f"home set {S.home[0]:.6f},{S.home[1]:.6f}")
                S.telemetry_updates.publish()
            elif t == "ack":
                fut = S.pending_acks.get(msg.get("cmd_id", ""))
                if fut and not fut.done():
                    if msg.get("ok", True):
                        fut.set_result(msg)
                    else:
                        fut.set_exception(RuntimeError(msg.get("error", "drone nack")))
            elif t == "hello":
                log(f"drone hello: {msg.get('drone_id')} ({msg.get('model', '?')})")
    except WebSocketDisconnect:
        pass
    finally:
        S.plan_epoch += 1
        S.watch.update(S.watch_event_id, "cancelled", "Aircraft disconnected; reset before another mission")
        await iphone_cancel_mission()
        S.drone_ws = None
        S.aircraft_readout = None
        S.aircraft_readout_at = 0.0
        S.telemetry_at = 0.0
        S.frame_epoch = getattr(S, "frame_epoch", 0) + 1
        for fut in list(S.pending_acks.values()):
            if not fut.done():
                fut.set_exception(RuntimeError("drone disconnected"))
        log("drone disconnected")
        await push_state()


@app.websocket("/ws/dashboard")
async def ws_dashboard(ws: WebSocket) -> None:
    await ws.accept()
    S.dash.add(ws)
    await ws.send_text(json.dumps({"type": "state", "state": S.snapshot()}))
    try:
        while True:
            await ws.receive_text()  # keepalive / ignore
    except WebSocketDisconnect:
        S.telemetry_updates.remove(ws)


@app.get("/")
async def index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))


app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
