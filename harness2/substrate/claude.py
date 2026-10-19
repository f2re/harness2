# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Claude Code solver substrate.

The editable tree stays Harness²-shaped: CLAUDE.md is the always-on body,
`.claude/skills/` holds skills, `sub_agents/<name>/AGENT.md` is the canonical
subagent representation, scripts are deterministic helpers, and
`.claude/settings.json` carries lifecycle hooks. Materialisation compiles the
canonical subagent representation into Claude Code's native `.claude/agents/`
layout.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Mapping

from ..core import runmark as RM
from ..core import tree as HT
from ..core.tree import SurfaceSpec
from .base import Install, Launcher, RunRequest
from .capabilities import CLAUDE_CAPABILITIES

CLAUDE_SURFACE = SurfaceSpec(
    name="claude",
    always_on=("CLAUDE.md",),
    always_on_max=24_000,
    always_on_cap_reason="CLAUDE.md is injected into project context; keep durable guidance concise",
    skill_dir=".claude/skills",
    skill_name_rule="overrides_dir",
    trigger_hint=(
        'Fix it by adding a trigger line naming `{name}` to CLAUDE.md, e.g. "When '
        "<the situation this skill handles>, read .claude/skills/{name}/SKILL.md and follow it.\""
    ),
    autotrigger_file="CLAUDE.md",
    trigger_line="- When {desc}, read .claude/skills/{name}/SKILL.md and follow it.\n",
    subagent_requires_mode=False,
    plugin_dir=None,
    hooks_file=".claude/settings.json",
    hook_events=frozenset(
        {
            "PreToolUse",
            "PostToolUse",
            "PermissionRequest",
            "Notification",
            "UserPromptSubmit",
            "SessionStart",
            "SessionEnd",
            "Stop",
            "SubagentStart",
            "SubagentStop",
            "PreCompact",
            "PostCompact",
        }
    ),
    compile_skill_scripts=True,
    reject_empty_always_on=True,
    stubs=(
        (
            "scripts/README.md",
            "<!-- c7: deterministic helpers, run as `python3 scripts/<name>.py`. -->\n",
        ),
        (
            "sub_agents/README.md",
            "<!-- c5: canonical delegated agents. Add sub_agents/<name>/AGENT.md with "
            "`description:` frontmatter; materialisation installs it as "
            ".claude/agents/<name>.md. -->\n",
        ),
        (
            ".claude/skills/README.md",
            "<!-- c6: Claude Code project skills. Add .claude/skills/<name>/SKILL.md "
            "with `description:` frontmatter. -->\n",
        ),
    ),
)


def _copy_if_exists(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _resolve_binary() -> str:
    configured = os.environ.get("HARNESS2_CLAUDE_BIN", "claude")
    p = Path(configured).expanduser()
    if p.is_file():
        return str(p)
    found = shutil.which(configured)
    if found:
        return found
    raise RuntimeError(
        "Claude Code CLI not found; install it or set HARNESS2_CLAUDE_BIN to the executable"
    )


class ClaudeSubstrate:
    """Claude Code CLI behind the Harness² Substrate interface."""

    name = "cc"
    capabilities = CLAUDE_CAPABILITIES

    def __init__(self, launcher: Launcher | None = None):
        self._launcher = launcher

    def surface(self) -> SurfaceSpec:
        return CLAUDE_SURFACE

    def materialise(self, tree_dir: Path, spec, ctx: Mapping[str, str]) -> Install:
        if spec.install_mode != "claude_root":
            raise ValueError(
                f"install_mode {spec.install_mode!r} is not the Claude mode; expected 'claude_root'"
            )
        tree_dir = Path(tree_dir)
        if not HT.is_tree(CLAUDE_SURFACE, tree_dir):
            raise ValueError(f"{tree_dir} is not a Claude harness tree (no CLAUDE.md)")

        staged = Path(tempfile.mkdtemp(prefix="adapt-cc-root-"))
        _copy_if_exists(tree_dir / "CLAUDE.md", staged / "CLAUDE.md")
        _copy_if_exists(tree_dir / ".claude" / "skills", staged / ".claude" / "skills")
        _copy_if_exists(
            tree_dir / ".claude" / "settings.json", staged / ".claude" / "settings.json"
        )
        _copy_if_exists(tree_dir / "scripts", staged / "scripts")

        sub_dir = tree_dir / "sub_agents"
        if sub_dir.is_dir():
            for agent_md in sorted(sub_dir.glob("*/AGENT.md")):
                target = staged / ".claude" / "agents" / f"{agent_md.parent.name}.md"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    agent_md.read_text(encoding="utf-8", errors="replace"), encoding="utf-8"
                )

        for key, body in ctx.items():
            if key.startswith("file:"):
                rel = HT.normalize_rel(key[len("file:") :])
                p = staged / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(body, encoding="utf-8")

        return Install(
            staging_dir=staged,
            fingerprint=RM.fingerprint(tree_dir),
            extras={
                "install_mode": "claude_root",
                **{k: v for k, v in ctx.items() if not k.startswith("file:")},
            },
        )

    def exec_argv(
        self,
        prompt: str,
        workspace: Path,
        model: str = "",
        *,
        max_turns: int | None = None,
        skip_permissions: bool = True,
    ) -> list[str]:
        argv = [
            _resolve_binary(),
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
        ]
        if model:
            argv += ["--model", model]
        if max_turns is not None:
            argv += ["--max-turns", str(int(max_turns))]
        if skip_permissions:
            argv.append("--dangerously-skip-permissions")
        return argv

    def execute(
        self, task_ref: str, install: Install, run_ids: list[str], timeout: int
    ) -> list[Path]:
        if self._launcher is None:
            raise RuntimeError(
                "ClaudeSubstrate was constructed without a launcher body; the benchmark "
                "adapter must supply workspace staging and read-back locations"
            )
        return self._launcher(
            RunRequest(task_ref=task_ref, run_ids=tuple(run_ids), timeout=int(timeout)), install
        )

    def read_trajectory(
        self, stream_path: Path, *, obs_trunc: int, max_chars: int, args_trunc: int = 2000
    ) -> str:
        return render_events(
            Path(stream_path), obs_trunc=obs_trunc, max_chars=max_chars, args_trunc=args_trunc
        )

    def preflight(self) -> None:
        _resolve_binary()


