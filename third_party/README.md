# Bundled third-party code

This source release contains the derived benchmark runners, compatibility patches, and
upstream license notices distributed with Harness².

| Directory | Source |
|---|---|
| `jb_runner/` | Job-Bench/job-bench-eval |
| `lab_runner/` | harveyai/harvey-labs |
| `wb_runner/` | Tencent/workbuddy-bench |
| `patches/` | Compatibility changes applied to the pinned upstream repositories |
| `licenses/` | License copies covering those patches |

Each runner retains its `LICENSE` and `PROVENANCE.md`. Research logic belongs in
`harness2/core/`; benchmark interfaces belong in `harness2/benchmarks/`.
Setup downloads upstream checkouts and data into the invocation's `dependencies/`
directory. Those downloads are excluded from version control.

`MANIFEST.in` includes the top-level `third_party/` tree and
`dependencies/ASSETS.json` in source distributions so a released source archive retains the
benchmark setup inputs. The Python wheel contains the `harness2` package itself; benchmark setup
should be run from this repository or a source distribution, not from a wheel-only installation.

The repository's `dependencies/ASSETS.json` records bundled asset hashes.
Run `python scripts/check_provenance.py` after changing these files. CI also verifies that every
shipped WorkBuddy runner asset is represented in the manifest.
