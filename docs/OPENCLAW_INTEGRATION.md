# Guardian Angel + OpenClaw

This adds a dedicated mission agent, a native OpenClaw tool plugin, durable mission notes, and an authenticated agent API. The iPhone remains the DJI flight controller. No firmware changes or Android device are involved.

Use current main for the merged phone UI, server and plugin. Follow [AUTONOMY_TEST.md](AUTONOMY_TEST.md) for the coordinated update and first launch test.

## What the agent receives and sends

```mermaid
sequenceDiagram
    participant O as OpenClaw mission agent
    participant S as Guardian Angel server
    participant I as iPhone / DJI SDK
    participant P as Pilot
    I->>S: Telemetry ~5 Hz, JPEG snapshots ~1 Hz
    O->>S: guardian_begin(objective, mode, target or Watch event)
    S-->>O: Mission ID + mission memory (lease kept inside plugin)
    O->>S: guardian_observe()
    S-->>O: Actual JPEG + observation ID + timestamps + telemetry + control gates
    O->>S: guardian_request_takeoff(observation ID)
    S->>I: request_takeoff command
    alt Live one-use pilot authorization
        I->>I: Consume authorization and prepare takeoff
    else No prior authorization
        I->>P: Confirm within 20 seconds?
        P->>I: Take off
    end
    I-->>S: Ack after telemetry confirms hover
    S-->>O: Completed, declined, expired or failed
    I->>I: If preauthorized, attempt flight enable after stable hover
    O->>S: Observe again; require flight_enabled
    O->>S: Observe, then one bounded movement/camera tool
    S->>I: Validated command
    I-->>S: Ack after actual completion
    O->>S: Observe again; save search notes or candidate evidence
```

OpenClaw uses its configured model and authentication. It sends the JPEG image block to that model as part of the tool result, alongside the objective and recent mission events. It does **not** watch a laptop screen, call the dashboard through a browser, or receive every video frame. The model must support images and tool calls. The dashboard's existing ChatGPT/Claude/API selector controls the **built-in planner**, not the OpenClaw agent.

The phone uploads a snapshot about once per second; the server receives navigation/display data about five times per second when available. OpenClaw gets one image when it calls `guardian_observe`. A usual loop is observe → reason → one action → wait for completion → observe. Model latency determines the reasoning cadence. DJI movement runs independently in the phone's existing 10 Hz deterministic loop, not at model speed.

## First setup on the teammate's Mac

1. Pull `main`, rebuild/install the iPhone app in Xcode, and restart the server. Old phone builds do not advertise the new takeoff-request/control capability; the agent will refuse control. Keep Guardian Angel foreground, USB-connected to the RC231/RC-N1. Its server connection and ground anchor are retained during launch; an actual aircraft disconnect still invalidates the anchor.

2. Generate **one random shared token** with `python3 -c 'import secrets; print(secrets.token_hex(32))'`. Keep it outside Git. This token authenticates the drone tools; it is not a model API key. In the terminal that starts Guardian Angel:

   ```bash
   cd /path/to/Hackathon-Drone-Project/server
   source .venv/bin/activate
   export GA_AGENT_TOKEN='paste-the-random-token-here'
   export GA_AGENT_MAX_MODE=observe
   export GA_MISSION_DRIVER=openclaw
   export AUTO_DISPATCH=0
   python -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1
   ```

   Use the project's existing virtual environment/install requirements. On PowerShell, set variables with `$env:GA_AGENT_TOKEN = '...'`, etc. A single server worker is required because aircraft ownership and command acknowledgements are in memory. Missing/short token disables all `/agent/*` endpoints. The default maximum mode is `observe`, even if an agent asks for flight.

3. On the computer running the **OpenClaw Gateway**, put the same `GA_AGENT_TOKEN=...` in its private `~/.openclaw/.env` (or its service process environment). Restart the Gateway after changing its environment. Setting a variable in an unrelated terminal will not update an already-running Gateway service. Do not put this token into agent prompts or workspace memory.

4. Install the local plugin using your existing OpenClaw installation:

   ```bash
   cd /path/to/Hackathon-Drone-Project
   openclaw --version
   openclaw plugins install --link ./integrations/openclaw
   openclaw plugins enable guardian-angel
   openclaw agents add guardian-angel --workspace /absolute/path/to/guardian-angel-workspace
   ```

   This package uses the current native `definePluginEntry` / `registerTool` interface, optional tools, a manifest, and runtime conversation IDs. OpenClaw's plugin SDK is experimental: use a version supporting those interfaces and check runtime registration below. The package declares the documented SDK baseline; that declaration is not a claim every later host release has been tested.

5. Copy the files from `integrations/openclaw/workspace/` into the **new** Guardian Angel workspace. Preserve your other agents' workspaces. Choose an image-capable model/auth profile for this agent through your usual OpenClaw setup; reuse the provider configuration you already have. No extra provider key belongs in this repo.

