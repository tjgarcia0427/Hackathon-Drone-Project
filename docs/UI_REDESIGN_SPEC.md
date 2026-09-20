# Handoff: Guardian Angel redesign — iPhone bridge app + operator command center

## Operational corrections approved for the iPhone implementation

See [IPHONE_UI_HANDOFF.md](IPHONE_UI_HANDOFF.md). These corrections override illustrative copy below: camera arming is optional and requires an explicit STOP before separate flight confirmation; read-only structured telemetry is additive to the original string callback; pending/failed control release must be shown explicitly; mock stays labeled in every mode; confirmation checks current complete readiness; STOP remains accessible in the log and modal. Preview labels must not claim recording, resolution or FPS that the bridge does not supply. Unknown telemetry is unavailable, not zero or current.

## Overview
Guardian Angel is a public-safety prototype: a Watch/phone incident trigger sends a location to a Python command center, which plans a supervised drone search and drives a DJI Mavic Air 2 through a locally installed iPhone bridge app. This handoff redesigns both operator surfaces:

1. **iPhone bridge app** (`iphone-bridge/ios/GuardianAngel`, Objective-C UIKit, single `BridgeViewController` in `AppDelegate.m`) — restructured into a guided **pre-flight procedure** (start bridge → connect server → optional camera check → STOP camera control → separately confirm flight) with an always-visible operational status strip, telemetry table, event log, and a persistent STOP control.
2. **Operator command center** (`server/static/index.html`, vanilla HTML/JS served by FastAPI) — restyled in the same institutional language; same panels and controls, new hierarchy.

Direction: **government / public-safety**. Modeled on U.S. government digital standards (USWDS-style palette, Public Sans, bordered tables, square corners, uppercase status labels). Not playful. Color carries operational meaning only.

**No protocol or safety-logic changes.** Everything in `docs/PROTOCOL.md`, `DroneBridge.m` flight limits, `safety.py`, and `app.py` behavior stays as-is. This is a presentation-layer rebuild.

## About the design files
`Guardian Angel Refined.dc.html` (with `ios-frame.jsx`, `support.js`, `_ds/`) is a **design reference built in HTML**. It is a clickable prototype showing intended look and behavior, not code to ship. Recreate it in the target environments:

- iOS: UIKit, programmatic Auto Layout, stock controls (`UIStackView`, `UILabel`, `UIButton`, `UIAlertController`, a pushed/modal `UIViewController` for the log). No storyboards, no new dependencies.
- Web: edit `server/static/index.html` in place — plain HTML/CSS/JS, keep the existing WebSocket `render(s)` contract and element ids so `app.py` needs no changes.

Open the HTML file in a browser to see the prototype. **Use the section labelled turn 2 (`#2a`, `#2b`) at the top.** Turn 1 (`#1a`–`#1c`) is an earlier, rejected direction using a fashion-app design system (Moda); ignore it and do not use the `_ds/` tokens or components.

## Fidelity
**High-fidelity.** Colors, type, spacing, copy, and states are final. Match them. Where UIKit forces a different control appearance (e.g. `UIAlertController`), keep the copy and semantics and accept the platform control.

---

## Platform 1 — iPhone bridge app (`#2a`)

### Screen: Bridge (root view controller)
Single scrolling screen inside a `UINavigationController` with the navigation bar hidden (the custom header replaces it). Layout, top to bottom:

```
[Header — navy]                     fixed, safe-area top
[Status strip — colored by state]    fixed
[Scroll content]                     flexible
   Camera preview 16:9
   Telemetry table (3 × 2)
   Pre-flight procedure card (4 rows + action area)
   Event log card (last 4 entries, tap to open full log)
   Legal/operational footnote
[STOP bar]                           fixed, safe-area bottom
```

Background of the whole screen: `#F0F0F0`. Horizontal margin: 16 pt. Vertical gap between cards: 12 pt. All cards: white `#FFFFFF`, 1 pt border `#DFE1E2`, corner radius 4 pt, **no shadows**.

