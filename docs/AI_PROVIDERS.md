# Choose ChatGPT, Claude, or API billing

The command center supports four AI providers. Choose one in the dashboard's **AI provider** panel while idle, then click **Apply**. That choice controls both incident planning and camera-based search decisions. The iPhone remains the DJI bridge; these changes run on the Windows laptop or Mac hosting the Python server.

| Dashboard option | `AI_PROVIDER` | Authentication on the server computer | Usage |
|---|---|---|---|
| ChatGPT subscription · Codex CLI | `codex` | Official Codex CLI, signed in with ChatGPT | Your account's Codex allowance |
| Claude subscription · Claude Code CLI | `claude_code` | Official Claude Code CLI, signed in with Claude | Your account's eligible Claude Code allowance |
| OpenAI API · API billing | `openai_api` | `OPENAI_API_KEY` environment variable | OpenAI API billing |
| Anthropic API · API billing | `anthropic_api` | `ANTHROPIC_API_KEY` environment variable | Anthropic API billing |

The subscription options invoke the official, unmodified CLI using the operator's saved login. They do not add a third-party OAuth login to the iPhone, extract tokens, or call private chat endpoints. The login must belong to the OS user running the server. Signing into a phone app or another teammate's laptop is not sufficient. Internet access and the selected plan's model access are still required. No automatic switch from subscription to API billing is implemented.

## First ChatGPT test

