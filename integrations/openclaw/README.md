# Guardian Angel OpenClaw plugin

Follow [the setup, first test, architecture and handoff](../../docs/OPENCLAW_INTEGRATION.md).

Install locally with `openclaw plugins install --link ./integrations/openclaw`
from the repository root. This package is private and is not published to npm.
No npm dependencies are needed beyond the existing compatible OpenClaw host.

The plugin registers 14 optional tools only for the configured agent ID (default
`guardian-angel`) with a runtime conversation ID. Enable them in that agent's tool
allowlist. It uses `GA_AGENT_TOKEN` from the Gateway process environment.

Tests: `node --test integrations/openclaw/test/*.test.mjs` from the repository root.
These are offline contract/transport tests; follow the guide's runtime inspection
and observation test on your installed Gateway before permitting movement.
