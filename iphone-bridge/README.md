# Guardian Angel — local iPhone drone bridge

This package contains the native iPhone source, an Xcode project, a mock test server, and a patch for your existing Python command center. Your teammate builds it on his Mac and installs it directly onto the iPhone that will connect to the drone controller. **No App Store upload is required.**

**Status:** prototype source, with navigation and server-support tests run on Windows. It has **not** been compiled in Xcode or tested on an iPhone/Mavic Air 2. The first hardware milestone is successful build → DJI registration → aircraft telemetry → video → gimbal movement. Do not treat the included flight controller as flight-validated.

## Who runs what

| Device | Role |
|---|---|
| Teammate's Mac | Install dependencies, sign/build the app with Xcode, install on iPhone |
| iPhone beside the drone | Run this app, connected by a data cable to the RC-N1 controller |
| DJI controller + Mavic Air 2 | Pilot supervision and aircraft connection |
| Your Windows laptop | Existing Python server, dashboard and AI planner |
| Apple Watch | Native button/shake app sends help and wearer GPS; see [Watch setup](../docs/WATCH_SETUP.md) |

You can develop remotely. **The controller-connected iPhone must physically be with the drone pilot.** A Mac or Watch by itself cannot replace it. If your only iPhone is with you elsewhere, your friend needs to borrow another compatible iPhone for the drone side.

The app uses DJI Mobile SDK **V4 iOS 4.16.2**, DJIWidget **1.6.8**, and iOS **15+** as its deployment target. This is an older SDK; compatibility with your exact Xcode, iOS and aircraft firmware still needs to be proved. The project uses Objective-C to match DJI's documented APIs directly. No firmware modification is involved.

## Mac setup — send your teammate this package

1. Install/open **full Xcode** and select its Command Line Tools under Xcode Settings → Locations. Sign into his Apple Account under Xcode Settings → Accounts.
2. Have Ruby and Bundler available. In Terminal, change to the extracted `ios` folder and run:

   ```bash
   bash setup-mac.sh
   ```

   This runs Bundler and CocoaPods and opens **GuardianAngel.xcworkspace**. Open the workspace for subsequent builds, not the `.xcodeproj`. Dependencies are downloaded on the Mac; vendor binaries and credentials are not included in this zip. If his existing Ruby cannot install CocoaPods, use a current Ruby installation rather than changing Apple's system Ruby.
