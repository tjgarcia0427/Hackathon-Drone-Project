"""Selectable API or official, locally signed-in CLI inference. No drone tools.

The caller validates the returned decision and controls the aircraft separately.
Credentials remain in environment variables / the official CLI credential store.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
from typing import Any

from pydantic import BaseModel

PROVIDERS = {
    "codex": "ChatGPT subscription · Codex CLI",
    "claude_code": "Claude subscription · Claude Code CLI",
    "openai_api": "OpenAI API · API billing",
    "anthropic_api": "Anthropic API · API billing",
}


class AIError(RuntimeError):
    pass


def default_model(provider: str) -> str:
    key, fallback = {
        "codex": ("CODEX_MODEL", ""),
        "claude_code": ("CLAUDE_CODE_MODEL", ""),
        "openai_api": ("OPENAI_MODEL", ""),
        "anthropic_api": ("CLAUDE_MODEL", "claude-fable-5-1"),
    }[provider]
    return os.environ.get(key, fallback).strip()


@dataclass(frozen=True)
class Settings:
    provider: str
    model: str = ""

    def __post_init__(self):
        if self.provider not in PROVIDERS:
            raise AIError("AI_PROVIDER must be codex, claude_code, openai_api, or anthropic_api")
        if len(self.model) > 120 or any(ord(c) < 32 for c in self.model):
            raise AIError("Invalid model name")

    @property
    def effective_model(self) -> str:
        return self.model or default_model(self.provider)

    def public(self) -> dict:
        return {"provider": self.provider, "label": PROVIDERS[self.provider],
                "model": self.model, "effective_model": self.effective_model or "CLI default",
                "billing": "subscription" if self.provider in ("codex", "claude_code") else "api"}


def from_environment() -> Settings:
    return Settings(os.environ.get("AI_PROVIDER", "anthropic_api").strip(),
                    os.environ.get("AI_MODEL", "").strip())


def options() -> list[dict]:
    return [{"provider": k, "label": v, "default_model": default_model(k)} for k, v in PROVIDERS.items()]


def cli_command(provider: str) -> list[str]:
    name = "codex" if provider == "codex" else "claude"
    configured = os.environ.get("CODEX_BIN" if name == "codex" else "CLAUDE_BIN", name)
    executable = shutil.which(configured)
    if not executable and Path(configured).is_file():
        executable = str(Path(configured).resolve())
    if not executable:
        raise AIError(f"Install the official {name} CLI and put it on PATH, or set {name.upper()}_BIN")
    path = Path(executable)
    # Never send prompts or JSON schemas through cmd.exe / shell=True.
    if path.suffix.lower() in (".cmd", ".bat", ".ps1"):
        packages = (["@openai/codex/bin/codex.js"] if name == "codex" else
                    ["@anthropic-ai/claude-code/bin/claude.exe", "@anthropic-ai/claude-code/cli.js"])
        candidates = [path.parent / "node_modules" / package for package in packages]
        path = next((candidate for candidate in candidates if candidate.is_file()), None)
        if path is None:
            raise AIError(f"Set {name.upper()}_BIN to the native executable or official npm .js entry point")
    if path.suffix.lower() == ".js":
        node = shutil.which("node")
        if not node:
            raise AIError("Node.js is required for this CLI installation")
        return [node, str(path)]
    return [str(path)]


def subscription_environment() -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if key in {"OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN", "OPENAI_BASE_URL",
                   "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                   "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDECODE"} or key.startswith("CLAUDE_CODE_USE_"):
            env.pop(key, None)
    return env


def run_cli(argv: list[str], stdin: str, cwd: Path, timeout: float, env: dict, *, status_output: bool = False) -> str:
    kwargs: dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=cwd, env=env, shell=False, **kwargs)
    except OSError as exc:
        raise AIError("Could not start the AI CLI; check its installation and executable path") from exc
    try:
        stdout, _stderr = proc.communicate(stdin.encode("utf-8"), timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        if os.name == "nt":
            try:
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                               capture_output=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW)
            except (OSError, subprocess.TimeoutExpired):
                pass
            finally:
                proc.kill()
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            proc.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                if pipe:
                    pipe.close()
        raise AIError("AI response timed out; no decision was accepted") from exc
    if proc.returncode:
        # Raw CLI errors may contain credentials, account information or prompts.
        raise AIError(f"AI CLI exited with code {proc.returncode}; run its login/status and update commands on the server")
    # Codex login status uses stderr in current releases. Never display this text.
    if status_output:
        stdout += b"\n" + _stderr
    if len(stdout) > 2_000_000:
        raise AIError("AI output exceeded the response size limit")
    return stdout.decode("utf-8", errors="strict")


def validate_setup(settings: Settings, *, authenticate: bool = False) -> None:
    provider = settings.provider
    if provider.endswith("_api"):
        package, key = ("openai", "OPENAI_API_KEY") if provider == "openai_api" else ("anthropic", "ANTHROPIC_API_KEY")
        if not settings.effective_model:
            raise AIError("Enter an API model ID available to your account")
        if not os.environ.get(key):
            raise AIError(f"Set {key} in the server environment, then restart the server")
        if importlib.util.find_spec(package) is None:
            raise AIError(f"Install server/requirements.txt (missing {package})")
        return
    command = cli_command(provider)
    if not authenticate:
        return
    with tempfile.TemporaryDirectory(prefix="guardian-ai-auth-") as folder:
        args = ["login", "status"] if provider == "codex" else ["auth", "status"]
        result = run_cli(command + args, "", Path(folder), 5, subscription_environment(),
                         status_output=provider == "codex")
    if provider == "codex":
        if "chatgpt" not in result.lower():
            raise AIError("Run codex login on the server and choose ChatGPT; saved API-key login is not subscription mode")
    else:
        try:
            auth = json.loads(result)
        except ValueError as exc:
            raise AIError("Update Claude Code and run claude auth login on the server") from exc
        if not auth.get("loggedIn") or auth.get("authMethod") != "claude.ai":
            raise AIError("Run claude auth login on the server with your Claude subscription, without --console")


def strict_schema(model: type[BaseModel]) -> dict:
    schema = model.model_json_schema()
    def walk(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)
    walk(schema)
    return schema


def validate_decision(value: Any, model: type[BaseModel]) -> BaseModel:
    if isinstance(value, BaseModel):
        value = value.model_dump()
    if not isinstance(value, dict) or set(value) - set(model.model_fields):
        raise AIError("AI returned missing structured output or unknown decision fields")
    def finite(v):
        if isinstance(v, float) and not math.isfinite(v):
            raise AIError("AI returned a non-finite number")
        if isinstance(v, dict):
            for item in v.values(): finite(item)
        if isinstance(v, list):
            for item in v: finite(item)
    finite(value)
    try:
        return model.model_validate(value, strict=True)
    except ValueError as exc:
        raise AIError("AI decision did not match the required schema") from exc


def generate(settings: Settings, model: type[BaseModel], system: str, prompt: str,
             frame: bytes | None = None, *, timeout: float = 60) -> BaseModel:
    if not math.isfinite(timeout) or timeout <= 0:
        raise AIError("AI timeout must be positive and finite")
    validate_setup(settings)
    encoded = base64.b64encode(frame).decode("ascii") if frame else None
    provider = settings.provider
    try:
        if provider == "anthropic_api":
            import anthropic
            content = [{"type": "text", "text": prompt}]
            if encoded:
                content.insert(0, {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": encoded}})
            with anthropic.Anthropic(timeout=timeout, max_retries=0) as client:
                response = client.messages.parse(model=settings.effective_model, max_tokens=2048,
                    system=system, messages=[{"role": "user", "content": content}], output_format=model)
            if response.stop_reason in ("refusal", "max_tokens"):
                raise AIError("Claude refused or could not complete a structured decision")
            value = response.parsed_output
        elif provider == "openai_api":
            from openai import OpenAI
            content = [{"type": "input_text", "text": prompt}]
            if encoded:
                content.insert(0, {"type": "input_image", "image_url": "data:image/jpeg;base64," + encoded})
            with OpenAI(timeout=timeout, max_retries=0) as client:
                response = client.responses.parse(model=settings.effective_model, instructions=system,
                    input=[{"role": "user", "content": content}], text_format=model, store=False)
            if response.status != "completed":
                raise AIError("OpenAI could not complete a structured decision")
            value = response.output_parsed
        else:
            # Verify subscription auth before use. No direct OAuth token handling.
            started = time.monotonic()
            validate_setup(settings, authenticate=True)
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise AIError("AI authentication check exceeded the decision deadline")
            with tempfile.TemporaryDirectory(prefix="guardian-ai-") as folder:
                root = Path(folder)
                schema = strict_schema(model)
                (root / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
                (root / "system.txt").write_text(system, encoding="utf-8")
                if provider == "codex":
                    argv = cli_command(provider) + ["exec", "--ignore-user-config", "--ephemeral",
                        "--skip-git-repo-check", "--sandbox", "read-only", "--color", "never",
                        "-c", 'web_search="disabled"', "-c", 'model_reasoning_effort="low"',
                        "--output-schema", str(root / "schema.json"),
                        "--output-last-message", str(root / "result.json")]
                    for feature in ("shell_tool", "apps", "plugins", "hooks", "multi_agent",
                                    "browser_use", "computer_use", "image_generation"):
                        argv += ["--disable", feature]
                    if settings.effective_model:
                        argv += ["--model", settings.effective_model]
                    if frame:
                        (root / "frame.jpg").write_bytes(frame)
                        argv += ["--image", str(root / "frame.jpg")]
                    argv += ["-"]
                    run_cli(argv, system + "\n\n" + prompt, root, remaining, subscription_environment())
                    result_file = root / "result.json"
                    if not result_file.is_file() or result_file.stat().st_size > 100_000:
                        raise AIError("Codex did not produce a structured decision")
                    value = json.loads(result_file.read_text(encoding="utf-8"))
                else:
                    argv = cli_command(provider) + ["-p", "--safe-mode", "--tools", "",
                        "--disallowedTools", "mcp__*", "--permission-mode", "dontAsk",
                        "--no-session-persistence", "--input-format", "stream-json", "--output-format", "json",
                        "--json-schema", json.dumps(schema), "--system-prompt-file", str(root / "system.txt")]
                    if settings.effective_model:
                        argv += ["--model", settings.effective_model]
                    content = [{"type": "text", "text": prompt}]
                    if encoded:
                        content.insert(0, {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": encoded}})
                    message = {"type": "user", "message": {"role": "user", "content": content}, "parent_tool_use_id": None}
                    result = json.loads(run_cli(argv, json.dumps(message) + "\n", root, remaining, subscription_environment()))
                    if result.get("is_error") or result.get("subtype") != "success":
                        raise AIError("Claude Code did not complete a structured decision")
                    value = result.get("structured_output")
        return validate_decision(value, model)
    except AIError:
        raise
    except Exception as exc:
        # Avoid echoing provider HTTP bodies, tokens, images or CLI account data to the dashboard.
        raise AIError(f"{PROVIDERS[provider]} failed ({type(exc).__name__}); check model, login and provider availability") from exc
