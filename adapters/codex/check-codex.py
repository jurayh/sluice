#!/usr/bin/env python3
"""PreToolUse hook for Codex CLI: block bulk reads, redirect to bulk-read.

Why this is a different script from the Claude Code hooks, not a copy:
Codex has no native Read tool in its core tool set. A Codex agent reads
files through the shell (the `Bash` hook path, unified exec included) or
through an MCP filesystem tool (`mcp__<server>__<tool>`). So the bulk-read
surface here is:

- `Bash` with an unpiped cat / less / more / Get-Content / gc / type
  against files totalling over the threshold, exactly as in Claude Code;
- `Bash` with `head` / `tail` and an explicit line count over the
  threshold (Codex-only addition: in Codex the shell IS the read path,
  so `head -n 1000 file` is a bulk read, not a curiosity. Bare `head`
  still defaults to 10 lines and passes untouched);
- a read-shaped tool (`Read`, `read_file`, or an MCP tool whose name
  contains "read") with a path argument and no targeted limit, when
  the file(s) total over the threshold.

Pass-through, untouched:
- piped commands, targeted reads (limit <= threshold), small files,
  missing or binary files, non-read tools (including `apply_patch`:
  edits are not reads, and Sluice never blocks edits);
- a payload that cannot be parsed, or a read tool whose path argument
  cannot be identified: the hook passes rather than blocking on a guess.
  Codex itself fails a hook open on error, so this matches the host.

Input contract (official Codex hooks docs, verified 2026-11-03 against
codex-cli 0.164.0 docs): one JSON object on stdin with `tool_name` and
`tool_input`. `Bash` and `apply_patch` use `tool_input.command`
(a string; a list form is joined with shlex.join if one arrives).
MCP and other local function tools send their arguments as
`tool_input`. Output contract is the same deny shape Claude Code
accepts: `hookSpecificOutput.permissionDecision: "deny"` plus the
legacy `decision: "block"`, exit 0.

Threshold: SLUICE_MIN_LINES, default 350. Relative paths resolve
against the payload's `cwd` when present, else the process cwd
(Codex runs command hooks with the session cwd).

Not covered, stated here, not buried (see adapters/codex/README.md):
- `sed -n`, `awk`, and `python -c open(...)` reads through the shell;
- MCP read tools whose argument names are not path / file_path /
  paths (server-dependent, so the adapter only blocks what it can
  identify);
- hosted tools such as WebSearch, which never reach PreToolUse;
- `write_stdin` polls of a unified-exec session that already passed
  PreToolUse once.
Codex's own docs call hooks a useful guardrail, not a complete
enforcement boundary. This adapter is that guardrail for bulk reads.
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
PATH_KEYS = ("path", "file_path", "file")
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


def check_bash(command, cwd: str) -> None:
    if isinstance(command, list):
        command = shlex.join(str(c) for c in command)
    if not isinstance(command, str) or not command:
        return
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


def check_read(tool_name: str, tool_input: dict, cwd: str) -> None:
    limit = None
    for key in LIMIT_KEYS:
        value = tool_input.get(key)
        if isinstance(value, (int, float)):
            limit = value
            break
    if limit is not None and limit <= threshold():
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
            "with limit <= threshold still passes."
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
    if tool_name == "Bash":
        command = None
        for key in ("command", "cmd", "shell_command"):
            if key in tool_input:
                command = tool_input[key]
                break
        check_bash(command, cwd)
        return 0
    if tool_name in ("Read", "read", "read_file", "read_text_file") or (
        tool_name.startswith("mcp__") and "read" in tool_name
    ):
        check_read(tool_name, tool_input, cwd)
        return 0
    return 0  # apply_patch, update_plan, hosted tools, everything else


if __name__ == "__main__":
    sys.exit(main())
