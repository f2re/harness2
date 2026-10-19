# Native Claude Code and Antigravity substrates

Harness² supports Claude Code and Google Antigravity as first-class solver substrates across
JobBench, Harvey LAB, and all WorkBuddy-Bench subsets. The adaptation algorithm, selector,
experience library, judge/report pipeline, and portable harness representation remain shared with
the existing OpenCode/Codex cells.

## Support matrix

| Substrate | token | JobBench | LAB | WorkBuddy office/web/code |
|---|---:|---:|---:|---:|
| OpenCode | `oc` | yes | yes | yes |
| Codex | `cx` | yes | yes | yes |
| Claude Code | `cc` | yes | yes | yes |
| Antigravity | `ag` | yes | yes | yes |

Python registry aliases include `opencode`, `codex`, `claude`, `claude-code`, `agy`, and
`antigravity`; public CLI choices remain the compact tokens so namespaces stay stable.

## Portable Harness IR

Claude Code and Antigravity intentionally reuse the Codex-shaped editable Harness IR:

```text
AGENTS.md
.agents/skills/<name>/SKILL.md
.agents/skills/<name>/scripts/*
sub_agents/<name>/AGENT.md
scripts/<name>.py
.codex/hooks.json
```

This is the representation the proposer/composer edits and the experience library stores. The
substrate compiler materialises native files immediately before a rollout.

Claude receives:

```text
CLAUDE.md
.claude/skills/<name>/SKILL.md
.claude/agents/<name>.md
.claude/settings.json
scripts/<name>.py
```

The compiler adds `name: <directory-name>` to a Claude skill when the portable skill omits it.
Use lowercase letters, digits, and hyphens for cross-substrate skill directory names.

Antigravity receives:

```text
AGENTS.md
.agents/skills/<name>/SKILL.md
.agents/agents/<name>/agent.md
.agents/hooks.json
scripts/<name>.py
```

Portable subagents gain missing native `name:` and `subagent: true` metadata. Portable hooks use
Harness²'s normalized Claude/Codex structure and are compiled to Antigravity named hooks. Event,
command, and common tool-matcher translation is supported; runtime-specific hook stdout/control
payloads are not claimed to be semantically identical between Claude/Codex and Antigravity.

## Common model configuration

Harness² still uses OpenCode for proposer/composer sessions, independently of the solver CLI:

```bash
export HARNESS2_IMPROVER_MODEL="google-vertex/<model>"
export HARNESS2_JUDGE_MODEL="<judge-model>"
export GOOGLE_CLOUD_PROJECT="<project>"       # when Vertex is used
```

JobBench/LAB native solvers do not need `HARNESS2_SOLVER_MODEL` unless it is also used as the
improver fallback. WorkBuddy is different: its model/judge proxy is part of the benchmark runtime,
so all WorkBuddy cells keep the normal Vertex solver route and therefore require
`HARNESS2_SOLVER_MODEL=google-vertex/<gemini-model>`.

## Claude Code

For JobBench and LAB, install/authenticate Claude Code normally and ensure `claude` is on `PATH`.
Overrides:

```bash
export HARNESS2_CLAUDE_BIN=claude
export HARNESS2_CLAUDE_MODEL=""  # empty = Claude CLI configured default
```

JobBench/LAB invoke `claude -p` with `stream-json` and autonomous benchmark permissions. WorkBuddy
does **not** use the host Claude installation: setup builds WorkBuddy's pinned Claude Code
`2.1.187` split-mount image and its `CcAgent` sends Anthropic-format requests through the benchmark
local proxy. Consequently the effective WorkBuddy Claude backend is the model named by
`HARNESS2_SOLVER_MODEL`, not `HARNESS2_CLAUDE_MODEL`.

## Antigravity

For JobBench and LAB, install `agy` using Google's supported installer, authenticate once, and keep
it on `PATH`. Overrides:

```bash
export HARNESS2_ANTIGRAVITY_BIN=agy
export HARNESS2_ANTIGRAVITY_MODEL=""  # empty = CLI default
```

Harness² uses `agy -p --output-format stream-json --effort high` and explicitly supplies
`--print-timeout` so Antigravity's shorter headless default does not terminate long benchmark
rollouts.

WorkBuddy cannot depend on a desktop keyring inside Harbor containers. It uses Antigravity's
headless Gemini API-key flow instead:

