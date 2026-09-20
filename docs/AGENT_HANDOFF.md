# Guardian Angel — teammate agent handoff

## Goal and current decisions

Build a supervised fall-response/observation demo using Mavic Air 2, a native iPhone bridge, a Python/Claude command center and a Watch/phone Shortcut incident trigger. The team has moved off the Android route. Use the existing DJI iOS SDK; do not modify aircraft firmware. Work directly on `main`, with no PR workflow, as explicitly requested by TJ. Preserve and coordinate concurrent teammate edits.

TJ develops on Windows. The teammate has a Mac, Watch and drone. A compatible iPhone must be physically connected by USB data cable to the RC-N1 beside the pilot. If TJ's only iPhone is remote, another local iPhone is still required. Mac/Xcode signs and installs locally; no App Store submission is needed.

## What is implemented

- `iphone-bridge/ios/GuardianAngel.xcodeproj` and shared scheme: Objective-C UIKit app, deployment target iOS 15+, physical iPhone build.
- `iphone-bridge/ios/setup-mac.sh`, `Gemfile`, `Podfile`, `Config/`: CocoaPods setup and local secret/signing configuration. SDK pins: DJI 4.16.2, DJIWidget 1.6.8, FlySafe resource 01.00.01.18. Open the generated `.xcworkspace` after setup.
- `DroneBridge.m`: aircraft/component delegates, decoded camera snapshots, GPS/battery/home telemetry, command validation, mock mode, 10 Hz control loop, local arm/disarm and interruptions.
- `BridgeClient.m`: WebSocket JSON, ping/pong heartbeat, raw JPEG upload, session-aware callbacks.
- `Navigation.c`: bounded target/velocity math shared by real and mock control. DJI Ground/Velocity axes are **roll = north velocity, pitch = east velocity**, positive verticalThrottle = up; yaw rate positive clockwise. These mappings were checked against official 4.16.2 headers and still require physical verification.
- `AppDelegate.m`: preview, server URL, mock selector, start/connect, camera-only enable, confirmed flight enable, STOP AI and log.
- `iphone-bridge/tools/smoke_server.py`: manual mock-only command/ack/frame test server, no AI costs and no live hardware.
- `server/app.py`: reviewed integration already applied. Adds bounded delivery/completion waits, expiry, fresh telemetry/frames, reset/abort cancellation, stop requests, one connection, disconnect cleanup and frame generation checks.
- `server/planner.py`, `server/safety.py`: guidance/limits aligned to the iPhone demo: 5 m moves, 35 m server radius with 40 m independent phone fence, 5–30 m altitude, about 10 m suggested altitude and 5–10 m demo search radius. Invalid/non-finite navigation parameters are rejected in server safety.

The original scaffold was `15359dc4306052695062c02092d709905009dcac`. `iphone-bridge/server-support/patch_server.py` is retained for older copies only; **do not apply it again to current main**. It checks the original AST fingerprint and refuses modified/duplicate inputs. Its patch touches `app.py` only, so old checkouts also need the current planner/safety/documentation changes.

## What has been checked

Portable C navigation tests passed with warnings treated as errors, including axes, wrap, bounds, velocity caps and convergence from 12 bearings. Thirteen package Python tests passed (10 actual patched-server function tests plus 3 FastAPI transport tests). Additional `server/test_safety.py` tests cover the aligned server limits and invalid inputs.

Objective-C files parsed without syntax errors; the Xcode project, scheme, source references and plist were checked. SDK method/delegate names were compared with official headers and DJIWidget source. This is **not** an Xcode compile or SDK type/link check. Read `iphone-bridge/REVIEW.md` and `VALIDATION.md` for the full record.

No physical iPhone/aircraft test, Xcode build, signed IPA, AI account/model call or end-to-end Watch demo was completed on Windows. The exact iOS/Xcode/firmware combination remains unverified. The existing `CLAUDE_MODEL` fallback was not confirmed; set it to an actual available model ID compatible with the planner call before testing the AI loop.

