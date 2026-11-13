# Sluice for Muse Code

The same shunt as the Claude Code plugin and the Codex adapter,
adapted to Muse Code's hook surface. Workers, meter, and skills are
unchanged: only the enforcement layer differs, because Muse Code's
tool names and plugin format differ.

## What is different here

- Tool names are lowercase snake_case: `bash` and `read_file`
  (not `Bash` / `Read`). Verified 2026-11-03 from a real Muse Code
  1.4.14 binary installed on this VM: a `--provider echo` run's
  PreLLMCall payload lists 31 tools, including `read_file`
  ("Read a line-numbered UTF-8 text file window") and `bash`.
- The hook input shape is the same JSON object on stdin
  (`hook_event_name`, `tool_name`, `tool_input`, `tool_use_id`,
  plus `session_id`, `cwd`, `transcript_path`, `model`,
  `permission_mode`, `turn_id`), and the deny shape is the same
  (`hookSpecificOutput.permissionDecision: "deny"` plus legacy
  `decision: "block"`) — with one Muse strictness: a deny
  requires a non-empty reason, and a bare allow without
  `updatedInput` is rejected, so the script never emits an allow.
- `read_file` parameter names are best-effort, not a published
  contract: Muse publishes no per-tool parameter table, and the
  PreLLMCall tool list carries names and descriptions only. The
  adapter accepts path / file_path / file / filename and a
  window via limit / max_lines / start_line + end_line, and
  passes when it cannot identify the read.

## What it blocks

- `bash`: unpiped `cat` / `less` / `more` / `Get-Content` / `gc` /
  `type` over the threshold (default 350 lines,
  `SLUICE_MIN_LINES`), and `head` / `tail` with an explicit `-n`
  over the threshold. Bare `head`, piped reads, and targeted
  counts pass.
- `bash`: `sed -n` windows whose sizes sum over the threshold
  (v0.3.2, ported verbatim from the Codex adapter: the June 2026
  Codex rollout corpus showed `sed -n` windows are the bulk-read
  path in shell-first agents — 102 of 113 bulk exec outputs
  would block under the rule, while `cat` never exceeded 89
  lines. Each window is capped at the file's actual length,
  chained windows sum per command, `sed` without `-n` is a full
  dump, `/pattern/p` is sized as the whole file, targeted windows
  and piped-onward output pass). The corpus evidence is
  Codex-only: no Muse session data proves `sed` is the Muse
  read path, so this port rests on shared shell-first behaviour,
  not on a measured Muse finding.
- `read_file`: a path argument with no targeted window/limit,
  when the file totals over the threshold. A window or limit <=
  threshold passes. Edits (`edit_file` / `write_file`) pass:
  Sluice never blocks edits.

## Install

Two routes. The plugin route is the one verified here:

```
muse plugins install <path-to-adapters/muse/plugin> --scope user
muse plugins approve sluice
```

`adapters/muse/plugin/` is a native Muse plugin bundle
(`.muse-plugin/plugin.json`, one PreToolUse hook capability,
`hooks/check-muse.py`). `muse plugins validate` reports zero
diagnostics for it.

The project route: copy `adapters/muse/check-muse.py` to
`<workspace>/.muse/hooks/check-muse.py` and
`adapters/muse/hooks.json` to `<workspace>/.muse/hooks.json`.
Project hooks load only when the workspace is trusted
(`--trust-workspace` for a run, or the TUI trust prompt). Do not
add group- or handler-level `description` fields: Muse drops
groups/handlers carrying unknown fields.

Skills: copy `plugins/sluice/skills/bulk-read/` and
`plugins/sluice/skills/code-write/` into a Muse skills directory
(`~/.agents/skills/` or `$XDG_CONFIG_HOME/muse/skills/`) so the
hook's redirect has somewhere to land.

Worker environment (`SLUICE_BASE_URL`, `SLUICE_MODEL`,
`SLUICE_API_KEY`, prices, meter file) is exactly as in the main
README. The meter is host-agnostic.

## Verified, and what is not

- Installed on this VM: Muse Code 1.4.14 (1.4.14-R7309.1),
  from Meta's installer
  (`curl -fsSL https://dev.meta.ai/install.sh`, inspected before
  running, installed into an isolated HOME with
  `MUSE_NO_MODIFY_PATH=1`, auto-update off). Install alone
  needed no sign-in.
- Plugin validation: `muse plugins validate` — zero
  diagnostics, hook recognised (PreToolUse, 10,000 ms timeout).
- Muse's own offline hook harness, `muse plugins hook test`,
  $0, no model, no auth, 15/15 cases as expected:
  block: bash cat of a 500-line file, `head -n 1000` of it,
  `read_file` of it, a `sed -n '1,400p'` window on it, chained
  `sed` windows summing over the threshold, and `nl | sed` on
  it; pass: small cat, piped cat, bare `head`, small read, a
  50-line `read_file` window, a targeted `sed` window, a
  `sed` window past the end of a short file, `rg --files`, and
  an edit of the large file.
- Hook-test fixture quirk found and documented: in 1.4.14 the
  fixture's `stdin` must be a JSON **object**, not a string.
  A string fixture is re-encoded and reaches the script as a
  quoted string, which the script (correctly, for a
  non-object payload) passes — every case silently passed
  until a dump hook showed what the harness actually feeds
  the script. Fixtures used here live outside the repo
  (test-home fixtures), because they name local test files.
- Unit tests: 31 in `tests/test_muse_hook.py` (84 total with
  the Claude Code and Codex suites).
- **Not yet verified: a hook firing in a live Muse Code
  session with a real model.** The echo provider never calls
  tools, so PreToolUse cannot fire in an echo run, and a real
  model run needs Muse Code auth plus a paid-model approval
  under the standing rule. That check — a large read actually
  blocked in a real session, summary usable, meter showing the
  session — is owed. Do not claim it until that run happens.
  What *is* verified since Nov 11, 2026: a scripted stub-model
  session (Muse Code 1.4.15, $0, no real model) in which the
  hook fires inside a real session loop — a 500-line read is
  denied with the bulk-read redirect and no content leaks,
  while a 40-line read passes and executes. The harness lives
  in `stub/` beside this file; the write-up is in
  `../../analysis/MUSE_STUB_SESSION_REPORT.md`.

## Not covered

- `awk` and `python -c open(...)` reads through the shell are
  not parsed (no bulk cases in the June 2026 Codex rollout
  corpus: 0 bulk awk/python reads, against 102 bulk `sed`
  windows).
- `read_file` calls whose parameter names fall outside the
  accepted set pass rather than blocking on a guess.
- Hosted / web tools never reach PreToolUse.
