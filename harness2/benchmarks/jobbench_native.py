# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""JobBench runner for headless Claude Code and Antigravity CLI substrates."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from .. import config
from ..core import tree as HT
from ..substrate.antigravity import AntigravitySubstrate
from ..substrate.claude import ClaudeSubstrate
from ..substrate.registry import normalize_substrate
from .jobbench import CX_BASE_HARNESS, JobBenchAdapter, make_spec

_PROMPT = """=== TASK FOLDER ===
{task_folder}

=== INSTRUCTIONS ===
1. Read TASK_INSTRUCTIONS.txt in the task folder.
2. Read every reference file the instructions require.
3. Complete the task exactly as specified.
4. Save only final deliverables to the output directory below.

=== OUTPUT DIRECTORY ===
{output_dir}

IMPORTANT:
- All supplied reference files are under {task_folder}.
- Final deliverables must be written under {output_dir}.
- Do not write deliverables elsewhere.
- Work only inside {workspace}, except for explicitly required public web research.
- For binary office files, use appropriate local tooling to inspect and create them.
- Re-open and verify every deliverable before finishing.
"""


def _copy_overlay(src: Path, dst: Path) -> None:
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


class JobBenchNativeAdapter(JobBenchAdapter):
    """JobBench using `claude -p` or `agy -p` directly.

    The parent adapter continues to own dataset selection, scoring, resume markers,
    artifact extraction and trajectory rendering. This subclass only replaces the
    substrate, base harness, preflight, and launcher body.
    """

    def __init__(
        self,
        substrate: str,
        *,
        timeout: int | None = None,
        store_root: Path | None = None,
        split_file: Path | None = None,
        model: str | None = None,
    ):
        substrate = normalize_substrate(substrate)
        if substrate not in ("cc", "ag"):
            raise ValueError("JobBenchNativeAdapter requires substrate 'cc' or 'ag'")

        self.split_file = split_file
        base = make_spec("cx")
        self.spec = replace(
            base,
            install_mode="claude_root" if substrate == "cc" else "antigravity_root",
            allow_subagents=True,
        )
        self.timeout = int(timeout or 3600)
        self.store = Path(store_root) if store_root else config.RUNS / "jb" / "dataset"

        if substrate == "cc":
            self.model = model or config.SOLVER_MODEL_CC
            self.substrate = ClaudeSubstrate(launcher=self._launch_native)
        else:
            self.model = model or config.SOLVER_MODEL_AG
            self.substrate = AntigravitySubstrate(launcher=self._launch_native)

    def base_harness(self) -> Path:
        surface = self.substrate.surface()
        d = self.spec.runs_root / f"_base_harness_{self.substrate.name}_{os.getpid()}"
        always_on = surface.always_on[0]
        if HT.is_tree(surface, d):
            return d

        source = CX_BASE_HARNESS / "AGENTS.md"
        if source.is_file():
            body = source.read_text(encoding="utf-8", errors="replace")
        else:
            body = (
                "You are an autonomous professional work agent. Read the task instructions, "
                "use the supplied references, create every requested deliverable in the output "
                "directory, and verify the files before finishing.\n"
            )
        HT.write_tree(surface, {always_on: body}, d)
        return d

    def _launch_native(self, req, install):
        task_id, label, timeout = self._launch_common(req)
        self.substrate.preflight()

        task_dir = self._ensure_store_task(task_id)
        final_output = self._out_dir(task_id, label)
        traj_dir = self._traj_dir(task_id, label)
        traj_dir.mkdir(parents=True, exist_ok=True)
        log_dir = self.store / ".harness2-logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        workspace = Path(tempfile.mkdtemp(prefix=f"h2_{self.substrate.name}_{label}_"))
        trajectory = traj_dir / (
            f"{task_id.replace('/', '_')}_{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        )
        log_file = log_dir / f"{self.substrate.name}_{task_id.replace('/', '_')}_{label}.log"

        try:
            shutil.copytree(task_dir, workspace / "task_folder")
            (workspace / "output").mkdir(parents=True, exist_ok=True)
            _copy_overlay(install.staging_dir, workspace)

            prompt = _PROMPT.format(
                task_folder=workspace / "task_folder",
                output_dir=workspace / "output",
                workspace=workspace,
            )
            if self.substrate.name == "cc":
                argv = self.substrate.exec_argv(prompt, workspace, self.model)
            else:
                argv = self.substrate.exec_argv(
                    prompt, workspace, self.model, reasoning_effort="high"
                )
                # Antigravity print mode defaults to five minutes, shorter than a
                # JobBench cell. Keep its internal ceiling aligned with the harness.
                argv += ["--print-timeout", f"{int(timeout)}s"]

            with trajectory.open("w", encoding="utf-8") as out, log_file.open(
                "a", encoding="utf-8"
            ) as err:
                try:
                    proc = subprocess.run(
                        argv,
                        cwd=workspace,
                        stdin=subprocess.DEVNULL,
                        stdout=out,
                        stderr=err,
                        timeout=timeout,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise RuntimeError(
                        f"{self.substrate.name} rollout timed out after {timeout}s for "
                        f"{task_id} @ {label}"
                    ) from exc

            if proc.returncode != 0:
                raise RuntimeError(
                    f"{self.substrate.name} CLI exited with status {proc.returncode}; "
                    f"see {log_file}"
                )

            produced = workspace / "output"
            if not produced.is_dir() or not any(p.is_file() for p in produced.rglob("*")):
                raise RuntimeError(
                    f"{self.substrate.name} produced no JobBench deliverables for "
                    f"{task_id} @ {label}; see {trajectory} and {log_file}"
                )

            final_output.mkdir(parents=True, exist_ok=True)
            for item in sorted(produced.iterdir()):
                target = final_output / item.name
                if item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, target)
            return [final_output]
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    def preflight(self) -> None:
        """Probe the native CLI and the existing JobBench judge environment."""
        self.substrate.preflight()
        judge_py = config.jb_repo() / "eval" / "judge.py"
        if not judge_py.is_file():
            raise RuntimeError(
                f"upstream JobBench judge missing at {judge_py}; "
                "run scripts/setup_benchmark.py jb"
            )
        py = config.JB_JUDGE_PYTHON
        remedy = "python scripts/setup_benchmark.py jb"
        if not py.is_file():
            raise RuntimeError(f"JB judge interpreter missing at {py}; {remedy}")
        try:
            r = subprocess.run(
                [str(py), "-c", "import pandas, openpyxl, docx"],
                capture_output=True,
                text=True,
                timeout=300,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise RuntimeError(f"JB judge interpreter {py} could not be run: {exc}; {remedy}") from exc
        if r.returncode != 0:
            raise RuntimeError(
                f"JB judge interpreter {py} lacks extraction dependencies: "
                f"{r.stderr.strip()[-300:]} -- {remedy}"
            )


__all__ = ["JobBenchNativeAdapter"]