#### Header
- Background `#162E51`. Padding: safe-area top + 0, 16 pt sides, 12 pt bottom. Contents bottom-aligned in a horizontal row, space-between.
- Left column:
  - Eyebrow: `DRONE BRIDGE · UNIT MA2-01` — Public Sans 600, 11/14, letter-spacing 1, uppercase, color `#A9AEB1`. (Unit ID should come from a constant; placeholder `MA2-01`.)
  - Title: `Guardian Angel` — Public Sans 800, 20/26, letter-spacing −0.2, white.
- Right column (right-aligned, 4 pt gap), Roboto Mono 11/14, color `#DFE1E2`, each row = 8 pt dot + text:
  - `SERVER ONLINE` / `SERVER OFFLINE` — dot `#00A91C` online, `#B50909` offline.
  - `MAVIC AIR 2` (dot `#00A91C`) or `MOCK HARDWARE` (dot `#A9AEB1`) or `NO AIRCRAFT` (dot `#B50909`).

#### Status strip
Full-width band directly under the header. Padding 12 pt 16 pt. Row: 24 pt Phosphor icon, then two text lines.
- Label: Public Sans 800, 15/20, letter-spacing 0.6, uppercase.
- Sub: Public Sans 400, 13/18, 90 % opacity.

| State (from `DroneBridge`) | Background | Text | Icon | Label | Sub |
|---|---|---|---|---|---|
| Not started | `#DFE1E2` | `#1B1B1B` | `power` | NOT STARTED | Start the bridge to begin the procedure. |
| Mock running | `#DFE1E2` | `#1B1B1B` | `flask` | MOCK MODE — NO AIRCRAFT | Simulated hardware. Server link online. Nothing will fly. |
| Live, disarmed | `#565C65` | `#FFFFFF` | `lock` | DISARMED | Aircraft connected. Server has no control. |
| Camera only | `#1A4480` | `#FFFFFF` | `video-camera` | CAMERA ONLY | Gimbal under server control. Flight remains with the pilot. |
| Flight enabled | `#FFBE2E` | `#1B1B1B` | `warning` | AI FLIGHT CONTROL ACTIVE | Server may move the aircraft. Keep the RC ready for takeover. |
| DJI returning (RTH) | `#565C65` | `#FFFFFF` | `house` | APP CONTROL RELEASED — DJI RTH | Return-to-home in progress. Cancel or take over with the RC. |
| Low battery release | `#B50909` | `#FFFFFF` | `battery-warning` | CONTROL RELEASED — BATTERY 24% | Below the 25% floor. Land or return with the RC now. |

Battery percentage in the low-battery label is live. Icons: Phosphor "fill" weight; on iOS use the closest SF Symbols (`power`, `flask`, `lock.fill`, `video.fill`, `exclamationmark.triangle.fill`, `house.fill`, `battery.25`).

#### Camera preview
- 16:9, width = content width, background `#000`, corner radius 4, 1 pt border `#565C65`. This is the `DJIVideoPreviewer` target view (`self.preview`).
- Top overlay bar (gradient black 55 % → 0): left `DJI CAMERA` (or `MOCK — NO CAMERA`), right `PREVIEW`. Do not show recording or FPS without measured source data. Roboto Mono 11/14 white.
- Bottom overlay bar (gradient 0 → black 55 %): left aircraft coordinates `25.7617 N  80.1918 W`, right last-telemetry clock `14:04:22`.

#### Telemetry table
Card with a section header row: `TELEMETRY` — Public Sans 700, 11/14, letter-spacing 1, uppercase, `#565C65`, padding 8 pt 12 pt, 1 pt bottom border `#DFE1E2`.
Grid 3 columns × 2 rows, cells padded 10 pt 12 pt, 1 pt `#DFE1E2` dividers between cells (no outer double borders).
Cell: label Public Sans 400, 10/12, letter-spacing 0.8, uppercase, `#565C65`; value Roboto Mono 500, 17/22, `#1B1B1B`.

