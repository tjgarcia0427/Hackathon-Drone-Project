# GPS update rate and missing altitude — September 20, 2026

## What changed

The iPhone now reports observations about **five times per second**, using the existing 10 Hz control loop. Previously reports were capped at roughly once per second. This improves delivery of DJI readings; it does not increase the sensor's own sample rate or invent intermediate positions. JPEG uploads remain roughly once per second.

Previously altitude and heading were copied only when GPS was strong. Server telemetry was withheld entirely until GPS, the ground anchor and battery were valid. The redesigned phone also hid altitude whenever its navigation position was unavailable. Now the phone captures barometric altitude and heading on every DJI flight-controller callback and displays them independently of GPS. **0.0 m on the ground is valid.** DJI altitude is relative to takeoff, not terrain clearance, sea-level elevation or Apple Watch altitude.

The dashboard sends the newest observations without making drone telemetry/command acknowledgments wait for a slow dashboard connection. Pending display updates are coalesced instead of queued. Slow dashboard sockets are closed so the browser can reconnect. Both phone versions show coordinates to six decimal places; the redesigned dashboard does too. Four-decimal latitude previously hid changes smaller than roughly 11 metres. More decimals improve visibility, not GPS accuracy.

## Flight behavior is preserved

`TelemetryDisplay.h` builds display-only observations. `DroneBridge.m` keeps the original navigation pose, ground-anchor recording, arming, freshness checks, command handling, control loop and video-decoding behavior. Full `telemetry` packets retain the original GPS/home/freshness gates and gain an `aircraft` field. When those gates fail, `aircraft_status` supplies only partial observations.

The server stores these observations separately from `DroneState`. They do not set home, refresh navigation readiness, authorize dispatch or relax GPS requirements. Stale or missing observations become JSON `null` / a displayed dash. Flight-controller observations expire after 1.5 seconds, battery after 5 seconds and gimbal after 1.5 seconds. Source age and server/browser elapsed time are included in expiry. See [PROTOCOL.md](PROTOCOL.md).

## Install and bench check

1. Pull the updated branch on the Mac. The telemetry fix is available on `main` and separately on `ui-redesign`; this does not merge the UI redesign into `main`.
2. Restart the Python server from the updated checkout. Refresh the dashboard so it loads `telemetry-display.js`.
3. Rebuild and install the updated iPhone app from `GuardianAngel.xcworkspace`. Updating only the server cannot make an older phone emit partial/faster telemetry. Existing DJI key/signing settings remain local.
4. With props off, connect phone, RC and aircraft. Start the live bridge and server connection. Fresh battery, heading and altitude should appear even while GPS/ground anchor say waiting. Flight stays disabled.
5. Read `http://localhost:8000/state` on the server Mac. Inspect `aircraft.altitude_m`, `fc_age_ms`, `gps_ok`, `gps_signal_level`, `satellites` and `ground_anchor_ok`. Altitude zero means a valid barometric reading; `null` means unavailable/stale. A missing/null `aircraft` usually means an older phone build or no new readings. `drone` may be null until navigation is ready.
6. Outdoors, once GPS is strong, both screens should show the same coordinates to six decimals. Network observations arrive about every 200 ms; unchanged coordinates can still be normal for a stationary aircraft or between DJI samples.
7. On disconnect or stale SDK data, readings should expire instead of freezing. Leave the outdoor flight test to the team's existing pilot procedure after this bench check.

## Review and validation handoff

Regression coverage checks grounded zero altitude, weak/missing GPS, independent source expiry, invalid readings, dashboard reconnection, old-navigation freshness, and ingestion of 100 updates plus an ACK while a dashboard is blocked. A source-preservation test compares flight, command, connection and video code to bench-tested commit `4ebcf22`; only the marked display observations/reporting and optional read-only UI snapshot are excluded.

The `Aircraft telemetry checks` workflow runs Foundation observation tests, navigation tests, dashboard JavaScript tests, preservation checks, and an unsigned production DJI build on `main`. The existing iPhone UI workflow builds `ui-redesign` and exercises an additional GPS-waiting/zero-altitude screen. Existing Watch/server CI runs the Python regression suite. Automated checks do not replace a real SDK/hardware test; Windows cannot run Xcode or measure the team's aircraft telemetry timing.

The original video fixes (OcuSync decoding-assist delegate, encoder selection, software decode and feed-byte logging) are retained. No AI provider, camera upload rate or flight limit was changed. Teammates should keep the functional patch on both branches when merging later.
