"""Partial aircraft observations and latest-only dashboard delivery.

These readings never create navigation state, set home or refresh flight
readiness. The existing complete telemetry message remains authoritative.
"""
from __future__ import annotations

import asyncio
import json
import math
from typing import Callable


def clean_readout(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("aircraft readout must be an object")
    result = {}
    for name in ("latitude", "longitude", "altitude_m", "heading_deg", "battery_pct",
                 "gimbal_pitch_deg", "gps_signal_level", "satellites", "fc_age_ms",
                 "battery_age_ms", "gimbal_age_ms"):
        value = raw.get(name)
        result[name] = value if type(value) in (int, float) and math.isfinite(value) else None
    for name in ("mock", "aircraft_connected", "gps_ok", "ground_anchor_ok"):
        result[name] = raw.get(name) is True
    result["flying"] = raw.get("flying") if type(raw.get("flying")) is bool else None
    result["drone_id"] = "air2"
    result["altitude_reference"] = "takeoff"
    return age_readout(result, 0)


def age_readout(readout: dict | None, elapsed: float) -> dict | None:
    if readout is None:
        return None
    result = dict(readout)
    for name in ("fc_age_ms", "battery_age_ms", "gimbal_age_ms"):
        age = result.get(name)
        result[name] = max(0, age) + max(0, elapsed)*1000 if age is not None else None
    fc_age = result["fc_age_ms"]
    if not result["aircraft_connected"] or fc_age is None or fc_age >= 1500:
        for name in ("latitude", "longitude", "altitude_m", "heading_deg", "gps_signal_level", "satellites", "flying"):
            result[name] = None
        result["gps_ok"] = False
    if not result["gps_ok"]:
        result["latitude"] = result["longitude"] = None
    if result["battery_age_ms"] is None or result["battery_age_ms"] >= 5000 or not result["aircraft_connected"]:
        result["battery_pct"] = None
    if result["gimbal_age_ms"] is None or result["gimbal_age_ms"] >= 1500 or not result["aircraft_connected"]:
        result["gimbal_pitch_deg"] = None
    return result


class LatestTelemetry:
    """One in-flight send plus one replaceable latest update per dashboard.

    Slow dashboards must not block drone telemetry ingestion or command ACKs.
    The payload factory runs at send time so waiting observations are aged.
    """
    def __init__(self, peers: set, payload: Callable[[], dict], timeout: float = 1.0):
        self.peers, self.payload, self.timeout = peers, payload, timeout
        self.tasks = {}
        self.revision = 0

    def publish(self) -> None:
        self.revision += 1
        for peer in tuple(self.peers):
            if peer not in self.tasks:
                self.tasks[peer] = asyncio.create_task(self._send(peer))

    async def _send(self, peer) -> None:
        try:
            while peer in self.peers:
                revision = self.revision
                await asyncio.wait_for(peer.send_text(json.dumps(self.payload())), self.timeout)
                if revision == self.revision:
                    break
        except Exception:
            self.peers.discard(peer)
            try:
                # Let the browser reconnect instead of leaving an open socket
                # silently excluded from all future telemetry updates.
                await asyncio.wait_for(peer.close(code=1013), self.timeout)
            except Exception:
                pass
        finally:
            self.tasks.pop(peer, None)

    def remove(self, peer) -> None:
        self.peers.discard(peer)
        task = self.tasks.pop(peer, None)
        if task:
            task.cancel()
