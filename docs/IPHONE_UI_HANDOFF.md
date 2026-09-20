# iPhone UI redesign — branch handoff

**Telemetry follow-up (September 20):** the functional telemetry fix is applied independently to `main` and this branch. Altitude/heading are now GPS-independent display observations, reporting is 5 Hz, and coordinates show six decimals. Flight/video preservation checks now allow the marked observation/reporting regions as well as the UI snapshot. See [TELEMETRY_FIX.md](TELEMETRY_FIX.md) for the implementation and regression handoff.

Work on `ui-redesign`; do not merge into `main` until Lorenzo finishes the device regression. TJ explicitly authorized this branch on September 20. No pull request is required. The existing dashboard redesign on this branch belongs to Alfred and was preserved unchanged by this update.

## What changed

The iPhone uses the existing navy / public-safety design: fixed header and operational status, camera preview, telemetry grid, guided controls, last four log entries, full event log, and a pinned STOP bar. UIKit, SF system fonts and SF Symbols; no new production dependencies or storyboards.

Corrections to the original redesign:

- **Camera control is an optional check.** After camera-only arming, the next action is explicitly **Stop camera control**. That action only calls STOP. **Enable flight** then opens a separate confirmation. A disarmed operator may go directly to that confirmation. The existing bridge interlock remains authoritative.
- **Confirmation reads current state**, including server/aircraft presence, GPS/anchor, telemetry age, battery, altitude, distance, airborne state, control transitions and release errors. It refreshes while open and checks again when tapped and before calling `armFlight:YES`. There is no automatic re-arm after a disconnect or STOP.
- **Pending is not released.** Waiting for a DJI callback and failed control release have distinct status strips; failures direct the pilot to the RC and STOP retry. No optimistic "pilot has control" label is inferred from `_flightEnabled` turning false.
- **Mock is explicit even while armed.** Mock flight and return states retain the mock label.
- **Preview labels are truthful.** No recording indicator, invented resolution or invented FPS. Unknown/stale telemetry is shown as unavailable; its clock is based on the last telemetry timestamp. Dashboard uploads remain the existing approximately one JPEG per second.
- **STOP is available on every screen**, including the full event log and the confirmation modal. The modal scrolls on small screens while its STOP stays pinned.
- **The old status callback remains.** `updated(NSString *)` still works. `stateUpdated(NSDictionary *)` adds read-only state at about 5 Hz; `telemetry` provides a fresh main-thread snapshot. The root UI polls the snapshot every 250 ms to expire stale readings promptly. These getters send no SDK commands.

The DJI decoder delegate, Mavic Air 2 encoder selection/reset, software decode, video byte diagnostic, decoded snapshot/upload code, command protocol, timers, flight limits, GPS/anchor logic and arm/release logic are preserved from the real-hardware bench commit `4ebcf22b1c09b9872ff9a4503dfccdfbbacacd99`. `check_bridge_preservation.py` verifies the complete source after removing only the additive read-only snapshot and callback.

## Validation

**Latest validated code: `1a8e69b91282aa66b4d8947c92e22c1b1ea76503`.** [Run 35492150230](https://github.com/tjgarcia0427/Hackathon-Drone-Project/actions/runs/35492150230) passed: production iPhone compile/link with DJI pods, presentation-state checks, navigation tests, full bridge-preservation check, and simulator UI interactions. Thirteen screenshots cover the main states, scrolled camera-to-flight procedure, confirmation, and event log. Final screenshots were visually reviewed; the ground-anchor label fits and STOP stays pinned. The simulator log contains no Auto Layout conflict messages. Later documentation-only commits do not change this tested code.

The first correction commit `73f4dcb` passed the [macOS iPhone build](https://github.com/tjgarcia0427/Hackathon-Drone-Project/actions/runs/35491353246): pinned CocoaPods installed, the **production iPhone target compiled and linked unsigned**, and presentation-state / navigation / preservation checks passed.

[Run 35491733367](https://github.com/tjgarcia0427/Hackathon-Drone-Project/actions/runs/35491733367) passed for `6abcd68`: the production app compiled/linked again, the simulator interaction sequence passed, and 12 state screenshots were captured. Review of the simulator log found no Auto Layout conflict messages. These are simulated hardware states, not a real DJI mission. Screenshot review led to the label-fitting and STOP alignment polish validated by the latest run above.

Later changes must pass the branch's `iPhone UI checks` workflow again. It also builds the production UIKit controller in a separate **simulator-only harness**, using fake hardware and server state. This exercises camera STOP, separate flight confirmation, log STOP, rejection of a disconnected/stale confirmation, and modal STOP. Artifacts contain state screenshots and build logs. The harness is never part of the production target and does not test DJI hardware or a real server mission.

The working original app passed Lorenzo's props-off bench, including phone/dashboard video and physical gimbal commands. The redesigned app still requires the same check on his physical iPhone. Real flight and physical Watch validation are separate outstanding gates. The Watch already compiled on macOS CI; it is not an unbuilt app.

## Mac build and device regression

Keep the working main checkout. Fetch the branch into a separate checkout if desired, and copy the existing local `Config/Secrets.xcconfig` to the UI checkout without committing it. Installing with the same bundle ID replaces the phone's app, so keep the known-good main build available to reinstall for the initial flight test.

From the UI checkout's `iphone-bridge/ios`:

```bash
bundle install
bundle exec pod install
xcodebuild -workspace GuardianAngel.xcworkspace -scheme GuardianAngel \
  -configuration Debug -sdk iphoneos -destination 'generic/platform=iOS' \
  -derivedDataPath build-ui -allowProvisioningUpdates build
```

Use the teammate's actual device ID when installing `build-ui/Build/Products/Debug-iphoneos/GuardianAngel.app`; the old handoff's device ID and DerivedData suffix are machine-specific. For local simulator UI checks, run `bash iphone-bridge/tests/ui/run-mac.sh` from the repository root. This simulator harness needs no DJI key, account or connected controller.

Regression order:

1. **Mock, actual project server:** Start → Connect → Arm camera only → **Stop camera control** → Enable flight → confirm → dashboard Simulate fall → Dispatch. Check acknowledgments through the mission and return. Confirm mock labels, server reconnect without re-arm, log STOP, and root STOP. No real person detection is expected from the mock frame.
2. **Props-off hardware:** restart with Mock off before Start → real aircraft connection → server connection → Arm camera only. Verify video on the phone and dashboard, plus the existing `/dev/cmd` gimbal check. Verify log navigation and foreground return do not disrupt video. Test STOP and explicit re-arm.
3. **Existing main first:** Lorenzo performs the separate outdoor GPS/flight test on the working main build before any UI merge. Merge only after the redesigned screen passes the above device checks and the pilot can identify current control state and STOP.

Correct gimbal request (server must start with `DEV_COMMANDS=1`):

```bash
curl -X POST http://localhost:8000/dev/cmd \
  -H 'Content-Type: application/json' \
  -d '{"action":"gimbal","pitch":-45}'
```

## Concurrent main update

Main also received the teammate's app-icon commit `da36a46`. This UI branch does not replace its asset catalog or project settings; a normal Git merge should retain that independent change. Do not overwrite the main project file with an older copy from this branch during handoff.

## Design reference

The written `UI_REDESIGN_SPEC.md` is available. The HTML prototype and runtime assets were not in the fetched repository when this work began. Use its accepted turn 2 (`#2a`) when supplied; operational truth and the above interlocks take precedence over decorative sample values. Do not import the rejected turn 1 design tokens.