3. Edit **ios/Config/Secrets.xcconfig**, created by the script. Choose a unique bundle identifier, for example `com.yourteam.guardianangel`. Register a **Mobile SDK iOS app** in the [DJI developer console](https://developer.dji.com/user/apps/) with the **same bundle identifier**, and enter its app key as `DJI_APP_KEY`. Do not use a cloud/API-service key. Keep this file out of Git.
4. In Xcode, select the **GuardianAngel target → Signing & Capabilities → Team**. Select his Personal Team or developer team; keep automatic signing enabled. Confirm the bundle identifier exactly matches the DJI app registration.
5. Connect the **physical iPhone** to the Mac, trust the computer, and select the iPhone as the run destination. Enable [Developer Mode](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device) when prompted. Press **Run**. The iOS Simulator is not a supported target for this package, even for mock mode.
6. Allow local-network access. After confirming installation, stop Xcode's debug session, unplug the iPhone from the Mac, and open the installed app from its home-screen icon. Connect it to the RC-N1 data port when testing hardware.

Apple supports local device testing using a [Personal Team](https://developer.apple.com/support/compare-memberships/); its provisioning profiles expire after seven days, so the app then needs rebuilding/reinstalling. A paid account is not required just to start local testing. Signing and SDK compatibility remain device-side checks.

Optional build log command, after setup and signing configuration:

```bash
xcodebuild -workspace GuardianAngel.xcworkspace -scheme GuardianAngel \
  -configuration Debug -destination 'generic/platform=iOS' \
  CODE_SIGNING_ALLOWED=NO build > build.log 2>&1
```

This checks compilation/linking only. Installing and running still requires signing. If a dependency, signing, linking or SDK-registration step fails, send the **first error and surrounding lines**, plus Xcode/iOS versions. Do not send the app key or signing credentials.

## First test: mock hardware, no AI costs

Mock hardware skips DJI registration, so this first test does **not** need a DJI app key. Xcode signing, a unique bundle ID, CocoaPods dependencies and a physical iPhone are still required. Add the matching DJI key before switching mock hardware off.

On your Windows laptop or his Mac:

```bash
cd tools
python -m pip install -r requirements.txt
python -m uvicorn smoke_server:app --host 0.0.0.0 --port 8000
```

Use a network where the laptop and iPhone can reach each other. In the iPhone app:

1. Leave **Mock hardware** switched on and tap **Start bridge**.
2. Enter `http://YOUR-LAPTOP-IP:8000`, then **Connect server**. `localhost` on the iPhone means the iPhone itself.
3. Tap **Enable flight**. Mock mode starts at latitude `25.7617`, longitude `-80.1918`, altitude `10 m`. These are simulated values.
4. Open `http://YOUR-LAPTOP-IP:8000/docs` on the laptop. Expand **POST /command**, click **Try it out**, and send these one at a time:

   ```json
   {"action":"gimbal","pitch":-60}
   ```

   ```json
   {"action":"yaw","deg":30}
   ```

   ```json
   {"action":"move","bearing":90,"dist":5}
   ```

   ```json
   {"action":"hold"}
   ```

5. Each response should return `ok: true` after completion. **GET /state** should show updated heading/location and a nonzero JPEG byte count. **GET /frame.jpg** shows an explicitly labelled mock image; it cannot demonstrate person detection.
6. Tap **STOP AI**, then repeat `move`: expect a negative acknowledgment. Stop the test server: expect the app to disarm after losing its connection. Reconnecting never enables flight automatically.

The smoke server rejects live-hardware connections. It has no `/incident` or AI mission planner. Stop it before running your existing project server on the same port.

## Connect to the existing hackathon server

The app lives in `iphone-bridge/` in the project repository. The repository's `server/app.py` already includes the reviewed iPhone integration. After cloning current `main`, **do not apply the patch again**. Read the root README, `docs/PROTOCOL.md`, and `docs/AGENT_HANDOFF.md` for the coordinated setup.

For an older checkout at scaffold commit `15359dc` only, the included patch adds the integration to `server/app.py`. From this package's root, first preview it:

```bash
python server-support/patch_server.py /path/to/Hackathon-Drone-Project/server/app.py
```

After reviewing the diff, run the same command with `--apply`. On Windows, use a quoted Windows path instead. It backs up the original as `app.py.before-iphone` and checks a fingerprint of the original server's Python syntax tree before making any edits. Comment-only changes are allowed; changed executable code or docstrings require manually merging the patch to preserve teammate work. Duplicate patching is refused. The ready-to-review diff is also in `server-support/iphone-integration.patch`.

The integrated server changes add:

- 180-second server RTH completion timeout, with failure reported honestly.
- Mission cancellation awaited before reset/abort; reset and command failures request local control release.
- A five-second command delivery expiry; phone/server clocks should be synchronized.
- Fresh telemetry and a new camera frame after each action before consulting the planner.
- A 10-second maximum age for the frame underlying a planner decision.
- One drone connection at a time, prompt pending-command failure on disconnect, and the app's recorded ground anchor for home.
- Mission cancellation on disconnect and frame-generation checks that discard images still processing across reset/reconnection.
- Dispatch rejection for targets beyond 35 m or altitude outside 1–30 m.

Keep **AUTO_DISPATCH=0** for the demo. The repository planner guidance now requests altitude around 10 m, a 5–10 m demo search radius, and relative moves of at most 5 m. Server safety uses a 35 m radius; the target plus planned search radius must fit inside it. Keep the demo incident within about 20 m of launch. The search radius may not cover the incident's full GPS uncertainty; this limitation must remain visible to the operator. The app deliberately rejects plans outside its local limits; it does not silently change them. Stop `sim_drone.py` when the iPhone is connected. Restart the server when changing launch locations or switching between mock and real aircraft so its home reference is not reused.

Choose ChatGPT subscription via Codex CLI, Claude subscription via Claude Code CLI, OpenAI API, or Anthropic API on the **server computer**. Follow [the AI setup guide](https://github.com/tjgarcia0427/Hackathon-Drone-Project/blob/main/docs/AI_PROVIDERS.md); the current repository is the source of truth if you received an older standalone iPhone zip. Login/keys and AI inference stay on the server; the iPhone does not need a ChatGPT/Claude login or app update for this selection. Run the existing server as its README describes, listening on the laptop's reachable interface. Use the same base URL in this app; it automatically uses `/ws/drone` and `/frame`.

For remote teammates, use a private authenticated VPN or run the server beside the pilot and access that machine through your existing secure connection. **This repository's server has no authentication. Do not publish it through an open internet tunnel:** anyone who can reach it can submit incidents/commands and images. For a shared venue network, use your own private network. The development app permits local HTTP traffic; public deployment would require TLS and server-side authentication.

## Redesigned UI on `ui-redesign`

See [UI handoff and regression](../docs/IPHONE_UI_HANDOFF.md). Camera-only control is optional. After arming it, tap **Stop camera control**, then **Enable flight** and confirm separately. STOP never automatically enables flight. The original flight checks and working video pipeline are preserved. The initial UI correction passed an unsigned production iPhone build in macOS CI; physical video/control regression is still required before merging.

## Hardware sequence

1. Initially remove propellers. Close DJI Fly, turn **Mock hardware off before Start bridge**, and connect aircraft, controller and iPhone. The first DJI registration requires internet access.
2. Verify registration, correct aircraft model, battery updates, and live preview. Tap **Arm camera only** and test a gimbal command through your server. The full existing mission begins with `goto`, so it will correctly fail while camera-only control is enabled; use a targeted gimbal test for this milestone.
3. For flight testing, the pilot configures/checks normal aircraft failsafes and RTH height in DJI Fly beforehand, then closes DJI Fly. Start the bridge on the ground in an open outdoor area and wait for **GPS OK / Ground anchor OK**. Keep the app open and connected.
4. Press **STOP AI** if camera-only mode is armed. Tap **Take off (pilot)** and confirm locally. Stay in Guardian Angel: the server connection, video and ground anchor remain intact through the approximately 1.2 m DJI takeoff. Wait for the hover confirmation, then enable flight when within **1–30 m above takeoff** near launch. Takeoff does not enable AI control. See [pilot takeoff](../docs/PILOT_TAKEOFF.md) for launch gates, interruptions and testing. Controller takeoff remains an alternative.
5. Tap **STOP AI** if camera-only mode was previously enabled, then **Enable flight** locally. Confirm the on-screen state. Test a small yaw, hold, then a short move with a clear flight path before attempting a server mission.
6. Test local STOP and loss of server connection. Confirm the pilot can take over using the RC. Then try a supervised incident → dispatch → camera search demonstration.

The app's GPS velocity controller does not plan around obstacles or terrain. A 40 m coordinate fence is not collision avoidance. Keep the demo path clear and the pilot present; do not aim the aircraft at a fallen person. This is an observation prototype, not an operational emergency-response system.

## What the app implements

| Capability | Behavior |
|---|---|
| Telemetry | Navigation plus independent altitude/heading/battery observations; about 5 Hz. See [telemetry fix](../docs/TELEMETRY_FIX.md) |
| Pilot takeoff | Local button + confirmation; DJI takeoff to about 1.2 m; server/anchor retained; agent request supported with one-use pilot authorization or local confirmation |
| Camera | DJIWidget preview; next-rendered-frame snapshots, JPEG downscaling, about 1 upload/sec without an upload queue |
| `gimbal` | Absolute pitch −90° to 0°, completion checked against gimbal telemetry |
| `yaw` | Relative rotation −180° to 180°, capped at 10°/sec, telemetry-based completion |
| `goto` | GPS target `lat`, `lng`, relative altitude `alt`; bounded local velocity control |
| `move` | Absolute compass `bearing` and relative distance `dist`, at most 5 m per command |
| `hold` | Zero virtual-stick commands until measured velocity settles; keeps flight enabled |
| `rtl` | Releases virtual stick, invokes DJI return-to-home, waits for landing before positive acknowledgment |
| `stop` | Requests cancellation of a pending pilot takeoff, releases AI flight control, disarms the app; acknowledgment means control-release request processed |
| Local limits | 40 m from ground anchor, 1–30 m altitude, 1 m/sec horizontal, 0.5 m/sec vertical |
| Interlocks | 30% battery to enable/new navigation; release below 25%, stale GPS/telemetry, link loss, inactive app, or loop delay |
| Duplicate commands | Last 256 completed IDs are cached for the app session; active duplicates are not re-executed |

Normal movement acknowledgments wait for telemetry convergence and one second of settling. SDK command acceptance is not treated as arrival. RTH may still require the pilot to confirm landing; timeout produces a negative acknowledgment. **STOP does not cancel DJI's own RTH/landing and never stops motors.** Use the physical controller to cancel RTH. If RTH was cancelled manually while airborne, restart/re-establish the bridge on the ground before another automated flight session.

The app's 40 m / 1–30 m limits apply to its virtual-stick navigation. DJI-managed RTH uses the aircraft's configured home point and RTH altitude, which can extend outside those limits; the pilot must check those settings before launch.

There is one active command and a 10 Hz local control loop. The app attempts to zero velocity and relinquish virtual stick when interrupted. An iOS process cannot guarantee a watchdog after force-kill, OS suspension or cable failure; the aircraft/controller's own failsafes and pilot takeover remain necessary. A short already-sent gimbal rotation can finish after STOP.

If the SDK reports that control release failed, the app blocks re-arming. Use physical RC takeover and press STOP again to retry the release. Video snapshots have a timeout and connection identifier so a delayed frame cannot be sent to a newly connected server. Upload failures appear in the app log.

The separate [native Watch app](../watch-app/README.md) now sends button/shake help alerts and wearer GPS. It does not subscribe to Apple's built-in fall-detection event. The iPhone bridge and server-side AI remain separate components. The current server's “found” coordinates are the **aircraft's coordinates**, not an estimated ground location of a person; treat detection as a visual candidate for human review.

## Tests and file map

Run the portable tests from the package root:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
cc -Wall -Wextra -Werror tests/navigation_test.c ios/GuardianAngel/Navigation.c -lm -o /tmp/ga-navigation-test
/tmp/ga-navigation-test
```

The three optional FastAPI transport tests require `python -m pip install -r tools/requirements.txt httpx`; otherwise they are skipped. Ten server-support tests use only Python's standard library.

- `ios/GuardianAngel/DroneBridge.m`: aircraft delegates, command validation, local flight loop, frames, mock hardware.
- `ios/GuardianAngel/BridgeClient.m`: text WebSocket JSON, heartbeat, frame uploads.
- `ios/GuardianAngel/Navigation.c`: bounded navigation math used by both real and mock control.
- `ios/GuardianAngel/AppDelegate.m`: native interface and local control buttons.
- `server-support/patch_server.py`: preview/apply integration script.
- `tools/smoke_server.py`: mock-only manual transport tests through FastAPI `/docs`.
- `VALIDATION.md`: what was verified and what still needs hardware.

API references: [DJI iOS SDK source/sample](https://github.com/dji-sdk/Mobile-SDK-iOS), [DJIWidget](https://github.com/dji-sdk/DJIWidget), [DJI flight controller API](https://developer.dji.com/api-reference/ios-api/Components/FlightController/DJIFlightController.html). Dependency licenses remain applicable; see `THIRD-PARTY-NOTICES.md`.


## Current autonomy update

See [the current launch guide and handoff](../docs/AUTONOMY_TEST.md) for the one-use launch permission, 1 m floor, coordinated rebuild/restart steps, diagnostics and tests. Main includes the merged UI. Database expansion remains paused. SDK -1008 still needs hardware evidence.
