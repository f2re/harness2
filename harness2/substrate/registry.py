# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Central solver-substrate registry."""

from __future__ import annotations

from typing import TypeAlias

from .antigravity import AntigravitySubstrate
from .base import Launcher, Substrate
from .capabilities import (
    ANTIGRAVITY_CAPABILITIES,
    CLAUDE_CAPABILITIES,
    CODEX_CAPABILITIES,
    OPENCODE_CAPABILITIES,
    Capabilities,
)
from .claude import ClaudeSubstrate
from .codex import CodexSubstrate
from .opencode import OpencodeSubstrate

SUBSTRATE_ALIASES = {
    "oc": "oc",
    "opencode": "oc",
    "cx": "cx",
    "codex": "cx",
    "cc": "cc",
    "claude": "cc",
    "claude-code": "cc",
    "ag": "ag",
    "agy": "ag",
    "antigravity": "ag",
}
SUBSTRATES = ("oc", "cx", "cc", "ag")
BENCHMARK_SUBSTRATES = {
    "jb": SUBSTRATES,
    "lab": ("oc", "cx"),
    "wb": ("oc", "cx"),
}

_CLASSES = {
    "oc": OpencodeSubstrate,
    "cx": CodexSubstrate,
    "cc": ClaudeSubstrate,
    "ag": AntigravitySubstrate,
}
_CAPABILITIES = {
    "oc": OPENCODE_CAPABILITIES,
    "cx": CODEX_CAPABILITIES,
    "cc": CLAUDE_CAPABILITIES,
    "ag": ANTIGRAVITY_CAPABILITIES,
}

SubstrateClass: TypeAlias = (
    type[OpencodeSubstrate]
    | type[CodexSubstrate]
    | type[ClaudeSubstrate]
    | type[AntigravitySubstrate]
)


def normalize_substrate(name: str) -> str:
    try:
        return SUBSTRATE_ALIASES[str(name).strip().lower()]
    except KeyError:
        raise ValueError(
            f"unknown substrate {name!r}; expected one of {', '.join(SUBSTRATES)} "
            "(aliases: opencode, codex, claude, antigravity)"
        ) from None


def substrate_class(name: str) -> SubstrateClass:
    return _CLASSES[normalize_substrate(name)]


def make_substrate(name: str, *, launcher: Launcher | None = None) -> Substrate:
    return substrate_class(name)(launcher=launcher)


def capabilities(name: str) -> Capabilities:
    return _CAPABILITIES[normalize_substrate(name)]


def ensure_benchmark_support(benchmark: str, substrate: str) -> str:
    substrate = normalize_substrate(substrate)
    supported = BENCHMARK_SUBSTRATES.get(benchmark)
    if supported is None:
        raise ValueError(f"unknown benchmark {benchmark!r}")
    if substrate not in supported:
        raise ValueError(
            f"{benchmark} does not yet have a benchmark-specific runner for substrate "
            f"{substrate!r}; supported: {supported}"
        )
    return substrate


__all__ = [
    "SUBSTRATES",
    "BENCHMARK_SUBSTRATES",
    "SUBSTRATE_ALIASES",
    "normalize_substrate",
    "substrate_class",
    "make_substrate",
    "capabilities",
    "ensure_benchmark_support",
]
