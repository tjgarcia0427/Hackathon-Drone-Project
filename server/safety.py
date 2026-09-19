"""Deterministic safety layer. Claude proposes; this code approves.

Nothing reaches the drone unless it passes here. Tune LIMITS for the venue.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from models import DroneState, MissionPlan, SearchStep

LIMITS = {
    "max_altitude_m": 30.0,
    "max_radius_from_home_m": 150.0,   # geofence around takeoff point
    "min_battery_pct": 30.0,
    "max_move_m": 15.0,                # per step
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
    return 2 * r * math.asin(math.sqrt(a))


def offset_latlng(lat: float, lng: float, bearing_deg: float, dist_m: float) -> tuple[float, float]:
    """Move a lat/lng by dist_m along bearing_deg (flat-earth approx, fine for <1km)."""
    dlat = dist_m * math.cos(math.radians(bearing_deg)) / 111_320.0
    dlng = dist_m * math.sin(math.radians(bearing_deg)) / (111_320.0 * math.cos(math.radians(lat)))
    return lat + dlat, lng + dlng


def check_mission(plan: MissionPlan, home_lat: float, home_lng: float, drone: DroneState | None) -> Verdict:
    if plan.altitude_m > LIMITS["max_altitude_m"]:
        return Verdict(False, f"altitude {plan.altitude_m}m > {LIMITS['max_altitude_m']}m")
    d = haversine_m(home_lat, home_lng, plan.target_lat, plan.target_lng)
    if d + plan.search_radius_m > LIMITS["max_radius_from_home_m"]:
        return Verdict(False, f"target+radius {d + plan.search_radius_m:.0f}m outside geofence")
    if drone and drone.battery_pct < LIMITS["min_battery_pct"]:
        return Verdict(False, f"battery {drone.battery_pct}% < {LIMITS['min_battery_pct']}%")
    return Verdict(True)


def check_step(step: SearchStep, drone: DroneState, home_lat: float, home_lng: float, step_no: int) -> Verdict:
    if step_no >= LIMITS["max_search_steps"]:
        return Verdict(False, "max search steps reached")
    if drone.battery_pct < LIMITS["min_battery_pct"]:
        return Verdict(False, "battery below floor")
    if step.action == "move":
        if step.move_distance_m is None or step.move_bearing_deg is None:
            return Verdict(False, "move without bearing/distance")
        if step.move_distance_m > LIMITS["max_move_m"]:
            return Verdict(False, f"move {step.move_distance_m}m > {LIMITS['max_move_m']}m")
        nlat, nlng = offset_latlng(drone.latitude, drone.longitude, step.move_bearing_deg, step.move_distance_m)
        if haversine_m(home_lat, home_lng, nlat, nlng) > LIMITS["max_radius_from_home_m"]:
            return Verdict(False, "move would exit geofence")
    if step.action == "yaw" and step.yaw_deg is None:
        return Verdict(False, "yaw without degrees")
    if step.action == "gimbal" and step.gimbal_pitch_deg is None:
        return Verdict(False, "gimbal without pitch")
    return Verdict(True)