Cells in order: Battery (`87%`; value turns `#B50909` when < 30 %), Altitude (`9.8 m`), Heading (`92°`), GPS fix (`OK` / `waiting`), Ground anchor (`OK` / `waiting`), Speed cap (`1.0 m/s`, constant from `Navigation.h`).

Source: parse the fields currently concatenated into the `updated` status string in `DroneBridge.m` line ~350 (`_battery`, `_pose.altitude`, `_pose.heading`, `_gps`, `_homeSet`, `_returning`/`_flightEnabled`/`_armed`). **Read-only addition:** retain `updated(NSString *)` and add `stateUpdated(NSDictionary *)` plus a main-thread `telemetry` getter so the view controller can populate cells and the status strip directly.

#### Pre-flight procedure card
Header row: `PRE-FLIGHT PROCEDURE` left, progress `2 / 4` right in Roboto Mono.
Four rows, each 1 pt `#DFE1E2` bottom border, padding 10 pt 12 pt, 12 pt gap:
- 24 × 24 square checkbox, radius 2, 2 pt border.
- Title Public Sans 700, 15/20; detail Public Sans 400, 12/16, `#565C65`.
- Right tag: Public Sans 700, 10/12, letter-spacing 0.8, uppercase.

| Row state | Box fill | Box border | Glyph | Tag | Tag color | Row bg |
|---|---|---|---|---|---|---|
| Complete | `#1A4480` | `#1A4480` | white check | COMPLETE | `#4D8055` | none |
| In progress | white | `#1A4480` | step number `#1A4480` | IN PROGRESS | `#1A4480` | `#EFF6FB` |
| Locked | white | `#A9AEB1` | step number `#A9AEB1`, title `#71767A` | LOCKED | `#71767A` | none |
| Released | `#B50909` | `#B50909` | white × | RELEASED | `#B50909` | `#FDF2F2` |

Steps and detail copy:
1. **Start bridge** — `Mock hardware · no aircraft` or `DJI registered · Mavic Air 2`
2. **Connect server** — the server origin (`http://192.168.1.100:8000`)
3. **Arm camera only** — `Gimbal and frames to the server`
4. **Enable flight** — `Airborne 5–30 m · within 40 m of anchor`; when control was released: `Released · pilot has control`

Action area under the rows (padding 12 pt), contents depend on the in-progress step:
- Step 1: mock toggle row (`Mock hardware (no drone needed)` + `UISwitch`, on by default) and primary button **Start bridge**.
- Step 2: URL field (`UITextField`, rounded-rect, URL keyboard, no autocorrect, placeholder `http://YOUR-LAPTOP-IP:8000`, persisted in `NSUserDefaults` `serverURL`) and primary button **Connect server**.
- Step 3: primary button **Arm camera only**; helper `Server can tilt the gimbal. Aircraft flight stays with the pilot.`
- Step 4: primary button **Enable flight**; helper `Aircraft airborne at 5–30 m, within 40 m of the anchor. You will confirm first.`
- All complete (flight enabled): row `Server command in progress` with 10 pt amber `#E5A000` dot and mono sub-line showing the current command, e.g. `Executing yaw 30° · cmd-42` (from the `Executing %@ (%@)` note).
- Released (RTH / low battery): step 4 shows RELEASED; button **Enable flight** disabled (`#DFE1E2` fill, `#565C65` text, 60 % opacity); helper `Available once return-to-home ends and the pilot has control.` or `Needs 30% battery to re-enable.`

Primary button: height 48, radius 4, fill `#1A4480`, white Public Sans 700 16. Pressed: `#162E51`. Helper text: Public Sans 400, 12/16, `#565C65`, centered.

