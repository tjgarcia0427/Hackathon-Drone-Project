"""Opt-in, single-owner agent interface. The phone remains the flight controller.

No provider/model calls here. OpenClaw owns the reasoning session; this module
owns leases, evidence, limits and command completion. One uvicorn worker only.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import time
from uuid import UUID, uuid4
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt
import geometry
import safety
from models import SearchStep

MODES = {"observe": 0, "camera": 1, "flight": 2}
LEASE_SECONDS = 90.0
MISSION_SECONDS = 600.0
OBSERVATION_SECONDS = 30.0


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Begin(Strict):
    objective: str = Field(min_length=1, max_length=2000)
    mode: Literal["observe", "camera", "flight"] = "observe"
    target_lat: Optional[float] = Field(None, gt=-85, lt=85, strict=True)
    target_lng: Optional[float] = Field(None, ge=-180, le=180, strict=True)
    watch_event_id: Optional[UUID] = None


class Owned(Strict):
    mission_id: UUID
    lease: str = Field(min_length=32, max_length=64)


class Act(Owned):
    action_id: UUID
    observation_id: UUID
    action: Literal["request_takeoff", "navigate", "move", "yaw", "gimbal", "hold", "return_home", "report_candidate"]
    altitude_m: Optional[float] = Field(None, ge=1, le=30, strict=True)
    bearing: Optional[float] = Field(None, ge=0, lt=360, strict=True)
    distance_m: Optional[float] = Field(None, ge=0, le=5, strict=True)
    degrees: Optional[float] = Field(None, ge=-180, le=180, strict=True)
    pitch: Optional[float] = Field(None, ge=-90, le=0, strict=True)
    bbox: Optional[list[StrictInt]] = Field(None, min_length=4, max_length=4)
    confidence: Optional[float] = Field(None, ge=0, le=1, strict=True)
    note: str = Field("", max_length=1000)


class MemoryNote(Owned):
    note: str = Field(min_length=1, max_length=2000)


def active(state):
    controller = getattr(state, "agent_api", None)
    return bool(controller and controller.current and controller.current["status"] in ("active", "stopping"))


def summary(state):
    controller = getattr(state, "agent_api", None)
    return controller.public() if controller else None


async def invalidate(state, reason):
    controller = getattr(state, "agent_api", None)
    if controller:
        await controller.close(reason)


class Controller:
    def __init__(self, runtime):
        self.r = runtime
        self.state = runtime.S
        self.current = None
        self.lease = ""
        self.expires = 0.0
        self.started = 0.0
        self.actions = {}
        self.observations = {}
        self.task = None
        self.watchdog = None
        self.last_action_at = 0.0
        self.steps = 0
        self.directory = Path(os.getenv("GA_AGENT_MEMORY_DIR", str(Path(__file__).parent / "data" / "agent")))

    def public(self):
        if not self.current:
            return None
        return {**self.current, "events": self.current["events"][-16:], "lease_remaining_s": max(0, self.expires-time.monotonic()),
                "action_active": bool(self.task and not self.task.done()), "steps_used": self.steps,
                "max_steps": safety.LIMITS["max_search_steps"]}

    def persist(self):
        # Write before sending a command; disk errors fail closed. No credentials
        # or live control leases survive a restart. Frames are retained only for candidates.
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / (self.current["mission_id"] + ".json")
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.current, allow_nan=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def record(self, kind, **fields):
        self.current["events"].append({"at": time.time(), "kind": kind, **fields})
        self.current["events"] = self.current["events"][-100:]
        self.persist()

    def own(self, owner):
        if not active(self.state) or self.current["status"] != "active" or str(owner.mission_id) != self.current["mission_id"] or not hmac.compare_digest(owner.lease, self.lease):
            raise HTTPException(409, "No matching active mission lease; do not replay old commands")
        now = time.monotonic()
        if now > self.expires or now-self.started > MISSION_SECONDS:
            raise HTTPException(409, "Mission lease expired; stop and start a new supervised mission")
        self.expires = now + LEASE_SECONDS

    def controls(self):
        if time.monotonic()-getattr(self.state, "agent_control_at", 0) > 3:
            return {}
        return getattr(self.state, "agent_control", {})

    async def begin(self, body):
        s = self.state
        if active(s) or (self.task and not self.task.done()) or s.planning or s.pending_acks or (s.search_task and not s.search_task.done()) or s.phase != "idle":
            raise HTTPException(409, "Reset the dashboard and wait for existing work before starting an agent mission")
        if MODES[body.mode] > MODES.get(os.getenv("GA_AGENT_MAX_MODE", "observe"), 0):
            raise HTTPException(403, "Requested mode exceeds GA_AGENT_MAX_MODE on the server")
        if s.drone_ws is None:
            raise HTTPException(409, "Connect the phone first")
        target = None
        if (body.target_lat is None) != (body.target_lng is None):
            raise HTTPException(422, "Supply both target coordinates")
        if body.target_lat is not None:
            target = [body.target_lat, body.target_lng]
        if body.watch_event_id:
            record = s.watch.records.get(str(body.watch_event_id))
            if not record or record["event"]["test_mode"] or record["status"] != "awaiting_agent" or time.monotonic()-record["received_monotonic"] > self.r.watch_alerts.MAX_DISPATCH_AGE:
                raise HTTPException(409, "Watch alert is not a fresh, actionable agent alert")
            target = [record["event"]["latitude"], record["event"]["longitude"]]
        self.current = {"mission_id": str(uuid4()), "objective": body.objective, "mode": body.mode,
                        "target": target, "watch_event_id": str(body.watch_event_id) if body.watch_event_id else None,
                        "status": "active", "created_at": time.time(), "events": []}
        self.actions, self.observations, self.steps = {}, {}, 0
        self.lease = uuid4().hex + uuid4().hex
        self.started = time.monotonic()
        self.expires = self.started + LEASE_SECONDS
        self.last_action_at = 0
        try:
            self.record("started")
        except OSError as exc:
            self.current = None
            raise HTTPException(503, "Cannot write mission memory; no control acquired") from exc
        s.watch.update(self.current["watch_event_id"], "agent_active", "Agent mission claimed; pilot supervision required")
        self.watchdog = asyncio.create_task(self.monitor())
        self.r.log(f"OpenClaw mission started ({body.mode})", mission_id=self.current["mission_id"])
        await self.r.push_state()
        return {"mission": self.public(), "lease": self.lease}

    async def monitor(self):
        try:
            while active(self.state):
                await asyncio.sleep(1)
                if time.monotonic() > self.expires or time.monotonic()-self.started > MISSION_SECONDS:
                    await self.close("Agent lease or ten-minute mission deadline expired")
                    return
        except asyncio.CancelledError:
            pass

    async def close(self, reason):
        if not self.current or self.current["status"] != "active":
            return
        # Mark closed before the first await: no command can slip in during STOP.
        self.current["status"] = "stopping"
        self.current["ended_at"] = time.time()
        self.lease = ""
        self.expires = 0
        task = self.task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self.watchdog and self.watchdog != asyncio.current_task():
            self.watchdog.cancel()
        # Observation-only sessions never acquire aircraft control.
        if self.current["mode"] != "observe":
            await self.r.iphone_stop(reason)
        self.current["status"] = "stopped"
        self.state.watch.update(self.current["watch_event_id"], "cancelled", reason)
        try:
            self.record("stopped", reason=reason)
        except OSError:
            self.r.log("Agent memory write failed during STOP; pilot control requested")
        await self.r.push_state()

    def observation(self, owner):
        self.own(owner)
        s, now = self.state, time.monotonic()
        frame_at = getattr(s, "latest_frame_at", 0)
        ready = bool(s.latest_frame and now-frame_at < 3 and frame_at > self.last_action_at)
        jpeg = s.latest_frame if ready else None
        dimensions = geometry.frame_size(jpeg) if jpeg else None
        if not dimensions:
            jpeg = None
        identifier = str(uuid4())
        drone = s.drone.model_dump() if self.r.iphone_telemetry_ready() else None
        obs = {"observation_id": identifier, "received_at": time.time(), "navigation": drone,
               "navigation_age_ms": s.navigation_age_ms(), "aircraft": s.display_readout(),
               "control": self.controls(), "frame": {"available": jpeg is not None,
                   "received_age_ms": (now-frame_at)*1000 if frame_at else None,
                   "sha256": hashlib.sha256(jpeg).hexdigest() if jpeg else None,
                   "width": dimensions[0] if dimensions else None, "height": dimensions[1] if dimensions else None},
               "mission": self.public(), "watch_alerts": s.watch.recent(),
               "limits": safety.LIMITS, "decision_expires_in_s": OBSERVATION_SECONDS}
        self.observations[identifier] = {"at": now, "frame_at": frame_at, "jpeg": jpeg,
                                        "dimensions": dimensions, "public": obs}
        while len(self.observations) > 4:
            del self.observations[next(iter(self.observations))]
        return {**obs, "jpeg_base64": base64.b64encode(jpeg).decode() if jpeg else None}

    def validate(self, body):
        s, action, now = self.state, body.action, time.monotonic()
        control = self.controls()
        observation = self.observations.get(str(body.observation_id))
        if not observation or now-observation["at"] > OBSERVATION_SECONDS or observation["at"] <= self.last_action_at:
            raise HTTPException(409, "Observation expired or predates the last action; observe again")
        if s.drone_ws is None or not control:
            raise HTTPException(409, "Fresh control status from the updated iPhone is required")
        mode = self.current["mode"]
        required = "observe" if action == "report_candidate" else "camera" if action == "gimbal" else "flight"
        if MODES[mode] < MODES[required]:
            raise HTTPException(403, "Action not permitted in this mission mode")
        if action not in ("hold", "return_home", "report_candidate") and self.steps >= safety.LIMITS["max_search_steps"]:
            raise HTTPException(409, "Action budget reached; hold, return home or stop")
        if action == "request_takeoff":
            # The iPhone boxes these gates as NSNumber ints (1/0), not JSON booleans.
            if control.get("takeoff_request_supported") not in (True, 1) or control.get("takeoff_ready") not in (True, 1):
                raise HTTPException(409, control.get("takeoff_problem") or "Phone is not ready for pilot takeoff")
            return "request_takeoff", {}, 65, observation
        if action == "report_candidate":
            if not observation["jpeg"] or now-observation["frame_at"] > OBSERVATION_SECONDS or body.bbox is None or not geometry.frame_size(observation["jpeg"]) or not self.r.models_valid_bbox(body.bbox, observation["dimensions"]) or body.confidence is None or not body.note.strip():
                raise HTTPException(422, "Candidate needs current evidence, an in-frame bbox, confidence and description")
            return None, {}, 0, observation
        if control.get("camera_enabled") is not True:
            raise HTTPException(409, "Pilot must enable camera or flight control on the phone")
        if action == "gimbal":
            if body.pitch is None:
                raise HTTPException(422, "pitch required")
            return "gimbal", {"pitch": body.pitch}, 25, observation
        if control.get("flight_enabled") is not True or not self.r.iphone_telemetry_ready():
            raise HTTPException(409, "Fresh navigation and pilot-enabled flight required")
        home = control.get("home")
        if not isinstance(home, list) or len(home) != 2 or not all(type(v) in (int, float) and math.isfinite(v) for v in home):
            raise HTTPException(409, "Fresh phone ground anchor required")
        d = s.drone
        if not all(math.isfinite(v) for v in (d.latitude, d.longitude, d.altitude_m, d.battery_pct, d.heading_deg, d.gimbal_pitch_deg)) or not -85 < d.latitude < 85 or not -85 < home[0] < 85 or not -180 <= d.longitude <= 180 or not -180 <= home[1] <= 180:
            raise HTTPException(409, "Invalid navigation")
        # Hold/RTH remain available for ending a mission at the battery floor.
        if action == "hold":
            return "hold", {}, 25, observation
        if action == "return_home":
            return "rtl", {}, 180, observation
        if not safety.LIMITS["min_altitude_m"] <= d.altitude_m <= safety.LIMITS["max_altitude_m"] or d.battery_pct < 30 or safety.haversine_m(*home, d.latitude, d.longitude) > 35:
            raise HTTPException(409, "Aircraft outside agent flight envelope")
        old = observation["public"]["navigation"]
        if not old or safety.haversine_m(old["latitude"], old["longitude"], d.latitude, d.longitude) > 2 or abs(old["altitude_m"]-d.altitude_m) > 1 or abs((old["heading_deg"]-d.heading_deg+180)%360-180) > 5 or abs(old["gimbal_pitch_deg"]-d.gimbal_pitch_deg) > 3:
            raise HTTPException(409, "Aircraft moved since observation; observe again")
        if action in ("move", "yaw") and (not observation["jpeg"] or now-observation["frame_at"] > OBSERVATION_SECONDS):
            raise HTTPException(409, "A fresh image is required for a visual movement decision")
        if action == "navigate":
            target = self.current["target"]
            if not target or body.altitude_m is None:
                raise HTTPException(422, "Navigate needs a mission target and altitude_m")
            if self.current["watch_event_id"]:
                record = s.watch.records.get(self.current["watch_event_id"])
                if not record or now-record["received_monotonic"] > self.r.watch_alerts.MAX_DISPATCH_AGE:
                    raise HTTPException(409, "Watch destination expired; request a new alert")
            if safety.haversine_m(*home, *target) > 35:
                raise HTTPException(422, "Mission target outside the 35 m fence")
            return "goto", {"lat": target[0], "lng": target[1], "alt": body.altitude_m}, 120, observation
        step = SearchStep(action=action, move_bearing_deg=body.bearing, move_distance_m=body.distance_m,
                          yaw_deg=body.degrees, observation=body.note)
        verdict = safety.check_step(step, d, *home, self.steps)
        if not verdict.ok:
            raise HTTPException(422, verdict.reason)
        params = {"bearing": body.bearing, "dist": body.distance_m} if action == "move" else {"deg": body.degrees}
        return action, params, 25, observation

    async def action(self, body):
        self.own(body)
        identifier = str(body.action_id)
        fingerprint = body.model_dump(mode="json", exclude={"lease"})
        previous = self.actions.get(identifier)
        if previous:
            if previous["request"] != fingerprint:
                raise HTTPException(409, "action_id already used for a different request")
            return previous["result"]
        if (self.task and not self.task.done()) or self.state.pending_acks:
            raise HTTPException(409, "Wait for the current action to finish")
        if len(self.actions) >= 50:
            raise HTTPException(409, "Mission action record limit reached; stop")
        wire_action, params, timeout, obs = self.validate(body)
        result = {"action_id": identifier, "action": body.action, "status": "pending"}
        self.actions[identifier] = {"request": fingerprint, "result": result}
        try:
            self.record("action_requested", request=fingerprint)
        except OSError as exc:
            self.actions.pop(identifier)
            await self.close("Cannot persist action audit")
            raise HTTPException(503, "Memory unavailable; no command sent") from exc
        self.observations.clear()  # no second action may use an old view
        self.last_action_at = time.monotonic()
        if wire_action is None:
            candidate = {"bbox": body.bbox, "confidence": body.confidence, "description": body.note,
                         "frame": obs["public"]["frame"], "observation_id": str(body.observation_id),
                         "aircraft_at_observation": obs["public"]["navigation"], "human_review_required": True}
            try:
                (self.directory / (identifier + ".jpg")).write_bytes(obs["jpeg"])
                self.record("candidate", evidence_file=identifier + ".jpg", **candidate)
            except OSError as exc:
                result.update(status="failed", error="Cannot save candidate evidence")
                await self.close("Candidate memory write failed")
                raise HTTPException(503, "Candidate evidence could not be saved") from exc
            result.update(status="completed", candidate=candidate)
            self.r.log("OpenClaw visual candidate saved for operator review", candidate=candidate)
            await self.r.push_state()
        else:
            if body.action not in ("hold", "return_home"):
                self.steps += 1
            self.task = asyncio.create_task(self.execute(identifier, wire_action, params, timeout))
        return result

    async def execute(self, identifier, action, params, timeout):
        result = self.actions[identifier]["result"]
        try:
            result["ack"] = await self.r.send_cmd(action, timeout=timeout, **params)
            result["status"] = "completed"
        except asyncio.CancelledError:
            result.update(status="cancelled", error="Mission stopped; pilot must verify aircraft state")
            raise
        except Exception as exc:
            result.update(status="failed", error=str(exc))
        finally:
            self.last_action_at = time.monotonic()
            self.observations.clear()
            try:
                self.record("action_result", **result)
            except OSError:
                self.r.log("Agent result memory unavailable")
                # Release control, even though the command may have completed.
                self.expires = 0
            await self.r.push_state()


def install(app, runtime):
    async def auth(authorization: str = Header("")):
        token = os.getenv("GA_AGENT_TOKEN", "")
        if len(token) < 32:
            raise HTTPException(503, "Agent API disabled; configure GA_AGENT_TOKEN (32+ characters)")
        if not hmac.compare_digest(authorization, "Bearer " + token):
            raise HTTPException(401, "Invalid agent token")

    router = APIRouter(prefix="/agent", dependencies=[Depends(auth)])

    def controller():
        if not getattr(runtime.S, "agent_api", None):
            runtime.S.agent_api = Controller(runtime)
        return runtime.S.agent_api

    @router.get("/status")
    async def status():
        return {"protocol": 1, "max_mode": os.getenv("GA_AGENT_MAX_MODE", "observe"),
                "mission": controller().public(), "state": runtime.S.snapshot(),
                "control": controller().controls(), "lease_seconds": LEASE_SECONDS}

    @router.post("/mission")
    async def begin(body: Begin):
        return await controller().begin(body)

    @router.post("/observation")
    async def observation(body: Owned):
        c = controller()
        c.own(body)
        # Let the next 1 Hz JPEG arrive after an action instead of returning the
        # previous view immediately. Bounded wait; disconnect/reset is rechecked.
        if not c.task or c.task.done():
            try:
                await runtime.iphone_fresh_frame(c.last_action_at)
            except RuntimeError:
                pass
        return c.observation(body)

    @router.post("/action", status_code=202)
    async def action(body: Act):
        return await controller().action(body)

    @router.post("/actions/{action_id}/wait")
    async def wait(action_id: UUID, body: Owned):
        c = controller()
        c.own(body)
        record = c.actions.get(str(action_id))
        if not record:
            raise HTTPException(404, "Unknown action")
        if record["result"]["status"] == "pending" and c.task:
            await asyncio.wait({c.task}, timeout=10)
        return record["result"]

    @router.post("/stop")
    async def stop():
        await controller().close("OpenClaw/operator requested STOP")
        return {"ok": True, "mission": controller().public()}

    @router.post("/release")
    async def release(body: Owned):
        c = controller()
        # Cleanup after an uncertain tool call may release only its own mission,
        # even if the lease has expired. It cannot stop a newer conversation.
        if not c.current or str(body.mission_id) != c.current["mission_id"] or not hmac.compare_digest(body.lease, c.lease):
            raise HTTPException(409, "This client no longer owns the mission")
        await c.close("Agent tool cancelled or failed; pilot control")
        return {"ok": True}

    @router.post("/memory")
    async def note(body: MemoryNote):
        c = controller()
        c.own(body)
        try:
            c.record("agent_note", note=body.note)
        except OSError as exc:
            await c.close("Agent memory unavailable")
            raise HTTPException(503, "Memory unavailable") from exc
        return {"ok": True}

    @router.get("/memory/{mission_id}")
    async def memory(mission_id: UUID):
        c = controller()
        path = c.directory / (str(mission_id) + ".json")
        if not path.exists():
            raise HTTPException(404, "Mission memory not found")
        result = json.loads(path.read_text(encoding="utf-8"))
        return {"historical": not(active(runtime.S) and c.current["mission_id"] == str(mission_id)),
                "note": "Memory never grants control or represents current telemetry", "memory": result}

    @router.get("/evidence/{action_id}.jpg")
    async def evidence(action_id: UUID):
        """The exact frame a candidate report was made on (token-gated, read-only, historical)."""
        from fastapi.responses import Response
        path = controller().directory / (str(action_id) + ".jpg")
        if not path.exists():
            raise HTTPException(404, "Evidence frame not found")
        return Response(path.read_bytes(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    app.include_router(router)