```bash
export HARNESS2_ANTIGRAVITY_API_KEY="..."   # or GEMINI_API_KEY
export HARNESS2_ANTIGRAVITY_MODEL=""       # optional agy model slug
# optional custom Gemini-compatible endpoint:
export HARNESS2_ANTIGRAVITY_BASE_URL="..." # or GOOGLE_GEMINI_BASE_URL
```

`harness2-setup wb --substrate ag` builds a Linux split-mount image from Google's official
Antigravity CLI installer. The build prints `agy --version`; contract version `1` in Harness²
pins the integration shape, while the upstream installer currently does not expose a documented
version-pinned install URL. Preserve the built Docker image when exact binary reproducibility is
required across repeated experiments.

## Setup

Run setup separately for each benchmark/substrate environment you intend to execute:

```bash
harness2-setup jb  --substrate cc
harness2-setup lab --substrate cc
harness2-setup wb  --substrate cc

harness2-setup jb  --substrate ag
harness2-setup lab --substrate ag
harness2-setup wb  --substrate ag
```

For WorkBuddy, `--subset office|web|code` limits dataset installation. Without it, setup installs
all three subsets. `cc` setup builds `claude-harness/2.1.187`; `ag` setup builds
`antigravity-harness/1`.

Then run the offline readiness gate before spending model calls:

```bash
harness2-check --bench jb  --substrate cc
harness2-check --bench lab --substrate ag
harness2-check --bench wb --subset office --substrate cc
harness2-check --bench wb --subset code   --substrate ag
```

## Running

The normal CLI is unchanged. Examples:

```bash
# JobBench / Claude
harness2 --bench jb --substrate cc --k 1 --mode parallel --max-tasks 1

# LAB / Antigravity
harness2 --bench lab --substrate ag --k 1 --mode parallel --max-tasks 1

# WorkBuddy office / Claude
harness2 --bench wb --subset office --substrate cc --k 1 --mode parallel --max-tasks 1

# WorkBuddy code / Antigravity
harness2 --bench wb --subset code --substrate ag --k 1 --mode parallel --max-tasks 1
```

Use `--dry-run` first to inspect stream order and namespaces without model calls. Judging and
reporting use the same substrate token:

```bash
harness2-judge  --bench lab --substrate ag --k 1 --mode parallel
harness2-report --bench lab --substrate ag --k 1 --mode parallel
```

Add `--subset` for WorkBuddy.

## Benchmark-specific execution contracts

### JobBench

Each rollout receives an isolated temporary workspace containing `task_folder/`, compiled native
harness files, and `output/`. The CLI event stream is persisted in JobBench's trajectory store;
only files under `output/` are copied into the benchmark result directory.

### Harvey LAB

LAB keeps the existing result/scoring contract. Native runners stage `documents/`, `output/`, and
`scripts/read_doc.py`, then write `claude_session.jsonl` or `antigravity_session.jsonl`, the final
`output/`, and a completion `metrics.json` into the standard LAB run directory. LAB's existing
judge/extraction code remains authoritative.

### WorkBuddy

WorkBuddy remains fully Harbor-native so the task environment and verifier are unchanged.
Harness² overlays two installed-agent classes:

- `claude-harness`: subclasses the pinned upstream `CcAgent`, materialises `CLAUDE.md/.claude`,
  then delegates execution and token/ATIF handling to upstream.
- `antigravity-harness`: materialises `AGENTS.md/.agents`, runs the split-mounted `agy` in headless
  mode, stores `agent/agy-output.jsonl`, and leaves scoring to the normal Harbor verifier.

The release-owned runner registry is overlaid during setup so `run.sh` recognizes all adaptive
harness names (`oc-harness`, `codex-harness`, `claude-harness`, `antigravity-harness`).

## Permission and security model

Benchmark solver runs are autonomous. Native launchers use the CLIs' explicit permission-bypass
mode so shell/file operations do not stall on an interactive approval. That is appropriate only
inside benchmark workspaces whose inputs you trust. For ordinary development, prefer scoped CLI
permissions.

Do not place benchmark answer keys, rubric files, or private unrelated material in a workspace.
WorkBuddy Antigravity's API key is injected into the ephemeral Harbor environment; it is not
written into the portable harness or experience library.

## Validation

The repository CI runs Ruff and the complete unittest discovery. Native-specific tests cover:
portable materialisation, skill/subagent/hook compilation, both stream-json parsers, the complete
benchmark/substrate support matrix, LAB native adapter contracts, and generated WorkBuddy native
job configuration. Real model smoke tests remain credentialed integration tests and are not run
by public CI.
