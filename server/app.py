"""Rescue command center.

Flow:  POST /incident  ->  Claude plans mission  ->  safety check  ->  POST /dispatch (or auto)
       -> drone flies to target  ->  search loop (frame -> detector -> Claude -> safety -> command)
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

import detector
import planner
import safety
from models import DroneState, FallEvent, MissionPlan, SearchStep

AUTO_DISPATCH = os.environ.get("AUTO_DISPATCH", "0") == "1"
ARRIVAL_RADIUS_M = 4.0

app = FastAPI(title="Rescue Command Center")


class State:
    def __init__(self) -> None:
        self.incident: FallEvent | None = None
        self.plan: MissionPlan | None = None
        self.plan_verdict: safety.Verdict | None = None
        self.drone: DroneState | None = None
        self.home: tuple[float, float] | None = None  # iPhone ground anchor; simulator falls back to first fix
        self.phase = "idle"  # idle | planned | dispatched | searching | found | aborted
        self.log: list[dict] = []
        self.history: list[str] = []
        self.latest_frame: bytes | None = None
        self.latest_detection: dict | None = None
        self.found: dict | None = None
        self.drone_ws: WebSocket | None = None
        self.dash: set[WebSocket] = set()
        self.pending_acks: dict[str, asyncio.Future] = {}
        self.search_task: asyncio.Task | None = None

    def snapshot(self) -> dict:
        return {
            "phase": self.phase,
            "incident": self.incident.model_dump() if self.incident else None,
            "plan": self.plan.model_dump() if self.plan else None,
            "plan_ok": self.plan_verdict.ok if self.plan_verdict else None,
            "plan_reason": self.plan_verdict.reason if self.plan_verdict else None,
            "drone": self.drone.model_dump() if self.drone else None,
            "drone_connected": self.drone_ws is not None,
            "detector": detector.available(),
            "found": self.found,
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
    for ws in S.dash:
        try:
            await ws.send_text(json.dumps(payload))
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

@app.post("/incident")
async def incident(fall: FallEvent) -> dict:
    """Entry point for the phone/watch Shortcut."""
    if S.search_task and not S.search_task.done():
        raise HTTPException(409, "search already in progress")
    S.incident, S.found, S.history = fall, None, []
    S.phase = "planned"
    log(f"FALL DETECTED at {fall.latitude:.6f},{fall.longitude:.6f} ±{fall.accuracy}m")
    try:
        S.plan = await asyncio.to_thread(planner.plan_mission, fall)
    except Exception as e:  # noqa: BLE001
        log(f"planner failed: {e}")
        raise HTTPException(502, f"planner failed: {e}") from e
    home = S.home or (fall.latitude, fall.longitude)
    S.plan_verdict = safety.check_mission(S.plan, *home, S.drone)
    log(f"mission planned: r={S.plan.search_radius_m}m alt={S.plan.altitude_m}m {S.plan.pattern} "
        f"| safety={'OK' if S.plan_verdict.ok else 'REJECTED: ' + S.plan_verdict.reason}")
    await push_state()
    if AUTO_DISPATCH and S.plan_verdict.ok:
        await dispatch()
    return {"ok": True, "plan": S.plan.model_dump(), "safety": S.plan_verdict.__dict__}


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
    S.phase = "dispatched"
    S.search_task = asyncio.create_task(run_mission())
    await push_state()
    return {"ok": True}


@app.post("/abort")
async def abort() -> dict:
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


@app.get("/state")
async def state() -> dict:
    return S.snapshot()


@app.post("/reset")
async def reset() -> dict:
    S.frame_epoch = getattr(S, "frame_epoch", 0) + 1
    await iphone_cancel_mission()
    await iphone_stop("mission reset")
    S.incident = S.plan = S.plan_verdict = S.found = None
    S.history, S.phase = [], "idle"
    S.latest_frame = S.latest_detection = None
    S.latest_frame_at = 0.0
    await push_state()
    return {"ok": True, "note": "AI control release requested; re-enable locally"}


# ---------- mission runner ----------

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
            step: SearchStep = await asyncio.to_thread(
                planner.next_search_step, S.drone, S.latest_frame, S.latest_detection,
                S.history, plan.target_lat, plan.target_lng,
            )
            if not iphone_telemetry_ready() or time.monotonic() - frame_at > 10.0:
                raise RuntimeError("planner result based on stale frame/telemetry")
            verdict = safety.check_step(step, S.drone, *home, step_no)
            desc = f"step {step_no + 1}: {step.action} {step.model_dump(exclude_none=True, exclude={'action', 'observation'})} — {step.observation}"
            S.history.append(desc)
            log(("✓ " if verdict.ok else f"✗ ({verdict.reason}) ") + desc)
            await broadcast({"type": "step", "step": step.model_dump(), "ok": verdict.ok, "reason": verdict.reason})
            if not verdict.ok:
                continue
            if step.action == "found":
                S.found = {
                    "lat": S.drone.latitude, "lng": S.drone.longitude,
                    "confidence": step.confidence,
                    "distance_from_report_m": round(safety.haversine_m(
                        plan.target_lat, plan.target_lng, S.drone.latitude, S.drone.longitude), 1),
                    "observation": step.observation,
                }
                S.phase = "found"
                log(f"SUBJECT LOCATED — {S.found['distance_from_report_m']}m from report, conf {step.confidence:.2f}")
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
        log("search ended without a find — returning home")
        await send_cmd("rtl", timeout=180)
    except asyncio.CancelledError:
        log("mission cancelled")
        raise
    except Exception as e:  # noqa: BLE001
        S.phase = "aborted"
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
            if t == "telemetry":
                S.telemetry_at = time.monotonic()
                S.drone = DroneState(**{k: v for k, v in msg.items() if k != "type"})
                if S.home is None:
                    S.home = (float(msg.get("home_latitude", S.drone.latitude)), float(msg.get("home_longitude", S.drone.longitude)))
                    log(f"home set {S.home[0]:.6f},{S.home[1]:.6f}")
                await broadcast({"type": "telemetry", "drone": S.drone.model_dump()})
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
        await iphone_cancel_mission()
        S.drone_ws = None
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
        S.dash.discard(ws)


@app.get("/")
async def index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))


app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
