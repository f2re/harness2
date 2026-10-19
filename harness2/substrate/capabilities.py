# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Capability metadata for solver substrates."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capabilities:
    """Features a solver substrate can expose to an editable harness."""

    skills: bool = True
    subagents: bool = True
    hooks: bool = True
    plugins: bool = False
    mcp: bool = True
    streaming_json: bool = True
    resume: bool = False


OPENCODE_CAPABILITIES = Capabilities(plugins=True, resume=True)
CODEX_CAPABILITIES = Capabilities(resume=True)
CLAUDE_CAPABILITIES = Capabilities(resume=True)
ANTIGRAVITY_CAPABILITIES = Capabilities(plugins=True, resume=True)


__all__ = [
    "Capabilities",
    "OPENCODE_CAPABILITIES",
    "CODEX_CAPABILITIES",
    "CLAUDE_CAPABILITIES",
    "ANTIGRAVITY_CAPABILITIES",
]
