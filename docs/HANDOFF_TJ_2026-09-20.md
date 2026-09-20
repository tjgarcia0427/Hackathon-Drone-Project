# Handoff to TJ — Sat night bench results + UI redesign task

_Written by Alfred (Lorenzo's agent) at 12:50 AM ET, Sun 2026-09-20. Read this before touching `main`._

## 1. What happened tonight (hardware bench, props off) — ALL GREEN

Ran on Lorenzo's Mac (Xcode 26.6, Python 3.9 venv), iPhone 14 Pro on the RC‑N1, Mavic Air 2 powered, indoors (no GPS).

| Gate | Result |
|---|---|
| Server + Claude loop (`sim_drone.py`) | ✅ SUBJECT LOCATED, via Claude Code CLI on Lorenzo's Max plan |
| iPhone app builds & installs | ✅ (command line; see §4 — Xcode GUI hits DJI issue #460) |
| DJI SDK registration | ✅ key `3d9d…` / bundle `com.lorenzoventures.guardianangel` |
| Aircraft detected, telemetry | ✅ "Mavic Air 2 • Battery 76%" |
| Phone ↔ server, camera-only armed | ✅ |
| Gimbal command from server → real aircraft | ✅ via `POST /dev/cmd` |
| Live video: phone preview + dashboard frames | ✅ **after four fixes to `DroneBridge.m` (see §2)** |
| Mock-mode full mission through the phone | ✅ goto→gimbal→yaw→move→RTL, honest "no find" (black mock camera) |

Not yet done (needs outdoors + GPS, Sunday morning): manual takeoff → Enable flight → yaw/move/goto over the real link → full mission.

## 2. Changes I made to YOUR code tonight — do not revert

All on `main`, commits `ecc4794`…`4ebcf22`, author Bibby95.

**`iphone-bridge/ios/GuardianAngel/DroneBridge.m`** — video was dead as shipped (feed bytes arrived, decoder never emitted a frame). Fixes, in order of importance:
1. **`DJIVideoPreviewerFrameControlDelegate` implemented** on `DroneBridge` and set as `[DJIVideoPreviewer instance].frameControlHandler`. OcuSync 2 aircraft (Air 2, Mini 2…) embed decoding assist info in the feed; the previewer must hand it back to the SDK via `primaryVideoFeed parseDecodingAssistInfoWithBuffer:…`. **This was the actual fix.** Mirrors DJI's sample `VideoPreviewerAdapter` (that class lives in the sample app, not the DJIWidget pod).
2. `[DJIVideoPreviewer instance].encoderType = H264EncoderType_MavicAir2` + `reset` when the aircraft connects.
3. `enableHardwareDecode = NO`, `type = DJIVideoPreviewerTypeAutoAdapt` (software decode works everywhere; you can try re-enabling HW decode later — verify on device).
4. A 5‑second "Video feed: N bytes" log line in `videoFeed:didUpdateVideoData:` — keep it, it's the fastest bench diagnostic.

**`Info.plist`** — Bluetooth usage string replaced (the build on Lorenzo's Mac showed "LETS HACK THIS DEVICE!!"; repo copy was already sane).

**`server/ai_backends.py`** — Claude Code CLI path was broken: `--input-format stream-json` requires `--output-format stream-json` + `--verbose`; result is now parsed from the final `"type":"result"` event. Verified on a real Max login with an image.

**`server/planner.py` / `app.py`** — search timeout 8 s → 30 s (`AI_SEARCH_TIMEOUT`), frame‑age window follows it. CLI providers take ~8–10 s per decision.

**`server/app.py`** — `POST /dev/cmd` (gated by `DEV_COMMANDS=1`): send one `gimbal|yaw|hold|stop|move` to the bridge without a mission. Props‑off bench tool (gimbal/hold/stop), plus supervised flight-test hops: `{"action":"move","bearing":0,"dist":5}` runs through `safety.check_step` (0–5 m, 35 m geofence, battery floor), needs live telemetry + ground anchor, and the phone still requires local Enable flight. Refuses while a mission is active.

**`server/requirements.txt`** — `eval_type_backport` (your `watch_alerts.py` uses `float | None`; Pydantic can't evaluate that on Python 3.9 without it).

## 3. Your task: iPhone bridge UI redesign

Full spec: **`docs/UI_REDESIGN_SPEC.md`** (Platform 1 section). Government/public‑safety look: navy header, colored status strip, telemetry table, 4‑step pre‑flight procedure card (Start bridge → Connect server → Arm camera only → Enable flight), event log, pinned STOP bar, custom Enable‑flight modal with live gate checks. High fidelity — match colors/type/copy.

**Hard rules**
- **Presentation only.** `DroneBridge.m` flight/safety logic, the protocol, and everything in §2 stay exactly as they are. The one allowed `DroneBridge` change is the spec's suggested refactor: have `updated` emit a struct/`NSDictionary` instead of a formatted string so the VC can fill cells. Keep the string path working too until the new VC is verified.
- **Work on a branch: `ui-redesign`.** `main` is the build that flies Sunday. Lorenzo merges after a mock‑mode regression on his Mac.
- Rebuild `BridgeViewController` in `AppDelegate.m` (or split into its own file) with UIKit + programmatic Auto Layout, no storyboards, no new pods. Add `LogViewController`.
- Fonts: bundling Public Sans/Roboto Mono is optional; SF Pro / SF Mono fallback is fine for the hackathon.
- Don't change the Mock switch default (on) or the "switch locked after Start" behavior.
- The dashboard (Platform 2) is **Alfred's** — don't touch `server/static/index.html`.

**Regression check before you push the branch:** mock mode against the project server: Start → Connect → Camera only → Enable flight (confirm) → dashboard Simulate fall → Dispatch → phone executes goto/gimbal/yaw/move → RTL. Then live: Start → aircraft detected → Connect → Camera only → `curl -X POST localhost:8000/dev/cmd -d '{"action":"gimbal","pitch":-45}'` tilts the camera and video shows on both screens.

## 4. Build/install on the Mac (Xcode GUI fails on `-lDJIWidget` after a clean; use these)

```
cd ~/Hackathon-Drone-Project/iphone-bridge/ios
git pull
xcodebuild -workspace GuardianAngel.xcworkspace -scheme GuardianAngel -configuration Debug -sdk iphoneos -destination 'generic/platform=iOS' -allowProvisioningUpdates build 2>&1 | grep -E "error:|BUILD"
xcrun devicectl device install app --device E9B7300D-1C4A-5DCE-B7A6-ABC9D642C571 ~/Library/Developer/Xcode/DerivedData/GuardianAngel-bwhidvkvwkaafbeazthjeleilxdd/Build/Products/Debug-iphoneos/GuardianAngel.app
```
Then force‑quit and relaunch the app on the phone (a fresh install resets Mock → on and the URL → placeholder). `Config/Secrets.xcconfig` on Lorenzo's Mac already has the real bundle ID + key; never commit it. Scheme fix worth doing: Edit Scheme → Build → uncheck "Parallelize Build" (or add `Pods-GuardianAngel` explicitly) so the GUI build stops racing the pod.

## 5. Gotchas learned tonight
- Only one app may own the RC: if DJI Fly auto‑launches when the cable is plugged, force‑close it or the bridge sees "No aircraft".
- iOS system prompts (accessory, Bluetooth, paste) need a physical tap; Bluetooth → Don't Allow is fine.
- After a server restart the phone must tap Connect again; after Reset on the dashboard the phone disarms (re‑arm Camera only).
- Indoors = "GPS waiting" = no telemetry stream = Dispatch refused. That's by design; use `/dev/cmd` for bench checks.
- Two apps with the same name were installed at one point (old `com.yourteam` bundle). `xcrun devicectl device uninstall app --device <id> com.yourteam.guardianangel` cleared it.

## 6. What I still need from you
Nothing blocking. Nice‑to‑have before the event:
- Confirm you're OK with the four `DroneBridge.m` changes (they're minimal and commented).
- The Watch app you pushed is unbuilt on a Mac; treat it as P1 after the flight test.
- If you re‑enable hardware decode, verify video on the device first.

— Alfred
