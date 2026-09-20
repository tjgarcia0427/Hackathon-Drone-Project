# Guardian Angel — teammate agent handoff

## Goal and current decisions

Build a supervised fall-response/observation demo using Mavic Air 2, a native iPhone bridge, a Python command center with selectable AI and a native Watch button/shake help trigger (legacy Shortcut still supported). The team has moved off the Android route. Use the existing DJI iOS SDK; do not modify aircraft firmware. TJ now authorizes `ui-redesign` for the iPhone UI work; keep the hardware-tested `main` unchanged until Lorenzo completes the device regression. No PR workflow is required. Preserve and coordinate concurrent teammate edits.

TJ develops on Windows. The teammate has a Mac, Apple Watch SE (2nd generation) on watchOS 26.5, and drone. A compatible iPhone must be physically connected by USB data cable to the RC-N1 beside the pilot. If TJ's only iPhone is remote, another local iPhone is still required. Mac/Xcode signs and installs locally; no App Store submission is needed.

## What is implemented

- `iphone-bridge/ios/GuardianAngel.xcodeproj` and shared scheme: Objective-C UIKit app, deployment target iOS 15+, physical iPhone build.
- `iphone-bridge/ios/setup-mac.sh`, `Gemfile`, `Podfile`, `Config/`: CocoaPods setup and local secret/signing configuration. SDK pins: DJI 4.16.2, DJIWidget 1.6.8, FlySafe resource 01.00.01.18. Open the generated `.xcworkspace` after setup.
- `DroneBridge.m`: aircraft/component delegates, decoded camera snapshots, GPS/battery/home telemetry, command validation, mock mode, 10 Hz control loop, local arm/disarm and interruptions.
- `BridgeClient.m`: WebSocket JSON, ping/pong heartbeat, raw JPEG upload, session-aware callbacks.
- `Navigation.c`: bounded target/velocity math shared by real and mock control. DJI Ground/Velocity axes are **roll = north velocity, pitch = east velocity**, positive verticalThrottle = up; yaw rate positive clockwise. These mappings were checked against official 4.16.2 headers and still require physical verification.
- `AppDelegate.m`: `BridgeViewController` (navy header, status strip, camera preview, telemetry table, 4-step pre-flight procedure, event-log tail, pinned STOP bar), `FlightConfirmViewController` (enable-flight modal with live gate checks) and `LogViewController` (full event log). Presentation only; all control goes through `DroneBridge`, whose original `updated(NSString *)` callback remains compatible. The additive `stateUpdated(NSDictionary *)` callback and read-only `telemetry` snapshot supply the new screen. See `docs/IPHONE_UI_HANDOFF.md` (repository root) for control-flow corrections, native build evidence and device regression.
- `iphone-bridge/tools/smoke_server.py`: manual mock-only command/ack/frame test server, no AI costs and no live hardware.
- `server/app.py`: reviewed integration already applied. Adds bounded delivery/completion waits, expiry, fresh telemetry/frames, reset/abort cancellation, stop requests, one connection, disconnect cleanup and frame generation checks.
- `server/planner.py`, `server/safety.py`: guidance/limits aligned to the iPhone demo: 5 m moves, 35 m server radius with 40 m independent phone fence, 1–30 m altitude, about 10 m suggested altitude and 5–10 m demo search radius. Invalid/non-finite navigation parameters are rejected in server safety.

The original scaffold was `15359dc4306052695062c02092d709905009dcac`. `iphone-bridge/server-support/patch_server.py` is retained for older copies only; **do not apply it again to current main**. It checks the original AST fingerprint and refuses modified/duplicate inputs. Its patch touches `app.py` only, so old checkouts also need the current planner/safety/documentation changes.

## AI provider changes (September 19, 2026)

The current server supports `codex` (ChatGPT subscription), `claude_code` (Claude subscription), `openai_api` and `anthropic_api`. See `docs/AI_PROVIDERS.md` in the repository for exact setup, billing/authentication distinctions and smoke commands. All four paths support typed mission plans and JPEG-based search decisions. No iPhone code change or OAuth app registration is needed.

