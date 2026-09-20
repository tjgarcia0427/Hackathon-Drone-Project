"""Project a camera-frame bounding box onto the ground.

Given aircraft altitude, heading and gimbal pitch, a pixel in the frame defines a ray; we
intersect it with the flat ground plane under the aircraft and return where that ray lands.
This turns "the drone is 6 m from the reported point" into "the *person* is ~4 m from the
reported point" — an estimate, not a survey. Flat ground and a rectilinear lens are assumed.
"""
from __future__ import annotations

import io
import math
import os
from dataclasses import dataclass

from safety import haversine_m, offset_latlng
from models import valid_bbox

# DJI Air 2 main camera: 84° diagonal on a 4:3 sensor; a 16:9 video frame crops the vertical.
# Horizontal FOV is what matters for a 16:9 frame; override for another airframe.
HFOV_DEG = float(os.environ.get("CAMERA_HFOV_DEG", "73"))
MIN_DEPRESSION_DEG = 3.0       # rays flatter than this never reach the ground usefully
MAX_GROUND_RANGE_M = 150.0     # beyond this the estimate is meaningless for a 10 m hover


@dataclass(frozen=True)
class GroundHit:
    north_m: float
    east_m: float
    lat: float
    lng: float
    range_m: float          # horizontal distance from the aircraft to the person
    distance_from_report_m: float


def frame_size(jpeg: bytes) -> tuple[int, int] | None:
    """(width, height) of a JPEG, or None if the bytes are not an image."""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(jpeg)) as img:
            return img.size
    except Exception:  # noqa: BLE001
        return None


def bbox_ground_point(bbox: list[int], frame_w: int, frame_h: int, *, altitude_m: float,
                      heading_deg: float, gimbal_pitch_deg: float) -> tuple[float, float, float] | None:
    """Return (north_m, east_m, range_m) of the bbox's ground contact relative to the aircraft.

    The ground contact is the bottom-centre of the box (feet / body on the ground), not the box centre.
    Returns None when the ray does not hit the ground within MAX_GROUND_RANGE_M.
    """
    if not valid_bbox(bbox, (frame_w, frame_h)) or frame_w <= 0 or frame_h <= 0 or altitude_m <= 0:
        return None
    x1, y1, x2, y2 = (float(v) for v in bbox)
    if not all(math.isfinite(v) for v in (x1, y1, x2, y2, altitude_m, heading_deg, gimbal_pitch_deg)):
        return None
    u = ((x1 + x2) / 2) / frame_w        # 0..1 left→right
    v = max(y1, y2) / frame_h            # 0..1 top→bottom, bottom edge of the box

    tan_h = math.tan(math.radians(HFOV_DEG / 2))
    tan_v = tan_h * frame_h / frame_w    # square pixels
    xn = (u - 0.5) * 2 * tan_h           # camera x (right)
    yn = (v - 0.5) * 2 * tan_v           # camera y (down in the image)

    # Body frame axes: F forward, R right, D down. Depression θ = -pitch (pitch -90 = straight down).
    theta = math.radians(-gimbal_pitch_deg)
    z_cam = (math.cos(theta), 0.0, math.sin(theta))        # optical axis
    y_cam = (-math.sin(theta), 0.0, math.cos(theta))       # image-down direction
    x_cam = (0.0, 1.0, 0.0)                                # image-right = body right
    d = tuple(xn * x_cam[i] + yn * y_cam[i] + z_cam[i] for i in range(3))
    depression = math.degrees(math.atan2(d[2], math.hypot(d[0], d[1])))
    if depression < MIN_DEPRESSION_DEG:
        return None
    t = altitude_m / d[2]
    forward, right = t * d[0], t * d[1]
    h = math.radians(heading_deg)
    north = forward * math.cos(h) - right * math.sin(h)
    east = forward * math.sin(h) + right * math.cos(h)
    rng = math.hypot(north, east)
    if rng > MAX_GROUND_RANGE_M:
        return None
    return north, east, rng


def locate(bbox: list[int], frame_w: int, frame_h: int, *, drone_lat: float, drone_lng: float,
           altitude_m: float, heading_deg: float, gimbal_pitch_deg: float,
           report_lat: float, report_lng: float) -> GroundHit | None:
    hit = bbox_ground_point(bbox, frame_w, frame_h, altitude_m=altitude_m,
                            heading_deg=heading_deg, gimbal_pitch_deg=gimbal_pitch_deg)
    if hit is None:
        return None
    north, east, rng = hit
    lat, lng = offset_latlng(drone_lat, drone_lng, 0, north)
    lat, lng = offset_latlng(lat, lng, 90, east)
    return GroundHit(round(north, 1), round(east, 1), lat, lng, round(rng, 1),
                     round(haversine_m(report_lat, report_lng, lat, lng), 1))
