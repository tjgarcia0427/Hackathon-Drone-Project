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

Navigation telemetry is sent about five times per second when GPS, the ground anchor, and telemetry freshness are valid:

```json
{"type":"telemetry","drone_id":"air2","latitude":25.7617,"longitude":-80.1918,"altitude_m":10.0,"heading_deg":135.0,"gimbal_pitch_deg":-60.0,"battery_pct":78,"status":"idle","home_latitude":25.7617,"home_longitude":-80.1918}
```

Full navigation packets also include a nested `aircraft` observation object. When navigation is unavailable, the phone sends only:

```json
{"type":"aircraft_status","aircraft":{"drone_id":"air2","mock":false,"aircraft_connected":true,"latitude":null,"longitude":null,"altitude_m":0.0,"altitude_reference":"takeoff","heading_deg":135,"battery_pct":78,"gimbal_pitch_deg":0,"gps_ok":false,"ground_anchor_ok":false,"gps_signal_level":2,"satellites":5,"flying":false,"fc_age_ms":20,"battery_age_ms":100,"gimbal_age_ms":30}}
```

`aircraft_status` is **display-only**. It never creates navigation state, sets server home or refreshes navigation readiness. Altitude/heading remain available without GPS; missing/stale numbers are `null`. The server exposes the independently aged object as `aircraft` in `/state`, dashboard state and dashboard telemetry messages. `navigation_age_ms` describes the age of the last complete navigation packet (or `null` if absent), including for older simulator clients. Source ages are milliseconds; FC/gimbal expire at 1500 ms and battery at 5000 ms. The dashboard ages them further between messages. Partial observations do not replace the `drone` used for dispatch/planning.

The five-Hz schedule sends the latest SDK observations; sensor timing and connectivity still limit actual freshness. Slow dashboard delivery is coalesced and does not block drone message ingestion. See [telemetry fix and bench checks](TELEMETRY_FIX.md).

Coordinates use decimal degrees. Altitude is metres relative to takeoff, not altitude above terrain or sea level. Heading/bearing is compass degrees clockwise from north. Bridge status is `idle`, `searching` while a command is active, or `rtl`; it does not attest that the phone is armed. Arm/disarm state is shown locally on the iPhone; updated phones also report it in the `control` object below.

The phone records home from valid GPS while on the ground. Start the bridge before takeoff. The local **Take off (pilot)** button retains that anchor and the server connection; the agent protocol can request that same local confirmation or consume a live one-use local pilot authorization. See [pilot takeoff](PILOT_TAKEOFF.md). The server uses `home_latitude`/`home_longitude`, falling back to the first telemetry coordinates for the older simulator. Restart the server when changing launch location or switching mock/live; resetting a mission does not reset its home reference.

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
| `request_takeoff` | none; delivery expiry required | Consume live one-use pilot authorization, or show 20-second pilot prompt. Ack means stable hover; require fresh flight-enabled status before movement. |
| `goto` | `lat`, `lng`, `alt` (1–30 m) | Fly to a GPS target using virtual-stick velocity control; no takeoff action |
| `move` | `bearing` (0..<360), `dist` (0–5 m) | Compute a nearby target from current telemetry, then use the same navigation controller |
| `yaw` | `deg` (relative −180..180) | Rotate toward current heading plus offset, at most 10°/s |
| `gimbal` | `pitch` (absolute −90..0) | SDK gimbal rotation; completion checked from fresh gimbal telemetry |
| `hold` | none | Zero commanded velocity and wait for measured motion to settle; flight remains enabled |
| `rtl` | none | Release virtual stick, request DJI RTH, then await accepted request plus landing telemetry |
| `stop` | none | Cancel pending action, request release of app flight control, and disarm locally |

One normal action is active at a time. `hold`/`rtl` may preempt another action; `stop` can always request release. Normal commands require local arming; navigation/yaw/RTH require flight enabled. Camera-only mode permits gimbal tests but cannot execute a full mission beginning with `goto`.

Most positive acknowledgments require telemetry convergence and one second of settling. RTH success means landing was observed after SDK acceptance, not just that the request was accepted. Landing may require pilot confirmation. `stop` is the exception: its positive acknowledgment means the release request was processed; it does not prove the SDK completed release. The app logs release failures and blocks re-arming until release succeeds.