6. Merge these plugin settings into OpenClaw's existing config, preserving other entries:

   ```json
   {
     "plugins": {
       "entries": {
         "guardian-angel": {
           "enabled": true,
           "config": {
             "serverUrl": "http://127.0.0.1:8000",
             "tokenEnv": "GA_AGENT_TOKEN",
             "agentId": "guardian-angel"
           }
         }
       }
     }
   }
   ```

   Add `guardian-angel` to that agent's **tool allowlist**. These tools are optional and hidden unless allowed. The plugin also checks the runtime agent ID and conversation ID; another agent gets no drone tools. Give this dedicated agent only the Guardian Angel tools for the flight test; it does not need browser, desktop or shell access. Newer hosts use `agents.entries`; some older hosts use `agents.list`. Edit the existing agent entry for your installed version rather than copying an incompatible full config. Verify in OpenClaw's agent tools view.

   If Gateway and server run on different laptops, `serverUrl` is the server laptop's private LAN/VPN address, such as `http://192.168.1.20:8000`. It is always resolved from the **Gateway**, not from the chat browser. Allow that port on the private network. The phone must independently reach the server too. Do not expose this prototype publicly: the new agent API uses a bearer token, but the existing dashboard, video and aircraft endpoints retain their trusted-LAN design. Use a private VPN/HTTPS when crossing networks.

7. Restart and verify:

   ```bash
   openclaw gateway restart
   openclaw plugins inspect guardian-angel --runtime --json
   ```

   Confirm all 14 `guardian_*` tools register. In the Guardian Angel agent conversation, ask for `guardian_status`. A 401 means mismatched token; 503 means the server token is absent/too short; unavailable tools mean plugin/allowlist/agent-context setup needs fixing.

## First test: observation, then camera, then supervised flight

Start with the iPhone's existing **Mock hardware** mode or connected real hardware with props off and server `GA_AGENT_MAX_MODE=observe`:

> Start an observe-only mission: describe the current camera image and report altitude, GPS and their freshness. Do not move the drone. Use guardian_observe and tell me whether this is a real camera image or the mock test card. Save one brief mission note, then guardian_stop.

The result should contain an image, observation ID and telemetry. The agent must report missing/stale data instead of guessing. The mock phone starts airborne at 10 m for existing network tests, so it cannot test takeoff; native request tests cover that flow without an aircraft. The legacy Python `sim_drone.py` does not advertise the new control capability and is not the agent-control test harness.

For a props-off gimbal test, restart the server with `GA_AGENT_MAX_MODE=camera`; tap **Enable camera** on the phone. Start a camera mission, observe, request gimbal pitch -45°, wait for completion, and observe again. `guardian_stop` releases camera control. Camera mode cannot yaw, move or request takeoff.

For the supervised outdoor trial, restart with `GA_AGENT_MAX_MODE=flight`. Start from a grounded, disarmed phone with strong GPS, ground anchor OK and battery ≥30%. Start a flight mission and call `guardian_request_takeoff` after observing. With one-use phone authorization, the request launches and attempts flight enable after stable hover. Otherwise the pilot must answer within 20 seconds and enable flight afterward. Obtain a new observation, request a 1 m move in a clear direction, check the result, then stop. Takeoff completion confirms hover only; require fresh flight-enabled status before movement.

GPS task example (substitute measured coordinates within the local fence):

> Start a supervised flight mission to latitude LAT, longitude LNG at 10 m. Request takeoff once using the pilot's current phone authorization. Once fresh status confirms flight enabled, navigate to the mission coordinates, inspect the scene for a person wearing a blue shirt, save possible candidates for review, hold, and report back. Stop on any error or missing fresh observation.

For a search without a GPS target, omit the coordinates; the agent can inspect, adjust gimbal, yaw and make bounded moves. `guardian_navigate` is unavailable until a mission has a pinned target. It cannot substitute a coordinate inferred from image text.

## Watch alerts

With `GA_MISSION_DRIVER=openclaw`, valid real Watch alerts become `awaiting_agent` and appear in `guardian_status` / observations. No built-in planning or automatic dispatch is run. Test-mode alerts remain tests. The operator starts the agent task and supplies the alert's `event_id`; `guardian_begin` then pins navigation to that alert's measured location, ignoring any conflicting proposed coordinates. Locations expire after 120 seconds for dispatch/navigation.

This version is **operator-started**: a Watch alert is an inbox item, not an automatic OpenClaw wake-up or automatic launch. Ask the agent to inspect the latest actionable Watch alert and begin with its event ID. Built-in Simulate fall/Dispatch are rejected while the OpenClaw driver is selected. This prevents two planning loops from competing. To return to the original dashboard workflow, stop the agent and restart with `GA_MISSION_DRIVER=builtin`.

## Tools, memory and limits

| Tool | Purpose |
|---|---|
| `guardian_status` | Connection, control gates, recent Watch alerts; no control lease renewal |
| `guardian_begin` | Objective, mode, optional measured target/Watch event; exclusive mission |
| `guardian_observe` | JPEG image block, observation ID, fresh telemetry, control state and recent memory |
| `guardian_request_takeoff` | One-use authorization or pilot confirmation → DJI launch → confirmed hover; observe flight-enable status |
| `guardian_navigate` | Existing mission GPS target and altitude, validated against fresh phone anchor |
| `guardian_move`, `guardian_yaw`, `guardian_gimbal` | Bounded movement/relative yaw/camera pitch |
| `guardian_hold`, `guardian_return_home` | Settled hold or DJI RTH; RTH completion means landing acknowledgement |
| `guardian_report_candidate` | Save exact JPEG, bounding box, confidence and description for human review |
| `guardian_remember`, `guardian_memory` | Write current mission notes; read historical mission notes |
| `guardian_stop` | End agent ownership, cancel launch requests and release app control |

