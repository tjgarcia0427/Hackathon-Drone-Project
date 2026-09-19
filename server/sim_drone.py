"""Simulated drone that speaks the same protocol as the Android app.

Lets you run the full loop (incident -> plan -> dispatch -> search -> found) with no aircraft.
It renders synthetic camera frames: grass + a "fallen person" that only appears when the
drone is within FOUND_RADIUS_M of the hidden subject AND roughly facing it.

Usage:
  python sim_drone.py --server http://localhost:8000 --home 25.7617,-80.1918 \
      --subject-offset 18,7      # subject is 18m north, 7m east of home
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import math
import random
import time

import httpx
import websockets
from PIL import Image, ImageDraw

from safety import haversine_m, offset_latlng

FOUND_RADIUS_M = 12.0
FOV_DEG = 80.0


class Sim:
    def __init__(self, home: tuple[float, float], subject: tuple[float, float]) -> None:
        self.lat, self.lng = home
        self.alt = 0.0
        self.heading = 0.0
        self.gimbal = 0.0
        self.battery = 92.0
        self.status = "idle"
        self.subject = subject

    def telemetry(self) -> dict:
        return {
            "type": "telemetry", "drone_id": "sim-air2",
            "latitude": self.lat, "longitude": self.lng, "altitude_m": self.alt,
            "heading_deg": self.heading, "gimbal_pitch_deg": self.gimbal,
            "battery_pct": self.battery, "status": self.status,
        }

    def bearing_to_subject(self) -> float:
        dlat = (self.subject[0] - self.lat) * 111_320.0
        dlng = (self.subject[1] - self.lng) * 111_320.0 * math.cos(math.radians(self.lat))
        return math.degrees(math.atan2(dlng, dlat)) % 360

    def subject_visible(self) -> bool:
        d = haversine_m(self.lat, self.lng, *self.subject)
        if d > FOUND_RADIUS_M or self.alt < 3:
            return False
        if d < 4 and self.gimbal <= -60:  # directly below with camera down
            return True
        diff = abs((self.bearing_to_subject() - self.heading + 180) % 360 - 180)
        return diff <= FOV_DEG / 2 and self.gimbal <= -30

    def frame(self) -> bytes:
        img = Image.new("RGB", (640, 360), (74, 120, 52))
        d = ImageDraw.Draw(img)
        rnd = random.Random(int(self.heading) + int(self.gimbal))
        for _ in range(60):  # grass texture / paths
            x, y = rnd.randint(0, 640), rnd.randint(0, 360)
            d.ellipse((x, y, x + rnd.randint(4, 30), y + rnd.randint(2, 8)), fill=(rnd.randint(60, 90), rnd.randint(100, 140), 50))
        d.rectangle((0, 0, 640, 40), fill=(0, 0, 0))
        d.text((8, 12), f"SIM  hdg={self.heading:.0f} gimbal={self.gimbal:.0f} alt={self.alt:.0f}m  "
                        f"dist_to_subject={haversine_m(self.lat, self.lng, *self.subject):.1f}m", fill=(255, 255, 255))
        if self.subject_visible():
            # a person lying on the ground: body + head + legs, drawn horizontally
            cx, cy = 400, 230
            d.rounded_rectangle((cx - 45, cy - 12, cx + 45, cy + 12), radius=8, fill=(40, 60, 160))
            d.ellipse((cx + 45, cy - 14, cx + 73, cy + 14), fill=(230, 190, 160))
            d.rectangle((cx - 100, cy - 8, cx - 45, cy + 8), fill=(30, 30, 30))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80)
        return buf.getvalue()

    async def execute(self, cmd: dict) -> None:
        a = cmd["action"]
        if a == "goto":
            self.status = "dispatched"
            target = (cmd["lat"], cmd["lng"])
            self.alt = cmd.get("alt", 20)
            for i in range(1, 11):  # 10 ticks of travel
                self.lat = self.lat + (target[0] - self.lat) * (i / 10)
                self.lng = self.lng + (target[1] - self.lng) * (i / 10)
                await asyncio.sleep(0.4)
            self.lat, self.lng = target
            self.status = "searching"
        elif a == "yaw":
            self.heading = (self.heading + cmd["deg"]) % 360
            await asyncio.sleep(0.8)
        elif a == "gimbal":
            self.gimbal = cmd["pitch"]
            await asyncio.sleep(0.5)
        elif a == "move":
            self.lat, self.lng = offset_latlng(self.lat, self.lng, cmd["bearing"], cmd["dist"])
            await asyncio.sleep(1.0)
        elif a == "hold":
            self.status = "found"
        elif a == "rtl":
            self.status = "rtl"
        self.battery -= 0.4


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://localhost:8000")
    ap.add_argument("--home", default="25.7617,-80.1918")
    ap.add_argument("--subject-offset", default="18,7", help="meters north,east of home")
    args = ap.parse_args()
    home = tuple(float(x) for x in args.home.split(","))
    n, e = (float(x) for x in args.subject_offset.split(","))
    slat, slng = offset_latlng(home[0], home[1], 0, n)
    slat, slng = offset_latlng(slat, slng, 90, e)
    sim = Sim(home, (slat, slng))
    ws_url = args.server.replace("http", "ws", 1) + "/ws/drone"
    print(f"sim: home={home} subject={sim.subject} -> {ws_url}")

    async with websockets.connect(ws_url) as ws, httpx.AsyncClient(base_url=args.server, timeout=10) as http:
        await ws.send(json.dumps({"type": "hello", "drone_id": "sim-air2", "model": "simulator"}))

        async def telemetry_loop() -> None:
            while True:
                await ws.send(json.dumps(sim.telemetry()))
                try:
                    await http.post("/frame", content=sim.frame(), headers={"Content-Type": "image/jpeg"})
                except Exception as ex:  # noqa: BLE001
                    print("frame post failed:", ex)
                await asyncio.sleep(1.0)

        asyncio.create_task(telemetry_loop())
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") != "cmd":
                continue
            print(f"{time.strftime('%H:%M:%S')} cmd {msg['action']} {msg}")
            try:
                await sim.execute(msg)
                await ws.send(json.dumps({"type": "ack", "cmd_id": msg["cmd_id"], "ok": True}))
            except Exception as ex:  # noqa: BLE001
                await ws.send(json.dumps({"type": "ack", "cmd_id": msg["cmd_id"], "ok": False, "error": str(ex)}))


if __name__ == "__main__":
    asyncio.run(main())