| Deadline | `request_takeoff` | none; delivery expiry required | Consume live one-use pilot authorization, or show 20-second pilot prompt. Ack means stable hover; require fresh flight-enabled status before movement. |
| `goto` | `rtl` | Other normal commands |
|---|---:|---:|---:|
| Server completion wait | 120 s | 180 s | 25 s |
| iPhone completion wait | 110 s | 170 s | 23 s |

The server allows up to 3 s to send a command. A negative acknowledgment, disconnect, or timeout fails the current command. Non-RTH failures request stop; mission failures also request control release. The server does not wait for the stop helper's acknowledgment.

**STOP never stops motors and does not cancel DJI RTH/landing.** The pilot uses the physical RC for takeover/cancelling RTH. DJI RTH uses its own configured home point and altitude and can exceed the application's virtual-stick envelope.

## Limits and interruptions

The server safety layer checks target plus planned search radius within 35 m of launch, movement endpoints within 35 m, altitude 1–30 m, moves ≤5 m, and battery ≥30%. Planner guidance requests about 10 m altitude and a 5–10 m demo search radius; large incident uncertainty may exceed the demonstrated area.

The phone independently enforces a 40 m ground-anchor radius, altitude 1–30 m, horizontal velocity ≤1 m/s and vertical velocity ≤0.5 m/s. It requests release/disarms on monitored heartbeat loss (>4 s), stale FC data (>1.5 s), stale battery (>5 s), GPS loss, battery below 25%, foreground loss, unavailable virtual stick, a loop stall >0.6 s, or leaving its envelope. It requires ≥30% battery for flight enable/new navigation.

These are application checks, not obstacle avoidance or a guaranteed watchdog after force-kill/cable loss. Pilot-operated takeoff, clear paths, DJI failsafes and pilot takeover remain part of the demo.

## Frames and mission lifecycle

The iPhone decodes DJI video through DJIWidget, snapshots a rendered frame, downsizes and uploads JPEG. Snapshot callbacks time out and are tied to the original server connection to avoid late uploads after reconnection.

The integrated server accepts nonempty frames up to 2 MB only while a drone WebSocket is connected. It waits for a fresh frame after each action before asking the planner; telemetry must be under 3 s old. Search inference uses `AI_SEARCH_TIMEOUT` (default 30 seconds). A planner decision based on a frame older than that deadline plus 5 s is rejected. A timeout fails the mission and requests app-control release. Reset/reconnection invalidates in-flight detector results from the previous session.

- `GET /ai`: selected provider/model, provider options and local setup status; no credentials.
- `POST /ai/config`: JSON `{ "provider":"codex", "model":"" }`; providers are `codex`, `claude_code`, `openai_api`, `anthropic_api`. Only allowed while idle, with no in-flight planning/search/commands. Invalid setup returns 400, busy state 409, unknown fields 422. Selection is in memory until restart. See [AI_PROVIDERS.md](AI_PROVIDERS.md).
- `POST /incident`: accepts `latitude`, `longitude`, `accuracy`, optional `timestamp`, and `source`; generates a plan for operator review with a 60-second deadline. Concurrent planning is rejected; reset/abort invalidates late results. It is a trigger endpoint, not an Apple fall-detection integration.
- `POST /dispatch`: starts an approved plan after connected/fresh telemetry and bounds checks. Keep `AUTO_DISPATCH=0`.
- `POST /reset`: awaits cancellation, requests stop, clears mission/frame state. It does not land the drone or cancel DJI RTH.
- `POST /abort`: awaits mission cancellation, requests RTH, waits for landing acknowledgment and returns `ok:false` if that fails. A disarmed phone rejects RTH; use the RC.
- WebSocket disconnect cancels the mission and fails pending commands. Reconnecting requires local re-arm.
- `GET /state`, `GET /frame.jpg`, `/ws/dashboard`: dashboard data and camera view.

`found.lat`/`found.lng` are the **aircraft coordinates**. Detection and confidence require human interpretation.

### Subject disambiguation (multiple people in frame)

Each search decision (`SearchStep`) now carries `candidates[]` — every person the AI can see — and `chosen_index`:

