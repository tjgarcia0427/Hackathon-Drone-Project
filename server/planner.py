"""Claude mission planner + search brain.

Two calls:
  plan_mission(fall)                  -> MissionPlan   (once, at dispatch)
  next_search_step(state, frame, det) -> SearchStep    (each loop iteration)

Both use structured outputs; deterministic server and iPhone limits still validate results.
Set CLAUDE_MODEL to a model available to your account; the scaffold default is unverified.
"""
from __future__ import annotations

import base64
import os

import anthropic

from models import DroneState, FallEvent, MissionPlan, SearchStep

MODEL = os.environ.get("CLAUDE_MODEL", "claude-fable-5-1")
client = anthropic.Anthropic()

PLANNER_SYSTEM = """You are the mission planner for a supervised drone observation demo.
A wearable/Shortcut reports an incident GPS point and accuracy radius. Produce a small search
mission at that reported point. Use altitude around 10m, a search radius of 5–10m, and gimbal
pitch -55 to -70 degrees. Explain in the rationale if that small demo radius does not cover
the reported GPS uncertainty; never claim exhaustive coverage. The server rejects target plus
search radius outside 35m from launch. The pilot must already have taken off and enabled the
iPhone locally. Do not plan autonomous takeoff or changes to the safety limits."""

SEARCH_SYSTEM = """You are the search brain of a supervised drone observation demo looking for a person who fell.
Each turn you get the drone's telemetry, the latest camera frame, a local person-detector result,
and a log of what has already been tried. Decide ONE next action:
- found: a fallen/lying person is clearly visible (confidence >= 0.8). This is a visual candidate for human review.
- yaw: rotate the camera to look at unexplored bearings (use ~45-90 degree steps, relative -180..180).
- gimbal: change camera pitch (e.g. -30 for distance, -75 for directly below; range -90..0).
- move: fly at most 5m toward an unexplored nearby area, compass bearing 0..<360 degrees.
- abort: if the search is hopeless or unsafe.
Prefer completing a full yaw sweep before moving. Do not revisit bearings already covered.
Do not approach a person or assume obstacle clearance from one image. The pilot must keep the path clear.
The server and iPhone enforce distance, speed and altitude limits independently.
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
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"model refused: {getattr(resp, 'stop_details', None)}")
