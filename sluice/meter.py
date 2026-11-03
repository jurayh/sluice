"""Sluice meter: append-only records, and a report that never prints an
estimate without the measured pair beside it.

Record fields:
  ts, kind ("bulk-read" | "code-write"), files, threshold_lines,
  decision, coordinator_tokens_measured (int or null),
  worker_tokens_measured (int or null), worker_dollars_measured (float or null),
  avoided_tokens_estimate (int or null).

Honesty rule, enforced in `report()`: the "avoided" figure is an ESTIMATE
(direct-read cost approximated from file size, chars/4, or, for
code-write, worker output tokens as a proxy for the coordinator output
that would have been spent). Coordinator and worker figures are
MEASURED (provider usage, or a caller-supplied coordinator count).
A record with unknown measured figures keeps nulls; it is never
reported as zero. The report prints measured and estimate columns
together, and its savings ratio is labelled estimate and is only
computed over records where the avoided estimate exists.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_METER_FILE = Path.home() / ".sluice" / "meter.jsonl"


def meter_path() -> Path:
    override = os.environ.get("SLUICE_METER_FILE")
    return Path(override) if override else DEFAULT_METER_FILE


def append_record(record: dict, path: Path | None = None) -> Path:
    path = path or meter_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(record)
    record.setdefault("ts", datetime.now(timezone.utc).isoformat())
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def load_records(path: Path | None = None) -> list[dict]:
    path = path or meter_path()
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def summarise(records: list[dict]) -> dict:
    """Summarise meter records, keeping measured and estimate separate.

    Key correction to an early draft: total tokens (worker input +
    worker output + coordinator summary) EXCEED the avoided direct-read
    tokens by design, because the worker reads the full file. The shunt
    saves coordinator context and, when the worker is cheaper per token,
    dollars -- it does not reduce total tokens. So the headline ratio
    is coordinator-context savings, not total-token savings:
      coordinator_context_saved_ESTIMATE = avoided_ESTIMATE
          - coordinator_summary_tokens (measured if supplied, else
            estimated from the summary text and labelled as such)
      coordinator_context_savings_ratio_ESTIMATE = saved / avoided
    Worker dollars are measured (provider usage x supplied prices, or
    unknown). Dollar savings vs the coordinator are only computable
    when the caller supplies a coordinator price; otherwise the report
    prints worker dollars and avoided tokens side by side and claims
    no dollar saving.
    """
    by_kind: dict[str, dict] = {}
    for rec in records:
        kind = rec.get("kind", "unknown")
        agg = by_kind.setdefault(kind, {
            "records": 0,
            "coordinator_tokens_measured": 0,
            "coordinator_summary_tokens_estimate": 0,
            "worker_tokens_measured": 0,
            "worker_dollars_measured": 0.0,
            "avoided_tokens_estimate": 0,
            "records_with_measured": 0,
            "records_with_avoided": 0,
        })
        agg["records"] += 1
        coord = rec.get("coordinator_tokens_measured")
        if isinstance(coord, int):
            agg["coordinator_tokens_measured"] += coord
            agg["coordinator_summary_tokens_estimate"] += coord
        elif isinstance(rec.get("coordinator_summary_tokens_estimate"), int):
            agg["coordinator_summary_tokens_estimate"] += rec["coordinator_summary_tokens_estimate"]
        if isinstance(rec.get("worker_tokens_measured"), int):
            agg["worker_tokens_measured"] += rec["worker_tokens_measured"]
            agg["records_with_measured"] += 1
        if isinstance(rec.get("worker_dollars_measured"), (int, float)):
            agg["worker_dollars_measured"] += float(rec["worker_dollars_measured"])
        if isinstance(rec.get("avoided_tokens_estimate"), int):
            agg["avoided_tokens_estimate"] += rec["avoided_tokens_estimate"]
            agg["records_with_avoided"] += 1
    total_avoided = sum(a["avoided_tokens_estimate"] for a in by_kind.values())
    total_summary = sum(a["coordinator_summary_tokens_estimate"] for a in by_kind.values())
    total_worker = sum(a["worker_tokens_measured"] for a in by_kind.values())
    saved_estimate = total_avoided - total_summary if total_avoided else None
    ratio_estimate = (saved_estimate / total_avoided) if total_avoided else None
    return {
        "records": len(records),
        "by_kind": by_kind,
        "measured_total_tokens": total_summary + total_worker,
        "worker_tokens_measured": total_worker,
        "coordinator_summary_tokens": total_summary,
        "avoided_tokens_estimate": total_avoided,
        "coordinator_context_saved_estimate": saved_estimate,
        "coordinator_context_savings_ratio_estimate": ratio_estimate,
        # Backwards-compatible aliases for the old net/ratio names, now
        # explicitly coordinator-context, not total-token, figures.
        "net_tokens_estimate": saved_estimate,
        "savings_ratio_estimate": ratio_estimate,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sluice-meter")
    sub = parser.add_subparsers(dest="cmd", required=True)
    rec_p = sub.add_parser("record", help="Append one meter record.")
    rec_p.add_argument("--kind", required=True, choices=["bulk-read", "code-write"])
    rec_p.add_argument("--file", dest="files", action="append", default=[])
    rec_p.add_argument("--threshold-lines", type=int, default=350)
    rec_p.add_argument("--decision", default="delegated")
    rec_p.add_argument("--coordinator-tokens", type=int, default=None)
    rec_p.add_argument("--worker-tokens", type=int, default=None)
    rec_p.add_argument("--worker-dollars", type=float, default=None)
    rec_p.add_argument("--avoided-estimate", type=int, default=None)
    rep_p = sub.add_parser("report", help="Print totals: measured beside estimate, always.")
    rep_p.add_argument("--meter-file", default=None)
    args = parser.parse_args(argv)
    if args.cmd == "record":
        path = append_record({
            "kind": args.kind,
            "files": args.files,
            "threshold_lines": args.threshold_lines,
            "decision": args.decision,
            "coordinator_tokens_measured": args.coordinator_tokens,
            "worker_tokens_measured": args.worker_tokens,
            "worker_dollars_measured": args.worker_dollars,
            "avoided_tokens_estimate": args.avoided_estimate,
        })
        print(f"meter record appended to {path}")
        return 0
    path = Path(args.meter_file) if args.meter_file else meter_path()
    summary = summarise(load_records(path))
    print(f"Sluice meter: {path} ({summary['records']} records)")
    print("kind | records | coordinator_tokens_MEASURED | coordinator_summary_ESTIMATE | worker_tokens_MEASURED | worker_dollars_MEASURED | avoided_tokens_ESTIMATE")
    for kind, agg in sorted(summary["by_kind"].items()):
        print(
            f"{kind} | {agg['records']} | {agg['coordinator_tokens_measured']} | "
            f"{agg['coordinator_summary_tokens_estimate']} | {agg['worker_tokens_measured']} | "
            f"{agg['worker_dollars_measured']:.6f} | {agg['avoided_tokens_estimate']}"
        )
    print(f"COORDINATOR summary tokens (measured where supplied, else estimate): {summary['coordinator_summary_tokens']}")
    print(f"WORKER tokens MEASURED: {summary['worker_tokens_measured']}")
    print(f"AVOIDED tokens (ESTIMATE, never printed alone): {summary['avoided_tokens_estimate']}")
    print("NOTE: total tokens (worker + coordinator summary) exceed avoided by design; the worker reads the full file. Savings are in coordinator context and, when the worker is cheaper per token, in dollars, not in total token count.")
    if summary["coordinator_context_saved_estimate"] is not None:
        print(f"COORDINATOR-CONTEXT SAVED (ESTIMATE = avoided - coordinator summary): {summary['coordinator_context_saved_estimate']}")
        print(f"COORDINATOR-CONTEXT SAVINGS RATIO (ESTIMATE): {summary['coordinator_context_savings_ratio_estimate']:.3f}")
    else:
        print("COORDINATOR-CONTEXT SAVINGS RATIO: not computable (no avoided estimate recorded)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