- `server/ai_backends.py`: lazy API clients, official CLI subprocesses, image/schema handling, subscription-login checks, finite-number validation and bounded process cleanup. Never extract tokens or silently fall back to API billing. Subprocess tools/customizations are disabled; model decisions still pass the existing safety layer.
- `server/planner.py`: provider-independent prompts and immutable provider/model settings. `AI_PROVIDER` defaults to the original Anthropic API path; explicitly set `codex` or `claude_code` for subscription use. `AI_MODEL` is optional for CLIs; use an account-accessible image/structured-output model for APIs.
- Dashboard + `GET /ai`, `POST /ai/config`: provider/model selection while idle only. Reset and finish outstanding planning/commands before switching. Configuration is memory-only; restart restores environment settings. No credential fields are accepted.
- Planning is bounded to 60 seconds; search uses `AI_SEARCH_TIMEOUT` (default 30 seconds), and the frame-age check is that timeout plus 5 seconds. Preserve this teammate change and the Claude stream-json/verbose fix. Reset/abort invalidates a late incident plan, and a timed-out search worker cannot issue its late action.
- `server/ai_smoke_test.py`: synthetic red-circle image, no drone connection. `--check-only` tests prerequisites/login; omit it to test real image inference. A pass is not a flight or latency guarantee.
- `server/test_ai_backends.py` and `test_ai_configuration.py`: real SDK serialization via mocked HTTP, actual CLI subprocess fixtures, key/login isolation, timeouts, switching locks and reset cancellation.

These changes were developed and published through the GitHub connector directly to `main`, with no PR. Continue using the connector when available; current iPhone UI updates belong on `ui-redesign`, not `main`. Preserve teammate changes; do not force-push or reapply the old server migration.

## What has been checked

Portable C navigation tests passed with warnings treated as errors, including axes, wrap, bounds, velocity caps and convergence from 12 bearings. Thirteen package Python tests passed (10 actual patched-server function tests plus 3 FastAPI transport tests). Additional `server/test_safety.py` tests cover the aligned server limits and invalid inputs.

Objective-C files parsed without syntax errors; the Xcode project, scheme, source references and plist were checked. SDK method/delegate names were compared with official headers and DJIWidget source. This is **not** an Xcode compile or SDK type/link check. Read `iphone-bridge/REVIEW.md` and `VALIDATION.md` for the full record.

The real Codex CLI signed in with ChatGPT passed a synthetic-image structured-output test in 5.67 seconds, and dashboard incident planning produced a valid plan. The full search test exceeded the 8-second deadline with the CLI default model and correctly failed; `gpt-5.6-luna` passed in 7.05 seconds. Use `python ai_smoke_test.py --provider codex --model gpt-5.6-luna --search-check` to repeat on the demo machine/network before flight. The earlier suite had 23 tests; the current suite has 37 including the Watch flow. The Claude CLI fixture now includes stream-json event types to match the teammate's production fix. The server suite covers all four adapters, but Claude subscription and both API modes still need live account/model checks. The Anthropic fallback model remains unverified; select an available model explicitly. No physical iPhone/aircraft test, iPhone Xcode build, signed IPA or end-to-end Watch demo was completed by this agent. The separate Watch app subsequently compiled and linked in macOS CI, with its Swift core and all 37 server tests passing; see `watch-app/VALIDATION.md` for the exact run/SDK and remaining SE device tests. The exact iOS/Xcode/firmware combination remains unverified.

## Native Watch addition and next-agent context

- Read `docs/WATCH_SETUP.md` first. `watch-app/GuardianWatch.xcodeproj` is a separate, single-target SwiftUI watch-only app, deployment target watchOS 9+. The actual SE runs 26.5, so select Xcode with matching device support. No DJI dependencies in this project.
- Button and deliberate shake use haptic + 5-second cancel, one-shot Core Location, server-session UUID, immediate receipt and persistent same-ID retry. Shake requires the active app, turns off on background/settings, uses three acceleration peaks in two seconds and a 30-second cooldown. This is not automatic fall detection. Test mode defaults ON each launch. A persisted LIVE retry stays live and needs explicit UI confirmation even after relaunch into Test mode.
- `server/watch_alerts.py` validates timezone-aware event time, GPS completeness/freshness/accuracy, and retains IDs for 15 minutes. `app.py` acknowledges `POST /watch/alerts` before asynchronous planning. Test/invalid-location/busy events never create a mission. Busy alerts are not queued. `/watch/status` and `/watch/alerts/{id}` support setup and receipt checks.
- Mission destination is pinned to measured incident GPS; dispatch rechecks battery and full geofence. Watch plans expire 120 seconds after receipt. Reset/abort/disconnect invalidate late results. No new takeoff, arm or emergency-services mechanism.
- Dashboard has Watch cards, coordinates/accuracy/map links and opt-in foreground sound. The first test requires no AI/drone: `python server/watch_smoke_test.py`, then the actual Watch in Test mode. Use `AUTO_DISPATCH=0`.
- `server/test_watch_alerts.py` adds 14 tests. `watch-app/test-core-mac.sh` tests the pure Swift gesture, location, URL and retry logic. `.github/workflows/watch-checks.yml` builds Watch simulator code and runs regressions on macOS, subject to repository Actions availability. Inspect its result; do not equate an unsigned simulator compile with physical validation.
- Remaining physical checks: signed install on SE, network through paired iPhone/Wi-Fi, permissions, GPS, haptics, shake thresholds, app lifecycle and lost-response retry. Reuse existing iPhone flight staging; keep bridge foregrounded. The watch does not require plugging anything into RC-N1.