#### Event log card
Header row `EVENT LOG` left, `14 entries ↗` right in Roboto Mono; whole header tappable → pushes the **Event log** screen.
Shows the **last 4** entries: Roboto Mono 11.5/16, timestamp `#71767A` then message; 1 pt `#F0F0F0` row dividers; padding 6 pt 12 pt. Messages wrap (no horizontal scrolling).

#### Footnote
Public Sans 400, 11/15, `#565C65`:
> Pilot-operated takeoff required. Use Take off (pilot) inside Guardian Angel, then climb with the RC to 5–30 m before enabling AI flight. Keep this app in the foreground. STOP requests cancellation of a pending pilot takeoff or releases AI flight control; DJI return-to-home and motor control remain with the aircraft and the pilot's RC. No obstacle or terrain avoidance is provided.

#### STOP bar (pinned)
White bar, 1 pt top border `#DFE1E2`, padding 10 pt 16 pt + safe-area bottom.
Button: full width, height 56, radius 4, fill `#B50909`, white, Public Sans 800 15, letter-spacing 0.8, uppercase, leading hand icon (`hand.raised.fill`, 22 pt):
`STOP AI — RETURN CONTROL TO PILOT`. Always enabled once the bridge is started. Calls `stopAutomation:@"Local STOP pressed; pilot control"`. Pressed: `#8B0A03`.

### Screen: Event log (pushed)
- Header identical to the root header (navy) with title `Event log` (Public Sans 800 18) and a right `× Close` action (Public Sans 700 14, white).
- Content: one white bordered card, all log entries, Roboto Mono 12/17, timestamp `#71767A`, 1 pt `#F0F0F0` dividers, padding 8 pt 12 pt. Newest at bottom; auto-scroll to bottom on append. Keep the existing 12 000-char trim from `append:`.

### Dialog: Enable supervised flight
Present as a custom modal (preferred) or `UIAlertController` with the same copy.
- Card: white, radius 4, 8 pt top border `#E5A000`, drop shadow `0 8 24 rgba(0,0,0,.3)`, dimmed backdrop `rgba(27,27,27,.7)`.
- Title row: `warning` icon 24 pt `#E5A000` + `Enable supervised flight?` (Public Sans 800 18/24).
- Body (Public Sans 400 14/20): `The pilot must have the aircraft airborne at 5–30 m in an open area, within 40 m of the recorded launch point. The server can now move it. Keep the RC ready.`
- Gate checks table (bordered, 3 rows, label `#565C65` 13, value Roboto Mono, green check `#4D8055`): `Battery ≥ 30%` → `78%`; `Altitude 5–30 m` → `9.8 m`; `Distance from anchor ≤ 40 m` → `3 m`. Values are live; a failing check shows the value in `#B50909` and an × instead of a check, and disables the confirm button.
- Buttons (44 pt, radius 4, side by side): **Cancel** outlined 2 pt `#565C65`; **Enable flight** filled `#1A4480` white. Confirm → `armFlight:YES`.

### Interactions & state (iOS)
State machine driven by `DroneBridge` callbacks; the view controller derives everything from it:

```
notStarted → (Start bridge) → started{mock|live}
started → (Connect) → connected
connected → (Arm camera only) → cameraOnly            // armFlight:NO
cameraOnly → (Stop camera control) → disarmed          // stopAutomation:
disarmed → (Enable flight → confirm) → flightEnabled  // armFlight:YES
flightEnabled → RTH detected → released(rth)
flightEnabled → battery < 25 % → released(lowBattery)
any → STOP → cameraOnly-or-disarmed per DroneBridge   // stopAutomation:
```
- Reconnect never re-arms (existing rule). After reconnect the procedure shows step 3 in progress again.
- Disable the mock switch and Start button after start (existing behavior); keep `idleTimerDisabled = YES`.
- Motion: none beyond system defaults. Status strip color change: 200 ms cross-fade. No bounces.
- Press feedback: standard `UIButton` highlight (darken fill as listed).

