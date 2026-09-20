# iPhone ↔ command center protocol

The native app in `iphone-bridge/ios/` uses DJI Mobile SDK V4 iOS 4.16.2 with the Mavic Air 2. The server selects actions; the iPhone validates them, executes a bounded local controller, and reports completion. No Android app or firmware changes are involved.

## Transport

- WebSocket `/ws/drone`: JSON text messages in both directions. The app derives `ws://` or `wss://` from the base server URL. Supply a base URL such as `http://192.168.1.20:8000`, without a path/query.
- HTTP POST `/frame`: raw JPEG bytes, `Content-Type: image/jpeg`, roughly once per second, max image dimension 640 px. The phone avoids an upload backlog.
- Standard WebSocket ping/pong frames provide the phone's heartbeat; no JSON heartbeat message is required.
- One drone WebSocket at a time. Stop the simulator before connecting the phone.

The current development server is unauthenticated. Use a private LAN or authenticated private VPN, not a public tunnel. The iPhone must physically connect by USB data cable to the RC-N1 and remain in the foreground.

## iPhone → server

First message:

```json
{"type":"hello","drone_id":"air2","model":"Mavic Air 2","mode":"live"}
```

`mode` is `mock` for simulated hardware. The mock smoke server rejects live mode. The project server accepts both; the operator is responsible for selecting the intended mode.

Telemetry is sent about once per second when GPS, the ground anchor, and telemetry freshness are valid:

```json
{"type":"telemetry","drone_id":"air2","latitude":25.7617,"longitude":-80.1918,"altitude_m":10.0,"heading_deg":135.0,"gimbal_pitch_deg":-60.0,"battery_pct":78,"status":"idle","home_latitude":25.7617,"home_longitude":-80.1918}
```

Coordinates use decimal degrees. Altitude is metres relative to takeoff, not altitude above terrain or sea level. Heading/bearing is compass degrees clockwise from north. Bridge status is `idle`, `searching` while a command is active, or `rtl`; it does not attest that the phone is armed. Arm/disarm state is shown locally on the iPhone.

The phone records home from valid GPS while on the ground. Start the bridge before manual takeoff. The server uses `home_latitude`/`home_longitude`, falling back to the first telemetry coordinates for the older simulator. Restart the server when changing launch location or switching mock/live; resetting a mission does not reset its home reference.

Completion acknowledgments:

```json
{"type":"ack","cmd_id":"1a2b3c4d","ok":true}
```

```json
{"type":"ack","cmd_id":"1a2b3c4d","ok":false,"error":"Local control is disabled"}
```

The last 256 completed command IDs are cached during the app session. Repeated active IDs do not start another action; completed IDs replay the stored result. Use a new ID for each new action. This is not persistent deduplication across app restarts.

## Server → iPhone

Parameters are **flat**, not nested in `params`:

```json
{"type":"cmd","cmd_id":"1a2b3c4d","action":"move","bearing":90,"dist":5,"expires_at_ms":1790000005000}
```

The timestamp above illustrates the shape only: generate `expires_at_ms` as current Unix milliseconds plus 5000. It is a delivery expiry, not a completion deadline. Synchronize phone/server clocks. The app accepts older messages without the field, but the integrated server includes it for normal commands. The stop helper intentionally omits expiry so a release request is still usable.

| Action | Parameters | Actual iPhone behavior |
|---|---|---|
| `goto` | `lat`, `lng`, `alt` (5–30 m) | Fly to a GPS target using virtual-stick velocity control; no takeoff action |
| `move` | `bearing` (0..<360), `dist` (0–5 m) | Compute a nearby target from current telemetry, then use the same navigation controller |
| `yaw` | `deg` (relative −180..180) | Rotate toward current heading plus offset, at most 10°/s |
| `gimbal` | `pitch` (absolute −90..0) | SDK gimbal rotation; completion checked from fresh gimbal telemetry |
| `hold` | none | Zero commanded velocity and wait for measured motion to settle; flight remains enabled |
| `rtl` | none | Release virtual stick, request DJI RTH, then await accepted request plus landing telemetry |
| `stop` | none | Cancel pending action, request release of app flight control, and disarm locally |

