# One-use agent launch and lower-altitude flight

Current main includes the merged phone UI, a **1–30 m altitude envelope relative to takeoff**, and optional one-use agent launch. Rebuild/install the phone app, restart the server, reload the OpenClaw plugin, and update the dedicated agent's workspace instructions together. No database change is involved.

## First run

1. Pull main on the Mac and rebuild/install `iphone-bridge/ios/GuardianAngel.xcworkspace` while grounded. Keep the existing DJI app key and pinned SDK dependencies.
2. Restart the server with the existing agent token, `GA_MISSION_DRIVER=openclaw` and `GA_AGENT_MAX_MODE=flight`. Keep `AUTO_DISPATCH=0`. Stop any simulated drone connection first.
3. Reload/reinstall `integrations/openclaw` using [OPENCLAW_INTEGRATION.md](OPENCLAW_INTEGRATION.md). Copy the updated workspace AGENTS.md and MEMORY.md guidance into the dedicated mission agent's workspace, preserving real mission notes. Restart the Gateway/start a fresh agent session so old launch instructions do not remain in context.
4. Connect the controller and grounded aircraft to the phone; start the real bridge and connect the server. Wait for fresh strong GPS, Ground anchor OK and battery ≥30%. Camera-only/flight control must be disarmed.
5. Tap **Authorize one agent launch**, then **Authorize** on the phone. This authorizes one launch and a flight-enable attempt after stable hover, for **five minutes**. It does not launch immediately. Keep Guardian Angel foreground and the RC ready. The button shows time remaining and can revoke authorization.
6. Give the agent the mission below. It calls `guardian_status`, `guardian_begin`, `guardian_observe`, then `guardian_request_takeoff`. A live phone authorization is consumed before the SDK call, so no second popup is needed.
7. After DJI accepts takeoff, the phone waits for fresh, settled flight telemetry at ≥1 m for one second, then attempts virtual-stick flight enable. The result confirms **hover**, not flight enable: the agent must observe again and see `control.flight_enabled` before movement. DJI's native hover is approximately 1.2 m.
8. First request one 1 m movement in a pilot-cleared direction, hold, then stop. Confirm measured motion, hover and RC takeover before a full search.

Example prompt (supply a real, clear bearing):

> I have authorized one agent launch on the phone and cleared the launch area and first movement path. Start a flight mission to test takeoff and a 1 m move at bearing BEARING. Check current status and observation. Request takeoff once. After confirmed hover, observe again; wait briefly for fresh flight_enabled=true before moving. Move 1 m, observe, hold, report the measured result and stop. On any failed, missing or uncertain result, stop and report it; do not retry takeoff automatically.

For GPS tasks, pin measured coordinates at `guardian_begin`; `guardian_navigate` accepts altitude 1–30 m. Visual searches use fresh images and bounded move/yaw/gimbal tools plus mission memory. The built-in dashboard planner remains separate and does not acquire launch authorization itself.

## Permission and limits

Authorization is local, in memory, one-use and time-limited. STOP, server/aircraft disconnect, app inactivity, restart or shutdown revokes it. It is never restored from a database. Ground/home recovery after app switching restores a reference point, not flight permission. Failed launches consume authorization and must not be automatically retried.

Without preauthorization, `guardian_request_takeoff` retains its 20-second local pilot prompt and leaves flight enable manual. **Take off (pilot)** also leaves flight enable manual. This build requires no RC climb to 5 m.

Unchanged: server radius 35 m, phone radius 40 m, movement step ≤5 m, horizontal speed ≤1 m/s, vertical speed ≤0.5 m/s, yaw ≤10°/s, battery/freshness/STOP checks. The 1 m floor is relative to launch, **not height above terrain or obstacles**. Neither model images nor the navigation controller provide obstacle/terrain avoidance. DJI RTH uses DJI's own configured home and altitude.

## DJI takeoff error -1008

The old log gave a generic command-execution error, not a specific cause. This update adds preparation and diagnostics; a real-aircraft retest must establish whether it resolves the error on this firmware.

Before launching, the phone reads virtual-stick mode, switches it off if necessary, and rechecks live launch conditions. It submits takeoff once. STOP during preparation invalidates callbacks so delayed responses cannot launch. It does not force motors on, spoof grounded state, disable DJI protections or retry rejected launches.

If it fails, copy these phone log entries:

- `Takeoff preparation...` (mode off / releasing mode)
- `Submitting DJI takeoff once: ...` (firmware, mode, motors, GPS, altitude, battery and diagnostics)
- `DJI takeoff response: ...` (error domain and code), or the preparation-stage error
- `Takeoff diagnostic snapshot: ...`, plus `DJI diagnostics: ...` reasons and solutions

The agent receives these details through `control.takeoff_last_error` and `control.takeoff_diagnostics`. An empty diagnostic list means no messages received, not certified readiness. Negative SDK error `-1008` is distinct from positive camera diagnostic `1008`.

If motors are on or the aircraft moves after an error, the pilot must verify/take control; the agent must not retry. If rejection persists while grounded, inspect DJI Fly's actual aircraft warnings and firmware versions. Resolve reported problems before returning and authorizing a new attempt. The [airborne recovery fallback](APP_SWITCH_RECOVERY.md) remains available after pilot takeoff.

References: [DJI flight-controller API](https://developer.dji.com/api-reference/ios-api/Components/FlightController/DJIFlightController.html), [SDK errors](https://developer.dji.com/api-reference/ios-api/Components/SDKError/DJIError.html). The project uses the exact DJI SDK 4.16.2 signatures.

## Regression coverage and handoff

Server tests cover 1 m/1.2 m acceptance, below-floor rejection, unchanged step limits and status delivery. Native tests cover navigation, permits, hover and cancellation. Production Objective-C seam tests exercise request deduplication, expiration, delayed SDK callbacks, STOP during preparation, GPS/link rechecks, SDK errors and auto-enable only after stable hover. UIKit tests cover the authorization controls; main now runs the UI workflow as well as the unsigned real DJI build. The bench preservation check still protects video and existing command/lifecycle code outside explicitly marked additions.

Remaining hardware evidence: successful SDK takeoff on the actual Mavic Air 2/RC231 firmware, flight enable, a short measured move and pilot takeover. Automated tests cannot prove aircraft compatibility or obstacle clearance. Database expansion remains paused.