The tool wrapper keeps the bearer token and mission lease outside the model's context. Action IDs prevent a retried HTTP request from repeating movement; one action runs at a time. The tool waits/polls for the actual command acknowledgement, renewing ownership only while that call is running. It does not retry an uncertain physical command.

Leases expire after **90 seconds** without an owning operation. Missions have a **10 minute** limit and **12** takeoff/navigation/movement/camera actions. Hold/RTH/candidate records do not consume that movement budget; the total action-record cap is 50. Expiry, reset, aircraft disconnect or cancelled action releases control and requires a new supervised mission. Restarting OpenClaw/server never restores authority from memory. STOP does not stop motors or cancel DJI's own RTH.

Observations expire after **30 seconds**, and images must be received within **3 seconds** when observed. An action invalidates all earlier observations; the next image must arrive after completion. Visual move/yaw requires that image, fresh current navigation, and no significant pose change (2 m position, 1 m altitude, 5° heading, 3° gimbal). GPS navigation uses the pinned objective and current telemetry. The server restricts agent flight to **35 m** from the **fresh phone anchor**, altitude **1–30 m**, battery ≥30%, and moves ≤5 m; the phone independently enforces its existing control limits. This provides no obstacle/terrain avoidance.

Mission memory is stored under `server/data/agent/` (Git-ignored), or `GA_AGENT_MEMORY_DIR`: UUID-named JSON journals, compact agent notes, and JPEGs for reported candidates. Each observation includes the last 16 mission events; full archived memory is available by mission ID. OpenClaw also retains its normal conversation context. No hidden autonomous memory service is created. Old coordinates are history, never current telemetry. Candidate confidence is a model assessment, not a verified identity, fall diagnosis, or exact person's GPS location. Candidate JPEG evidence is saved on disk and its metadata appears in the agent result; the dashboard logs the report but does not draw new agent candidate overlays.

## Validation and handoff

Run `python -m unittest discover -s server -p 'test_*.py' -v` from the repo root and `node --test integrations/openclaw/test/*.test.mjs`. macOS CI also runs the production takeoff-request methods with SDK/UI seams, the native takeoff/navigation suites and the real DJI iPhone build. Main includes simulator scenarios for authorization/revocation and fallback prompt dismissal without launching.

The local plugin tests exercise registration contracts, image results, session isolation, cancellation and HTTP polling without a live OpenClaw installation. Runtime plugin inspection plus a real image/model call on the team's installed Gateway, signed iPhone installation and supervised hardware checks remain required. No real aircraft commands were issued while developing this integration.

Implementation: `server/agent_api.py`, small ownership/control-status hooks in `server/app.py`, `integrations/openclaw/`, and marked agent takeoff additions in `DroneBridge.m` / `AppDelegate.m`. The existing OcuSync decoding assistance, encoder setup, software decoder and navigation loop are preserved by the repository's comparison check. Ground-anchor caching across an actual aircraft disconnect is not added.

Primary OpenClaw references checked September 20, 2026: [building tools](https://docs.openclaw.ai/plugins/building-plugins), [plugin manifest](https://docs.openclaw.ai/plugins/manifest), [agent workspaces](https://docs.openclaw.ai/concepts/multi-agent), [Gateway environment](https://docs.openclaw.ai/help/environment). These SDK/config surfaces can change; runtime inspection is part of setup.

### Recorded build results — September 20, 2026

Implementation commits: main `69d983707f9fbb9dbdbeb6f14c4bb708f93dbc2c`; matching UI branch `0cb65eca78a92b4d3b8b0016b4afb1f4539d94e0`.

- **95 server tests pass**, including 21 new agent API/lifecycle tests; **8 OpenClaw plugin tests pass**.
- [Main native checks and real DJI iPhone build passed](https://github.com/tjgarcia0427/Hackathon-Drone-Project/actions/runs/35527894867).
- [Main server and Watch checks passed](https://github.com/tjgarcia0427/Hackathon-Drone-Project/actions/runs/35527894876).
- [UI branch native/server checks passed](https://github.com/tjgarcia0427/Hackathon-Drone-Project/actions/runs/35527896746).
- [UI branch real DJI build and all 18 UIKit simulator scenarios passed](https://github.com/tjgarcia0427/Hackathon-Drone-Project/actions/runs/35527896755), including the agent pilot prompt/dismissal scenario.

Both branches execute the production takeoff-request methods in the native test harness: no automatic launch, approval, decline, expired/late approval, duplicate IDs, readiness revalidation, interruption and SDK rejection. Flight/video preservation checks also pass. These results do not substitute for the team's installed OpenClaw runtime, signed iPhone or real-aircraft validation described above.
