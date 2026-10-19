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

"""Solver substrates behind the common interface in substrate/base.py."""

from .antigravity import ANTIGRAVITY_SURFACE, AntigravitySubstrate
from .base import Install, Launcher, RunRequest, Substrate
from .capabilities import Capabilities
from .claude import CLAUDE_SURFACE, ClaudeSubstrate
from .codex import CODEX_SURFACE, CodexSubstrate
from .opencode import OPENCODE_SURFACE, OpencodeSubstrate
from .registry import (
    BENCHMARK_SUBSTRATES,
    SUBSTRATES,
    capabilities,
    ensure_benchmark_support,
    make_substrate,
    normalize_substrate,
    substrate_class,
)

__all__ = [
    "Install",
    "Launcher",
    "RunRequest",
    "Substrate",
    "Capabilities",
    "OpencodeSubstrate",
    "OPENCODE_SURFACE",
    "CodexSubstrate",
    "CODEX_SURFACE",
    "ClaudeSubstrate",
    "CLAUDE_SURFACE",
    "AntigravitySubstrate",
    "ANTIGRAVITY_SURFACE",
    "SUBSTRATES",
    "BENCHMARK_SUBSTRATES",
    "normalize_substrate",
    "substrate_class",
    "make_substrate",
    "capabilities",
    "ensure_benchmark_support",
]
