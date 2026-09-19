# Hackathon Drone Project — AI fall-response drone

**Claude Code Build Day · Miami · Sun 2026-09-20 · Breakthrough track**

A wearable reports a fall → the command center asks Claude to plan a search mission → a safety
layer approves it → the drone (DJI Mavic Air 2) flies to the location → Claude drives the camera
search (yaw / gimbal / move) until the person is found → dashboard shows **SUBJECT LOCATED**.

The breakthrough: **Claude Fable 5.1 is the search brain**, deciding each move from the live camera
frame, while deterministic code keeps it inside hard safety limits.

```
⌚/📱 iOS Shortcut ──POST /incident──▶ 🖥 server/app.py ──WS──▶ 📱 Android app (MSDK v4) ──▶ 🚁 Air 2
                                       │  planner.py (Claude)        ◀── telemetry + JPEG frames ──┘
                                       │  safety.py  (limits)
                                       │  detector.py (YOLO, optional)
                                       └─▶ dashboard  http://localhost:8000
```

## Repo layout

| path | what | owner |
|---|---|---|
| `server/app.py` | FastAPI command center: incident intake, dispatch, search loop, dashboard WS | Lorenzo |
| `server/planner.py` | Claude calls: `plan_mission()` and `next_search_step()` (structured outputs) | Lorenzo |
| `server/safety.py` | Hard limits (altitude, geofence, battery, step cap). Claude proposes, this approves | Lorenzo |
| `server/detector.py` | Optional local YOLOv8n person detector | either |
| `server/sim_drone.py` | Fake drone speaking the real protocol — run the whole demo with no aircraft | — |
| `server/static/index.html` | Dashboard | Lorenzo |
| `docs/PROTOCOL.md` | The WebSocket/HTTP contract the Android app must implement | both |
| `android/` | DJI MSDK v4 app (fork of `dji-sdk/Mobile-SDK-Android` sample) | TJ |

## Run it (no drone needed)

```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...          # from console.anthropic.com (event credits attach to an Org)

uvicorn app:app --host 0.0.0.0 --port 8000   # terminal 1
python sim_drone.py                          # terminal 2
```

Open http://localhost:8000 → **Simulate fall (dev)** → **Dispatch drone**. Watch Claude search.

Real trigger from an iPhone/Apple Watch (no app build needed): Shortcuts → new shortcut →
*Get Current Location* → *Get Contents of URL* (POST, JSON: `latitude`, `longitude`, `accuracy`
from the location, `source: "watch"`) to `http://<laptop-ip>:8000/incident`. Add it to the watch face.

Env knobs: `CLAUDE_MODEL` (default `claude-fable-5-1`), `AUTO_DISPATCH=1` to skip the operator button.

## Tonight (Sat) checklist

- [ ] DJI developer account → create app → App Key (instant) — https://developer.dji.com
- [ ] Anthropic Console **Organization** exists (credits attach to the Org, not claude.ai)
- [ ] **Android phone** (8–13) + USB cable for the RC-N1. MSDK v4 is Android-first; iOS v4 is abandoned
- [ ] Clone `dji-sdk/Mobile-SDK-Android` (**v4**, not V5), drop the App Key in, build, confirm the Air 2 registers
- [ ] `server/` runs against `sim_drone.py` end to end with your API key
- [ ] Check DJI GEO zones for the venue — Air 2 may refuse takeoff near MIA / Class B. Plan to demo on the
      MSDK simulator (DJI Assistant 2, aircraft on USB) + outdoor clip if needed

## Tomorrow build order (6 h)

1. **0:00–0:30** — both: server + sim running on the venue Wi‑Fi; Shortcut fires a real incident
2. **0:30–3:30** — TJ: Android agent → WS connect, telemetry, `gimbal`, `yaw`, `hold`, `rtl`, frame POST.
   `goto`/`move` last (virtual stick). Lorenzo: tune prompts/safety with the sim, dashboard polish, YOLO if cheap
3. **3:30–4:30** — integrate on the MSDK simulator; run the full loop 3× clean
4. **4:30–5:15** — outdoor run if airspace/wx allow, or record the simulator run
5. **5:15–6:00** — demo script, fallback video, 2‑minute pitch

## Demo script (2 min)

1. Watch face → tap **Fall** → dashboard flashes FALL DETECTED with GPS
2. Claude's mission plan appears → safety layer stamps APPROVED (show one rejected plan for effect)
3. **Dispatch** → drone climbs and flies to the point
4. Search loop log: Claude's observation per step, yaw sweep, gimbal down, one move
5. **SUBJECT LOCATED — 11.4 m from report · 94 %** → drone holds
6. Close: "Claude isn't chatting. It's flying the search. The old model couldn't hold this loop."

## Safety / legal (for the pitch, and for real)

- Human pilot on the sticks with VLOS at all times; the RC overrides the app instantly
- Part 107 / recreational rules apply; no flight over people; respect GEO zones
- Claude never issues raw motor commands — `safety.py` validates every step against fixed limits