## Next tasks, in order

1. Read the root README, `iphone-bridge/README.md` and `docs/PROTOCOL.md`. On Mac, run `bash setup-mac.sh` in `iphone-bridge/ios`. Resolve CocoaPods and prove an Xcode compile/link before spending time on flight features.
2. Create a DJI **Mobile SDK iOS** app registration with a unique bundle ID. Put matching `PRODUCT_BUNDLE_IDENTIFIER` and `DJI_APP_KEY` in local `Config/Secrets.xcconfig`; select the Apple team/signing in Xcode. Never commit secrets. Build/install onto the physical phone, then launch independently of the Mac.
3. Run mock-only smoke tests through FastAPI `/docs`: gimbal, yaw, 5 m move, hold, STOP and reconnect. Check acknowledgments and frame byte count. Do not run simulator and phone concurrently against one server.
4. With propellers removed, switch mock off before starting the bridge. Close DJI Fly; connect controller/phone/aircraft. Prove registration, aircraft model/telemetry, video and a camera-only gimbal command. The project has no general `/command` endpoint; use a small controlled server-side command harness or the existing mission runner only after appropriate local flight enable. Do not remove the smoke server's live-hardware rejection.
5. Check Anthropic model access, structured outputs, detector and Watch/Shortcut incident submission separately. Keep `AUTO_DISPATCH=0`. Show the operator any GPS uncertainty outside the small demo search area.
6. On real hardware, check normal DJI failsafes/RTH height first, record the ground GPS anchor with the bridge running, manually take off with the RC, stay at 5–30 m, and enable flight locally. Verify axes, small yaw/move/hold, STOP, link loss, physical takeover and RTH/landing under controlled conditions before a full mission.
7. Use the coordinated server for a nearby incident → operator dispatch → camera search → candidate review demonstration. Record actual results/remaining issues in validation docs. If DJI build or hardware validation blocks progress, demonstrate clearly labelled simulation.

The first useful error report is the earliest Xcode/dependency error with surrounding lines, Xcode/iOS versions and firmware/controller versions. Do not share app keys, signing material or unrelated logs.

## Contract and behavior to preserve

Commands are flat JSON: `{ "type":"cmd", "cmd_id":"unique-id", "action":"move", "bearing":90, "dist":5, "expires_at_ms":<now+5000> }`. See protocol for `goto`, `yaw`, `gimbal`, `hold`, `rtl`, `stop`. Most positive ACKs wait for telemetry settling; RTH waits for SDK acceptance plus landing (server 180 s, phone 170 s). STOP ACK means the release request was processed, not completed by hardware.

There is no remote takeoff command. Reconnect/foreground loss must not auto-arm. STOP requests control release and never kills motors or cancels DJI RTH. The RC remains necessary for takeover and RTH cancellation. A failed SDK release blocks re-arm and STOP can retry. Local limits do not bound DJI's own configured RTH path/altitude. No obstacle/terrain planning or force-kill-proof watchdog is implemented.

Keep stale-frame/telemetry and session-generation checks. Avoid enabling concurrent normal commands or loosening safety to accommodate a planner output. Restart the server if launch/home changes or mock/live modes are switched. Preserve connection-aware JPEG callbacks and duplicate-ID handling.

The iPhone is a bridge/controller, not an onboard visual AI model. Claude/detector run on the server. The Shortcut supplies incident data; no Apple built-in fall-detection subscription or Watch app exists. Current "found" coordinates indicate the aircraft, not a triangulated person position. No real emergency notification or emergency-service dispatch is implemented.

The backend is unauthenticated and intended for a private demo network or authenticated VPN. Do not use an unauthenticated public tunnel. Keep the bridge app foregrounded; triggering a Shortcut by switching apps on that same iPhone can disarm the bridge, so use a separate incident device or the laptop's demo trigger.