- `candidates[i]`: `bbox` `[x1,y1,x2,y2]` pixels in the judged frame, `posture` (`prone|sitting|upright|unknown`), `is_moving`, `subject_confidence` (0–1, "is *this* the reported subject"), `reason`.
- The prompt orders the pick: prone/lying > sitting > upright; motionless across steps > moving; nearest the frame centre (the aircraft hovers over the reported GPS point). If the top two are within 0.15 the AI must keep searching rather than commit.
- `safety.check_found` enforces this deterministically: `found` is rejected unless `confidence >= 0.8`, `candidates` is non-empty, `chosen_index` is valid, the chosen posture is `prone`/`sitting`, `is_moving` is false, the chosen `subject_confidence` is at least 0.8, every box is ordered/nonempty/within the judged image, and the chosen score beats every other candidate by `min_candidate_margin` (0.15). A rejected `found` and its reason are included in history supplied to the next AI call, and the bounded loop continues. Numeric fractional pixel coordinates are rounded before strict validation; strings/booleans/non-finite numbers remain invalid.
- The server projects each bbox onto the ground using altitude, heading and gimbal pitch (`geometry.py`, flat-ground assumption, `CAMERA_HFOV_DEG` default 73). Each candidate gains `est_north_m`/`est_east_m`/`est_range_m` (relative to the aircraft), `est_lat`/`est_lng`, and `est_distance_from_report_m`; these are `null` when the ray does not reach the ground. Estimates, not a survey.
- `found` gains `people_in_frame`, `subject` (the chosen candidate incl. estimates), `subject_lat`/`subject_lng`, `subject_distance_from_report_m`, and `candidates`.
- Dashboard `step` events carry `candidates`, `frame` `[w,h]`, `decision_id` and `judged_at`. `GET /step.jpg?decision_id=ID` returns only the matching decision image (409 if superseded). The dashboard uses a separate decision image for boxes and keeps the live camera live. `/state` includes `last_step`. The unversioned endpoint remains available for older clients but the new dashboard always requests an ID.
- `sim_drone.py --bystanders N` draws upright walkers alongside the prone subject to exercise this path. The local detector (if installed) now reports all `persons`, not only the best box.

## Native Watch alert protocol (v1)

The Watch is an HTTP client of the project server, independent of the iPhone/drone WebSocket. Run a single server worker on a private LAN. See [WATCH_SETUP.md](WATCH_SETUP.md) for installation and device tests.

1. `GET /watch/status` returns `protocol: 1`, a per-process `server_session` UUID, `max_event_age_seconds: 60`, `max_location_age_seconds: 15`, `max_accuracy_m: 20`, and `auto_dispatch`.
2. `POST /watch/alerts` receives the following JSON. Create a new `event_id` for each deliberate trigger. Use current timezone-aware timestamps and the session from step 1. Example values below are placeholders, not a replayable flight request:

```json
{
  "event_id": "11111111-1111-4111-8111-111111111111",
  "server_session": "22222222-2222-4222-8222-222222222222",
  "source": "watch_button",
  "timestamp": "2026-09-20T16:00:00.000Z",
  "test_mode": true,
  "latitude": 25.7617,
  "longitude": -80.1918,
  "accuracy": 8.0,
  "location_timestamp": "2026-09-20T16:00:00.000Z"
}
```

`source` is `watch_button` or `watch_shake`; neither implies automatic fall detection. `test_mode` must be a JSON boolean (defaults true when omitted). Omit all four location fields or set them all to null when a usable fix is unavailable; partial location fields are invalid. Coordinates/accuracy must be finite JSON numbers. Latitude is restricted to the demo's navigation range, -85 to 85 exclusive; longitude -180 to 180 inclusive; accuracy nonnegative. Unknown fields are rejected.

An accepted event returns HTTP **202** with `accepted: true`, `duplicate: false`, the event fields, `received_at` (Unix seconds), `status` and `message`. This acknowledges receipt **before** asynchronous AI planning. The same UUID and identical normalized payload return `duplicate: true` and the retained status without replanning, even after reset/cancellation. Reusing an ID with a different payload or session returns 409. An unknown old event (>60 seconds), a trigger clock >5 seconds ahead, or malformed payload returns 422. Capacity returns 429; IDs are not evicted early. A changed session means restart: do not replay it as a new event automatically.

Test mode always produces `test_received` and no mission. Live events without GPS, with location age >15 seconds or >5 seconds in the future, or accuracy >20 m produce `location_rejected`: operator alert only. If another mission is not idle, status is `busy`; no replacement/queue is created. Otherwise status starts `planning`, then becomes `planned`, `rejected`, `failed` or `cancelled`. Internal incident type is `help_requested`. Plan coordinates are fixed to the submitted GPS; AI cannot replace them.