## Next tasks, in order

1. Read the root README, `iphone-bridge/README.md` and `docs/PROTOCOL.md`. On Mac, run `bash setup-mac.sh` in `iphone-bridge/ios`. Resolve CocoaPods and prove an Xcode compile/link before spending time on flight features.
2. Create a DJI **Mobile SDK iOS** app registration with a unique bundle ID. Put matching `PRODUCT_BUNDLE_IDENTIFIER` and `DJI_APP_KEY` in local `Config/Secrets.xcconfig`; select the Apple team/signing in Xcode. Never commit secrets. Build/install onto the physical phone, then launch independently of the Mac.
3. Run mock-only smoke tests through FastAPI `/docs`: gimbal, yaw, 5 m move, hold, STOP and reconnect. Check acknowledgments and frame byte count. Do not run simulator and phone concurrently against one server.
4. With propellers removed, switch mock off before starting the bridge. Close DJI Fly; connect controller/phone/aircraft. Prove registration, aircraft model/telemetry, video and a camera-only gimbal command. The project has no general `/command` endpoint; use a small controlled server-side command harness or the existing mission runner only after appropriate local flight enable. Do not remove the smoke server's live-hardware rejection.
5. Choose an AI provider and run its login/configuration and synthetic-image smoke tests from `docs/AI_PROVIDERS.md`. Check latency, detector and Watch test-mode and live GPS incident submission separately using `docs/WATCH_SETUP.md`. Keep `AUTO_DISPATCH=0`. Show the operator any GPS uncertainty outside the small demo search area.
6. On real hardware, check normal DJI failsafes/RTH height first, record the ground GPS anchor with the bridge running, use the local Take off (pilot) button or RC, then enable flight within 1–30 m above takeoff, or use one-use agent launch. Verify axes, small yaw/move/hold, STOP, link loss, physical takeover and RTH/landing under controlled conditions before a full mission.
7. Use the coordinated server for a nearby incident → operator dispatch → camera search → candidate review demonstration. Record actual results/remaining issues in validation docs. If DJI build or hardware validation blocks progress, demonstrate clearly labelled simulation.

The first useful error report is the earliest Xcode/dependency error with surrounding lines, Xcode/iOS versions and firmware/controller versions. Do not share app keys, signing material or unrelated logs.

## Contract and behavior to preserve

Commands are flat JSON: `{ "type":"cmd", "cmd_id":"unique-id", "action":"move", "bearing":90, "dist":5, "expires_at_ms":<now+5000> }`. See protocol for `goto`, `yaw`, `gimbal`, `hold`, `rtl`, `stop`. Most positive ACKs wait for telemetry settling; RTH waits for SDK acceptance plus landing (server 180 s, phone 170 s). STOP ACK means the release request was processed, not completed by hardware.

Remote request_takeoff uses one-use local authorization or an expiring local confirmation. The local Take off (pilot) button requires confirmation, preserves the current connection/anchor and leaves AI disarmed; see docs/PILOT_TAKEOFF.md. STOP also requests cancellation of a pending pilot takeoff. Reconnect/foreground loss must not auto-arm. STOP requests control release and never kills motors or cancels DJI RTH. The RC remains necessary for takeover and RTH cancellation. A failed SDK release blocks re-arm and STOP can retry. Local limits do not bound DJI's own configured RTH path/altitude. No obstacle/terrain planning or force-kill-proof watchdog is implemented.

Keep stale-frame/telemetry and session-generation checks. Avoid enabling concurrent normal commands or loosening safety to accommodate a planner output. Restart the server if launch/home changes or mock/live modes are switched. Preserve connection-aware JPEG callbacks and duplicate-ID handling.

The iPhone is a bridge/controller, not an onboard visual AI model. The selected AI and optional detector run on the server. The native Watch app supplies button/shake help events and GPS; legacy Shortcut input remains. No Apple built-in fall-detection integration exists. Current "found" coordinates indicate the aircraft, not a triangulated person position. No real emergency notification or emergency-service dispatch is implemented.

The backend is unauthenticated and intended for a private demo network or authenticated VPN. Do not use an unauthenticated public tunnel. Keep the bridge app foregrounded; triggering a Shortcut by switching apps on that same iPhone can disarm the bridge, so use a separate incident device or the laptop's demo trigger.


## Current autonomy update

See [the current launch guide and handoff](../docs/AUTONOMY_TEST.md) for the one-use launch permission, 1 m floor, coordinated rebuild/restart steps, diagnostics and tests. Main includes the merged UI. Database expansion remains paused. SDK -1008 still needs hardware evidence.
