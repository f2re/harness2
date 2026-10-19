# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Google Antigravity CLI solver substrate.

Antigravity uses the same canonical editable Harness IR as Codex: `AGENTS.md`,
`.agents/skills/`, `sub_agents/<name>/AGENT.md`, `scripts/`, and
`.codex/hooks.json`. Materialisation preserves the compatible paths and compiles
subagents plus normalized hooks to Antigravity's native `.agents/agents/` and
`.agents/hooks.json` representations.
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
from .capabilities import ANTIGRAVITY_CAPABILITIES

ANTIGRAVITY_SURFACE = SurfaceSpec(
    name="codex",
    always_on=("AGENTS.md",),
    always_on_max=8_000,
    always_on_cap_reason="portable always-on guidance consumes Antigravity context on every run",
    skill_dir=".agents/skills",
    skill_name_rule="overrides_dir",
    trigger_hint=(
        'Fix it by adding a trigger line naming `{name}` to AGENTS.md, e.g. "When '
        "<the situation this skill handles>, read .agents/skills/{name}/SKILL.md and follow it.\""
    ),
    autotrigger_file="AGENTS.md",
    trigger_line="- When {desc}, read .agents/skills/{name}/SKILL.md and follow it.\n",
    subagent_requires_mode=False,
    plugin_dir=None,
    hooks_file=".codex/hooks.json",
    hook_events=frozenset(
        {"SessionStart", "PreToolUse", "PostToolUse", "PreInvocation", "PostInvocation", "Stop"}
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
            "<!-- c5: portable delegated agents. Add sub_agents/<name>/AGENT.md with "
            "`description:` frontmatter; the Antigravity compiler installs it under "
            ".agents/agents/. -->\n",
        ),
        (
            ".agents/skills/README.md",
            "<!-- c6: portable skills; Antigravity consumes these paths natively. -->\n",
        ),
        (
            ".codex/README.md",
            "<!-- c8 portable lifecycle hooks. Use the normalized top-level `hooks` object; "
            "the Antigravity compiler emits native .agents/hooks.json. -->\n",
        ),
    ),
)


def _resolve_binary() -> str:
    configured = os.environ.get("HARNESS2_ANTIGRAVITY_BIN", "agy")
    p = Path(configured).expanduser()
    if p.is_file():
        return str(p)
    found = shutil.which(configured)
    if found:
        return found
    raise RuntimeError(
        "Antigravity CLI not found; install `agy` or set HARNESS2_ANTIGRAVITY_BIN "
        "to the executable"
    )


