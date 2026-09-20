"""Deterministic limits for the supervised iPhone demo.

Claude proposes; the server validates. The iPhone independently enforces its envelope.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from models import DroneState, MissionPlan, SearchStep

LIMITS = {
    "max_altitude_m": 30.0,
    "max_radius_from_home_m": 35.0,   # leaves margin inside the iPhone's 40 m fence
    "min_battery_pct": 30.0,
    "max_move_m": 5.0,
    "max_search_steps": 12,
}


@dataclass
class Verdict:
    ok: bool
    reason: str = "ok"


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def offset_latlng(lat: float, lng: float, bearing_deg: float, dist_m: float) -> tuple[float, float]:
    """Move a lat/lng by dist_m along bearing_deg (flat-earth approx, fine for <1km)."""
    dlat = dist_m * math.cos(math.radians(bearing_deg)) / 111_320.0
    dlng = dist_m * math.sin(math.radians(bearing_deg)) / (111_320.0 * math.cos(math.radians(lat)))
    return lat + dlat, lng + dlng


def check_mission(plan: MissionPlan, home_lat: float, home_lng: float, drone: DroneState | None) -> Verdict:
    values = (home_lat, home_lng, plan.target_lat, plan.target_lng, plan.altitude_m,
              plan.search_radius_m, plan.gimbal_pitch_deg)
    if not all(math.isfinite(v) for v in values):
        return Verdict(False, "non-finite mission coordinates or parameters")
    if not (-85 < home_lat < 85 and -85 < plan.target_lat < 85 and
            -180 <= home_lng <= 180 and -180 <= plan.target_lng <= 180):
        return Verdict(False, "coordinates outside demo navigation range")
    if not 5 <= plan.altitude_m <= LIMITS["max_altitude_m"]:
        return Verdict(False, "altitude must be 5–30 m")
    if plan.search_radius_m < 5 or not -90 <= plan.gimbal_pitch_deg <= 0:
        return Verdict(False, "invalid search radius or gimbal pitch")
    d = haversine_m(home_lat, home_lng, plan.target_lat, plan.target_lng)
    if d + plan.search_radius_m > LIMITS["max_radius_from_home_m"]:
        return Verdict(False, f"target+radius {d + plan.search_radius_m:.0f}m outside geofence")
    if drone and (not math.isfinite(drone.battery_pct) or drone.battery_pct < LIMITS["min_battery_pct"]):
        return Verdict(False, "battery below floor or invalid")
    return Verdict(True)


def check_step(step: SearchStep, drone: DroneState, home_lat: float, home_lng: float, step_no: int) -> Verdict:
    if step_no >= LIMITS["max_search_steps"]:
        return Verdict(False, "max search steps reached")
    if not math.isfinite(drone.battery_pct) or drone.battery_pct < LIMITS["min_battery_pct"]:
        return Verdict(False, "battery below floor or invalid")
    if step.action == "move":
        if step.move_distance_m is None or step.move_bearing_deg is None:
            return Verdict(False, "move without bearing/distance")
        if not (math.isfinite(step.move_distance_m) and 0 <= step.move_distance_m <= LIMITS["max_move_m"]):
            return Verdict(False, "move distance must be 0–5 m")
        if not (math.isfinite(step.move_bearing_deg) and 0 <= step.move_bearing_deg < 360):
            return Verdict(False, "bearing must be 0..<360 degrees")
        if not all(math.isfinite(v) for v in (drone.latitude, drone.longitude, home_lat, home_lng)):
            return Verdict(False, "invalid navigation coordinates")
        if not (-85 < drone.latitude < 85 and -85 < home_lat < 85 and
                -180 <= drone.longitude <= 180 and -180 <= home_lng <= 180):
            return Verdict(False, "coordinates outside demo navigation range")
        nlat, nlng = offset_latlng(drone.latitude, drone.longitude, step.move_bearing_deg, step.move_distance_m)
        if haversine_m(home_lat, home_lng, nlat, nlng) > LIMITS["max_radius_from_home_m"]:
            return Verdict(False, "move would exit geofence")
    if step.action == "yaw" and (step.yaw_deg is None or not math.isfinite(step.yaw_deg) or not -180 <= step.yaw_deg <= 180):
        return Verdict(False, "yaw must be -180..180 degrees")
    if step.action == "gimbal" and (step.gimbal_pitch_deg is None or not math.isfinite(step.gimbal_pitch_deg) or not -90 <= step.gimbal_pitch_deg <= 0):
        return Verdict(False, "gimbal pitch must be -90..0 degrees")
    return Verdict(True)
