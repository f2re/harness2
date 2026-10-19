# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");

"""Small setup helpers for native substrate overlays.

Kept separate from install.py so benchmark pin/patch logic remains unchanged.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import config


def workbuddy_runner_overlay(repo: Path, *, dry_run: bool = False) -> None:
    """Install release-owned WorkBuddy runner modules after the upstream patch."""
    src = config.THIRD_PARTY / "wb_runner" / "runner"
    dst = Path(repo) / "src" / "workbuddy_bench" / "runner"
    if dry_run:
        print(f"DRY overlay {src} -> {dst}")
        return
    if not src.is_dir():
        raise RuntimeError(f"native WorkBuddy runner overlay missing: {src}")
    shutil.copytree(src, dst, dirs_exist_ok=True)