`GET /watch/alerts/{event_id}` returns the retained event/status, or 404 if unknown/expired/restarted. At dispatch, the server requires `planned`, non-test status, matching target, fresh aircraft telemetry, current battery and full search-area limits; a Watch destination expires 120 seconds after receipt (monotonic clock). Subsequent statuses include `dispatched`, `found`, `aborted`, `failed`, `cancelled`.

`/ws/dashboard` emits `{"type":"watch_alert","alert":{...}}` once for each new accepted ID. State snapshots include `watch_alerts` (eight most recent records with updated status). Retries do not emit another new-alert notification. Retention is 15 minutes, capped at 256 records per process. Records are not durable across server restarts; the changing session UUID prevents unknown delayed retries from generating another mission.

## Test modes

`server/sim_drone.py` is the original server-only simulator and does not implement every iPhone interlock or RTH completion behavior. Use it to exercise the dashboard/planner, not to certify this protocol on hardware.

For the iPhone wire contract, use the app's mock mode with `iphone-bridge/tools/smoke_server.py`; follow [the bridge test instructions](../iphone-bridge/README.md). Its `/command` endpoint sends commands and returns their acknowledgments, `/state` shows telemetry/JPEG byte count, and `/frame.jpg` shows a labelled mock image. This smoke server has no incident/planner flow and rejects live aircraft connections.

## OpenClaw agent extension (protocol 1)

`telemetry` and `aircraft_status` additionally carry `control`:

```json
{"control":{"camera_enabled":false,"flight_enabled":false,"takeoff_request_supported":true,"takeoff_ready":true,"takeoff_problem":"","takeoff_pending":false,"home":[25.7617,-80.1918]}}
```

This is observed phone state, never permission to arm. The server expires it after 3 seconds and requires it for agent commands. `home` is null until the phone has a ground anchor. Agent navigation uses this fresh phone anchor; the built-in simulator/home compatibility behavior remains unchanged.

New wire action: `request_takeoff`, with `cmd_id` and mandatory `expires_at_ms`. Normal delivery expiry is 5 seconds. Receipt consumes a live one-use pilot authorization, or presents a pilot prompt; launch requires disarmed controls. The fallback prompt expires after 20 seconds. Authorization or confirmation rechecks every local takeoff condition and invokes the existing pilot takeoff implementation. Ack is `ok:true` only after stable hover telemetry; decline, expiry, SDK failure or interruption is `ok:false`. STOP cancels the prompt and requests cancellation of any active takeoff. Duplicate IDs cannot launch twice. The server waits at most 65 seconds. No remote grant-permission action exists. Preauthorized launches attempt flight enable only after stable hover; require fresh flight_enabled status before moving.

Agent HTTP routes require `Authorization: Bearer <GA_AGENT_TOKEN>`: GET `/agent/status`, POST `/agent/mission`, POST `/agent/observation`, POST `/agent/action`, POST `/agent/actions/{UUID}/wait`, POST `/agent/memory`, GET `/agent/memory/{UUID}`, POST `/agent/release` and POST `/agent/stop`. `/docs` exposes exact request schemas. `mission` returns a private lease; subsequent owning requests carry `mission_id` and `lease`. An action also carries an `action_id` and `observation_id`. Responses to accepted actions are initially `pending`; poll/wait for `completed`, `failed` or `cancelled`. HTTP 202 alone is not physical completion.

`/agent/release` can clean up only its matching mission; `/agent/stop` is the explicit authenticated operator/agent stop-all endpoint. Old leases cannot regain control after disconnect, reset, expiry or restart. Existing dashboard reset/abort can release agent control. See [OpenClaw integration](OPENCLAW_INTEGRATION.md) for limits, Watch routing, memory and deployment.

## Agent launch control status

Phone `control` now includes `takeoff_authorized`, `takeoff_authorization_seconds`, `takeoff_auto_enable_pending`, `takeoff_last_error`, `takeoff_diagnostics` and `flight_limits`. These are observations, not a remote authorization API. Authorization expires after five minutes, is consumed once, and is cleared by STOP/disconnect/inactivity/restart. The existing 65-second request wait includes the optional 20-second prompt and up to 30 seconds for preparation/hover. Success confirms hover, not virtual-stick enable. See [AUTONOMY_TEST.md](AUTONOMY_TEST.md).
