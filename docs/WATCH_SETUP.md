# Apple Watch help button and shake alerts

The native Watch app lives in `watch-app/`. The team's device is **Apple Watch SE (2nd generation), watchOS 26.5**. Source deployment target is watchOS 9+, but your Xcode must support the actual installed watchOS version. The app installs locally through Xcode; no App Store release, DJI SDK, HealthKit entitlement or AI login is needed on the Watch.

This is a deliberate help gesture, **not Apple's built-in Fall Detection** and not a classifier that proves somebody fell. It alerts the team's dashboard, not emergency services. Shake monitoring runs only while the app is active and visible, and turns off when it leaves the foreground. There is no always-on background monitoring.

## What happens

```mermaid
sequenceDiagram
    participant W as Watch wearer
    participant S as Python server
    participant D as Dashboard operator
    participant I as Pilot iPhone + RC + drone
    W->>W: Send Help or three deliberate shakes
    W->>W: Haptic + 5-second cancel countdown
    W->>S: Read server session, then send UUID + time + GPS
    S-->>W: Receipt immediately (AI planning is asynchronous)
    S-->>D: Help/test alert, coordinates, accuracy, status
    alt Test mode / poor GPS / already busy
        S-->>D: Alert only; no new mission
    else Live alert with usable location and idle server
        S->>S: AI proposes search; fixed Watch destination + safety checks
        D->>S: Review and dispatch
        S->>I: Existing bounded navigation/search commands
    end
```

The Watch reports a **single location fix**, not a moving destination. The server pins the plan to that fix even if the AI returns different target coordinates. The iPhone uses the existing DJI control loop to navigate at the plan's altitude, relative to the aircraft's launch reference; Watch altitude is not used. The pilot must already have taken off and enabled flight locally. This adds no automatic takeoff, landing on the wearer or obstacle avoidance.

## 1. Start the project server

Use the real command center in `server/`, not the separate iPhone mock smoke server. On the Mac:

```bash
cd server
source .venv/bin/activate  # create/install from requirements.txt first if necessary
export AUTO_DISPATCH=0
# Retain your working AI_PROVIDER / AI_MODEL and CLI login for later live planning.
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Run **one server process/worker**; alert IDs, mission state and server session are in memory. Do not use multiple workers or `--reload` for the demo. Restarting changes the session and invalidates retries from that session.

Open `http://localhost:8000` on the Mac. The new **Watch help alerts** panel sits above the camera. Click **Enable alert sound** once if you want a brief browser chirp for new alerts. The browser must stay open; this is not SMS, push notification or a background emergency notification.

For the Watch, find the Mac's address under macOS System Settings → Wi-Fi → Details → TCP/IP, for example `192.168.1.50`. Use `http://192.168.1.50:8000`, **not localhost**. Put the Watch and Mac on a network that permits device-to-device connections. Watch networking may route through its paired iPhone; that device also needs a route to the server. A cellular connection alone cannot reach a private Mac LAN address. Guest/event Wi-Fi often isolates clients, so verify with Test connection; use a suitable private Wi-Fi network if needed. Allow incoming Python connections in the Mac firewall if prompted.

The backend has no authentication. Keep it on a private demo network. The app allows cleartext HTTP only for private IPv4 addresses or `.local` hostnames; HTTPS origins are also accepted. Its development ATS exception permits LAN HTTP. Do not expose this server through a public tunnel.

## 2. Build and install on the Watch

Pull current `main` first, preserving any local teammate edits. From the repository root:

```bash
cd watch-app
bash setup-mac.sh
```

1. Use full Xcode with watchOS support and support for **watchOS 26.5**. The setup script checks that a watchOS SDK is selected and opens `GuardianWatch.xcodeproj`. No CocoaPods or XcodeGen is needed for this Watch project.
2. Edit the newly copied `Config/Local.xcconfig`. Set a unique `PRODUCT_BUNDLE_IDENTIFIER` and your Apple `DEVELOPMENT_TEAM`. This file is ignored by Git. Do not change the DJI iPhone app's existing identifier/key.
3. Add the Apple account in Xcode Settings → Accounts and keep automatic signing enabled for the `GuardianWatch` target. Resolve any signing prompts in Xcode.
4. Pair the SE to its normal iPhone, connect/trust that iPhone on the Mac if Xcode needs it, and choose the **physical Apple Watch** as the run destination. Use Xcode's Devices and Simulators window to complete pairing. Enable Developer Mode on the required devices when prompted. The Watch is not plugged into the drone controller.
5. Select scheme **GuardianWatch**, press Run, and open Guardian Angel on the Watch. If Xcode says the OS is unsupported or device support is unavailable, update Xcode/platform components before debugging app code.
6. Open **Server settings**, enter the Mac's URL, tap **Test connection**, then **Enable location** and allow location access. SE does not have a full on-watch keyboard; use Scribble/dictation or the paired iPhone's text-input prompt and verify every character. Return to the main app screen.

The Watch app is separate from `iphone-bridge/`. Install the iPhone bridge using its own README only when testing the aircraft. Its iPhone remains attached to RC-N1 and foregrounded during flight. The Mac is used for development/server operation, not as a replacement for that bridge.

## 3. First test: no drone or AI required

1. Leave **Test mode ON** (it defaults on at each app launch).
2. Keep the Watch app visible and tap **Send Test Help**. It vibrates and counts down five seconds. Cancel during that period to prove that no alert appears on the dashboard.
3. Wait for the 30-second trigger cooldown, then send again without cancelling. After the countdown, connection and GPS acquisition can take several seconds. The Watch should show **Received — Test alert received; no mission created**.
4. Confirm a blue **TEST** card on the dashboard. No AI planning or drone command is created, even if somebody configured server auto-dispatch. A test can succeed without GPS; the card then says no usable location was supplied.
5. After cooldown, enable **Shake to alert** and make three deliberate wrist movements within two seconds. Three distinct acceleration peaks are required, with relaxation between them. Confirm a new TEST card labelled **Shake gesture**. Try button/cancel first rather than calibrating motion with live flight enabled.
6. Leave and reopen the Watch app: shake should be off. Enable it again for each active demonstration.

