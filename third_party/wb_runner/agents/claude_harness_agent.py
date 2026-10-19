"""Claude Code agent that installs a Harness² native workspace before execution.

The pinned WorkBuddy release already ships ``CcAgent``.  This subclass only adds
portable-harness materialisation; endpoint/model/auth behavior remains upstream.
"""
from __future__ import annotations

import base64
import io
import tarfile
from pathlib import Path

from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from workbuddy_bench.agents.cc_agent import CcAgent

_HARNESS_ENTRIES = ("CLAUDE.md", ".claude", "scripts")


class ClaudeHarnessAgent(CcAgent):
    """Pinned WorkBuddy Claude Code runtime + Harness² native files."""

    def __init__(self, logs_dir: Path, *args, **kwargs):
        ws = kwargs.pop("WB_HARNESS_WS", None)
        self._harness_ws: Path | None = Path(ws) if ws else None
        super().__init__(logs_dir, *args, **kwargs)

    @staticmethod
    def name() -> str:
        return "claude-harness"

    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        if self._harness_ws is not None:
            await self._materialize_harness(environment)
        await super().run(instruction, environment, context)

    def _harness_payload(self) -> tuple[bytes, int]:
        ws = self._harness_ws
        payload = io.BytesIO()
        n = 0
        with tarfile.open(fileobj=payload, mode="w:gz") as tar:
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
        ws = self._harness_ws
        if ws is None or not ws.is_dir():
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
        log = getattr(self, "logger", None)
        if log is not None:
            log.info("materialized + committed %d Claude harness file(s) from %s", n, ws)
