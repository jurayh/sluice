#!/usr/bin/env python3
"""PreToolUse hook: block a Read over the threshold, redirect to bulk-read.

Reads stdin JSON from Claude Code (tool_name + tool_input, or a bare
tool_input for testing), exits 0 silently when the read may proceed,
and exits 0 with a block JSON when it must not.

Pass-through, untouched:
- non-Read tools
- a missing file (let the tool report the error)
- a binary file (line counting would mislead)
- a Read with an explicit limit <= threshold (targeted read)
- a file with <= threshold lines

Blocked:
- a Read of a file with > threshold lines and no targeted limit.
  The reason tells the coordinator to use the bulk-read skill, which
  runs the bulk-read worker and returns bullets, not file contents.

Threshold: SLUICE_MIN_LINES, default 350. The line count is computed
in streaming chunks, so a 100k-line file costs no full read here.
"""
from __future__ import annotations

import json
import os
import sys

DEFAULT_THRESHOLD = 350


def threshold() -> int:
    try:
        return int(os.environ.get("SLUICE_MIN_LINES", DEFAULT_THRESHOLD))
    except ValueError:
        return DEFAULT_THRESHOLD


def count_lines(path: str) -> int | None:
    """Line count, or None for a missing / binary file."""
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


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # unparseable input: do not block on a hook bug
    if not isinstance(data, dict):
        return 0
    tool_name = data.get("tool_name") or ""
    tool_input = data.get("tool_input") or data
    if tool_name and tool_name != "Read":
        return 0
    if not isinstance(tool_input, dict):
        return 0
    file_path = tool_input.get("file_path")
    if not file_path or not isinstance(file_path, str):
        return 0
    limit = tool_input.get("limit")
    if isinstance(limit, (int, float)) and limit <= threshold():
        return 0  # targeted read, untouched
    lines = count_lines(file_path)
    if lines is None:
        return 0  # missing or binary: let the tool handle it
    if lines <= threshold():
        return 0
    reason = (
        f"Blocked by Sluice: Read of '{file_path}' is {lines} lines, over "
        f"the {threshold()}-line threshold (SLUICE_MIN_LINES). Do not read "
        "the full file. Use the bulk-read skill instead: ask the bulk-read "
        "worker for exactly what you need from this file, and use only its "
        "structured bullets (names, types, line numbers) to continue. "
        "A targeted Read with limit <= threshold still passes."
    )
    block(reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
