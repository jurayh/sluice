#!/usr/bin/env python3
"""PreToolUse hook for Muse Code: block bulk reads, redirect to bulk-read.

Muse Code's tool names are lowercase snake_case, not Claude/Codex
capitalised names: `bash` for shell and `read_file` for reads
(verified 2026-11-03 from a real Muse Code 1.4.14 binary: a
`--provider echo` run's PreLLMCall payload lists 31 tools, including
`read_file` — "Read a line-numbered UTF-8 text file window" — and
`bash`). The hook input shape is the same JSON object on stdin
(`hook_event_name`, `tool_name`, `tool_input`, `tool_use_id`, plus
`session_id`, `cwd`, `transcript_path`, `model`, `permission_mode`,
`turn_id`), and the deny shape is the same
`hookSpecificOutput.permissionDecision: "deny"` plus legacy
`decision: "block"` — with one Muse-specific strictness: a deny
requires a non-empty reason, and a bare `permissionDecision: "allow"`
without `updatedInput` is rejected, so this script never emits an
allow (it exits silently to allow).

Blocked:
- `bash` with an unpiped cat / less / more / Get-Content / gc / type
  against files totalling over the threshold, and `head` / `tail`
  with an explicit `-n` over the threshold (bare `head` defaults
  to 10 lines and passes);
- `bash` with `sed -n` windows whose sizes sum over the threshold
  (v0.3.2, ported from the Codex adapter: the June 2026 Codex
  rollout corpus showed `sed -n 'A,Bp'` windows, not `cat`, are
  the bulk-read path in shell-first agents — 96 of 113 bulk exec
  outputs, while `cat` never exceeded 89 lines. Window sizes are
  summed per command, so chained targeted windows that add up to
  a bulk read block too, and each window is capped at the file's
  actual length, so a `1,1000p` window on a 100-line file passes.
  A `sed` without `-n` prints the whole file, so it is treated
  like `cat`; a `/pattern/p` print is unbounded, so it is sized
  as the whole file. Targeted windows (<= threshold) pass
  untouched, as does `sed` whose output is piped onward). The
  corpus evidence is Codex-only — no Muse session data proves
  `sed` is the Muse read path; the port rests on the shared
  shell-first behaviour, and is stated as such here and in the
  README, not as a measured Muse finding;
- `read_file` with a path argument and no targeted window/limit,
  when the file totals over the threshold. A window (start/end
  line) or limit <= threshold passes untouched.

Pass-through, untouched:
- piped commands, targeted reads, small files, missing or binary
  files, non-read tools (including `edit_file` / `write_file`:
  edits are not reads, and Sluice never blocks edits);
- a payload that cannot be parsed, or a read whose path argument
  cannot be identified: the hook passes rather than blocking on a
  guess.

Threshold: SLUICE_MIN_LINES, default 350. Relative paths resolve
against the payload's `cwd` when present, else the process cwd.

Parameter names for `read_file` are best-effort, not a published
contract: Muse publishes no per-tool parameter table, and the
PreLLMCall tool list carries names and descriptions only, no
parameter schemas. The adapter therefore accepts every plausible
path key (path, file_path, file, filename) and window key
(limit, max_lines, start_line + end_line, offset + limit), and
passes when it cannot identify the read. See
adapters/muse/README.md for what this does and does not prove.

Not covered, stated here, not buried:
- `awk` and `python -c open(...)` reads through the shell (no bulk
  cases in the June 2026 Codex rollout corpus: 0 bulk awk/python
  reads, against 102 bulk `sed` windows);
- hosted / web tools, which never reach PreToolUse;
- a live Muse Code session with a real model: the echo provider
  never calls tools, so PreToolUse cannot fire in an echo run.
  Verification here is via `muse plugins hook test` fixtures
  (Muse's own offline hook harness, $0, no model, no auth) plus
  unit tests — not a live session. That check is still owed.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys

DEFAULT_THRESHOLD = 350
READ_VERBS = {"cat", "less", "more", "get-content", "gc", "type"}
HEAD_TAIL = {"head", "tail"}
PATH_KEYS = ("path", "file_path", "file", "filename")
LIMIT_KEYS = ("limit", "max_lines", "line_count", "count")


def threshold() -> int:
    try:
        return int(os.environ.get("SLUICE_MIN_LINES", DEFAULT_THRESHOLD))
    except ValueError:
        return DEFAULT_THRESHOLD


def count_lines(path: str, cwd: str) -> int | None:
    """Line count, or None for a missing / binary file."""
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    try:
        lines = 0
        last_byte = b"\n"
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                if b"\x00" in chunk[:8192] and lines == 0:
                    return None  # binary
                lines += chunk.count(b"\n")
                last_byte = chunk[-1:]
        if last_byte != b"\n":
            lines += 1
        return lines
    except OSError:
        return None


def block(reason: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
        "decision": "block",
        "reason": reason,
    }
    print(json.dumps(payload))
    sys.exit(0)


def split_segments(command: str) -> list[str]:
    segments, buf, quote = [], [], None
    i = 0
    while i < len(command):
        ch = command[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif command[i:i + 2] in ("&&", "||"):
            segments.append("".join(buf))
            buf = []
            i += 1
        elif ch in (";", "\n"):
            segments.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    segments.append("".join(buf))
    return [s.strip() for s in segments if s.strip()]


def tokens_of(segment: str) -> list[str]:
    try:
        return [t.strip('"').strip("'") for t in shlex.split(segment, posix=False)]
    except ValueError:
        return []


def head_tail_count(tokens: list[str]) -> int | None:
    """Explicit -n value for head/tail, or None for the 10-line default."""
    i = 1
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("-n", "--lines"):
            if i + 1 < len(tokens):
                m = re.search(r"\d+", tokens[i + 1])
                return int(m.group()) if m else None
            return None
        m = re.match(r"^--lines=(\d+)", tok)
        if m:
            return int(m.group(1))
        m = re.match(r"^-n(\d+)$", tok)
        if m:
            return int(m.group(1))
        m = re.match(r"^-(\d+)$", tok)  # head -20 file, tail -5 file
        if m:
            return int(m.group(1))
        i += 1
    return None


def sed_scripts_and_files(tokens: list[str]) -> tuple[list[str], list[str]]:
    """(scripts, data files) from one sed invocation's tokens.

    Scripts arrive as `-e` / `--expression` arguments or as the bare
    first non-flag argument. `-f` / `--file` names a script file, not
    data, so it and its value are skipped. Everything else non-flag
    after the script is a data file.
    """
    scripts, files = [], []
    i = 1
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("-e", "--expression"):
            if i + 1 < len(tokens):
                scripts.append(tokens[i + 1])
            i += 2
            continue
        if tok.startswith("--expression="):
            scripts.append(tok.split("=", 1)[1])
            i += 1
            continue
        if tok in ("-f", "--file"):
            i += 2
            continue
        if tok.startswith("--file="):
            i += 1
            continue
        if tok.startswith("-") and tok != "-":
            i += 1
            continue
        if not scripts:
            scripts.append(tok)
        else:
            files.append(tok)
        i += 1
    return scripts, files


def sed_quiet(tokens: list[str]) -> bool:
    """True when -n / --quiet / --silent (or a combined -n flag) is set."""
    for tok in tokens[1:]:
        if tok in ("-n", "--quiet", "--silent"):
            return True
        if tok.startswith("-") and not tok.startswith("--") and "n" in tok[1:]:
            return True
    return False


_RANGE_RE = re.compile(r"(\d+)\s*,\s*(\d+)\s*p\b")
_RANGE_DOLLAR_RE = re.compile(r"(\d+)\s*,\s*\$\s*p\b")
_SINGLE_RE = re.compile(r"(?<![\d,])(\d+)\s*p\b")
_PATTERN_RE = re.compile(r"/(?:[^/\\]|\\.)*/\s*p\b")
_SUBST_P_RE = re.compile(r"s/(?:[^/\\]|\\.)*/(?:[^/\\]|\\.)*/[a-z]*p\b")
_BARE_P_RE = re.compile(r"(^|[;{}])\s*p\s*($|[;{}])")


def sed_script_lines(script: str, file_lines: list[int], per_file: bool) -> int:
    """Lines one sed script prints, given the input files' line counts.

    `per_file` is True when sed reads its own file operands (ranges
    reset per file, so each window is capped at each file's length
    and summed); False when sed reads stdin (one stream, so the
    window is capped once at the total stream length). Returns 0
    for a script that prints nothing (e.g. `sed -n '1,10d'`).
    """
    stream = sum(file_lines)

    def window(a: int, b: int) -> int:
        if per_file:
            return sum(max(0, min(b, fl) - a + 1) for fl in file_lines)
        return max(0, min(b, stream) - a + 1)

    def single(a: int) -> int:
        if per_file:
            return sum(1 for fl in file_lines if a <= fl)
        return 1 if a <= stream else 0

    def whole_file() -> int:
        return stream  # per-file and stream agree: every line, once

    total = 0
    rest = script
    for m in _RANGE_DOLLAR_RE.finditer(rest):
        total += window(int(m.group(1)), stream)
    rest = _RANGE_DOLLAR_RE.sub("", rest)
    for m in _RANGE_RE.finditer(rest):
        total += window(int(m.group(1)), int(m.group(2)))
    rest = _RANGE_RE.sub("", rest)
    for m in _SINGLE_RE.finditer(rest):
        total += single(int(m.group(1)))
    rest = _SINGLE_RE.sub("", rest)
    if _PATTERN_RE.search(rest) or _SUBST_P_RE.search(rest):
        total += whole_file()
        rest = _PATTERN_RE.sub("", rest)
        rest = _SUBST_P_RE.sub("", rest)
    if _BARE_P_RE.search(rest):
        total += whole_file()
    return total


def sed_effective_lines(scripts: list[str], files: list[str], cwd: str,
                        quiet: bool, per_file: bool) -> int | None:
    """Lines a sed invocation prints, or None if it cannot be sized.

    Without -n, sed prints the whole input (transformed), so the
    size is the files' total lines regardless of script. With -n,
    only `p` commands print, sized per script above. No sizable
    file (missing files, or no operand at all) means None: the
    caller passes rather than blocking on a guess.
    """
    file_lines = []
    for path in files:
        lines = count_lines(path, cwd)
        if lines is not None:
            file_lines.append(lines)
    if not file_lines:
        return None
    if not quiet:
        return sum(file_lines)
    return sum(sed_script_lines(s, file_lines, per_file) for s in scripts)


def check_sed(command: str, cwd: str) -> None:
    """Block a sed read whose printed lines sum over the threshold.

    Works at pipe-part level: a command is split into segments, each
    segment into `|`-separated parts. A sed part whose output is
    piped onward (e.g. `sed ... | head -20`) passes, matching the
    piped-read rule elsewhere. A sed part reading stdin (e.g.
    `nl -ba file | sed -n '1,520p'`) is sized against the file
    operands found elsewhere in the command, as one stream.
    Window sizes sum across all sed parts in the command, so
    chained targeted windows that add up to a bulk read block.
    """
    if not isinstance(command, str) or not command:
        return
    parts: list[tuple[list[str], bool]] = []  # (tokens, has_later_part)
    for segment in split_segments(command):
        tokens = tokens_of(segment)
        current: list[str] = []
        segment_parts: list[list[str]] = []
        for tok in tokens:
            if tok == "|":
                segment_parts.append(current)
                current = []
            else:
                current.append(tok)
        segment_parts.append(current)
        for idx, part in enumerate(segment_parts):
            if part:
                parts.append((part, idx < len(segment_parts) - 1))
    total = 0
    sized = False
    for tokens, piped_onward in parts:
        if not tokens or os.path.basename(tokens[0]).lower() != "sed":
            continue
        if piped_onward:
            continue
        scripts, own_files = sed_scripts_and_files(tokens)
        quiet = sed_quiet(tokens)
        if own_files:
            effective = sed_effective_lines(
                scripts, own_files, cwd, quiet, per_file=True)
        else:
            upstream: list[str] = []
            for other, _ in parts:
                if other is tokens:
                    continue
                upstream.extend(
                    t for t in other[1:]
                    if not t.startswith("-") and t != "|")
            effective = sed_effective_lines(
                scripts, upstream, cwd, quiet, per_file=False)
        if effective is None:
            continue
        sized = True
        total += effective
    if sized and total > threshold():
        block(
            f"Blocked by Sluice: sed window(s) totalling {total} lines, "
            f"over the {threshold()}-line threshold (SLUICE_MIN_LINES). "
            "Do not dump the file(s) through the shell. Use the "
            "bulk-read skill instead, and use only its structured "
            "bullets to continue. Targeted sed windows (<= threshold) "
            "and piped output still pass."
        )



def check_bash(command, cwd: str) -> None:
    if isinstance(command, list):
        command = shlex.join(str(c) for c in command)
    if not isinstance(command, str) or not command:
        return
    check_sed(command, cwd)
    for segment in split_segments(command):
        if "|" in segment:
            continue  # piped: targeted, passes through
        tokens = tokens_of(segment)
        if not tokens:
            continue
        verb = tokens[0].lower()
        if verb in READ_VERBS:
            operands = [t for t in tokens[1:]
                        if not t.startswith("-") and t not in (">", ">>", "2>&1")]
            details, total = [], 0
            for operand in operands:
                lines = count_lines(operand, cwd)
                if lines is not None:
                    details.append(f"{operand} ({lines} lines)")
                    total += lines
            if details and total > threshold():
                block(
                    f"Blocked by Sluice: shell read of {', '.join(details)} "
                    f"totals {total} lines, over the {threshold()}-line "
                    "threshold (SLUICE_MIN_LINES). Do not dump the file(s) "
                    "through the shell. Use the bulk-read skill instead, and "
                    "use only its structured bullets to continue. Piped and "
                    "targeted shell reads still pass."
                )
        elif verb in HEAD_TAIL:
            wanted = head_tail_count(tokens)
            if wanted is None or wanted <= threshold():
                continue  # default 10, or a targeted count: passes
            operands = [t for t in tokens[1:]
                        if not re.match(r"^-", t) and not t.isdigit()]
            details, total = [], 0
            for operand in operands:
                lines = count_lines(operand, cwd)
                if lines is not None:
                    details.append(f"{operand} ({lines} lines)")
                    total += lines
            if details and total > threshold():
                block(
                    f"Blocked by Sluice: {verb} -n {wanted} of "
                    f"{', '.join(details)} totals {total} lines, over the "
                    f"{threshold()}-line threshold (SLUICE_MIN_LINES). Do "
                    "not dump the file(s) through the shell. Use the "
                    "bulk-read skill instead, and use only its structured "
                    "bullets to continue. A targeted count (<= threshold) "
                    "still passes."
                )


def window_size(tool_input: dict) -> int | None:
    """Targeted window/limit size, or None when the read is unbounded."""
    for key in LIMIT_KEYS:
        value = tool_input.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    start = tool_input.get("start_line")
    end = tool_input.get("end_line")
    if isinstance(start, (int, float)) and isinstance(end, (int, float)):
        return int(end) - int(start) + 1
    start = tool_input.get("start")
    end = tool_input.get("end")
    if isinstance(start, (int, float)) and isinstance(end, (int, float)):
        return int(end) - int(start) + 1
    return None


def check_read(tool_name: str, tool_input: dict, cwd: str) -> None:
    size = window_size(tool_input)
    if size is not None and size <= threshold():
        return  # targeted read, untouched
    paths: list[str] = []
    for key in PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            paths.append(value)
    value = tool_input.get("paths")
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item:
                paths.append(item)
            elif isinstance(item, dict):
                for key in PATH_KEYS:
                    if isinstance(item.get(key), str):
                        paths.append(item[key])
    if not paths:
        return  # unidentified read: pass rather than block on a guess
    details, total = [], 0
    for path in paths:
        lines = count_lines(path, cwd)
        if lines is not None:
            details.append(f"{path} ({lines} lines)")
            total += lines
    if details and total > threshold():
        block(
            f"Blocked by Sluice: {tool_name} of {', '.join(details)} "
            f"totals {total} lines, over the {threshold()}-line threshold "
            "(SLUICE_MIN_LINES). Do not read the full file(s). Use the "
            "bulk-read skill instead, and use only its structured bullets "
            "(names, types, line numbers) to continue. A targeted read "
            "with a window <= threshold still passes."
        )


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # unparseable input: do not block on a hook bug
    if not isinstance(data, dict):
        return 0
    event = data.get("hook_event_name") or data.get("hookEventName") or ""
    if event and event != "PreToolUse":
        return 0
    tool_name = data.get("tool_name") or ""
    tool_input = data.get("tool_input") or data
    if not isinstance(tool_input, dict):
        return 0
    cwd = data.get("cwd") or os.getcwd()
    if not isinstance(cwd, str):
        cwd = os.getcwd()
    if tool_name == "bash":
        command = None
        for key in ("command", "cmd", "shell_command"):
            if key in tool_input:
                command = tool_input[key]
                break
        check_bash(command, cwd)
        return 0
    if tool_name in ("read_file", "read"):
        check_read(tool_name, tool_input, cwd)
        return 0
    return 0  # edit_file, write_file, search, subagents, everything else


if __name__ == "__main__":
    sys.exit(main())
