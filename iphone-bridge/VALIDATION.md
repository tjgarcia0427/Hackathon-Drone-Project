# Validation record

Prepared on Windows, September 19, 2026, for the Mavic Air 2 / iPhone bridge.

## Passed locally

- Compiled `Navigation.c` with a C compiler (Zig's Clang frontend) using `-Wall -Wextra -Werror` and executed `navigation_test.c`.
- Navigation assertions cover north/east/west directions, heading and longitude wrap, finite values, altitude/radius bounds, capped horizontal and vertical velocities, vertical adjustment before translation, and convergence from 12 bearings.
- Ten Python server-support tests passed: flattened command envelope and pending-ack cleanup, timeout stop, negative-ack stop, reset cancellation order, abort/RTH order, fresh-frame waiting and stale telemetry rejection, incompatible/duplicate patch refusal, preservation of changed teammate code, mission cancellation on disconnect, and rejection of old frames after reset.
- Three FastAPI tests passed: mock WebSocket command/ack round trip and raw frame transfer, rejection of live hardware, rejection of a second drone connection without disconnecting the first.
- All three Objective-C implementation files parsed without syntax-error nodes using tree-sitter-objc. **This is syntax validation, not Apple/SDK compilation or type checking.**
- The Xcode project parsed as an OpenStep property list; source entries and object references were checked. The shared scheme and Info.plist parsed successfully.
- The server patch applied in memory to the retrieved scaffold at `15359dc` and the result parsed as Python. The generated unified diff is included. The same integration is included in the coordinated repository update; the patch script is retained for older checkouts only.
- DJI class/method names, velocity coordinate mapping, delegate signatures, gimbal rotation constructor, and snapshot API were checked against the official iOS 4.16.2 headers and DJIWidget source.

Python transport tests used Python 3.12, FastAPI 0.141.1, Starlette 1.6.0, and HTTPX 0.28.1. The test client emitted a deprecation warning for HTTPX; all thirteen tests completed successfully. No AI service calls or physical flight commands were sent in these tests.

The coordinated repository update additionally passed six `server/test_safety.py` cases for the 35 m server fence, full search-area bounds, 5 m moves, altitude/angle limits, battery/step limits and invalid numeric inputs. These exercise the actual safety functions with numeric test objects; they do not validate the Anthropic API or Pydantic schema. At the original iPhone integration milestone, `server/app.py` matched the migration exercised by the package tests, with **19 Python tests passed** across the package and coordinated update. The subsequent AI-provider changes below extend the current server beyond that migration snapshot.

## AI provider update — September 19, 2026

- **23 current server tests passed**: six navigation/safety tests, twelve AI adapter tests and five configuration/lifecycle tests. API tests use the actual OpenAI 2.54.0 and Anthropic 0.125.0 Python SDKs with mocked HTTP; they do not establish live API access. CLI fixtures launch real subprocesses to test image/schema handling, login checks, timeout cleanup and Windows executable resolution.
- A real Codex CLI signed in with ChatGPT identified a synthetic red-circle image in **5.67 s**. The dashboard applied the provider and produced a valid incident plan. No aircraft was connected.
- The CLI's default model timed out on the full search prompt/schema at 8 s; the late decision was rejected. Selecting `gpt-5.6-luna` passed the full search check in **7.05 s** with a valid yaw decision and no person detected. This single synthetic check has a small timing margin and does not prove field performance.
- Provider changes are blocked during active work. Tests verify reset invalidates a pending plan and search timeout requests stop without applying a late movement decision.
- Claude subscription and both API options still require live checks with the team's accounts. No iPhone source changes were needed for provider selection.
- Updated setup is in `docs/AI_PROVIDERS.md` in the repository and `AI_PROVIDERS.md` in the refreshed standalone iPhone package. Use current repository `server/` files for these features; the old scaffold migration is not a provider installer.

## Additional review fixes

- Snapshot timeouts recover from interrupted video; delayed JPEG callbacks are tied to the original server connection. Mock JPEGs use an explicit 1x scale.
- Old aircraft/component references are cleared during connection changes, and delegates bind when components arrive later.
- A failed SDK control release blocks re-arming until a subsequent release succeeds.
- RTH completion requires SDK acceptance plus landing telemetry. Mock RTH continues independently after app STOP, matching the documented behavior of DJI-managed return.
- The server patch verifies the original source syntax tree before replacing functions. Tests exercise the actual patched function definitions from a saved scaffold fixture.
- Mac setup verifies full Xcode and the iPhoneOS SDK, rather than accepting Command Line Tools alone.

## Still required on your teammate's Mac and aircraft

- CocoaPods dependency resolution and an actual Xcode compile/link.
- Correct DJI app registration key, matching bundle ID, Apple signing, Developer Mode and installation.
- Compatibility with the actual iPhone/iOS, Xcode, aircraft firmware and controller firmware.
- Aircraft connection/delegate delivery, decoded video, and camera frame uploads.
- Gimbal completion and physical flight-axis verification in a controlled test.
- Flight convergence, RC takeover, RTH/landing behavior, link-loss and iOS lifecycle behavior on real hardware.
- End-to-end operation with your real planner, Watch/Shortcut trigger, and fall/person-detection scenario.

The mock mode shares navigation math with the real bridge but does not simulate GPS noise, aircraft inertia, terrain, obstacles, radio delay, or DJI failsafes. Its results do not validate physical flight performance. No `.ipa` or signed binary is included because the Apple build/signing steps require a Mac.

