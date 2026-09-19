"""Claude mission planner + search brain.

Two calls:
  plan_mission(fall)                  -> MissionPlan   (once, at dispatch)
  next_search_step(state, frame, det) -> SearchStep    (each loop iteration)

Both use structured outputs so the result is always schema-valid JSON.
Model defaults to Claude Fable 5.1 (the event's headline model); override with CLAUDE_MODEL.
"""
from __future__ import annotations

import base64
import os

import anthropic

from models import DroneState, FallEvent, MissionPlan, SearchStep

MODEL = os.environ.get("CLAUDE_MODEL", "claude-fable-5-1")
client = anthropic.Anthropic()

PLANNER_SYSTEM = """You are the mission planner for an autonomous search-and-rescue drone.
A wearable reported a fall at a GPS point with a given accuracy radius. Produce a search mission
around that point. Keep altitude modest (15-25m) so a person on the ground is visible to the camera,
size the search radius to ~3x the GPS accuracy (min 20m), and pitch the gimbal down (-55 to -70)."""

SEARCH_SYSTEM = """You are the search brain of a rescue drone looking for a person who fell.
Each turn you get the drone's telemetry, the latest camera frame, a local person-detector result,
and a log of what has already been tried. Decide ONE next action:
- found: a fallen/lying person is clearly visible (confidence >= 0.8). Stop there.
- yaw: rotate the camera to look at unexplored bearings (use ~45-90 degree steps).
- gimbal: change camera pitch (e.g. -30 for distance, -75 for directly below).
- move: fly up to 15m toward an unexplored area of the search radius.
- abort: only if the search is hopeless or unsafe.
Prefer completing a full yaw sweep before moving. Do not revisit bearings already covered.
Be honest in the observation about what you actually see."""


def plan_mission(fall: FallEvent) -> MissionPlan:
    resp = client.messages.parse(
        model=MODEL,
        max_tokens=2048,
        system=PLANNER_SYSTEM,
        output_config={"effort": "low"},
        messages=[{
            "role": "user",
            "content": (
                f"Fall reported at lat={fall.latitude}, lng={fall.longitude}, "
                f"GPS accuracy ±{fall.accuracy}m, source={fall.source}. Plan the mission."
            ),
        }],
        output_format=MissionPlan,
    )
    _raise_on_refusal(resp)
    return resp.parsed_output


def next_search_step(
    drone: DroneState,
    frame_jpeg: bytes | None,
    detection: dict | None,
    history: list[str],
    target_lat: float,
    target_lng: float,
) -> SearchStep:
    content: list[dict] = []
    if frame_jpeg:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.standard_b64encode(frame_jpeg).decode("utf-8"),
            },
        })
    det_txt = "none" if not detection else (
        f"person={detection.get('person', False)} conf={detection.get('confidence', 0):.2f} "
        f"bbox={detection.get('bbox')}"
    )
    content.append({
        "type": "text",
        "text": (
            f"Target: {target_lat:.6f},{target_lng:.6f}\n"
            f"Drone: lat={drone.latitude:.6f} lng={drone.longitude:.6f} alt={drone.altitude_m:.1f}m "
            f"heading={drone.heading_deg:.0f} gimbal={drone.gimbal_pitch_deg:.0f} battery={drone.battery_pct:.0f}%\n"
            f"Local detector: {det_txt}\n"
            f"Steps so far ({len(history)}):\n" + ("\n".join(f"- {h}" for h in history) or "- none") +
            "\n\nChoose the next action."
        ),
    })
    resp = client.messages.parse(
        model=MODEL,
        max_tokens=2048,
        system=SEARCH_SYSTEM,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": content}],
        output_format=SearchStep,
    )
    _raise_on_refusal(resp)
    return resp.parsed_output


def _raise_on_refusal(resp) -> None:
    # Fable 5.1 can return HTTP 200 with stop_reason "refusal"; treat as a planner failure.
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"model refused: {getattr(resp, 'stop_details', None)}")