def _copy_if_exists(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _has_frontmatter_key(text: str, key: str) -> bool:
    head = text[:1000]
    return any(line.strip().startswith(key + ":") for line in head.splitlines())


def _ensure_antigravity_subagent(text: str, name: str) -> str:
    """Make a canonical AGENT.md discoverable/invokable as an Antigravity subagent."""
    if text.lstrip().startswith("---"):
        body = text
        if not _has_frontmatter_key(body, "name"):
            body = body.replace("---\n", f"---\nname: {name}\n", 1)
        if not _has_frontmatter_key(body, "subagent"):
            body = body.replace("---\n", "---\nsubagent: true\n", 1)
        return body
    return (
        "---\n"
        f"name: {name}\n"
        "description: delegated Harness2 subagent\n"
        "subagent: true\n"
        "---\n\n"
        + text
    )


_TOOL_MATCHERS = {
    "Bash": "run_command",
    "Read": "view_file",
    "Write": "write_to_file",
    "Edit": "replace_file_content",
}
_SUPPORTED_HOOK_EVENTS = {
    "SessionStart",
    "PreToolUse",
    "PostToolUse",
    "PreInvocation",
    "PostInvocation",
    "Stop",
}


def _translate_matcher(value) -> str:
    """Translate common Claude/Codex tool names in simple matcher alternations."""
    matcher = str(value or "")
    return "|".join(_TOOL_MATCHERS.get(part, part) for part in matcher.split("|"))


def _compile_hooks(src: str) -> str:
    """Compile Harness² normalized hooks into Antigravity's named-hook schema.

    The portable tree uses the existing Codex/Claude matcher-entry shape. Native
    Antigravity uses named hook definitions and different canonical tool names.
    Tool-control output semantics are runtime-specific; command side effects and
    native event outputs remain the hook command's responsibility.
    """
    doc = json.loads(src)
    hooks = doc.get("hooks", {}) if isinstance(doc, dict) else {}
    native: dict[str, dict] = {}
    direct_events = {"SessionStart", "PreInvocation", "PostInvocation", "Stop"}
    for event, entries in hooks.items():
        if event not in _SUPPORTED_HOOK_EVENTS:
            raise ValueError(f"Antigravity does not support portable hook event {event!r}")
        if not isinstance(entries, list):
            continue
        if event in direct_events:
            handlers = []
            for entry in entries:
                if isinstance(entry, dict) and isinstance(entry.get("hooks"), list):
                    handlers.extend(h for h in entry["hooks"] if isinstance(h, dict))
            native[f"harness2-{event.lower()}"] = {event: handlers}
        else:
            translated = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                item = dict(entry)
                if "matcher" in item:
                    item["matcher"] = _translate_matcher(item.get("matcher"))
                translated.append(item)
            native[f"harness2-{event.lower()}"] = {event: translated}
    return json.dumps(native, indent=2) + "\n"


class AntigravitySubstrate:
    """Antigravity CLI behind the Harness² Substrate interface."""

    name = "ag"
    capabilities = ANTIGRAVITY_CAPABILITIES

    def __init__(self, launcher: Launcher | None = None):
        self._launcher = launcher

    def surface(self) -> SurfaceSpec:
        return ANTIGRAVITY_SURFACE

    def materialise(self, tree_dir: Path, spec, ctx: Mapping[str, str]) -> Install:
        if spec.install_mode != "antigravity_root":
            raise ValueError(
                f"install_mode {spec.install_mode!r} is not the Antigravity mode; "
                "expected 'antigravity_root'"
            )
        tree_dir = Path(tree_dir)
        if not HT.is_tree(ANTIGRAVITY_SURFACE, tree_dir):
            raise ValueError(f"{tree_dir} is not a portable harness tree (no AGENTS.md)")

        staged = Path(tempfile.mkdtemp(prefix="adapt-ag-root-"))
        _copy_if_exists(tree_dir / "AGENTS.md", staged / "AGENTS.md")
        _copy_if_exists(tree_dir / ".agents" / "skills", staged / ".agents" / "skills")
        _copy_if_exists(tree_dir / "scripts", staged / "scripts")

        hooks = tree_dir / ".codex" / "hooks.json"
        if hooks.is_file():
            target = staged / ".agents" / "hooks.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(_compile_hooks(hooks.read_text(encoding="utf-8")), encoding="utf-8")

        sub_dir = tree_dir / "sub_agents"
        if sub_dir.is_dir():
            for agent_md in sorted(sub_dir.glob("*/AGENT.md")):
                name = agent_md.parent.name
                target = staged / ".agents" / "agents" / name / "agent.md"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    _ensure_antigravity_subagent(
                        agent_md.read_text(encoding="utf-8", errors="replace"), name
                    ),
                    encoding="utf-8",
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
                "install_mode": "antigravity_root",
                **{k: v for k, v in ctx.items() if not k.startswith("file:")},
            },
        )

    def exec_argv(
        self,
        prompt: str,
        workspace: Path,
        model: str = "",
        *,
        reasoning_effort: str = "high",
        skip_permissions: bool = True,
    ) -> list[str]:
        argv = [_resolve_binary(), "-p", prompt, "--output-format", "stream-json"]
        if model:
            argv += ["--model", model]
        if reasoning_effort:
            argv += ["--effort", reasoning_effort]
        if skip_permissions:
            argv.append("--dangerously-skip-permissions")
        return argv

    def execute(
        self, task_ref: str, install: Install, run_ids: list[str], timeout: int
    ) -> list[Path]:
        if self._launcher is None:
            raise RuntimeError(
                "AntigravitySubstrate was constructed without a launcher body; the benchmark "
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
        return [{"event": "_read_error", "message": str(exc)}]
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


def render_events(path: Path, *, obs_trunc: int, max_chars: int, args_trunc: int = 2000) -> str:
    """Render `agy --output-format stream-json` into Harness²'s shared grammar."""
    lines: list[str] = []
    for event in _load_events(Path(path)):
        et = event.get("event", "")
        if et == "_read_error":
            return f"(failed to read trajectory: {event.get('message')})"

        if et == "init":
            init = event.get("init") or {}
            lines.append(
                "[HARNESS] Antigravity init: "
                + _clip(
                    {
                        "cwd": init.get("cwd"),
                        "model": init.get("model"),
                        "agent": init.get("agent"),
                        "permission_mode": init.get("permission_mode"),
                    },
                    obs_trunc,
                )
            )
            continue

        if et == "step_update":
            step = event.get("step_update") or {}
            st = step.get("step_type", "")
            if st == "agent_response":
                text = step.get("text_delta")
                if isinstance(text, str) and text:
                    lines.append(f"[ASSISTANT] {_clip(text, obs_trunc)}")
            elif st == "tool":
                name = step.get("tool_name") or "tool"
                info = step.get("tool_info") or {}
                lines.append(f"[ACTION] {name}: {_clip(info, args_trunc)}")
                if step.get("state") == "DONE":
                    lines.append(f"[OBSERVATION] {_clip(info, obs_trunc)}")
            elif st == "user_input":
                text = step.get("text_delta")
                if isinstance(text, str) and text.strip():
                    lines.append(f"[USER] {_clip(text, obs_trunc)}")
            elif st:
                lines.append(f"[HARNESS] Antigravity {st}: {_clip(step, obs_trunc)}")
            continue

        if et == "result":
            result = event.get("result") or {}
            text = result.get("response")
            if isinstance(text, str) and text.strip():
                lines.append(f"[ASSISTANT] {_clip(text, obs_trunc)}")
            status = result.get("status")
            if status and status != "SUCCESS":
                lines.append(f"[HARNESS] Antigravity result status={status}: {_clip(result, 1000)}")
            continue

    rendered = "\n".join(lines) or "(empty Antigravity trajectory)"
    return _clip(rendered, max_chars)


__all__ = ["AntigravitySubstrate", "ANTIGRAVITY_SURFACE", "render_events"]