---

## Platform 2 — Operator command center (`#2b`)

Edit `server/static/index.html`. Keep every element `id` used by `render()` (`phase`, `dronedot`, `dronetxt`, `foundBanner`, `cam`, `det`, `incident`, `plan`, `drone`, `log`, `ai-provider`, `ai-model`, `ai-apply`, `ai-status`). Desktop-first at 1280; below 760 px collapse to one column (existing media query).

Page background `#F0F0F0`. Font Public Sans; mono Roboto Mono (Google Fonts, or self-host in `static/`). Body text `#1B1B1B`.

### Header bar
`#162E51`, padding 14 px 28 px, flex row, gap 24.
- Eyebrow `GUARDIAN ANGEL · INCIDENT RESPONSE` (600, 11/14, ls 1, `#A9AEB1`) over title `Command center` (800, 20/26, white).
- Phase chip (`#phase`): padding 6 px 12 px, radius 4, 800 12, ls 0.8, uppercase, icon + text. Colors by phase: idle `#DFE1E2`/`#1B1B1B`; planning `#1A4480`/white; dispatched + searching `#E5A000`/`#1B1B1B`; found `#008817`/white; aborted `#B50909`/white.
- Right cluster (mono 12, `#DFE1E2`): `● BRIDGE MA2-01 CONNECTED` (dot `#00A91C`; `#B50909` + `NO BRIDGE` when disconnected), `● AI <label> · <effective_model>`, and a live clock `14:04:31 EDT`.

### Found banner (`#foundBanner`)
Full-width `#008817` white band under the header, padding 12 px 28 px: person icon, `SUBJECT CANDIDATE LOCATED — HUMAN REVIEW REQUIRED` (800 15, ls 0.6, uppercase), mono detail `6 m from reported fall · confidence 82% · aircraft holding`, right-aligned note `Coordinates are the aircraft's position, not the person's.` Hidden unless `s.found`.

### Body grid
`grid-template-columns: 1.35fr 1fr; gap 16px; padding 16px 28px 28px`.
All panels: white, 1 px `#DFE1E2`, radius 4, no shadow. Panel header: padding 8 px 14 px, 1 px bottom border, 700 11/14, ls 1, uppercase, `#565C65`; optional right-side mono meta.

Left column:
1. **Live camera · Mavic Air 2** — meta `frame 1.2 s ago · 8 fps` (compute from frame message time). 16:9 black `#cam` with 12 px inset; detection overlay drawn from `m.detection.bbox` as a 2 px `#00A91C` rectangle with a `#00A91C` label `PERSON 82%` (mono 11, white); bottom gradient strip with `ALT · HDG · lat/lon` left and frame time right. Under the image: `#det` mono 12 `#565C65`.
2. **Controls** — flex row, gap 10, wrap. `Dispatch drone` filled `#1A4480`; `Abort · return home` filled `#B50909` with hand icon; `Reset` outlined 2 px `#565C65`; right-aligned text button `Simulate fall` `#1A4480` with a `DEV` tag (10, ls 0.8, 1 px `#A9AEB1` border). Buttons 44 px tall, radius 4, 700 15. Disabled: `#A9AEB1` fill, white text, no pointer.
3. **Event log** (`#log`) — rows mono 12.5/18, timestamp `#71767A`, 1 px `#F0F0F0` dividers, padding 7 px 14 px, max-height 340, auto-scroll bottom.

