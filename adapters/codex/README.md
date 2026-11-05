# Sluice for Codex CLI

The same shunt as the Claude Code plugin, adapted to Codex's hook
surface. Workers, meter, and skills are unchanged: only the
enforcement layer differs, because Codex's tool set differs.

## The one fact that shapes this adapter

Codex's core tool set has no native Read tool. A Codex agent reads
files through the shell (`Bash`, unified exec included) or through an
MCP filesystem tool. So there is no Read hook to port: the bulk-read
surface in Codex is the shell, plus MCP reads. `check-codex.py` is
one script for all three matcher groups, so a single install covers
them.

## What it blocks

- `Bash`: unpiped `cat` / `less` / `more` / `Get-Content` / `gc` /
  `type` against files totalling over the threshold (default 350
  lines, `SLUICE_MIN_LINES`), and `head` / `tail` with an explicit
  `-n` over the threshold. Bare `head` (10 lines), piped reads,
  and targeted counts pass untouched. The `head -n` rule is
  Codex-only: in Codex the shell IS the read path, so
  `head -n 1000 file` is a bulk read, and the Claude Code hook's
  "head alone passes" rule would leave it open.
- `Bash`: `sed -n` windows whose sizes sum over the threshold
  (v0.3.1, built from the June 2026 rollout analysis: `sed -n`
  windows are the bulk-read path in Codex sessions — 96 of 113
  bulk exec outputs, plus 6 more through `nl | sed`, while `cat`
  never exceeded 89 lines). Each window is capped at the file's
  actual length, so `1,1000p` on a 100-line file passes; chained
  windows sum per command, so targeted windows that add up to a
  bulk read block. `sed` without `-n` prints the whole file and
  is treated like `cat`; a `/pattern/p` print is unbounded and
  is sized as the whole file. Targeted windows pass, as does
  `sed` whose output is piped onward.
- Read-shaped tools (`Read`, `read_file`, `read_text_file`) and MCP
  tools whose name contains `read` (`mcp__filesystem__read_text_file`,
  and so on): a path / file_path / paths argument with no targeted
  limit, when the file(s) total over the threshold. A limit <=
  threshold passes, as does a read whose path argument cannot be
  identified — the adapter passes rather than blocking on a guess.

The deny output is the same shape Claude Code accepts
(`hookSpecificOutput.permissionDecision: "deny"` plus legacy
`decision: "block"`), which the official Codex hooks docs also
document for PreToolUse, so the script needed no output change.

## Install

Codex does not (yet) have a Sluice plugin bundle; this is a manual
hooks install, not a marketplace install.

```
mkdir -p ~/.codex/hooks
cp adapters/codex/check-codex.py ~/.codex/hooks/
```

Merge `adapters/codex/hooks.json` into `~/.codex/hooks.json`
(do not overwrite an existing file: Codex loads hooks from all
sources, and a single layer with both `hooks.json` and inline
`[hooks]` in `config.toml` warns at startup, so keep one
representation per layer).

Skills: copy the two skill folders into Codex's skills directory
so the hook's redirect has somewhere to land:

```
cp -r plugins/sluice/skills/bulk-read ~/.codex/skills/
cp -r plugins/sluice/skills/code-write ~/.codex/skills/
```

Then trust the hooks: Codex requires non-managed hooks to be
reviewed and trusted before they run (trust is recorded against
the hook's hash, so editing the script re-prompts). Open `/hooks`
in the Codex CLI and trust the three Sluice groups. For a one-off
test without persisting trust, pass
`--dangerously-bypass-hook-trust` to that invocation only.

Worker environment (`SLUICE_BASE_URL`, `SLUICE_MODEL`,
`SLUICE_API_KEY`, prices, meter file) is exactly as in the main
README. The meter is host-agnostic: `python3 -m sluice.meter report`
works the same after a Codex session.

## Verified, and what is not

- Adapter logic: 36 tests in `tests/test_codex_hook.py`
  (65 total with the Claude Code and Muse Code suites), feeding the adapter
  Codex-shaped payloads from the official hooks docs: Bash string
  and list commands, relative paths resolved against `cwd`,
  `head -n` large and small, `sed -n` windows (targeted pass,
  over-threshold and chained windows block, short-file and
  piped `nl | sed` cases, `rg` / `git diff` passing), MCP single
  and multi-file reads, targeted limits, unidentified reads,
  `apply_patch` passing.
- Hook file: `hooks.json` parses, and Codex 0.164.0 accepts the
  `~/.codex/hooks.json` location (verified by `codex doctor`
  against a test `CODEX_HOME`; doctor does not itself validate
  hooks, so this is a location check, not a hook check).
- A real `codex exec` invocation with the adapter installed and
  `--dangerously-bypass-hook-trust` started cleanly: it printed
  the hook-trust bypass warnings and no hook parse error, then
  failed before any tool call with `ERROR: Reconnecting... 2/5`
  and a 60-second timeout, so the model turn never reached a
  shell read.
- **Not yet verified: a hook firing in a live Codex session.**
  The live-session check — a large shell read actually blocked,
  the bulk-read summary usable, meter showing the session — is
  owed, on a machine where Codex can reach its model. Do not
  claim it until that run happens.

## Not covered (honest gaps, same as the host's own caveat)

Codex's docs call hooks a useful guardrail, not a complete
enforcement boundary, and this adapter inherits that:

- `awk` and `python -c open(...)` reads through the shell are
  not parsed. No bulk cases in the June 2026 rollout corpus
  (0 bulk awk/python reads, against 102 bulk `sed` windows),
  so they stay a stated gap rather than a built rule.
- MCP read tools with argument names other than path / file_path /
  paths are not identified, and MCP tool names and arguments are
  server-dependent, so the MCP rule is best-effort.
- Hosted tools such as WebSearch never reach PreToolUse.
- A `write_stdin` poll of a unified-exec session that already
  passed PreToolUse does not re-run the hook.
- A hook error, timeout, or malformed response fails the hook
  without blocking the tool, per Codex's own docs. The adapter
  therefore fails open on unparseable input rather than
  pretending otherwise.
