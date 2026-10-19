# Setup guide

Start with the [quick start](../README.md#install). This guide covers benchmark
dependencies, model credentials, and all four executor substrates. For individual
benchmarks, see the [benchmark guides](BENCHMARKS.md). Native Claude Code and
Antigravity details are collected in [NATIVE_SUBSTRATES.md](NATIVE_SUBSTRATES.md).

## Requirements

Use Linux and Python 3.12 for benchmark runs; the Python package also supports
3.13. On Debian/Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y git curl unzip ca-certificates pandoc poppler-utils
```

Pandoc and Poppler are needed by LAB. Also install:

- [Node.js](https://nodejs.org/en/download) 20 or newer.
- [uv](https://docs.astral.sh/uv/getting-started/installation/).
- [Google Cloud CLI](https://cloud.google.com/sdk/docs/install).
- [Docker Engine](https://docs.docker.com/engine/install/) for WorkBuddy-Bench,
  with permission to run `docker info`.

Benchmark setup installs its own pinned Bun runtime under `dependencies/`.
Keep the main Harness² environment active when running the commands below.

For host-side Claude Code (`cc`) or Antigravity (`ag`) JobBench/LAB runs, also
install the corresponding CLI. WorkBuddy builds Linux CLI split-mount images and
does not rely on the host CLI executable.

## Models and credentials

Copy `.env.example` to `.env` if you have not already done so. Set your Vertex AI
project and model IDs, then authenticate:

```bash
gcloud auth application-default login
```

Shell environment variables take precedence over `.env`.
`GOOGLE_CLOUD_PROJECT` identifies your project; `GOOGLE_CLOUD_LOCATION` defaults
to `global`. Your account must have access to each configured model.

| Setting | Meaning |
|---|---|
| `HARNESS2_SOLVER_MODEL` | OpenCode executor model in `provider/model` format; also the WorkBuddy model-proxy route |
| `HARNESS2_IMPROVER_MODEL` | Improver model in OpenCode format; defaults to the OpenCode executor |
| `HARNESS2_JUDGE_MODEL` | Bare judge model ID; the adapter supplies the Vertex prefix where required |
| `HARNESS2_CLAUDE_MODEL` | Optional host Claude Code solver model for JobBench/LAB |
| `HARNESS2_ANTIGRAVITY_MODEL` | Optional Antigravity solver model |
| `HARNESS2_ANTIGRAVITY_API_KEY` | WorkBuddy Antigravity Gemini API key; falls back to `GEMINI_API_KEY` |
| `HARNESS2_ANTIGRAVITY_BASE_URL` | Optional Gemini-compatible Antigravity endpoint |
| `HARNESS2_RUNS_DIR` | Output root; defaults to `runs/` |

The provided configuration uses Vertex Gemini executors and judges, and supports
either Vertex Claude or Gemini as the improver. LAB also supports the upstream
judge's direct providers when their credentials are configured. For WorkBuddy,
setup generates the Gemini solver and judge routes from these settings; rerun
setup after changing either model.

### Authentication alternatives

On a machine with a configured attached service account, Application Default
Credentials can use that account. Other options include:

- `gcloud auth application-default login --no-browser`, which prints a command
  to run on another machine that has a browser.
- `GOOGLE_APPLICATION_CREDENTIALS` pointing at a service account key file.
- `gcloud auth application-default login --impersonate-service-account=<account>`.

Keep `gcloud` on `PATH` for these Vertex configurations, including the key-file
route: the installation check runs
`gcloud auth application-default print-access-token`.

## Benchmark installation

Install only the benchmark/substrate cells you intend to run:

```bash
harness2-setup lab --substrate oc
harness2-check --bench lab --substrate oc

harness2-setup lab --substrate cc
harness2-check --bench lab --substrate cc
```

Use `jb` for JobBench or `wb` for WorkBuddy-Bench. Executor tokens are:

- `oc` — OpenCode (default)
- `cx` — Codex
- `cc` — Claude Code
- `ag` — Antigravity

All four are supported by JobBench, LAB, and WorkBuddy. WorkBuddy additionally
requires `--subset office|web|code` for check/run/judge/report; setup can omit
`--subset` to install all three datasets.

The runner overlays and compatibility patches are included in
[`third_party/`](../third_party/README.md). Setup clones supported upstream
revisions under `dependencies/`, applies the patches, creates the benchmark
environments, copies release-owned runner overlays, and downloads task data.

Each benchmark environment lives inside its upstream checkout:

- `dependencies/harvey-labs/.venv`
- `dependencies/job-bench-eval/.venv`
- `dependencies/workbuddy-bench/.venv`

Harness² selects these interpreters automatically; do not activate them for the
main commands.

### Installation checks

`harness2-setup <bench> --dry-run` previews setup without making changes.
`harness2-check` checks installed dependencies, credentials, native CLI/container
configuration, and derived runner files without calling a model. Refinement runs
perform the same checks, including judge configuration, before starting.

These checks do not test model availability. Access to an executor, improver, or
judge model is tested when that model is first called. Refinement and judging
return a nonzero exit status when incomplete.

## Codex executor

The Codex executor connects to a Responses API endpoint. For Gemini on Vertex
AI, the included `harness2-bridge` provides this interface through a local
LiteLLM server, using the same Application Default Credentials and
`GOOGLE_CLOUD_PROJECT`.

Install the optional dependencies and start the bridge in a separate session:

```bash
uv pip install -e '.[render,bridge]'
harness2-bridge                 # for WorkBuddy: harness2-bridge --host 0.0.0.0
```

The bridge prints the `HARNESS2_CODEX_*` settings to add to `.env`. Its port and
generated access key are stored under `dependencies/codex/` and reused on
restart. Pass `--substrate cx` to setup, checks, refinement, judging, and
reporting:

```bash
harness2-setup lab --substrate cx
harness2-check --bench lab --substrate cx
harness2 --bench lab --substrate cx --k 1 --mode parallel \
  --only-domains antitrust-competition --max-tasks 1
```

WorkBuddy executes Codex inside Docker containers, so the bridge must listen on
`--host 0.0.0.0`; it also prints `HARNESS2_CODEX_CONTAINER_URL`. This binds the
bridge to all network interfaces; restrict access to the intended clients.

To use another Responses API endpoint, set `HARNESS2_CODEX_BASE_URL`,
`HARNESS2_CODEX_API_KEY`, and `HARNESS2_CODEX_MODEL` directly. Setup records the
endpoint and model in `dependencies/codex/home/config.toml`; rerun setup after
changing either. `harness2-check` reports stale configuration until then.

## Claude Code executor

For JobBench and LAB, install and authenticate Claude Code normally. Harness²
uses `claude` on `PATH`, or the executable named by `HARNESS2_CLAUDE_BIN`.
`HARNESS2_CLAUDE_MODEL` is optional; when empty, Claude Code uses its configured
default model.

```bash
harness2-setup jb --substrate cc
harness2-check --bench jb --substrate cc
harness2 --bench jb --substrate cc --k 1 --mode parallel --max-tasks 1
```

WorkBuddy does not depend on the host Claude installation. Setup builds the
pinned Claude Code `2.1.187` split-mount image and runs the benchmark's `CcAgent`
through its local Anthropic-compatible model proxy. Therefore WorkBuddy's actual
Claude backend is the `HARNESS2_SOLVER_MODEL` route.

## Antigravity executor

For JobBench and LAB, install Google's Antigravity CLI (`agy`) and authenticate
it normally. Harness² uses `agy` on `PATH`, or
`HARNESS2_ANTIGRAVITY_BIN`. `HARNESS2_ANTIGRAVITY_MODEL` is optional.

```bash
harness2-setup lab --substrate ag
harness2-check --bench lab --substrate ag
harness2 --bench lab --substrate ag --k 1 --mode parallel --max-tasks 1
```

Native headless runs use streaming JSON, `--effort high`, autonomous benchmark
permissions, and an explicit print timeout matching the Harness² rollout budget.

WorkBuddy builds a Linux Antigravity split-mount image and cannot use an
interactive desktop keyring. Set `HARNESS2_ANTIGRAVITY_API_KEY` (or
`GEMINI_API_KEY`) for this cell. An optional custom Gemini-compatible endpoint
can be supplied with `HARNESS2_ANTIGRAVITY_BASE_URL`.

See [NATIVE_SUBSTRATES.md](NATIVE_SUBSTRATES.md) for the portable Harness IR,
container contracts, and reproducibility boundary of the Antigravity installer.

## Network access during setup

Setup downloads dependencies from the following hosts:

| Host | Used for |
|---|---|
| `github.com` | Pinned upstream checkouts |
| `registry.npmjs.org` | Pinned Bun runtime and Codex/Claude-related package builds |
| `antigravity.google` | WorkBuddy Antigravity split-mount build |
| `huggingface.co` and its CDN | JobBench data and WorkBuddy subset archives |
| A Docker registry | WorkBuddy container and split-mount base images |
| `astral.sh` | CPython 3.12 when the host has no system Python 3.12 |

Use `harness2-setup <bench> --dry-run` to review setup commands when configuring
network access. Experiments also access the model endpoints configured in
`.env`. Setup downloads and executor web access have different requirements;
see [web access during evaluation](EXPERIMENTS.md#web-access).

## Wheel installations

A wheel ships the `harness2` package only. The task partitioner,
`python scripts/split_tasks.py`, requires this source tree. The benchmark runner
overlays under `third_party/` are also source-release assets; benchmark setup is
therefore intended from a source checkout. For a wheel-only installation, use
the demo/package APIs or work from a source release containing those assets.