To check the backend/dashboard before the Watch is installed, run this in another terminal:

```bash
cd server
python watch_smoke_test.py --server http://127.0.0.1:8000
python watch_smoke_test.py --server http://127.0.0.1:8000 --source watch_shake
```

The script has no live mode. It sends a test event and repeats the same ID to verify deduplication. Its location is intentionally absent; this does not validate Watch GPS, haptics or motion.

## 4. Live GPS planning and supervised navigation

First finish the iPhone bench/flight checks in `iphone-bridge/README.md`. Keep `AUTO_DISPATCH=0` for this sequence.

1. Restart the server when moving the launch site or switching simulation/live hardware. Stop `sim_drone.py` before connecting the actual iPhone. Confirm fresh drone telemetry, camera and ground home anchor.
2. Position the wearer in the clear demo area, roughly 10–20 m from launch. The full target plus search radius must fit within the server's **35 m** fence; the phone independently enforces 40 m. GPS error and obstacles still matter.
3. Outdoors, get a useful location and ensure Watch/Mac clocks are automatic. Turn Test mode off and accept the Watch's live-alert confirmation. Send Help; remain at the reported location.
4. Dashboard should show **HELP → planning → planned**, coordinates, accuracy and the AI plan. The initial Watch receipt means **received**, not that a drone is en route. Tap **Refresh alert status** for an updated server status.
5. Review the reported coordinates against the wearer's actual nearby position. GPS must have reported accuracy ≤20 m and be no more than 15 seconds old at receipt. If unavailable/stale/inaccurate, the help alert still appears, but no mission is generated. Fix GPS and send a fresh alert after cooldown.
6. With an approved plan, a manually airborne aircraft, local flight enable, current telemetry, sufficient battery and a clear path, the operator clicks **Dispatch drone**. Dispatch must occur within **120 seconds of server receipt**; otherwise reset and send a fresh location. Battery and the entire search area are checked again at dispatch.
7. Observe the aircraft approaching the fixed location at the selected altitude, then the existing camera search loop. Use local STOP AI, RC takeover or dashboard Abort/RTL as described in the bridge guide. A visual "found" remains a human-reviewed candidate; its coordinates are the aircraft's coordinates.

A second live alert while a mission is planned/planning/running/found/aborted is displayed with status **busy**. It never replaces or queues another mission. Handle it on the dashboard, reset when appropriate, then ask for a fresh alert. Reset does not itself land the aircraft.

## Cancellation, retries and failure states

- **Before sending:** Cancel or leaving the active app cancels countdown/GPS work. Permission prompts can interrupt this flow; enable location from Settings before the test. Nothing is posted until GPS lookup completes or fails and the payload is persisted.
- **After sending starts:** the server may already have received the alert. There is no Watch-side mission-abort button. Use the dashboard/physical pilot controls to stop an active mission.
- **Delivery unconfirmed:** the Watch saves the original payload and UUID before posting. Retry delivery sends that exact payload, with the same server session. A saved LIVE retry remains live even after relaunch into Test mode; the app labels it and asks for confirmation before retrying. Do not assume a timeout means the server never received it.
- **Server restarted / alert too old:** do not transform an old retry into a new mission. Check the dashboard, discard the local retry and explicitly send a fresh alert. Discarding a local retry does not cancel anything already received.
- **Received with `location_rejected`, `busy` or `test_received`:** the event reached the operator, but created no mission. **`rejected`** means the resulting plan failed safety checks; **`failed`** means planning/mission work failed. Correct the cause, reset as needed, and send a new event. Replaying the same ID returns the original record/status; it never creates a replacement mission.
- IDs are retained for 15 minutes with a cap of 256 records. Capacity returns 429 instead of evicting live IDs. Only eight recent alerts appear in the dashboard; specific retained receipts remain accessible by ID. Server restart clears records and changes its session ID.

## Verification and remaining device work

Run server tests with `python -m unittest discover -s server -p 'test_*.py' -v` from repo root. On Mac run `bash watch-app/test-core-mac.sh` for gesture/cooldown, location policy, URL validation and pending-payload serialization. `.github/workflows/watch-checks.yml` also runs those checks and compiles the Watch app for the simulator without signing, when GitHub Actions is enabled and the connector permits publishing workflow files.

A simulator compile is not signed installation or physical validation. Verify on this SE: permissions, receipt over the venue network, outdoor GPS accuracy, deliberate motion thresholds (1.5 g trigger, 0.45 g reset, three peaks ≥0.25 s apart in two seconds), haptics, cancellation, app backgrounding and lost-response retry. Tune motion only after observing test-mode behavior on the real Watch. No physical Watch/aircraft test can be performed from the Windows development environment.

Implementation reference: [Apple Core Motion](https://developer.apple.com/documentation/coremotion/cmmotionmanager), [one-shot Core Location](https://developer.apple.com/documentation/corelocation/cllocationmanager/requestlocation()), [Watch networking](https://developer.apple.com/documentation/technotes/tn3135-low-level-networking-on-watchos), [single-target Watch apps](https://developer.apple.com/documentation/watchos-apps/migrating-to-a-single-target-watchos-app). Apple's dedicated [fall-detection manager](https://developer.apple.com/documentation/coremotion/cmfalldetectionmanager) is a separate entitlement-gated capability and is not used here.
