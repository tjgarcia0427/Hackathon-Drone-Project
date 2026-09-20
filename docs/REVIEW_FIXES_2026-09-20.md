# Dashboard stats and independent review fixes

Reviewed the supplied September 20 handoff against current `main`, including the team's later supervised `/dev/cmd` move endpoint. The review's baseline (`b07152a`, 57 tests) predates the 5 Hz telemetry fix. The following changes are implemented; branches remain separate.

## Operator-visible changes

- **Aircraft stats at the top of both dashboards:** altitude, latitude, longitude, battery, heading, gimbal pitch, airborne/ground state, GPS readiness, satellites, GPS signal, ground anchor and reading age. Six-decimal coordinates and valid zero altitude are preserved. Stale/missing values show a dash. Simulator clients without the additional DJI fields show a dash for those fields.
- The repeated iPhone `Video feed: ... bytes so far` log is removed at the user's request. Frame delivery, `_videoTime`, decoder input, software decode, encoder selection and the OcuSync assist delegate are preserved.
- On `main`, live video remains live. **Last AI decision** shows a separate, versioned image with its own boxes, timestamp and accepted/rejected status. An old decision image request returns 409 rather than supplying an unrelated newer image. The unmerged UI branch suppresses its unversioned detector overlay and keeps textual detector information until the full multi-person dashboard is reconciled.

## Findings and disposition

| Review finding | Resolution |
|---|---|
| 1. Rejections missing from planner history | Both branches now feed the rejection reason and reassessment instruction back into the next decision. The bounded search loop and flight limits remain. |
| 2. Floating-point bounding boxes fail strict parsing | `main` normalizes finite numeric pixel coordinates before strict validation. Strings, booleans and non-finite values remain invalid. Malformed/provider failures still stop the mission; no automatic retries of failed flight decisions were added. |
| 3. Watch cancellation consumes cooldown | Cancelling before a POST releases both the button and shake cooldown. A normal motion restart and an actual/unconfirmed delivery retain cooldown and retry identity. Includes cancellation surfaced as a cancelled network request. |
| 4. Out-of-frame boxes get clamped | `main` rejects unordered, empty, negative and out-of-frame boxes for found decisions and returns no ground projection for invalid boxes. A valid image size is required before accepting found. |
| 5. Motionless/server-enforced claim | A chosen candidate reported as moving is rejected, as is a chosen candidate score below 0.8. The README now accurately describes prone **or sitting**, reported motion and model-provided scores. These are consistency checks on AI reports, not independent proof of identity or immobility. |
| 6. Stale boxes on fresh video | Separate versioned decision image on `main`; no old AI boxes on the live feed. Late loads and image dimension mismatches cannot draw boxes. |
| 7. Stale test count | Current counts are 74 server tests on `main`, 44 on `ui-redesign`, plus native/JavaScript checks. Historical handoffs retain their original dates/counts. |
| 8. Unvalidated default API model | Removed the scaffold's hard-coded Anthropic model. Both API providers require an explicit model ID. `start_demo.py --provider ...` requires a deliberate provider and checks setup/login before serving. Subscription CLI defaults remain supported. |
| 9. Search smoke image has no people | `main` search smoke test uses the simulator's prone figure plus two upright bystanders, requires candidate output, checks boxes and uses the configured search deadline (default 30 s). Live latency must be remeasured on the demo computer; the old 7.05 s figure is not current evidence. |

Additional fixes found while reproducing the review: a Windows console encoding error could turn a ✓/✗ log message into mission failure; console output now falls back safely while dashboard logs retain their text. The team's new standalone move endpoint now requires fresh navigation and rejects invalid numeric input before command dispatch. Local iPhone flight control remains unchanged.

An in-frame box expressed in the wrong coordinate scale cannot reliably be detected by bounds checking alone. Ground projections still assume the camera calibration, flat ground, correct image coordinates and suitable telemetry. They remain estimates for human review.

## Validation and handoff

- Python regression suites: `python -m unittest discover -s server -p 'test_*.py' -v`.
- The new mission regression uses simulator imagery with two bystanders and mocked AI/command transport: ambiguous found → rejection feedback → yaw → clear three-person result → hold. It does not exercise a live model or aircraft.
- JavaScript tests cover the production dashboard scripts, key stats, stale readings, late evidence loads and separation from live images. Both dashboard themes were inspected in the local browser with simulated telemetry.
- macOS workflows compile the production iPhone apps and Watch app, run navigation/telemetry tests and Watch cooldown tests, and compare the bridge against the bench source, allowing only read-only telemetry changes and the explicitly removed diagnostic lines.
- Still required on the team's Mac: live AI search smoke test using the chosen account/model, signed Watch/iPhone installation, Watch cancel-then-shake test, and the established physical regression. An unsigned CI build against its available SDK does not establish compatibility with the SE's installed watchOS 26.5.

From `server/`, examples (pick your provider; API mode also needs its key in the environment):

```bash
python ai_smoke_test.py --provider claude_code --search-check
python start_demo.py --provider claude_code
# Or:
python ai_smoke_test.py --provider codex --search-check
python start_demo.py --provider codex
```

Use `--model YOUR_MODEL_ID` on both commands when choosing a specific model. For API use, select `openai_api` or `anthropic_api` and supply the model explicitly. Keep credentials outside Git. Restart the server and hard-refresh the dashboard for the new stats/evidence UI. Rebuild the iPhone to remove byte logs; rebuild the Watch app for the cooldown fix.

**Merge handoff:** `ui-redesign` still lacks `main`'s subject-disambiguation models, geometry and multi-candidate evidence endpoint/UI. Reconcile those features and the redesigned markup deliberately after the team's physical regression; do not choose one entire `index.html` and discard the other features. Both branches have the new stats, log removal, Watch cooldown, history feedback and explicit API model setup. This update does not merge branches or change DJI firmware.

### CI results

- Main: [Watch build/core tests and 74 server tests passed](https://github.com/tjgarcia0427/Hackathon-Drone-Project/actions/runs/35522722396); [production iPhone build, navigation/preservation and dashboard checks passed](https://github.com/tjgarcia0427/Hackathon-Drone-Project/actions/runs/35522722399).
- UI branch: [production iPhone build and 14 UIKit scenarios passed](https://github.com/tjgarcia0427/Hackathon-Drone-Project/actions/runs/35522749041); [44 server tests on Python 3.9 and telemetry/dashboard checks passed](https://github.com/tjgarcia0427/Hackathon-Drone-Project/actions/runs/35522748926).
- Native source is unchanged by the final dashboard-only formatting follow-up: DJI's no-GPS enum displays “No signal”, not “6 / 5”. The updated panel and production dashboard JavaScript tests pass locally.

