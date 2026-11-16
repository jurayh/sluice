# Changelog

All notable changes to Sluice will be documented in this file.

## [Unreleased]

- CI: GitHub Actions workflow runs the 84-test unit suite on Python 3.11 and 3.12 on every push and pull request; first run green on both.
- Muse Code adapter: stub-model session harness moved to `adapters/muse/stub/`; re-verified in place, all pass.
- Docs: Muse stub-model session report (Nov 11) — a $0 scripted session in which the hook fires inside a real session loop.
- Tooling: remote-tree verify script kept in `analysis/`.

## [0.3.2] - 2026-11-10

- Muse Code adapter: `sed -n` range rule ported verbatim from the Codex adapter — windows whose sizes sum over the threshold are blocked.
- Note: no Muse session data proves `sed` is the bulk-read path for Muse; stated as such in `adapters/muse/README.md`.

## [0.3.1] - 2026-11-04

- Codex CLI adapter: `sed -n` range rule. The rollout analysis (53 Codex rollouts) showed `sed` windows, not `cat`, are the bulk-read path in Codex sessions; the rule would block 102 of the 113 bulk exec outputs the shipped adapter blocked 0 of.
- Added `analysis/CODEX_ROLLOUT_REPORT.md` with the measurement script and results.

## [0.3.0] - 2026-11-03

- Muse Code adapter (native plugin): one PreToolUse guard for `bash` and `read_file`. Ships as a native plugin bundle (`adapters/muse/plugin/`) or as a project `.muse/hooks.json` pair. Verified on Muse Code 1.4.14: plugin validation clean, offline hook-test harness passes.

## [0.2.0] - 2026-11-03

- Codex CLI adapter: one PreToolUse script for the shell / MCP read surface — unpiped `cat`/`less`/`more`, `head`/`tail` with an explicit `-n` over the threshold, read-shaped and MCP read tools with no targeted limit. 17 adapter tests.

## [0.1.1] - 2026-11-03

- Worker switched to Responses API style.
- Live benchmark PASS: 96.6% coordinator-context savings, 100% identifier accuracy, $0.002021 measured.
- Fixed the token-count bug (`input_tokens`/`output_tokens`).

## [0.1.0] - 2026-11-03

- Initial release: hook-enforced, provider-agnostic token saver with meter. Claude Code plugin (bulk-read and code-write skills), standalone worker (`bulk_read`, `code_write`, `meter`), Phase 0 proxy measurement and stub benchmark.
