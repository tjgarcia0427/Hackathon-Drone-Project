"""Watch help-event validation and bounded, per-server-session deduplication."""
from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

MAX_EVENT_AGE = 60.0
MAX_LOCATION_AGE = 15.0
MAX_LOCATION_ACCURACY = 20.0
MAX_DISPATCH_AGE = 120.0
FUTURE_TOLERANCE = 5.0
RETENTION = 900.0
MAX_RECORDS = 256


class WatchAlert(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    event_id: UUID
    server_session: UUID
    source: Literal["watch_button", "watch_shake"]
    timestamp: AwareDatetime
    test_mode: bool = Field(True, strict=True)
    latitude: float | None = Field(None, gt=-85, lt=85, strict=True)
    longitude: float | None = Field(None, ge=-180, le=180, strict=True)
    accuracy: float | None = Field(None, ge=0, strict=True)
    location_timestamp: AwareDatetime | None = None

    @model_validator(mode="after")
    def complete_location(self):
        fields = (self.latitude, self.longitude, self.accuracy, self.location_timestamp)
        if any(v is not None for v in fields) and not all(v is not None for v in fields):
            raise ValueError("Supply all location fields, or omit all when location is unavailable")
        return self

    def age(self, now: datetime | None = None) -> float:
        return ((now or datetime.now(timezone.utc)) - self.timestamp).total_seconds()

    def location_problem(self, now: datetime | None = None) -> str | None:
        if self.latitude is None:
            return "Location unavailable; no mission created"
        age = ((now or datetime.now(timezone.utc)) - self.location_timestamp).total_seconds()
        if age < -FUTURE_TOLERANCE or age > MAX_LOCATION_AGE:
            return "Location is stale or its clock is ahead; no mission created"
        if self.accuracy > MAX_LOCATION_ACCURACY:
            return "Location accuracy exceeds 20 m; no mission created"
        return None


class AlertStore:
    def __init__(self):
        self.session = str(uuid4())
        self.records: dict[str, dict] = {}

    def prune(self):
        now = time.monotonic()
        for key in list(self.records):
            if now - self.records[key]["received_monotonic"] > RETENTION:
                del self.records[key]

    def add(self, event: WatchAlert, status: str, message: str) -> dict:
        # Never evict a still-retained ID: reject capacity instead of risking a replay.
        if len(self.records) >= MAX_RECORDS:
            raise ValueError("Watch alert capacity reached; wait before sending another alert")
        record = {"event": event.model_dump(mode="json"), "status": status, "message": message,
                  "received_at": time.time(), "received_monotonic": time.monotonic()}
        self.records[str(event.event_id)] = record
        return record

    @staticmethod
    def public(record: dict) -> dict:
        return {**record["event"], "status": record["status"], "message": record["message"],
                "received_at": record["received_at"]}

    def recent(self) -> list[dict]:
        self.prune()
        return [self.public(r) for r in list(self.records.values())[-8:]][::-1]

    def update(self, event_id: str | None, status: str, message: str):
        if event_id in self.records:
            self.records[event_id].update(status=status, message=message)
