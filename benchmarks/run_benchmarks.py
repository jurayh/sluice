"""Sluice benchmark, $0, with a local mock worker (NOT a live model).

This benchmark proves plumbing, hooks, meter arithmetic, and the
measurement method. It does NOT prove live-model quality or live
savings: the mock worker extracts identifiers deterministically from
the numbered prompt, so its identifier accuracy is 100% by construction
for the extraction task. The live benchmark, with a real worker, uses
the same tasks, the same pre-registered expected lists, and the same
kill bars (mean bulk-read coordinator savings >= 50%, identifier
accuracy >= 90%, hook p95 < 100 ms). Until that live run is approved
and run, the live columns in the README are PENDING, not claimed.

Tasks (pre-registered before running):
  BR1 checks_fixture.py, question: list every check class + line number
      expected: 18 check classes (Alpha..Sigma, excluding Finding)
  BR2 model_fixture.py, question: list every model class + line number
      expected: TrajectoryStep, Attempt, TaskSample, IntegrityModel
  BR3 both files, question: list every class + line number
      expected: BR1 + BR2 + Finding = 23 classes
  CW1 code-write spec + reference -> generated module must pass tests
      for add_pair, scale_pair, pair_total, and stdout must not contain code
  TR  targeted flows must pass both hooks unchanged
  HOOK hook overhead on typical reads

Token figures are chars/4 estimates, labelled as such. Worker tokens
in the mock are computed the same way from the mock prompt/response,
and are therefore also estimates in this stub run, not provider-measured
usage (the mock has no provider). The real worker path returns provider
usage, tested separately in tests/test_worker_client.py.
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "benchmarks" / "fixtures"
sys.path.insert(0, str(ROOT))

EXPECTED_BR1 = [
    "AlphaCheck", "BetaCheck", "GammaCheck", "DeltaCheck", "EpsilonCheck", "ZetaCheck",
    "EtaCheck", "ThetaCheck", "IotaCheck", "KappaCheck", "LambdaCheck", "MuCheck",
    "NuCheck", "XiCheck", "OmicronCheck", "PiCheck", "RhoCheck", "SigmaCheck",
]
EXPECTED_BR2 = ["TrajectoryStep", "Attempt", "TaskSample", "IntegrityModel"]
EXPECTED_BR3 = ["Finding"] + EXPECTED_BR1 + EXPECTED_BR2

CODE_WRITE_CODE = '''"""Generated pair arithmetic module (mock worker output)."""


def add_pair(a, b):
    return a + b


def scale_pair(a, b, factor):
    return (a * factor, b * factor)


def pair_total(pair):
    return pair[0] + pair[1]
'''


def est(text: str) -> int:
    return math.ceil(len(text) / 4) if text else 0


def make_handler():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            try:
                body_in = json.loads(raw.decode())
            except Exception:
                body_in = {}
            user_text = ""
            for msg in body_in.get("messages", []):
                if msg.get("role") == "user":
                    user_text = msg.get("content", "")
            if "Spec:" in user_text and "Reference file" in user_text:
                text = CODE_WRITE_CODE
            else:
                # Deterministic extraction from numbered prompt lines.
                found = []
                for line in user_text.splitlines():
                    m = re.match(r"^(\d+)\| class (\w+)", line.strip())
                    if m:
                        found.append(f"- {m.group(2)} (class, line {m.group(1)})")
                text = "\n".join(found) if found else "Cannot be answered from the files."
            body = json.dumps({
                "choices": [{"message": {"content": text}}],
                "usage": {"prompt_tokens": est(user_text), "completion_tokens": est(text), "total_tokens": est(user_text) + est(text)},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler


def run_bulk_read(files, question, env, meter_file):
    proc = subprocess.run(
        [sys.executable, str(ROOT / "sluice" / "bulk_read.py"), "--files"] + [str(f) for f in files]
        + ["--question", question, "--meter-file", str(meter_file)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=30, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"bulk-read failed: {proc.stderr[:500]}")
    return proc.stdout


def hook_output(script, payload):
    proc = subprocess.run(
        [sys.executable, str(ROOT / "plugins" / "sluice" / "hooks" / script)],
        input=json.dumps(payload).encode(), stdout=subprocess.PIPE, timeout=10,
    )
    return proc.stdout.decode().strip()


def main():
    server = HTTPServer(("127.0.0.1", 0), make_handler())
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    env = dict(__import__("os").environ)
    env.update({
        "SLUICE_BASE_URL": f"http://127.0.0.1:{port}/v1",
        "SLUICE_MODEL": "mock-model",
        "SLUICE_API_KEY": "test",
        "SLUICE_PRICE_INPUT_PER_1M": "0.10",
        "SLUICE_PRICE_OUTPUT_PER_1M": "0.20",
    })
    results = {"worker": "MOCK (local server, $0, NOT a live model)", "tasks": []}
    with tempfile.TemporaryDirectory() as tmp:
        meter = Path(tmp) / "meter.jsonl"
        tasks = [
            ("BR1", [FIX / "checks_fixture.py"], "List every check class in this file, with its line number.", EXPECTED_BR1),
            ("BR2", [FIX / "model_fixture.py"], "List every model class in this file, with its line number.", EXPECTED_BR2),
            ("BR3", [FIX / "checks_fixture.py", FIX / "model_fixture.py"], "List every class in these files, with its line number.", EXPECTED_BR3),
        ]
        savings = []
        accuracies = []
        for task_id, files, question, expected in tasks:
            before = sum(est(f.read_text()) for f in files)
            summary = run_bulk_read(files, question, env, meter)
            after = est(summary)
            found = [name for name in expected if name in summary]
            accuracy = len(found) / len(expected) if expected else 0
            saving = (before - after) / before if before else 0
            savings.append(saving); accuracies.append(accuracy)
            results["tasks"].append({
                "id": task_id, "files": [f.name for f in files],
                "before_tokens_ESTIMATE": before, "coordinator_tokens_after_ESTIMATE": after,
                "savings_pct": round(100 * saving, 1), "identifier_accuracy_pct": round(100 * accuracy, 1),
                "expected": len(expected), "found": len(found),
            })
        # CW1 code-write plumbing
        out_file = Path(tmp) / "generated_pair.py"
        proc = subprocess.run(
            [sys.executable, str(ROOT / "sluice" / "code_write.py"),
             "--spec", str(FIX / "code_write_spec.md"), "--reference", str(FIX / "code_write_reference.py"),
             "--out", str(out_file), "--meter-file", str(meter)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=30, text=True,
        )
        assert proc.returncode == 0, proc.stderr[:500]
        assert "def add_pair" not in proc.stdout, "coordinator stdout must not contain generated code"
        assert out_file.is_file()
        sys.path.insert(0, tmp)
        import generated_pair
        assert generated_pair.add_pair(2, 3) == 5
        assert generated_pair.scale_pair(2, 3, 10) == (20, 30)
        assert generated_pair.pair_total((4, 6)) == 10
        results["tasks"].append({"id": "CW1", "code_write_tests": "PASS (3/3)", "stdout_contains_code": False, "out": str(out_file)})
        # TR targeted flows must pass
        small = FIX / "small_fixture.py"
        large = FIX / "checks_fixture.py"
        targeted = [
            ("check-file-size.py", {"tool_name": "Read", "tool_input": {"file_path": str(small)}}),
            ("check-file-size.py", {"tool_name": "Read", "tool_input": {"file_path": str(large), "limit": 50}}),
            ("check-file-size.py", {"tool_name": "Read", "tool_input": {"file_path": str(large), "offset": 100, "limit": 50}}),
            ("check-bash-read.py", {"tool_name": "Bash", "tool_input": {"command": f"cat {small}"}}),
            ("check-bash-read.py", {"tool_name": "Bash", "tool_input": {"command": f"cat {large} | head -20"}}),
            ("check-bash-read.py", {"tool_name": "Bash", "tool_input": {"command": f"head {large}"}}),
            ("check-bash-read.py", {"tool_name": "Bash", "tool_input": {"command": "python -m pytest -q"}}),
        ]
        passed = sum(1 for script, payload in targeted if hook_output(script, payload) == "")
        results["targeted_flows"] = {"passed": passed, "total": len(targeted)}
        # HOOK overhead: 20 runs each, small (pass) and large (block)
        def time_hook(script, payload, n=20):
            times = []
            for _ in range(n):
                t0 = time.perf_counter()
                hook_output(script, payload)
                times.append((time.perf_counter() - t0) * 1000)
            times.sort()
            return {"p50_ms": round(times[len(times)//2], 1), "p95_ms": round(times[int(len(times)*0.95)-1], 1)}
        results["hook_overhead"] = {
            "small_read_pass": time_hook("check-file-size.py", {"tool_name": "Read", "tool_input": {"file_path": str(small)}}),
            "large_read_block": time_hook("check-file-size.py", {"tool_name": "Read", "tool_input": {"file_path": str(large)}}),
        }
        results["mean_bulk_savings_pct_stub"] = round(100 * sum(savings) / len(savings), 1) if savings else 0
        results["mean_identifier_accuracy_pct_stub"] = round(100 * sum(accuracies) / len(accuracies), 1) if accuracies else 0
        # Meter report from the stub run (measured here = mock usage, labelled in README as stub)
        meter_proc = subprocess.run(
            [sys.executable, "-m", "sluice.meter", "report", "--meter-file", str(meter)],
            stdout=subprocess.PIPE, text=True, cwd=str(ROOT), timeout=10,
        )
        results["meter_report_stub"] = meter_proc.stdout
    server.shutdown()
    out_path = ROOT / "benchmarks" / "benchmark_results.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
