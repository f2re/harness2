# workbuddy-bench runner assets

These assets extend the pinned `Tencent/workbuddy-bench` integration and retain its
[upstream license](LICENSE). See the [pinned revision and patches](../../../dependencies/PINNED.md).

Harness² overlays the pinned checkout at setup time. The release-owned files add adaptive
harness installation and the native solver families needed by the cross-substrate experiments:

- `agents/oc_agent.py` and the existing OpenCode harness assets adapt the pinned OpenCode runtime.
- `agents/codex_agent.py` / `codex_harness_agent.py` adapt the pinned Codex CLI runtime.
- `agents/claude_harness_agent.py` subclasses WorkBuddy's pinned upstream `CcAgent`; it only
  materialises the compiled Harness² tree before delegating execution, stream parsing, token
  accounting, and proxy behavior back to upstream.
- `agents/agy_harness_agent.py` is the Harness² Antigravity installed-agent adapter. It executes
  Google's `agy` CLI headlessly inside the Harbor task container and leaves task scoring to the
  normal WorkBuddy verifier.
- `configs/harnesses/claude-harness/` pins Claude Code `2.1.187` and reuses the upstream Claude
  split-mount Dockerfile/settings preset.
- `configs/harnesses/antigravity-harness/` builds a Linux `agy` split-mount image using Google's
  official installer. Integration contract `1` pins the Harness²/WorkBuddy shape; Google's public
  installer currently does not expose a documented version-select argument, so the build records
  `agy --version` and the resulting Docker image should be retained for exact experiment replay.
- `runner/harness_adapters.py` is a complete overlay of WorkBuddy's centralized runtime registry,
  preserving the pinned upstream entries while adding `opencode`, `oc-harness`, `codex-harness`,
  `claude-harness`, and `antigravity-harness`.

Local model-provider names, environment variables, and log paths use the `harness2` namespace.
Credentials are never vendored here. WorkBuddy Antigravity receives its Gemini API key only in the
ephemeral job environment.

[ASSETS.json](../../../dependencies/ASSETS.json) records shipped third-party file checksums.
Verify them with `python scripts/check_provenance.py`.
