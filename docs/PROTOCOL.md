# Drone ↔ Command Center protocol

The Android app (DJI MSDK v4, Mavic Air 2) is a thin agent. It never decides anything — it
executes commands from the server and streams telemetry + frames back. `server/sim_drone.py`
implements this exact contract, so the Android app can be developed against the same server.

## Transport

- **WebSocket** `ws://<server>:8000/ws/drone` — JSON text messages both directions.
- **HTTP POST** `http://<server>:8000/frame` — raw JPEG body (`Content-Type: image/jpeg`), ~1 per second.

## Drone → server

```jsonc
{"type": "hello", "drone_id": "air2", "model": "Mavic Air 2"}

{"type": "telemetry", "drone_id": "air2",          // every ~1s
 "latitude": 25.7617, "longitude": -80.1918, "altitude_m": 20.5,
 "heading_deg": 135, "gimbal_pitch_deg": -60, "battery_pct": 78, "status": "searching"}

{"type": "ack", "cmd_id": "1a2b3c4d", "ok": true}                       // when a command finishes
{"type": "ack", "cmd_id": "1a2b3c4d", "ok": false, "error": "GEO zone"} // or fails
```

The **first telemetry fix is treated as HOME** (takeoff point) for the geofence. Send telemetry
before takeoff.

## Server → drone

Every command carries a `cmd_id`; ack it when the action has *completed*, not when received.

| action   | params                                   | MSDK v4 mapping (suggested)                                  |
|----------|------------------------------------------|--------------------------------------------------------------|
| `goto`   | `lat`, `lng`, `alt` (m)                  | takeoff if needed → WaypointMission (1 waypoint) or virtual-stick fly-to; ack on arrival (<4 m) |
| `yaw`    | `deg` (relative, −180..180)              | virtual stick yaw with `YAW_CONTROL_MODE = ANGLE` on absolute (heading+deg) |
| `gimbal` | `pitch` (−90..0)                         | `Gimbal.rotate(Rotation ABSOLUTE_ANGLE pitch)`               |
| `move`   | `bearing` (0..360), `dist` (m)           | virtual stick BODY/GROUND velocity for `dist / speed` seconds, or 1-waypoint mission |
| `hold`   | —                                        | stop sticks / hover                                          |
| `rtl`    | —                                        | `FlightController.startGoHome`                                |

Timeouts on the server side: `goto` 120 s, everything else 25 s. Un-acked commands fail the mission.

## Frames

`POST /frame` with the JPEG bytes. Source on Android: `VideoFeeder.getPrimaryVideoFeed()` →
`DJICodecManager` → `getYuvData` callback → convert to JPEG (`YuvImage.compressToJpeg`) → OkHttp POST.
Downscale to ~640 px wide before posting; 1 fps is plenty.

## Testing without the aircraft

```
cd server
uvicorn app:app --reload            # terminal 1
python sim_drone.py                 # terminal 2
open http://localhost:8000          # click "Simulate fall (dev)" → "Dispatch drone"
```

Or fire the real trigger from a phone:

```
curl -X POST http://<server>:8000/incident -H 'Content-Type: application/json' \
  -d '{"latitude":25.7619,"longitude":-80.1917,"accuracy":8,"source":"curl"}'
```
