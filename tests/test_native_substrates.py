# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

from __future__ import annotations

import json
import shutil
from types import SimpleNamespace

from harness2.core import prompts
from harness2.core import tree as HT
from harness2.substrate.antigravity import ANTIGRAVITY_SURFACE, AntigravitySubstrate
from harness2.substrate.claude import CLAUDE_SURFACE, ClaudeSubstrate
from harness2.substrate.registry import capabilities, normalize_substrate


def _tree(surface, root):
    return HT.write_tree(
        surface,
        {
            "AGENTS.md": "Use the `check-files` skill when validating outputs.\n",
            ".agents/skills/check-files/SKILL.md": (
                "---\n"
                "description: Validates generated files before completion.\n"
                "---\n\n"
                "Run the validation procedure.\n"
            ),
            "sub_agents/reviewer/AGENT.md": (
                "---\n"
                "description: Reviews final artifacts for omissions.\n"
                "---\n\n"
                "Review the requested output and return only defects.\n"
            ),
            "scripts/check.py": "print('ok')\n",
            ".codex/hooks.json": json.dumps(
                {
                    "hooks": {
                        "PostToolUse": [
                            {
                                "matcher": "Bash",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python3 scripts/check.py",
                                    }
                                ],
                            }
                        ]
                    }
                }
            ),
        },
        root,
        stubs=False,
    )


def test_native_surfaces_reuse_portable_codex_prompt_grammar():
    # Native compilers intentionally present the existing portable Codex IR to
    # the proposer/composer; only materialisation knows the runtime file names.
    assert CLAUDE_SURFACE.name == "codex"
    assert ANTIGRAVITY_SURFACE.name == "codex"
    assert "AGENTS.md" in prompts._st(CLAUDE_SURFACE).surface_md
    assert "AGENTS.md" in prompts._st(ANTIGRAVITY_SURFACE).surface_md


def test_claude_materialise_compiles_portable_tree(tmp_path):
    src = _tree(CLAUDE_SURFACE, tmp_path / "portable")
    inst = ClaudeSubstrate().materialise(
        src, SimpleNamespace(install_mode="claude_root"), {}
    )
    try:
        root = inst.staging_dir
        assert (root / "CLAUDE.md").read_text().startswith("Use the `check-files` skill")
        skill = root / ".claude/skills/check-files/SKILL.md"
        assert skill.is_file()
        assert "name: check-files" in skill.read_text()
        assert (root / ".claude/agents/reviewer.md").is_file()
        assert (root / "scripts/check.py").is_file()
        settings = json.loads((root / ".claude/settings.json").read_text())
        assert "PostToolUse" in settings["hooks"]
        assert not (root / "AGENTS.md").exists()
    finally:
        shutil.rmtree(inst.staging_dir, ignore_errors=True)


def test_antigravity_materialise_compiles_agents_and_hooks(tmp_path):
    src = _tree(ANTIGRAVITY_SURFACE, tmp_path / "portable")
    inst = AntigravitySubstrate().materialise(
        src, SimpleNamespace(install_mode="antigravity_root"), {}
    )
    try:
        root = inst.staging_dir
        assert (root / "AGENTS.md").is_file()
        assert (root / ".agents/skills/check-files/SKILL.md").is_file()
        agent = (root / ".agents/agents/reviewer/agent.md").read_text()
        assert "name: reviewer" in agent
        assert "subagent: true" in agent
        native_hooks = json.loads((root / ".agents/hooks.json").read_text())
        assert "hooks" not in native_hooks
        assert "harness2-posttooluse" in native_hooks
        assert "PostToolUse" in native_hooks["harness2-posttooluse"]
    finally:
        shutil.rmtree(inst.staging_dir, ignore_errors=True)


def test_claude_stream_json_renderer(tmp_path):
    stream = tmp_path / "claude.jsonl"
    stream.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {"type": "text", "text": "Inspecting files"},
                                {
                                    "type": "tool_use",
                                    "name": "Bash",
                                    "input": {"command": "ls"},
                                },
                            ]
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "user",
                        "message": {
                            "content": [
                                {"type": "tool_result", "content": "a.txt", "is_error": False}
                            ]
                        },
                    }
                ),
                json.dumps({"type": "result", "result": "Done"}),
            ]
        )
        + "\n"
    )
    rendered = ClaudeSubstrate().read_trajectory(stream, obs_trunc=1000, max_chars=10000)
    assert "[ASSISTANT] Inspecting files" in rendered
    assert "[ACTION] Bash" in rendered
    assert "[OBSERVATION] a.txt" in rendered
    assert "[ASSISTANT] Done" in rendered


def test_antigravity_stream_json_renderer(tmp_path):
    stream = tmp_path / "agy.jsonl"
    stream.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event": "init",
                        "init": {"cwd": "/tmp/work", "permission_mode": "always-proceed"},
                    }
                ),
                json.dumps(
                    {
                        "event": "step_update",
                        "step_update": {
                            "step_type": "tool",
                            "state": "DONE",
                            "tool_name": "run_command",
                            "tool_info": {"command": "ls", "output": "a.txt"},
                        },
                    }
                ),
                json.dumps(
                    {
                        "event": "result",
                        "result": {"status": "SUCCESS", "response": "Done"},
                    }
                ),
            ]
        )
        + "\n"
    )
    rendered = AntigravitySubstrate().read_trajectory(stream, obs_trunc=1000, max_chars=10000)
    assert "[HARNESS] Antigravity init" in rendered
    assert "[ACTION] run_command" in rendered
    assert "[OBSERVATION]" in rendered
    assert "[ASSISTANT] Done" in rendered


def test_registry_aliases_and_capabilities():
    assert normalize_substrate("claude") == "cc"
    assert normalize_substrate("claude-code") == "cc"
    assert normalize_substrate("agy") == "ag"
    assert normalize_substrate("antigravity") == "ag"
    assert capabilities("cc").skills
    assert capabilities("ag").subagents
