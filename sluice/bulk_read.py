"""sluice bulk-read: files + a question in, structured bullets out.

The coordinator never receives the file contents, only this script's
output. Usage (from the plugin's bulk-read skill, or directly):
    python3 sluice/bulk_read.py --files a.py b.py --question "List the check classes and their line numbers"
    python3 sluice/bulk_read.py --files a.py --question "..." --dry-run   # $0: print prompt + estimates, call nothing
    python3 sluice/bulk_read.py --files a.py --question "..." --coordinator-tokens 180
        # coordinator_tokens = measured tokens of the summary as the
        # coordinator will consume it, when the caller knows it; null otherwise.

Exclusions (also in the README and the skill): no debugging, no
architecture decisions, no safety-critical code, no edits based on
summaries. This worker only summarises.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sluice.meter import append_record  # noqa: E402
from sluice.worker import BULK_READ_SYSTEM, call_worker  # noqa: E402


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / 4) if text else 0


def build_prompt(files: list[Path], question: str) -> tuple[str, int, int]:
    parts = [f"Question: {question}\n"]
    total_lines = 0
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        raw_lines = text.splitlines()
        total_lines += len(raw_lines)
        # Numbered lines: the worker cites these numbers, so it does not
        # have to count lines itself (a common source of wrong citations).
        numbered = "\n".join(f"{i + 1}| {line}" for i, line in enumerate(raw_lines))
        parts.append(f"\n=== FILE: {f} ({len(raw_lines)} lines) ===\n{numbered}")
    prompt = "\n".join(parts)
    return prompt, total_lines, estimate_tokens(prompt)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sluice-bulk-read")
    parser.add_argument("--files", nargs="+", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--dry-run", action="store_true", help="Print the prompt and estimates; make no worker call ($0).")
    parser.add_argument("--no-meter", action="store_true")
    parser.add_argument("--coordinator-tokens", type=int, default=None)
    parser.add_argument("--meter-file", default=None)
    args = parser.parse_args(argv)
    files = [Path(p) for p in args.files]
    for f in files:
        if not f.is_file():
            print(f"bulk-read: file not found: {f}", file=sys.stderr)
            return 2
    prompt, total_lines, prompt_tokens_est = build_prompt(files, args.question)
    if args.dry_run:
        print(f"files: {[str(f) for f in files]}")
        print(f"total_lines: {total_lines}")
        print(f"prompt_tokens_ESTIMATE (chars/4): {prompt_tokens_est}")
        print("--- prompt (dry run, no worker call) ---")
        print(prompt)
        return 0
    result = call_worker(BULK_READ_SYSTEM, prompt)
    # The summary is the only thing the coordinator sees.
    print(result["text"])
    if not args.no_meter:
        avoided = sum(estimate_tokens(f.read_text(encoding="utf-8", errors="replace")) for f in files)
        append_record({
            "kind": "bulk-read",
            "files": [str(f) for f in files],
            "threshold_lines": 350,
            "decision": "delegated",
            "coordinator_tokens_measured": args.coordinator_tokens,
            "coordinator_summary_tokens_estimate": estimate_tokens(result["text"]),
            "worker_tokens_measured": result["worker_tokens"],
            "worker_dollars_measured": result["worker_dollars"],
            "avoided_tokens_estimate": avoided,
        }, Path(args.meter_file) if args.meter_file else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
