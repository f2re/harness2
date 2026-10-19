"""Antigravity CLI + Harness² workspace adapter for WorkBuddy-Bench.

The CLI binary is staged by ``harness2-setup`` and bind-mounted read-only at
``/opt/antigravity``.  Headless WorkBuddy runs use Gemini API-key authentication
rather than a desktop keyring so the container contract is deterministic.
"""
from __future__ import annotations

import base64
import io
import json
import shlex
import tarfile
from pathlib import Path

from harbor.agents.installed.base import BaseInstalledAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from workbuddy_bench.agents._agent_user import ensure_agent_user

_OUTPUT_FILENAME = "agy-output.jsonl"
_STDERR_FILENAME = "agy-stderr.log"
_HARNESS_ENTRIES = ("AGENTS.md", ".agents", "scripts")


class AntigravityHarnessAgent(BaseInstalledAgent):
    """A pinned host-staged ``agy`` binary running inside the Harbor task container."""

    SUPPORTS_ATIF = False

    def __init__(self, logs_dir: Path, *args, **kwargs):
        self._bin_dir = str(kwargs.pop("AGY_BIN_DIR", "/opt/antigravity")).rstrip("/")
        self._agy_model = str(kwargs.pop("AGY_MODEL", "") or "")
        self._effort = str(kwargs.pop("AGY_EFFORT", "high") or "high")
        self._print_timeout = str(kwargs.pop("AGY_PRINT_TIMEOUT", "60m") or "60m")
        ws = kwargs.pop("WB_HARNESS_WS", None)
        self._harness_ws: Path | None = Path(ws) if ws else None
        # Generic WorkBuddy manifest fields are not Antigravity constructor args.
        kwargs.pop("model_params", None)
        kwargs.pop("connection", None)
        kwargs.pop("context_window", None)
        kwargs.pop("context_compact_pct", None)
        kwargs.pop("settings_preset", None)
        kwargs.pop("models_preset", None)
        kwargs.pop("mount_path", None)
        kwargs.pop("instance_id", None)
        super().__init__(logs_dir, *args, **kwargs)

    @staticmethod
    def name() -> str:
        return "antigravity-harness"

    def get_version_command(self) -> str | None:
        return 'export PATH="/usr/local/bin:$PATH"; agy --version'

    async def install(self, environment: BaseEnvironment) -> None:
        binary = f"{self._bin_dir}/agy"
        await self.exec_as_root(
            environment,
            command=(
                f'if [ ! -x "{binary}" ]; then '
                f'echo "ERROR: Antigravity binary missing at {binary}" >&2; exit 1; fi && '
                f'ln -sf "{binary}" /usr/local/bin/agy && agy --version'
            ),
        )
        await ensure_agent_user(self, environment)

    def _harness_payload(self) -> tuple[bytes, int]:
        ws = self._harness_ws
        payload = io.BytesIO()
        n = 0
        with tarfile.open(fileobj=payload, mode="w:gz") as tar:
            if ws is not None:
                for entry in _HARNESS_ENTRIES:
                    src = ws / entry
                    if src.is_file():
                        tar.add(src, arcname=entry)
                        n += 1
                    elif src.is_dir():
                        for path in sorted(src.rglob("*")):
                            if path.is_file():
                                tar.add(path, arcname=f"{entry}/{path.relative_to(src)}")
                                n += 1
        return payload.getvalue(), n

    async def _materialize_harness(self, environment: BaseEnvironment) -> None:
        if self._harness_ws is None or not self._harness_ws.is_dir():
            return
        payload, n = self._harness_payload()
        if not n:
            return
        blob = base64.b64encode(payload).decode()
        cmd = (
            "cd /workspace && "
            f"echo {blob} | base64 -d | tar -xzf - -C /workspace && "
            "if git rev-parse --git-dir >/dev/null 2>&1; then "
            "git add -A && "
            "{ git diff --cached --quiet || "
            "git -c user.email=harness@bench -c user.name=harness "
            "commit -q -m 'harness install (pre-agent)'; }; "
            "fi"
        )
        await self.exec_as_agent(environment, command=cmd)

    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        if self._harness_ws is not None:
            await self._materialize_harness(environment)
        instruction = self.render_instruction(instruction)
        api_key = self._get_env("GEMINI_API_KEY") or ""
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is missing inside the WorkBuddy Antigravity container; "
                "set HARNESS2_ANTIGRAVITY_API_KEY before setup/run"
            )
        env = {
            "GEMINI_API_KEY": api_key,
            "AGY_CLI_DISABLE_AUTO_UPDATE": "true",
        }
        base_url = self._get_env("GOOGLE_GEMINI_BASE_URL") or ""
        if base_url:
            env["GOOGLE_GEMINI_BASE_URL"] = base_url

        # API-key auth in headless mode requires the Gemini model provider selected
        # in the Antigravity CLI settings file.
        settings = base64.b64encode(json.dumps({"modelProvider": "gemini"}).encode()).decode()
        setup = (
            'export HOME="$(getent passwd "$(id -u)" | cut -d: -f6)"; '
            'mkdir -p "$HOME/.gemini/antigravity-cli" && '
            f'echo {settings} | base64 -d > "$HOME/.gemini/antigravity-cli/settings.json"'
        )
        await self.exec_as_agent(environment, command=setup, env=env)

        flags = [
            "-p",
            shlex.quote(instruction),
            "--output-format",
            "stream-json",
            "--dangerously-skip-permissions",
            "--print-timeout",
            shlex.quote(self._print_timeout),
        ]
        if self._agy_model:
            flags += ["--model", shlex.quote(self._agy_model)]
        if self._effort:
            flags += ["--effort", shlex.quote(self._effort)]
        output = f"/logs/agent/{_OUTPUT_FILENAME}"
        stderr = f"/logs/agent/{_STDERR_FILENAME}"
        command = (
            'export PATH="/usr/local/bin:$PATH"; '
            'export HOME="$(getent passwd "$(id -u)" | cut -d: -f6)"; '
            f"cd /workspace && agy {' '.join(flags)} </dev/null 2>{stderr} | tee {output}"
        )
        await self.exec_as_agent(environment, command=command, env=env)

    def populate_context_post_run(self, context: AgentContext) -> None:
        """Best-effort token accounting from the terminal stream-json result event."""
        path = self.logs_dir / _OUTPUT_FILENAME
        if not path.is_file():
            return
        terminal = None
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.lstrip().startswith("{"):
                    continue
                event = json.loads(line)
                if isinstance(event, dict) and event.get("event") == "result":
                    terminal = event.get("result")
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(terminal, dict):
            return
        usage = terminal.get("usage") if isinstance(terminal.get("usage"), dict) else {}
        context.n_input_tokens = int(usage.get("input_tokens") or 0)
        context.n_output_tokens = int(usage.get("output_tokens") or 0)
        context.n_cache_tokens = int(usage.get("cache_read_tokens") or 0)