def _clip(value, n: int) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\x00", "")
    if n <= 0 or len(text) <= n:
        return text
    return text[:n] + f"…(+{len(text) - n} chars — render truncation)"


def _load_events(path: Path) -> list[dict]:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [{"type": "_read_error", "message": str(exc)}]
    out: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _content_blocks(message) -> list[dict]:
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, list):
        return [x for x in content if isinstance(x, dict)]
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return []


def render_events(path: Path, *, obs_trunc: int, max_chars: int, args_trunc: int = 2000) -> str:
    """Render Claude Code stream-json into Harness²'s shared trajectory grammar."""
    lines: list[str] = []
    for event in _load_events(Path(path)):
        et = event.get("type", "")
        if et == "_read_error":
            return f"(failed to read trajectory: {event.get('message')})"

        if et == "assistant":
            for block in _content_blocks(event.get("message")):
                bt = block.get("type")
                if bt == "text" and str(block.get("text", "")).strip():
                    lines.append(f"[ASSISTANT] {_clip(block.get('text'), obs_trunc)}")
                elif bt == "tool_use":
                    name = block.get("name") or "tool"
                    lines.append(f"[ACTION] {name}: {_clip(block.get('input'), args_trunc)}")
                elif bt in ("thinking", "reasoning") and str(block.get("thinking", "")).strip():
                    lines.append(f"[REASONING] {_clip(block.get('thinking'), obs_trunc)}")
            continue

        if et == "user":
            for block in _content_blocks(event.get("message")):
                if block.get("type") == "tool_result":
                    tag = "OBSERVATION ERROR" if block.get("is_error") else "OBSERVATION"
                    lines.append(f"[{tag}] {_clip(block.get('content'), obs_trunc)}")
                elif block.get("type") == "text" and str(block.get("text", "")).strip():
                    lines.append(f"[USER] {_clip(block.get('text'), obs_trunc)}")
            continue

        if et == "result":
            result = event.get("result")
            if isinstance(result, str) and result.strip():
                lines.append(f"[ASSISTANT] {_clip(result, obs_trunc)}")
            if event.get("is_error"):
                lines.append(f"[HARNESS] Claude result error: {_clip(event, 1000)}")
            continue

        if et == "system":
            subtype = event.get("subtype", "system")
            lines.append(f"[HARNESS] Claude {subtype}: {_clip(event, obs_trunc)}")
            continue

    rendered = "\n".join(lines) or "(empty Claude trajectory)"
    return _clip(rendered, max_chars)


__all__ = ["ClaudeSubstrate", "CLAUDE_SURFACE", "render_events"]
