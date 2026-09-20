# Pilot takeoff and optional agent launch

Use current main and rebuild/install the iPhone app. See [AUTONOMY_TEST.md](AUTONOMY_TEST.md) for coordinated server/OpenClaw setup, first test, diagnostics and teammate handoff.

## Local takeoff

With the real bridge/server connected, strong GPS, Ground anchor OK, battery ≥30%, motors off and camera/flight control disarmed, tap **Take off (pilot)** and confirm. The phone keeps the server connection and anchor while DJI launches. It waits for accepted takeoff plus fresh stable hover at ≥1 m for one second; DJI normally hovers around 1.2 m. Tap **Enable flight** afterward. The envelope is **1–30 m above takeoff**; no climb to 5 m is required.

## Agent takeoff

Tap **Authorize one agent launch** and confirm locally before giving the mission. It permits one agent launch plus a flight-enable attempt after stable hover, expires in five minutes, and is consumed even if launch fails. STOP, disconnect, inactivity or restart revokes it. The agent request then needs no second popup.

Without this permission, the tool opens **Agent requests takeoff**, expiring after 20 seconds. Confirmation launches but leaves AI disabled until the pilot enables flight. Takeoff acknowledgment confirms hover only; agents need fresh `control.flight_enabled` before movement.

## Interruptions and errors

The phone reads virtual-stick mode, releases it if necessary, and rechecks live launch prerequisites before sending one SDK takeoff command. Launch still requires grounded telemetry within 5 m of the anchor and relative altitude within ±2 m, distinct from the in-flight envelope.

STOP before submission cancels preparation; afterward it requests DJI takeoff cancellation. Delayed callbacks cannot enable AI after STOP. Cancellation does not stop motors or command landing. Uncertain outcomes require pilot verification. Missing callbacks or loss of foreground, link, fresh telemetry or GPS triggers cancellation handling. No automatic launch retry occurs.

Error -1008 now logs the error domain, stage and diagnostic snapshot. This is a control-mode preparation change and troubleshooting instrumentation, not a confirmed firmware fix. Follow [AUTONOMY_TEST.md](AUTONOMY_TEST.md). The [app-switch fallback](APP_SWITCH_RECOVERY.md) remains available after pilot takeoff in DJI Fly.

## Validation

Native tests cover the state machine and permit. The two production Objective-C seam suites exercise remote request handling and delayed SDK read/release/launch/cancel callbacks. UIKit tests cover visible controls; CI compiles/links DJI SDK 4.16.2 and DJIWidget 1.6.8. Actual launch compatibility, clear flight paths and RC takeover require hardware verification.