Right column:
1. **Incident** (`#incident`) — meta `#<id> · <source>`; key/value rows (label 13 `#565C65`, value mono 13), 1 px `#F0F0F0` dividers. Keep the `kv()` helper but render rows as `<div class="row"><span>k</span><span>v</span></div>`.
2. **Mission plan · AI → safety layer** (`#plan`) — right-side status: `✓ Approved` in `#4D8055` when `plan_ok`, else `✕ Rejected: <reason>` in `#B50909`. Same kv rows.
3. **Aircraft telemetry** (`#drone`) — 3 × 2 cell grid like the phone: Battery, Altitude, Heading, From home (35 max), Speed, Commands run. Label 10 ls 0.8 uppercase `#565C65`; value mono 500 18/24.
4. **AI provider** — labels 700 12; `select`/`input` 40 px tall, 1 px `#565C65`, radius 2, padding 0 10; model input in mono 13; `Apply` 40 px `#1A4480` (disabled `#A9AEB1`). `#ai-status` below in 12/16 `#565C65`. Keep existing lock behavior text: `Locked while a mission is active. Reset and finish planning to change. API keys remain in the server environment.`

Remove the 🚁 emoji from the title. No emoji anywhere.

---

## Design tokens (both platforms)

Colors
- Navy header `#162E51` · Primary action `#1A4480` (pressed `#162E51`)
- Ink `#1B1B1B` · Secondary text `#565C65` · Muted `#71767A` · Disabled `#A9AEB1`
- Border `#DFE1E2` · Row divider `#F0F0F0` · Page bg `#F0F0F0` · Card `#FFFFFF`
- Stop / error `#B50909` (pressed `#8B0A03`) · Error accent `#D83933` · Error tint `#FDF2F2`
- Caution (AI control active) `#FFBE2E` · Caution dark `#E5A000`
- OK / connected `#00A91C` · Approved text `#4D8055` · Found banner `#008817`
- Info tint (in-progress row) `#EFF6FB`

Type
- Public Sans (400/600/700/800) for all UI text; Roboto Mono (400/500) for every number, timestamp, coordinate, command id, URL.
- Sizes used: 10/12, 11/14, 11.5/16, 12/16, 13/18, 14/20, 15/20, 16, 17/22, 18/24, 20/26.
- Uppercase labels always carry letter-spacing 0.6–1.0.
- iOS: if bundling fonts is not possible for the hackathon, fall back to SF Pro (same weights) and SF Mono; keep sizes.

Spacing: 4-pt base. Screen margin 16. Card gap 12 (iOS) / 16 (web). Cell padding 10 × 12. Header padding 8 × 12 (iOS) / 8 × 14 (web).
Radius: cards/buttons 4 · checkboxes/inputs 2. No pill shapes. No shadows except the modal.

Icons: Phosphor (web, `ph-fill` weight) — `flask`, `video-camera`, `warning`, `house`, `battery-warning`, `hand-palm`, `person-simple`, `radar`, `check`, `x`, `arrow-up-right`, `caret-down`, `check-circle`. iOS: SF Symbols equivalents listed above.

## Copy rules
Sentence case for buttons and body. Uppercase only for status labels, section headers, tags, and header telemetry. No exclamation marks, no emoji. Safety copy is verbatim from the current app and README; do not soften it.

## Files in this bundle
- `Guardian Angel Refined.dc.html` — the prototype. Open in a browser; use turn 2 (`#2a` app, `#2b` dashboard). The chips above the phone switch the five states; the procedure flow is clickable (Arm camera → Enable flight → confirm).
- `ios-frame.jsx`, `support.js`, `_ds/` — runtime needed for the HTML to render. `_ds/` belongs to the rejected turn-1 direction; do not lift anything from it.
- `GuardianAngel Bridge.dc.html` — faithful render of the **current** shipped screen, for before/after reference.

## Suggested split for agents
- **iOS agent** (TJ): rebuild `BridgeViewController` per Platform 1; add read-only structured telemetry while preserving `DroneBridge.updated`; add `LogViewController`; keep all `DroneBridge` calls and safety behavior unchanged. Verify in mock mode against `tools/smoke_server.py` before hardware.
- **Server agent**: restyle `server/static/index.html` per Platform 2 without touching `app.py`; run `python sim_drone.py` to exercise phases idle → planning → dispatched → searching → found → aborted and confirm every `render()` path still populates.
