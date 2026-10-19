# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
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


class NativeSubstrateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_native_surfaces_reuse_portable_codex_prompt_grammar(self):
        self.assertEqual(CLAUDE_SURFACE.name, "codex")
        self.assertEqual(ANTIGRAVITY_SURFACE.name, "codex")
        self.assertIn("AGENTS.md", prompts._st(CLAUDE_SURFACE).surface_md)
        self.assertIn("AGENTS.md", prompts._st(ANTIGRAVITY_SURFACE).surface_md)

    def test_claude_materialise_compiles_portable_tree(self):
        src = _tree(CLAUDE_SURFACE, self.root / "portable-cc")
        inst = ClaudeSubstrate().materialise(
            src, SimpleNamespace(install_mode="claude_root"), {}
        )
        self.addCleanup(shutil.rmtree, inst.staging_dir, True)
        root = inst.staging_dir
        self.assertTrue((root / "CLAUDE.md").read_text().startswith("Use the `check-files` skill"))
        skill = root / ".claude/skills/check-files/SKILL.md"
        self.assertTrue(skill.is_file())
        self.assertIn("name: check-files", skill.read_text())
        self.assertTrue((root / ".claude/agents/reviewer.md").is_file())
        self.assertTrue((root / "scripts/check.py").is_file())
        settings = json.loads((root / ".claude/settings.json").read_text())
        self.assertIn("PostToolUse", settings["hooks"])
        self.assertFalse((root / "AGENTS.md").exists())

    def test_antigravity_materialise_compiles_agents_and_hooks(self):
        src = _tree(ANTIGRAVITY_SURFACE, self.root / "portable-ag")
        inst = AntigravitySubstrate().materialise(
            src, SimpleNamespace(install_mode="antigravity_root"), {}
        )
        self.addCleanup(shutil.rmtree, inst.staging_dir, True)
        root = inst.staging_dir
        self.assertTrue((root / "AGENTS.md").is_file())
        self.assertTrue((root / ".agents/skills/check-files/SKILL.md").is_file())
        agent = (root / ".agents/agents/reviewer/agent.md").read_text()
        self.assertIn("name: reviewer", agent)
        self.assertIn("subagent: true", agent)
        native_hooks = json.loads((root / ".agents/hooks.json").read_text())
        self.assertNotIn("hooks", native_hooks)
        self.assertIn("harness2-posttooluse", native_hooks)
        self.assertIn("PostToolUse", native_hooks["harness2-posttooluse"])

    def test_claude_stream_json_renderer(self):
        stream = self.root / "claude.jsonl"
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
                                    {
                                        "type": "tool_result",
                                        "content": "a.txt",
                                        "is_error": False,
                                    }
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
        self.assertIn("[ASSISTANT] Inspecting files", rendered)
        self.assertIn("[ACTION] Bash", rendered)
        self.assertIn("[OBSERVATION] a.txt", rendered)
        self.assertIn("[ASSISTANT] Done", rendered)

    def test_antigravity_stream_json_renderer(self):
        stream = self.root / "agy.jsonl"
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
        self.assertIn("[HARNESS] Antigravity init", rendered)
        self.assertIn("[ACTION] run_command", rendered)
        self.assertIn("[OBSERVATION]", rendered)
        self.assertIn("[ASSISTANT] Done", rendered)

    def test_registry_aliases_and_capabilities(self):
        self.assertEqual(normalize_substrate("claude"), "cc")
        self.assertEqual(normalize_substrate("claude-code"), "cc")
        self.assertEqual(normalize_substrate("agy"), "ag")
        self.assertEqual(normalize_substrate("antigravity"), "ag")
        self.assertTrue(capabilities("cc").skills)
        self.assertTrue(capabilities("ag").subagents)


if __name__ == "__main__":
    unittest.main()
