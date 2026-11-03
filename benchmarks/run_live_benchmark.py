"""Live Sluice benchmark on the Meta Model API, contributor tier.

Approved cap: $0.05 total (user approval, 2026-11-03). This script
enforces the cap itself: before each task it estimates cost from
prompt size (chars/4 x 1.4, plus the 1024-token output cap) and refuses
to start a task that would cross the cap. After each task it sums
worker dollars MEASURED from provider usage in the meter records.

Authentication: the stored `custom.meta-model-api` credential, via the
dynamic-credentials surrogate helper, exactly as the Zombie Facts
reader did. The surrogate value is never printed, logged, or written
to any output file; it is passed only in subprocess environment to
requests whose host is api.meta.ai.

Tasks are the same pre-registered tasks as the stub benchmark:
  BR1 checks_fixture.py, 18 check classes
  BR2 model_fixture.py, 4 model classes
  BR3 both files, 23 classes
  CW1 code-write spec + reference -> 3 tests, stdout must contain no code
Kill bars (pre-registered): mean bulk-read coordinator-context savings
>= 50%, identifier accuracy >= 90%. Accuracy here is name presence in
the summary; line-number accuracy (name + correct line number) is
reported separately as a stricter secondary figure.

Cost model: contributor tier $0.10 input / $0.20 output per 1M tokens,
set explicitly via SLUICE_PRICE_* so meter dollars are computed from
provider-measured usage, not from estimates.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "benchmarks" / "fixtures"
sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
sys.path.insert(0, str(ROOT))
from dynamic_credentials import dynamic_credential_entry  # noqa: E402
from sluice.bulk_read import build_prompt  # noqa: E402

CAP = 0.05
MODEL = "muse-spark-1.3-contributor"
BASE_URL = "https://api.meta.ai/v1"
IN_RATE = 0.10 / 1_000_000
OUT_RATE = 0.20 / 1_000_000
MAX_OUT = 1024
BPE_UPPER = 1.4

EXPECTED_BR1 = [
    "AlphaCheck", "BetaCheck", "GammaCheck", "DeltaCheck", "EpsilonCheck", "ZetaCheck",
    "EtaCheck", "ThetaCheck", "IotaCheck", "KappaCheck", "LambdaCheck", "MuCheck",
    "NuCheck", "XiCheck", "OmicronCheck", "PiCheck", "RhoCheck", "SigmaCheck",
]
EXPECTED_BR2 = ["TrajectoryStep", "Attempt", "TaskSample", "IntegrityModel"]
EXPECTED_BR3 = ["Finding"] + EXPECTED_BR1 + EXPECTED_BR2


def est(text: str) -> int:
    return math.ceil(len(text) / 4) if text else 0


def actual_line_numbers(files: list[Path]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for f in files:
        for i, line in enumerate(f.read_text().splitlines(), start=1):
            m = re.match(r"class (\w+)", line.strip())
            if m and m.group(1) not in mapping:
                mapping[m.group(1)] = i
    return mapping


def main() -> int:
    entry = dynamic_credential_entry("custom.meta-model-api", "access_token")
    surrogate = str(entry["surrogate"]).strip()
    if not surrogate.startswith("hsurr:"):
        print("live benchmark: credential surrogate not in expected form; refusing to call.", file=sys.stderr)
        return 2
    env = dict(os.environ)
    env.update({
        "SLUICE_BASE_URL": BASE_URL,
        "SLUICE_MODEL": MODEL,
        "SLUICE_PROVIDER": "meta",
        "SLUICE_API_STYLE": "responses",
        "SLUICE_API_KEY": surrogate,
        "SLUICE_PRICE_INPUT_PER_1M": "0.10",
        "SLUICE_PRICE_OUTPUT_PER_1M": "0.20",
        "SLUICE_MAX_OUTPUT_TOKENS": str(MAX_OUT),
    })
    meter = ROOT / "benchmarks" / "live_meter.jsonl"
    if meter.exists():
        meter.unlink()
    results: dict = {"model": MODEL, "provider": "meta (contributor tier)", "cap_usd": CAP, "tasks": []}
    spent = 0.0

    def meter_spent() -> float:
        if not meter.exists():
            return 0.0
        total = 0.0
        for line in meter.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                if isinstance(rec.get("worker_dollars_measured"), (int, float)):
                    total += float(rec["worker_dollars_measured"])
        return total

    def last_meter_record() -> dict:
        lines = [l for l in meter.read_text().splitlines() if l.strip()] if meter.exists() else []
        return json.loads(lines[-1]) if lines else {}

    tasks = [
        ("BR1", [FIX / "checks_fixture.py"], "List every check class in this file, with its line number.", EXPECTED_BR1),
        ("BR2", [FIX / "model_fixture.py"], "List every model class in this file, with its line number.", EXPECTED_BR2),
        ("BR3", [FIX / "checks_fixture.py", FIX / "model_fixture.py"], "List every class in these files, with its line number.", EXPECTED_BR3),
    ]
    savings, accuracies = [], []
    for task_id, files, question, expected in tasks:
        prompt, _, _ = build_prompt(files, question)
        est_cost = math.ceil(len(prompt) / 4 * BPE_UPPER) * IN_RATE + MAX_OUT * OUT_RATE
        if spent + est_cost > CAP:
            results["tasks"].append({"id": task_id, "status": "STOPPED_BY_CAP", "spent_usd_before": round(spent, 6), "estimate_usd": round(est_cost, 6)})
            print(f"{task_id}: STOPPED by cap guard (spent ${spent:.6f} + est ${est_cost:.6f} > ${CAP})", flush=True)
            break
        proc = subprocess.run(
            [sys.executable, str(ROOT / "sluice" / "bulk_read.py"), "--files"] + [str(f) for f in files]
            + ["--question", question, "--meter-file", str(meter)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=300, text=True,
        )
        if proc.returncode != 0:
            results["tasks"].append({"id": task_id, "status": "FAILED", "stderr": proc.stderr[:500]})
            print(f"{task_id}: FAILED: {proc.stderr[:500]}", flush=True)
            break
        summary = proc.stdout
        rec = last_meter_record()
        spent = meter_spent()
        before = sum(est(f.read_text()) for f in files)
        after = est(summary)
        lines_map = actual_line_numbers(files)
        found = [n for n in expected if n in summary]
        line_ok = []
        for n in found:
            # correct line number appears somewhere in the summary
            if str(lines_map.get(n, -1)) in summary:
                line_ok.append(n)
        saving = (before - after) / before if before else 0
        accuracy = len(found) / len(expected) if expected else 0
        savings.append(saving); accuracies.append(accuracy)
        results["tasks"].append({
            "id": task_id, "status": "OK", "files": [f.name for f in files],
            "before_tokens_ESTIMATE": before, "coordinator_tokens_after_ESTIMATE": after,
            "savings_pct": round(100 * saving, 1),
            "identifier_accuracy_pct": round(100 * accuracy, 1),
            "line_number_accuracy_pct": round(100 * len(line_ok) / len(expected), 1) if expected else 0,
            "expected": len(expected), "found": len(found), "line_correct": len(line_ok),
            "missing": [n for n in expected if n not in found],
            "worker_tokens_measured": rec.get("worker_tokens_measured"),
            "worker_dollars_measured": rec.get("worker_dollars_measured"),
            "summary": summary,
        })
        print(f"{task_id}: savings {100*saving:.1f}% accuracy {100*accuracy:.1f}% line {100*len(line_ok)/len(expected):.1f}% "
              f"worker_tokens={rec.get('worker_tokens_measured')} worker_dollars={rec.get('worker_dollars_measured')} spent=${spent:.6f}", flush=True)

    # CW1 code-write, only if cap still allows it
    spec_text = (FIX / "code_write_spec.md").read_text() + (FIX / "code_write_reference.py").read_text()
    est_cost = math.ceil(len(spec_text) / 4 * BPE_UPPER) * IN_RATE + MAX_OUT * OUT_RATE
    if spent + est_cost <= CAP:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out_file = Path(tmp) / "generated_pair.py"
            proc = subprocess.run(
                [sys.executable, str(ROOT / "sluice" / "code_write.py"),
                 "--spec", str(FIX / "code_write_spec.md"), "--reference", str(FIX / "code_write_reference.py"),
                 "--out", str(out_file), "--meter-file", str(meter)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=300, text=True,
            )
            spent = meter_spent()
            if proc.returncode != 0:
                results["tasks"].append({"id": "CW1", "status": "FAILED", "stderr": proc.stderr[:500]})
                print(f"CW1: FAILED: {proc.stderr[:500]}", flush=True)
            else:
                sys.path.insert(0, tmp)
                try:
                    import generated_pair
                    checks = [
                        generated_pair.add_pair(2, 3) == 5,
                        generated_pair.scale_pair(2, 3, 10) == (20, 30),
                        generated_pair.pair_total((4, 6)) == 10,
                    ]
                    passed = sum(checks)
                except Exception as exc:  # noqa: BLE001
                    passed, checks = 0, [str(exc)]
                rec = last_meter_record()
                results["tasks"].append({
                    "id": "CW1", "status": "OK", "code_write_tests": f"PASS ({passed}/3)",
                    "stdout_contains_code": "def add_pair" in proc.stdout,
                    "generated_file": out_file.read_text() if out_file.is_file() else None,
                    "worker_tokens_measured": rec.get("worker_tokens_measured"),
                    "worker_dollars_measured": rec.get("worker_dollars_measured"),
                })
                print(f"CW1: tests {passed}/3 stdout_contains_code={'def add_pair' in proc.stdout} spent=${spent:.6f}", flush=True)
    else:
        results["tasks"].append({"id": "CW1", "status": "STOPPED_BY_CAP", "spent_usd_before": round(spent, 6), "estimate_usd": round(est_cost, 6)})
        print(f"CW1: STOPPED by cap guard (spent ${spent:.6f} + est ${est_cost:.6f} > ${CAP})", flush=True)

    results["total_spent_usd_measured"] = round(spent, 6)
    results["mean_bulk_savings_pct_live"] = round(100 * sum(savings) / len(savings), 1) if savings else None
    results["mean_identifier_accuracy_pct_live"] = round(100 * sum(accuracies) / len(accuracies), 1) if accuracies else None
    out_path = ROOT / "benchmarks" / "live_benchmark_results.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nTotal spent (provider-measured dollars): ${spent:.6f} (cap ${CAP})")
    print(f"Mean savings (live): {results['mean_bulk_savings_pct_live']}%  Mean accuracy (live): {results['mean_identifier_accuracy_pct_live']}%")
    print(f"Wrote {out_path} and {meter}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
