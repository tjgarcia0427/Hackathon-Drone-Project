# Pilot takeoff inside Guardian Angel

The iPhone now has **Take off (pilot)**. It calls DJI Mobile SDK's standard
`startTakeoffWithCompletion:` only after a local confirmation. The OpenClaw tool can request a pilot confirmation on the phone; only the pilot's approval initiates launch. A Watch alert alone cannot launch. No firmware change is involved.

## First hardware test

1. Pull the updated branch and rebuild/install the iPhone app from Xcode. A server
   restart alone cannot add this button. Keep using your existing DJI key/signing.
2. Complete DJI Fly's normal preflight checks and RTH configuration while grounded,
   then close DJI Fly. Prepare the aircraft for an outdoor flight with the RC pilot.
3. Open Guardian Angel, choose live hardware before starting the bridge, and connect
   the server. Wait for fresh telemetry, **GPS OK** and **Ground anchor OK**.
4. If camera-only mode was enabled, press **STOP AI** first and wait for release.
   Tap **Take off (pilot)**, review the confirmation, then tap **Take off**.
5. Stay in Guardian Angel. DJI's standard takeoff targets about **1.2 m**, below our
   AI flight envelope. Wait for the log **Takeoff hover confirmed**. The server
   should stay connected, the same ground anchor should remain recorded, and the
   dashboard altitude/flying fields should update. AI remains disabled.
6. Use the RC to climb to **5–30 m**, staying within **40 m** of the recorded anchor.
   Tap **Enable flight** and confirm separately. Begin with a short supervised
   movement/hold check before an incident mission. The existing 1 m/s AI speed cap
   and server checks still apply.

The original mock-hardware startup remains airborne at 10 m for compatibility
with existing mission tests. Its Take off button is therefore unavailable. The
native policy tests and simulator UI scenarios exercise the grounded takeoff flow
without changing that existing mock mission behavior.

## What persists

Takeoff keeps the **same DroneBridge instance, server WebSocket, recorded launch
coordinates, camera preview and telemetry stream**. The takeoff implementation
does not reconnect, recreate the bridge, change the anchor, or enable virtual stick.
No transition to DJI Fly is needed.

This is continuity through an in-app takeoff, **not restoration across app
termination, aircraft replacement, a power cycle or an actual DJI disconnect**.
Those events still invalidate flight-session state. Backgrounding disables AI and
disconnects the server as before. Do not rely on a saved old anchor for another
flight. Continue to restart the server when changing launch sites/mock-live mode.

## Gates and interruptions

- The app must be active, linked to the server with a recent heartbeat, and have
  the supported aircraft, strong GPS, a recorded anchor and fresh flight/battery
  data. Battery must be at least 30%, motors off, and the aircraft grounded within
  5 m of the anchor with relative altitude within ±2 m. Stop camera/AI control first.
- The bridge checks these conditions again at confirmation. DJI's own takeoff
  restrictions remain authoritative; any SDK error is displayed in the event log.
- Repeated taps cannot start overlapping takeoffs. AI/camera arming is blocked
  throughout takeoff. A successful SDK callback at about 0.5 m is only acceptance;
  completion also requires fresh airborne telemetry outside automatic takeoff/
  return/landing mode and a stable hover for one second.
- **STOP AI also requests cancellation of an in-progress pilot takeoff.** This
  does not kill motors or command landing. DJI RTH/landing are not cancelled.
  Link/GPS/telemetry loss, app inactivity or a 30-second takeoff timeout also request
  cancellation. The RC pilot remains responsible if the connection is unavailable.
- Cancellation errors/timeouts keep AI blocked; use the RC and press STOP to retry.
  A late takeoff acceptance after cancellation requests cancellation again. Missing
  SDK responses never count as success; if the state cannot resolve, land under
  pilot control before restarting the bridge.

## Implementation and validation

`PilotTakeoff.h` contains the gate and request state machine, separate from the
anchor/server/AI state. `DroneBridge.m` supplies fresh DJI observations, calls the
SDK and checks callback identities. Both iPhone UIs expose the same local action.
The video decoding implementation and navigation limits remain unchanged.
The optional OpenClaw extension adds `request_takeoff` and read-only control status; it does not add remote flight arming. The preservation check permits only the explicit pilot-takeoff additions
alongside the previously reviewed telemetry updates.

Run on macOS:

```bash
xcrun clang -std=c11 -Wall -Wextra -Werror -Iiphone-bridge/ios/GuardianAngel \
  iphone-bridge/tests/pilot_takeoff_test.c -lm -o /tmp/pilot_takeoff_test
/tmp/pilot_takeoff_test
python3 iphone-bridge/tests/check_telemetry_preservation.py
```

The native tests cover launch gates, early callbacks, hover settling, duplicate
requests, cancellation ordering, SDK rejection, timeout and loss of live checks.
On `ui-redesign`, the simulator harness adds `takeoff-ready`, `takeoff-confirm` and
`takeoff-pending` scenarios. CI compiles the production app with the pinned DJI SDK
and DJIWidget libraries. These checks do not replace the first real aircraft test.

DJI reference: [takeoff and cancellation API](https://developer.dji.com/api-reference/ios-api/Components/FlightController/DJIFlightController.html).

## Validation record — September 20, 2026

- Main implementation: `9b0c51910b060bfd45738929b9cdc80881e16881`.
  [Main native tests and production iPhone build passed](https://github.com/tjgarcia0427/Hackathon-Drone-Project/actions/runs/35525740287).
- UI implementation: `99a7e5d5afaf32b041f699846c9f8433f526fed5`, with the
  simulator runner's Unix line endings corrected in `aa6bef3da2ed8083e63ca5a6a8cceb14c5720e78`.
  [All 17 UIKit scenarios and production iPhone build passed](https://github.com/tjgarcia0427/Hackathon-Drone-Project/actions/runs/35525822568).
  [UI branch native/dashboard checks and 44 server tests passed](https://github.com/tjgarcia0427/Hackathon-Drone-Project/actions/runs/35525822397).
- The native takeoff state-machine suite also passed locally on Windows. Preservation
  checks confirm the existing video, navigation and command code outside the
  explicitly allowed pilot-takeoff additions remains unchanged.
- No command was sent to a real aircraft during implementation. Signed installation
  and the first outdoor takeoff/hover/state-continuity check remain with the pilot.

## OpenClaw request flow

An agent takeoff request opens a separate **Agent requests takeoff** confirmation on the iPhone. Decline or wait 20 seconds to reject it. Confirming runs the same checks and launch path above, retains the current bridge/server/anchor, and leaves AI disabled. STOP, disconnect or app inactivity cancels the request; stale approval callbacks cannot launch. The phone acknowledges success only after the stable hover check. See [OpenClaw integration and setup](OPENCLAW_INTEGRATION.md).
