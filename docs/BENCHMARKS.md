# Benchmark guides

Complete the [installation and credentials](SETUP.md) first. Each benchmark
installs separately; install the ones you intend to run. Every benchmark supports
all four executor substrates: `oc` (OpenCode, default), `cx` (Codex), `cc`
(Claude Code), and `ag` (Antigravity). Choose the recursion mode with
`--mode parallel` or `--mode sequential` and the task-level recursion budget
with `--k`. Keep benchmark, subset, substrate, recursion mode, budget, and seed
identical across run, judge, and report commands.

Native Claude/Antigravity details are in
[NATIVE_SUBSTRATES.md](NATIVE_SUBSTRATES.md).

## LAB

Upstream: [harveyai/harvey-labs](https://github.com/harveyai/harvey-labs).
Legal work tasks with source documents and rubric-based grading. The adapter
groups tasks by practice area and removes criteria from the material passed to
the improver. Needs Pandoc and Poppler.

```bash
harness2-setup lab --substrate oc
harness2-check --bench lab --substrate oc
harness2 --bench lab --substrate oc --k 1 --mode parallel
harness2-judge --bench lab --substrate oc --k 1 --mode parallel
harness2-report --bench lab --substrate oc --k 1 --mode parallel
```

Use `--substrate cx`, `cc`, or `ag` consistently to select another executor.
Sequential recursion runs the same commands with `--mode sequential`.

Tasks arrive with the pinned checkout at
`dependencies/harvey-labs/tasks/<practice-area>/<task>/task.json`, and the adapter
discovers all installed tasks; no separate task list is required. Setup installs
the LAB dependency environment, runner overlays, and the included Vertex judge
patch.

OpenCode and Codex use the release's existing LAB runtime adapters. Claude Code
and Antigravity use isolated host workspaces with the same LAB result contract:
source material is staged under `documents/`, final artifacts under `output/`,
and `scripts/read_doc.py` provides the benchmark's document extraction path.
Their streaming JSON trajectories are saved beside the run and rendered through
the shared Harness² trajectory grammar.

The judge reads outputs only after selection. Reports use Partial (fraction of
criteria passed) and All-pass (all criteria passed). A failed judge remains
unscored and writes its output to `judge.log` in the run directory; a Vertex
`429 RESOURCE_EXHAUSTED` there means quota, so rerun `harness2-judge` later.
Changing the judge model changes the measurement. Outputs are under
`runs/lab/`.

## JobBench

Upstream: [Job-Bench/job-bench-eval](https://github.com/Job-Bench/job-bench-eval).
Data: [JobBench/job-bench](https://huggingface.co/datasets/JobBench/job-bench).
Professional tasks, with the library grouped by the dataset's occupation
directories.

```bash
harness2-setup jb --substrate cc
harness2-check --bench jb --substrate cc
harness2 --bench jb --substrate cc --k 1 --mode parallel
harness2-judge --bench jb --substrate cc --k 1 --mode parallel
harness2-report --bench jb --substrate cc --k 1 --mode parallel
```

The same sequence works with `oc`, `cx`, or `ag`. Sequential recursion uses
`--mode sequential`.

Setup downloads only the main dataset from Hugging Face — public and ungated, so
no account, token, or terms acceptance is required — records its revision, and
places tasks at `dependencies/job-bench-eval/dataset/main/`. It also installs the
document extraction dependencies and a judge patch that handles reasoning effort
and empty completions. Rubrics stay outside the improver's evidence.

Native Claude/Antigravity runs use isolated temporary workspaces, persist their
streaming event logs in the existing trajectory store, and copy only files from
the designated `output/` directory into the benchmark result tree.

With a Gemini `HARNESS2_JUDGE_MODEL`, the judge uses the project's Vertex
OpenAI-compatible endpoint and Application Default Credentials. For a separate
judge provider, set `HARNESS2_JUDGE_BASE_URL`, `HARNESS2_JUDGE_API_KEY`, and the
model ID that endpoint accepts. The reported score uses the upstream rubric
weights; unscored tasks are reported separately. Results are under `runs/jb/`.

Note: JobBench data, including `RUBRICS.json`, is public on Hugging Face, so an
executor with web access may retrieve it. Block those hosts during runs as
described under [Web access](EXPERIMENTS.md#web-access).

## WorkBuddy-Bench

Upstream: [Tencent/workbuddy-bench](https://github.com/Tencent/workbuddy-bench).
Data: [tencent/workbuddy-bench](https://huggingface.co/datasets/tencent/workbuddy-bench).
Office, web, and code subsets. Needs Docker.

The upstream custom Tencent license includes a territorial limitation; read
[the license](https://github.com/Tencent/workbuddy-bench/blob/main/LICENSE)
before downloading or using the benchmark. Derived runner files and patches
retain that license.

```bash
docker info
harness2-setup wb --subset office --substrate cc
harness2-check --bench wb --subset office --substrate cc
harness2 --bench wb --subset office --substrate cc --k 1 --mode parallel
harness2-judge --bench wb --subset office --substrate cc --k 1 --mode parallel
harness2-report --bench wb --subset office --substrate cc --k 1 --mode parallel
```

Replace `cc` with `oc`, `cx`, or `ag` for another executor. Sequential recursion
uses `--mode sequential`.

`harness2-setup wb` without `--subset` installs all three subsets in one run;
pass `--subset` to install only the one you intend to run. Every other command
takes one subset at a time.

Setup installs the pinned Harbor-based runtime, applies the included adapter,
mount, and credential/transport patches, copies the Harness² runner overlays,
creates solver and judge routes from `.env`, downloads the requested subset, and
builds the substrate-specific split mount where one is required:

- OpenCode builds the pinned OpenCode harness mount.
- Codex uses the existing staged Codex distribution/bridge path.
- Claude Code builds `claude-harness/2.1.187` and delegates execution to the
  pinned upstream `CcAgent` after materialising the compiled Harness² tree.
- Antigravity builds `antigravity-harness/1`, which installs Google's Linux
  `agy` CLI in a read-only split mount and runs it headlessly inside Harbor.

The public Vertex setup uses a `google-vertex/gemini...` executor and a bare
`gemini...` judge ID; no model YAML or account-specific proxy configuration
needs to be copied from another checkout. Setup refuses to run unless
`HARNESS2_SOLVER_MODEL` is a `google-vertex/gemini...` ID and
`HARNESS2_JUDGE_MODEL` a bare `gemini...` one, with `GOOGLE_CLOUD_PROJECT` set;
`--dry-run` reports the requirement and still prints the rest of the plan. The
benchmark's job-local proxy refreshes ADC tokens and preserves Gemini tool-call
thought signatures.

WorkBuddy Claude uses that local model proxy as its effective backend. WorkBuddy
Antigravity instead needs `HARNESS2_ANTIGRAVITY_API_KEY` (or `GEMINI_API_KEY`)
inside the ephemeral Harbor environment; it still uses the standard WorkBuddy
solver/judge configuration for the benchmark infrastructure and judge.

Setup patches the upstream fetch script to download with `curl` (then `wget`,
then `hf`) and to require the dataset repository's `SHA256SUMS`: an archive that
cannot be verified is not unpacked. A verified download prints
`wb-bench-<subset>-v1.0.tar.gz: OK`.

Tasks are discovered from `task.toml` and `instruction.md` under
`dependencies/workbuddy-bench/datasets/wb-bench-<subset>-v1.0/tasks/`. Libraries use
`metadata.role` on code and `metadata.category` on office and web. Each rollout
uses a fresh benchmark container. The adapter reads the verifier's `score.json`;
the improver never receives verifier output. Missing verifier results remain
unscored. Runs live under `runs/wb/<subset>/`.

For Codex, start the bridge with `harness2-bridge --host 0.0.0.0` so the
containers can reach it. Claude and Antigravity do not use this bridge.