One normal action is active at a time. `hold`/`rtl` may preempt another action; `stop` can always request release. Normal commands require local arming; navigation/yaw/RTH require flight enabled. Camera-only mode permits gimbal tests but cannot execute a full mission beginning with `goto`.

Most positive acknowledgments require telemetry convergence and one second of settling. RTH success means landing was observed after SDK acceptance, not just that the request was accepted. Landing may require pilot confirmation. `stop` is the exception: its positive acknowledgment means the release request was processed; it does not prove the SDK completed release. The app logs release failures and blocks re-arming until release succeeds.

| Deadline | `goto` | `rtl` | Other normal commands |
|---|---:|---:|---:|
| Server completion wait | 120 s | 180 s | 25 s |
| iPhone completion wait | 110 s | 170 s | 23 s |

The server allows up to 3 s to send a command. A negative acknowledgment, disconnect, or timeout fails the current command. Non-RTH failures request stop; mission failures also request control release. The server does not wait for the stop helper's acknowledgment.

**STOP never stops motors and does not cancel DJI RTH/landing.** The pilot uses the physical RC for takeover/cancelling RTH. DJI RTH uses its own configured home point and altitude and can exceed the application's virtual-stick envelope.

## Limits and interruptions

The server safety layer checks target plus planned search radius within 35 m of launch, movement endpoints within 35 m, altitude 5–30 m, moves ≤5 m, and battery ≥30%. Planner guidance requests about 10 m altitude and a 5–10 m demo search radius; large incident uncertainty may exceed the demonstrated area.

The phone independently enforces a 40 m ground-anchor radius, altitude 5–30 m, horizontal velocity ≤1 m/s and vertical velocity ≤0.5 m/s. It requests release/disarms on monitored heartbeat loss (>4 s), stale FC data (>1.5 s), stale battery (>5 s), GPS loss, battery below 25%, foreground loss, unavailable virtual stick, a loop stall >0.6 s, or leaving its envelope. It requires ≥30% battery for flight enable/new navigation.

These are application checks, not obstacle avoidance or a guaranteed watchdog after force-kill/cable loss. Manual takeoff, clear paths, DJI failsafes and pilot takeover remain part of the demo.

## Frames and mission lifecycle

The iPhone decodes DJI video through DJIWidget, snapshots a rendered frame, downsizes and uploads JPEG. Snapshot callbacks time out and are tied to the original server connection to avoid late uploads after reconnection.

The integrated server accepts nonempty frames up to 2 MB only while a drone WebSocket is connected. It waits for a fresh frame after each action before asking the planner; telemetry must be under 3 s old. A planner decision based on a frame older than 10 s is rejected. Reset/reconnection invalidates in-flight detector results from the previous session.

- `POST /incident`: accepts `latitude`, `longitude`, `accuracy`, optional `timestamp`, and `source`; generates a plan for operator review. It is a trigger endpoint, not an Apple fall-detection integration.
- `POST /dispatch`: starts an approved plan after connected/fresh telemetry and bounds checks. Keep `AUTO_DISPATCH=0`.
- `POST /reset`: awaits cancellation, requests stop, clears mission/frame state. It does not land the drone or cancel DJI RTH.
- `POST /abort`: awaits mission cancellation, requests RTH, waits for landing acknowledgment and returns `ok:false` if that fails. A disarmed phone rejects RTH; use the RC.
- WebSocket disconnect cancels the mission and fails pending commands. Reconnecting requires local re-arm.
- `GET /state`, `GET /frame.jpg`, `/ws/dashboard`: dashboard data and camera view.

The server's current `found.lat`/`found.lng` are the **aircraft coordinates**, not person geolocation. Detection and confidence require human interpretation.

## Test modes

`server/sim_drone.py` is the original server-only simulator and does not implement every iPhone interlock or RTH completion behavior. Use it to exercise the dashboard/planner, not to certify this protocol on hardware.

For the iPhone wire contract, use the app's mock mode with `iphone-bridge/tools/smoke_server.py`; follow [the bridge test instructions](../iphone-bridge/README.md). Its `/command` endpoint sends commands and returns their acknowledgments, `/state` shows telemetry/JPEG byte count, and `/frame.jpg` shows a labelled mock image. This smoke server has no incident/planner flow and rejects live aircraft connections.