Install a current [official Codex CLI](https://developers.openai.com/codex/cli/). Run these commands in the same account/terminal environment that will host the server:

```text
codex login
codex login status
```

Choose ChatGPT login and complete the official browser sign-in yourself. The status must say it is using ChatGPT. The bridge rejects a saved API-key login when you select subscription mode.

Then, from the repository's `server` directory with its Python environment activated:

```text
python -m pip install -r requirements.txt
python ai_smoke_test.py --provider codex --check-only
python ai_smoke_test.py --provider codex
```

The second command checks installation/login without inference. The third creates a synthetic red-circle image and sends it through the selected AI. It should return `ok: true`, identify a red circle with no person, and report elapsed time. It never connects to or commands a drone.

Before testing a search mission, check the actual search prompt/schema and its 8-second deadline:

```text
python ai_smoke_test.py --provider codex --model gpt-5.6-luna --search-check
```

This model passed that check on the development laptop. Use it only if available to your account; repeat the check on the machine and network that will run the demo. The synthetic scene contains no person, so a `found` decision fails the check. No returned action is sent anywhere.

Start the command center on Windows PowerShell:

```powershell
$env:AI_PROVIDER = 'codex'
$env:AI_MODEL = 'gpt-5.6-luna'
$env:AUTO_DISPATCH = '0'
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Or on macOS:

```bash
export AI_PROVIDER=codex
export AI_MODEL=gpt-5.6-luna
export AUTO_DISPATCH=0
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`. Confirm the selected provider, click **Simulate fall (dev)** and check that a plan appears. With no drone attached this only tests planning and the dashboard. Follow the root README and iPhone guide for separate simulator, mock-phone and hardware milestones.

## Claude subscription

Install the current [official Claude Code CLI](https://code.claude.com/docs/en/setup), then run:

```text
claude auth login
claude auth status
python ai_smoke_test.py --provider claude_code --check-only
python ai_smoke_test.py --provider claude_code
python ai_smoke_test.py --provider claude_code --search-check
```

Use the Claude subscription login, without `--console`. The bridge checks for `loggedIn: true` and `authMethod: "claude.ai"`. Set `AI_PROVIDER=claude_code` before launch or select Claude in the idle dashboard. This uses non-interactive `claude -p` with image input and structured output. A current version supporting `--safe-mode`, `--json-schema` and `auth status` is required; update the CLI if it reports an unsupported flag. Safe mode skips user customizations while retaining the normal login; do not replace it with `--bare`, which uses different authentication behavior.

As checked September 19, 2026, Anthropic's [subscription guidance for programmatic Claude Code](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan) says the previously announced June 15 change is paused and this usage continues to draw from plan limits. Account eligibility and provider policy can change. Use the official CLI with your own account; do not collect or forward a teammate's OAuth tokens.

## API options

Set the relevant key **only on the server**, choose a model available to that API account that supports images and structured output, and restart the server. A ChatGPT/Claude subscription login does not provide API credits.

Windows examples, choose one:

```powershell
# OpenAI API
$env:AI_PROVIDER = 'openai_api'
$env:OPENAI_API_KEY = 'your-key'
$env:AI_MODEL = 'your-available-image-and-structured-output-model'
python ai_smoke_test.py

# Or Anthropic API
$env:AI_PROVIDER = 'anthropic_api'
$env:ANTHROPIC_API_KEY = 'your-key'
$env:AI_MODEL = 'your-available-image-and-structured-output-model'
python ai_smoke_test.py
```

On macOS use `export NAME='value'` instead of PowerShell's `$env:NAME = 'value'`. Do not commit keys, put them in the iPhone app, or enter them into the dashboard. The configuration endpoint deliberately rejects credential fields. After a successful smoke test, launch Uvicorn as above. API clients are loaded only when used, so subscription mode can start without any API keys.

## Model settings and switching

- `AI_PROVIDER` defaults to `anthropic_api` for older checkouts' launch scripts. Set it explicitly for subscription use.
- `AI_MODEL` selects the initial model for the chosen provider. Otherwise provider-specific defaults are `CODEX_MODEL`, `CLAUDE_CODE_MODEL`, `OPENAI_MODEL`, or the existing `CLAUDE_MODEL`.
- Blank model for either subscription option uses the CLI's normal default. Codex ignores user project/tool configuration for these calls and uses low reasoning effort. For explicit model selection, use a model your account can access.
- OpenAI API requires a model ID. Anthropic retains the original scaffold's `claude-fable-5-1` fallback for compatibility, but that fallback has not been validated; enter an available model explicitly.
- **Apply** changes the running server's provider/model in memory. Restarting restores environment settings. Reset the mission and wait for in-flight planning/commands to finish before changing providers. Failed configuration leaves the old provider selected.
- “Configuration detected” checks local prerequisites, not remote account/model access. Run the smoke test to verify live inference.
- If an executable is not found, fix `PATH` or set `CODEX_BIN` / `CLAUDE_BIN` to its full native executable path. Official npm wrappers are resolved without invoking a shell; older `.js` entries need Node.js on `PATH`.

## Timing and flight behavior

Incident planning has a 60-second deadline. Each visual search decision has an **8-second deadline**, preserving the existing 10-second maximum frame age. CLI startup, login checking, model latency and network time all count. The smoke test reports `within_search_deadline` as a rough readiness signal; a simple test image cannot guarantee a full mission meets that deadline. Test the chosen model and venue network before flight. If it is too slow, select a faster available model/provider; do not loosen frame-age checks to accept old observations.

Failures, refusal, malformed decisions and timeout produce no AI movement decision. A running mission fails and requests release of app control; the pilot remains responsible for takeover. Reset/abort invalidates a late incident plan. AI returns typed decisions only: it is not given shell access or flight-control tools, and existing server/iPhone limits still validate every action. Subscription subprocesses run in temporary working folders, with tools/customizations disabled, and are terminated on timeout. A cancelled worker can finish in the background, but its result cannot issue commands.

## Validation and handoff

September 19, 2026: the real Codex CLI, signed in with ChatGPT, identified the synthetic red circle and produced valid structured output in **5.67 seconds**. The dashboard was checked in a browser, including provider application and incident planning. The CLI's default model exceeded the 8-second deadline on the full search test and its decision was rejected. Selecting **`gpt-5.6-luna` passed the full search check in 7.05 seconds**, returning a valid yaw decision and correctly reporting no person. That leaves a small timing margin: this is local integration evidence, not aircraft validation or a latency guarantee.

Automated tests exercise both actual Python SDKs with mocked HTTP responses, both CLI protocols with subprocess fixtures, subscription-login checks, timeout cleanup, provider switching, late-plan cancellation and navigation bounds. Run from `server/`:

```text
python -m unittest discover -s . -p "test_*.py" -v
```

Claude subscription and both API providers still need live tests with the team's accounts. Xcode compilation and physical phone/drone testing remain outstanding. See [AGENT_HANDOFF.md](AGENT_HANDOFF.md) for teammate context.

Implementation references: [Codex non-interactive execution](https://developers.openai.com/codex/noninteractive), [Codex authentication](https://developers.openai.com/codex/auth), [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Claude Code programmatic usage](https://code.claude.com/docs/en/headless), [Claude CLI flags](https://code.claude.com/docs/en/cli-reference).
