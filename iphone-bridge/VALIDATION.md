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

The coordinated repository update additionally passed six `server/test_safety.py` cases for the 35 m server fence, full search-area bounds, 5 m moves, altitude/angle limits, battery/step limits and invalid numeric inputs. These exercise the actual safety functions with numeric test objects; they do not validate the Anthropic API or Pydantic schema. The uploaded `server/app.py` syntax tree matches the migration exercised by the package tests. Total Python tests across the package and coordinated server update: **19 passed**.

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
