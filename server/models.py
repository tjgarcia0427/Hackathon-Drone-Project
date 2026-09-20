"""Shared data models for the rescue command center."""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class FallEvent(BaseModel):
    """Incident input; manual Watch help is not an automatically detected fall."""
    event: Literal["fall_detected", "help_requested"] = "fall_detected"
    latitude: float
    longitude: float
    accuracy: float = Field(10.0, description="GPS accuracy radius in meters")
    timestamp: Optional[str] = None
    source: str = "shortcut"


class DroneState(BaseModel):
    """Telemetry pushed by the drone app every ~1s."""
    drone_id: str = "air2"
    latitude: float
    longitude: float
    altitude_m: float
    heading_deg: float
    gimbal_pitch_deg: float = 0.0
    battery_pct: float = 100.0
    status: str = "idle"  # idle | dispatched | searching | found | rtl


class MissionPlan(BaseModel):
    """The selected AI's proposed mission (validated by safety.py before use)."""
    target_lat: float
    target_lng: float
    search_radius_m: float = Field(ge=5, le=120)
    altitude_m: float = Field(ge=5, le=60)
    pattern: Literal["expanding_square", "spiral", "grid"] = "expanding_square"
    gimbal_pitch_deg: float = Field(-60, ge=-90, le=0)
    rationale: str


class PersonCandidate(BaseModel):
    """One person the AI can see in the current frame. Every visible person is listed, not just the pick."""
    bbox: list[int] = Field(description="pixel box [x1, y1, x2, y2] in the supplied frame; exactly 4 integers")
    posture: Literal["prone", "sitting", "upright", "unknown"]
    is_moving: bool = Field(description="appears to be walking/moving compared with earlier frames; false if unknown")
    subject_confidence: float = Field(ge=0, le=1, description="how likely THIS person is the reported subject")
    reason: str = Field(description="one short sentence: why this person is or is not the subject")


class SearchStep(BaseModel):
    """One decision from the selected AI during the search loop."""
    action: Literal["yaw", "gimbal", "move", "found", "abort"]
    yaw_deg: Optional[float] = Field(None, description="relative yaw, -180..180")
    gimbal_pitch_deg: Optional[float] = Field(None, ge=-90, le=0)
    move_bearing_deg: Optional[float] = Field(None, ge=0, lt=360)
    move_distance_m: Optional[float] = Field(None, ge=0)
    confidence: float = Field(0.0, ge=0, le=1)
    observation: str
    # Subject disambiguation: list every person in frame, then pick one (or nobody).
    candidates: list[PersonCandidate] = Field(default_factory=list)
    chosen_index: Optional[int] = Field(None, ge=0, description="index into candidates of the chosen subject; null if none")
