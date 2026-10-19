# Native Claude Code and Antigravity substrates

Harness² can use Claude Code and Google Antigravity as native solver substrates for
JobBench while keeping the existing OpenCode/Codex harnessing algorithm unchanged.

## Support matrix

| Substrate | CLI token | JobBench | LAB | WorkBuddy |
|---|---:|---:|---:|---:|
| OpenCode | `oc` | yes | yes | yes |
| Codex | `cx` | yes | yes | yes |
| Claude Code | `cc` | yes | not yet | not yet |
| Antigravity | `ag` | yes | not yet | not yet |

Aliases accepted by the Python registry include `claude`, `claude-code`, `agy`, and
`antigravity`. The public CLI intentionally exposes the compact tokens so result namespaces
stay short and stable.

## Portable Harness IR

Claude Code and Antigravity do not introduce another editor prompt vocabulary. They share the
canonical Codex-shaped Harness IR:

```text
AGENTS.md
.agents/skills/<name>/SKILL.md
.agents/skills/<name>/scripts/*
sub_agents/<name>/AGENT.md
scripts/<name>.py
.codex/hooks.json
```

The substrate compiler converts that IR immediately before a rollout.

Claude Code receives:

```text
CLAUDE.md
.claude/skills/<name>/SKILL.md
.claude/agents/<name>.md
.claude/settings.json
scripts/<name>.py
```

The compiler adds `name: <directory-name>` to a Claude skill when the portable skill omits it.
For cross-substrate skills, use lowercase letters, digits, and hyphens in directory names.

Antigravity receives:

```text
AGENTS.md
.agents/skills/<name>/SKILL.md
.agents/agents/<name>/agent.md
.agents/hooks.json
scripts/<name>.py
```

Portable subagents gain the required Antigravity `name:` and `subagent: true` fields when
missing. Portable hooks use Harness²'s normalized Claude/Codex shape (`{"hooks": {...}}`);
materialisation compiles it to Antigravity's named-hook schema.

This design keeps proposals, compositions, experience-library entries, validation, and diffs
comparable across Codex, Claude Code, and Antigravity.

## Claude Code prerequisites

Install and authenticate Claude Code normally. Harness² looks for `claude` on `PATH` unless
`HARNESS2_CLAUDE_BIN` points to another executable.

Optional solver configuration:

```bash
export HARNESS2_CLAUDE_BIN=claude
export HARNESS2_CLAUDE_MODEL=""
```

An empty `HARNESS2_CLAUDE_MODEL` lets the Claude CLI use its configured default model.

The Harness² proposer/composer still runs through OpenCode, so configure an improver model in
OpenCode provider/model syntax. It can be independent of the native solver:

```bash
export HARNESS2_IMPROVER_MODEL="google-vertex/gemini-3.5-flash"
```

Configure the judge exactly as for existing JobBench runs.

## Antigravity prerequisites

Install Antigravity CLI and authenticate once interactively so headless `agy` runs can reuse
cached credentials. Harness² looks for `agy` on `PATH` unless
`HARNESS2_ANTIGRAVITY_BIN` is set.

Optional solver configuration:

```bash
export HARNESS2_ANTIGRAVITY_BIN=agy
export HARNESS2_ANTIGRAVITY_MODEL=""
```

An empty model setting leaves model selection to Antigravity. When a model is supplied,
Harness² passes it with `--model`; it also requests `--effort high` for solver rollouts.

## Setup and run

Claude Code:

```bash
harness2-setup jb --substrate cc
harness2-check --bench jb --substrate cc
harness2 --bench jb --substrate cc --k 1 --mode parallel --max-tasks 1
harness2-judge --bench jb --substrate cc --k 1 --mode parallel
harness2-report --bench jb --substrate cc --k 1 --mode parallel
```

Antigravity:

```bash
harness2-setup jb --substrate ag
harness2-check --bench jb --substrate ag
harness2 --bench jb --substrate ag --k 1 --mode parallel --max-tasks 1
harness2-judge --bench jb --substrate ag --k 1 --mode parallel
harness2-report --bench jb --substrate ag --k 1 --mode parallel
```

Use `--dry-run` first to inspect task selection and namespaces without model calls.

## Execution and trajectories

The native JobBench adapter creates an isolated temporary workspace for each rollout, copies the
JobBench task into `task_folder/`, overlays the compiled harness, and requires final artifacts
under `output/`.

Claude Code is launched in print/headless mode with streaming JSON. Antigravity is launched in
headless mode with streaming JSON. Their event streams are persisted in JobBench's existing
`model_traj/<label>/` layout and normalized by each substrate into the shared Harness² trajectory
grammar (`[ASSISTANT]`, `[ACTION]`, `[OBSERVATION]`, `[HARNESS]`, and related tags).

## Permission model

JobBench solver rollouts are autonomous. The native launchers therefore use the CLIs' explicit
permission-bypass flags so shell and file operations do not stall waiting for an interactive
approval. Treat the task workspace and supplied benchmark material as trusted before enabling
this mode, and apply the same network/rubric-access restrictions recommended for existing Codex
experiments.

For ordinary non-benchmark use, prefer scoped permissions instead of blanket approval.

## Current boundary

`cc` and `ag` are intentionally rejected for LAB and WorkBuddy until those benchmarks receive
native runner/container adapters. They are not silently routed through the Codex runner. This
keeps benchmark results attributable to the actual substrate being measured.
