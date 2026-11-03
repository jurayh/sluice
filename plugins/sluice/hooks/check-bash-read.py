#!/usr/bin/env python3
"""PreToolUse hook: catch cat/head/tail/less/more against large files.

Closes the shell bypass around check-file-size: a coordinator that
cannot Read a 600-line file must not simply `cat` it instead.

Pass-through, untouched (per the spec):
- non-Bash / non-PowerShell tools
- piped commands (`cat file | head -20` is targeted; the pipe limits it)
- head / tail alone (they default to 10 lines)
- commands with no readable file operand, or only missing files
- a file set whose total lines are <= threshold

Blocked:
- an unpiped cat / less / more / Get-Content / gc / type segment
  whose file operands total > threshold lines (SLUICE_MIN_LINES,
  default 350). The reason redirects to the bulk-read skill, as with
  the Read hook.

Parsing is deliberately conservative: segments are split on ;, &&,
|| and newlines outside quotes, and a segment whose first token is
not a read verb is ignored. Quoted semicolons inside a segment are
not split. If parsing cannot identify a file, the segment passes
rather than blocking on a guess.
"""
from __future__ import annotations

import json
import os
import shlex
import sys

DEFAULT_THRESHOLD = 350
READ_VERBS = {"cat", "less", "more", "get-content", "gc", "type"}


def threshold() -> int:
    try:
        return int(os.environ.get("SLUICE_MIN_LINES", DEFAULT_THRESHOLD))
    except ValueError:
        return DEFAULT_THRESHOLD


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


def count_lines(path: str) -> int | None:
    try:
        if not os.path.isfile(path):
            return None
        lines = 0
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                if b"\x00" in chunk[:8192] and lines == 0:
                    return None
                lines += chunk.count(b"\n")
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


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(data, dict):
        return 0
    tool_name = data.get("tool_name") or ""
    tool_input = data.get("tool_input") or data
    if tool_name and tool_name not in ("Bash", "PowerShell"):
        return 0
    if not isinstance(tool_input, dict):
        return 0
    command = tool_input.get("command")
    if not command or not isinstance(command, str):
        return 0
    for segment in split_segments(command):
        if "|" in segment:
            continue  # piped: targeted, passes through
        try:
            tokens = shlex.split(segment, posix=False)
        except ValueError:
            continue
        if not tokens:
            continue
        verb = tokens[0].strip('"').lower()
        if verb not in READ_VERBS:
            continue  # head/tail alone, and everything else, passes
        operands = []
        for tok in tokens[1:]:
            t = tok.strip('"').strip("'")
            if t.startswith("-") or t in (">", ">>", "2>&1"):
                continue
            operands.append(t)
        details = []
        total = 0
        for operand in operands:
            lines = count_lines(operand)
            if lines is not None:
                details.append(f"{operand} ({lines} lines)")
                total += lines
        if details and total > threshold():
            reason = (
                f"Blocked by Sluice: shell read of {', '.join(details)} "
                f"totals {total} lines, over the {threshold()}-line "
                "threshold (SLUICE_MIN_LINES). Do not dump the file(s) "
                "through the shell. Use the bulk-read skill instead, and "
                "use only its structured bullets to continue. Piped and "
                "targeted shell reads still pass."
            )
            block(reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
