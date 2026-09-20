# OpenClaw integration on main

The matching iPhone takeoff-confirmation request flow is included on this UI branch. The complete server, plugin, workspace templates and setup guide are on **main**:

[OpenClaw setup, architecture, first test and teammate handoff](https://github.com/tjgarcia0427/Hackathon-Drone-Project/blob/main/docs/OPENCLAW_INTEGRATION.md)

Use the server from current main with this phone build. Do not replace main's newer server with the UI branch's server. The redesigned UI remains separate until the team's Mac/iPhone regression review.

Validation for UI implementation `0cb65eca78a92b4d3b8b0016b4afb1f4539d94e0`: [real DJI iPhone build and all 18 simulator UI scenarios passed](https://github.com/tjgarcia0427/Hackathon-Drone-Project/actions/runs/35527896755). [Native request, telemetry, navigation and server checks passed](https://github.com/tjgarcia0427/Hackathon-Drone-Project/actions/runs/35527896746). Runtime testing with the team's OpenClaw Gateway and physical hardware remains.
