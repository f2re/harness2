# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""LAB runner for headless Claude Code and Antigravity substrates.

The benchmark-facing contract remains the one implemented by :class:`LabAdapter`:
run directories, output extraction, resume markers, judging and reporting are
unchanged. This module only owns native CLI workspace staging and execution.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

from .. import config
from ..core import tree as HT
from ..substrate.antigravity import AntigravitySubstrate
from ..substrate.claude import ClaudeSubstrate
from ..substrate.registry import normalize_substrate
from .lab import CODEX_BASE_BODY, JUDGE_MODEL, LabAdapter, _lab_env, lab_spec

_PROMPT = """You are completing this Harvey LAB assignment autonomously.

{task}

Workspace contract:
- `documents/` contains the supplied matter files and is read-only source material.
- `output/` is the only deliverable directory. Create every requested file there.
- `scripts/read_doc.py` extracts text from .docx/.pdf/.pptx/.xlsx files.
- Use `python3 scripts/read_doc.py <path>` for binary source documents.
- Re-open and verify every deliverable before finishing.
- Do not look for evaluation criteria, answer keys, scores, or hidden benchmark material.
"""


def _copy_overlay(src: Path, dst: Path) -> None:
    if not src.is_dir():
        return
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


class LabNativeAdapter(LabAdapter):
    """Harvey LAB using native ``claude`` or ``agy`` execution."""

    def __init__(
        self,
        *,
        substrate: str,
        model: str | None = None,
        timeout: int | None = None,
        solver_effort: str = "high",
        judge_model: str = JUDGE_MODEL,
        split_file: Path | None = None,
    ):
        substrate = normalize_substrate(substrate)
        if substrate not in ("cc", "ag"):
            raise ValueError("LabNativeAdapter requires substrate 'cc' or 'ag'")
        self.split_file = split_file
        self.spec = replace(
            lab_spec("cx"),
            install_mode="claude_root" if substrate == "cc" else "antigravity_root",
            allow_subagents=True,
        )
        self.timeout = int(timeout or 3600)
        self.skill_mode = "native"
        self.solver_effort = solver_effort
        self.judge_model = judge_model
        self._deliverables: dict[str, dict[str, str]] = {}
        self._results_root = config.RUNS / "lab" / "results" / substrate
        if substrate == "cc":
            self.model = model or config.SOLVER_MODEL_CC
            self.substrate = ClaudeSubstrate(launcher=self._launch_native)
        else:
            self.model = model or config.SOLVER_MODEL_AG
            self.substrate = AntigravitySubstrate(launcher=self._launch_native)

    def base_harness(self) -> Path:
        """Portable H0; native paths are produced only by substrate materialisation."""
        surface = self.substrate.surface()
        d = self.spec.runs_root / f"_base_harness_{self.substrate.name}_{os.getpid()}"
        if not HT.is_tree(surface, d):
            HT.write_tree(surface, {"AGENTS.md": CODEX_BASE_BODY}, d, stubs=True)
        return d

    def trajectory(self, run_dir: Path, *, obs_trunc: int) -> str:
        name = "claude_session.jsonl" if self.substrate.name == "cc" else "antigravity_session.jsonl"
        stream = Path(run_dir) / name
        if not stream.is_file():
            return f"(no trajectory recorded for {Path(run_dir).name})"
        return self.substrate.read_trajectory(stream, obs_trunc=obs_trunc, max_chars=10**9)

    def _launch_native(self, req, install):
        dirs: list[Path] = []
        read_doc = config.lab_repo() / "opencode" / "scripts" / "read_doc.py"
        if not read_doc.is_file():
            raise RuntimeError(
                f"LAB document reader missing at {read_doc}; run harness2-setup lab"
            )

        for run_id in req.run_ids:
            out = self._run_dir(run_id)
            out.mkdir(parents=True, exist_ok=True)
            workspace = Path(
                tempfile.mkdtemp(prefix=f"h2_lab_{self.substrate.name}_{run_id[:24]}_")
            )
            stream = out / (
                "claude_session.jsonl"
                if self.substrate.name == "cc"
                else "antigravity_session.jsonl"
            )
            stderr_path = out / f"{self.substrate.name}_stderr.log"
            try:
                documents = workspace / "documents"
                source = self.task_files(req.task_ref)
                if source and source.is_dir():
                    shutil.copytree(source, documents)
                else:
                    documents.mkdir(parents=True, exist_ok=True)
                (workspace / "output").mkdir(parents=True, exist_ok=True)
                (workspace / "scripts").mkdir(parents=True, exist_ok=True)
                shutil.copy2(read_doc, workspace / "scripts" / "read_doc.py")
                _copy_overlay(install.staging_dir, workspace)

                prompt = _PROMPT.format(task=self.task_prompt(req.task_ref, max_chars=100_000))
                if self.substrate.name == "cc":
                    argv = self.substrate.exec_argv(prompt, workspace, self.model)
                else:
                    argv = self.substrate.exec_argv(
                        prompt, workspace, self.model, reasoning_effort=self.solver_effort
                    )
                    argv += ["--print-timeout", f"{int(req.timeout)}s"]

                env = _lab_env()
                env["LAB_BENCH_ROOT"] = str(config.lab_repo())
                env["LAB_DOC_PARSER"] = "host"
                if self.substrate.name == "cc" and self.solver_effort:
                    env["CLAUDE_CODE_EFFORT_LEVEL"] = self.solver_effort

                with stream.open("w", encoding="utf-8") as stdout, stderr_path.open(
                    "w", encoding="utf-8"
                ) as stderr:
                    try:
                        proc = subprocess.run(
                            argv,
                            cwd=workspace,
                            env=env,
                            stdin=subprocess.DEVNULL,
                            stdout=stdout,
                            stderr=stderr,
                            timeout=req.timeout,
                        )
                    except subprocess.TimeoutExpired as exc:
                        raise RuntimeError(
                            f"lab-{self.substrate.name} timed out after {req.timeout}s for "
                            f"{req.task_ref} @ {run_id}"
                        ) from exc
                if proc.returncode != 0:
                    raise RuntimeError(
                        f"lab-{self.substrate.name} exited with status {proc.returncode}; "
                        f"see {stderr_path}"
                    )

                produced = workspace / "output"
                if not any(p.is_file() for p in produced.rglob("*")):
                    raise RuntimeError(
                        f"lab-{self.substrate.name} produced no deliverables for "
                        f"{req.task_ref} @ {run_id}; see {stream} and {stderr_path}"
                    )
                final_output = out / "output"
                if final_output.exists():
                    shutil.rmtree(final_output)
                shutil.copytree(produced, final_output)
                (out / "metrics.json").write_text(
                    json.dumps(
                        {
                            "status": "completed",
                            "substrate": self.substrate.name,
                            "model": self.model,
                            "task": req.task_ref,
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                dirs.append(out)
            finally:
                shutil.rmtree(workspace, ignore_errors=True)
        return dirs

    def preflight(self) -> None:
        """Everything needed before a native LAB rollout incurs model cost."""
        self.substrate.preflight()
        if not config.LAB_PYTHON.is_file():
            raise RuntimeError(
                f"LAB interpreter missing at {config.LAB_PYTHON}; run harness2-setup lab"
            )
        read_doc = config.lab_repo() / "opencode" / "scripts" / "read_doc.py"
        parser = config.lab_repo() / "sandbox" / "parsers" / "parse_doc.py"
        if not read_doc.is_file():
            raise RuntimeError(f"LAB document reader missing at {read_doc}; run harness2-setup lab")
        if not parser.is_file():
            raise RuntimeError(f"LAB document parser missing at {parser}; run harness2-setup lab")
        try:
            r = subprocess.run(
                [str(config.LAB_PYTHON), "-c", "import evaluation.scoring"],
                cwd=config.lab_repo(),
                env=_lab_env(),
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"could not probe LAB native dependencies: {exc}") from exc
        if r.returncode != 0:
            raise RuntimeError(
                "LAB native judge dependencies are incomplete; rerun harness2-setup lab"
            )


__all__ = ["LabNativeAdapter"]
