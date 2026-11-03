"""sluice code-write: spec + reference file in, code only out, to disk.

The coordinator never sees the generated code: this script writes it
straight to --out and prints only a small JSON summary (path, lines,
bytes, measured worker tokens/dollars) to stdout. If the worker wraps
the code in a single markdown fence, the fence is stripped before
writing; anything else is written verbatim.

Usage:
    python3 sluice/code_write.py --spec spec.md --reference ref.py --out new_module.py
    python3 sluice/code_write.py --spec spec.md --reference ref.py --out new_module.py --dry-run  # $0, no call
    python3 sluice/code_write.py --spec spec.md --reference ref.py --out new_module.py --task-type implementation
        # --task-type debug|architecture|safety-critical is REFUSED, per the
        # exclusion list (no debugging, no architecture decisions, no
        # safety-critical code, no edits based on summaries).

The spec and reference must be files the user already has; this script
does not fetch anything.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sluice.meter import append_record  # noqa: E402
from sluice.worker import CODE_WRITE_SYSTEM, call_worker  # noqa: E402

REFUSED_TYPES = {"debug", "debugging", "architecture", "safety-critical", "safety", "edit-from-summary"}


def strip_single_fence(text: str) -> str:
    stripped = text.strip()
    match = re.match(r"^```[a-zA-Z0-9_-]*\n(.*)\n```$", stripped, flags=re.DOTALL)
    return match.group(1) if match else text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sluice-code-write")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--task-type", default="implementation")
    parser.add_argument("--dry-run", action="store_true", help="Print the prompt; make no worker call ($0); write nothing.")
    parser.add_argument("--no-meter", action="store_true")
    parser.add_argument("--coordinator-tokens", type=int, default=None)
    parser.add_argument("--meter-file", default=None)
    args = parser.parse_args(argv)
    if args.task_type.strip().lower() in REFUSED_TYPES:
        print(
            f"code-write: refused task-type '{args.task_type}'. Exclusion list: "
            "no debugging, no architecture decisions, no safety-critical code, "
            "no edits based on summaries.",
            file=sys.stderr,
        )
        return 2
    spec = Path(args.spec)
    reference = Path(args.reference)
    out = Path(args.out)
    for f in (spec, reference):
        if not f.is_file():
            print(f"code-write: file not found: {f}", file=sys.stderr)
            return 2
    prompt = (
        f"Spec:\n{spec.read_text(encoding='utf-8', errors='replace')}\n\n"
        f"Reference file ({reference}):\n{reference.read_text(encoding='utf-8', errors='replace')}\n"
    )
    if args.dry_run:
        print(prompt)
        return 0
    result = call_worker(CODE_WRITE_SYSTEM, prompt)
    code = strip_single_fence(result["text"])
    if not code.strip():
        print("code-write: worker returned empty code; wrote nothing.", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(code if code.endswith("\n") else code + "\n", encoding="utf-8")
    lines = code.count("\n") + 1
    summary = json.dumps({
        "out": str(out),
        "lines": lines,
        "bytes": len(code.encode("utf-8")),
        "worker_tokens_measured": result["worker_tokens"],
        "worker_dollars_measured": result["worker_dollars"],
        "model": result["model"],
    })
    print(summary)
    import math as _math
    summary_tokens_estimate = _math.ceil(len(summary) / 4)
    if not args.no_meter:
        # Avoided estimate for code-write: worker output tokens as a proxy
        # for the coordinator output that would otherwise have been spent.
        # Labelled estimate in the meter; it is not a measured coordinator count.
        append_record({
            "kind": "code-write",
            "files": [str(spec), str(reference), str(out)],
            "threshold_lines": 350,
            "decision": "delegated",
            "coordinator_tokens_measured": args.coordinator_tokens,
            "coordinator_summary_tokens_estimate": summary_tokens_estimate,
            "worker_tokens_measured": result["worker_tokens"],
            "worker_dollars_measured": result["worker_dollars"],
            "avoided_tokens_estimate": result["completion_tokens"],
        }, Path(args.meter_file) if args.meter_file else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
