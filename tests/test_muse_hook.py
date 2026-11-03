"""Muse Code adapter tests: Muse-shaped payloads, no network, no model.

Payload shapes follow the hook input contract verified 2026-11-03
against Muse Code 1.4.14: JSON on stdin with hook_event_name,
tool_name, tool_input, tool_use_id, session_id, cwd; tool names are
lowercase snake_case (`bash`, `read_file`, from the PreLLMCall tool
list of a real --provider echo run). The live Muse session check is
still owed: these tests prove the adapter against documented /
observed shapes, not against a real model session.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "adapters" / "muse" / "check-muse.py"


def run_hook(payload):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload).encode(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
    )
    assert proc.returncode == 0, proc.stderr.decode()
    out = proc.stdout.decode().strip()
    return json.loads(out) if out else {}


def write_lines(path, n):
    path.write_text("".join(f"line {i}\n" for i in range(n)))


def muse_payload(tool_name, tool_input, cwd=None):
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "01a1a27e-test",
        "tool_name": tool_name,
        "tool_use_id": "call_test",
        "tool_input": tool_input,
    }
    if cwd:
        payload["cwd"] = cwd
    return payload


class TestMuseBash(unittest.TestCase):
    def test_cat_large_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            out = run_hook(muse_payload("bash", {"command": f"cat {f}"}))
            self.assertEqual(out.get("decision"), "block")
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertTrue(out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_cat_small_passes(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "small.py"; write_lines(f, 40)
            self.assertEqual(run_hook(muse_payload("bash", {"command": f"cat {f}"})), {})

    def test_piped_cat_passes(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            self.assertEqual(run_hook(muse_payload("bash", {"command": f"cat {f} | head -20"})), {})

    def test_head_n_large_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            out = run_hook(muse_payload("bash", {"command": f"head -n 1000 {f}"}))
            self.assertEqual(out.get("decision"), "block")

    def test_capitalised_bash_passes(self):
        # Muse tool names are lowercase; a "Bash" payload is not a
        # Muse tool name, so the adapter must not invent a match.
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            self.assertEqual(run_hook(muse_payload("Bash", {"command": f"cat {f}"})), {})


class TestMuseReadFile(unittest.TestCase):
    def test_read_large_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            out = run_hook(muse_payload("read_file", {"path": str(f)}))
            self.assertEqual(out.get("decision"), "block")

    def test_read_small_passes(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "small.py"; write_lines(f, 40)
            self.assertEqual(run_hook(muse_payload("read_file", {"path": str(f)})), {})

    def test_read_window_passes(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            out = run_hook(muse_payload("read_file", {"path": str(f), "start_line": 100, "end_line": 149}))
            self.assertEqual(out, {})

    def test_read_window_large_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            out = run_hook(muse_payload("read_file", {"path": str(f), "start_line": 1, "end_line": 500}))
            self.assertEqual(out.get("decision"), "block")

    def test_read_limit_passes(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            out = run_hook(muse_payload("read_file", {"path": str(f), "limit": 50}))
            self.assertEqual(out, {})

    def test_read_unidentified_passes(self):
        out = run_hook(muse_payload("read_file", {"uri": "file:///x.py"}))
        self.assertEqual(out, {})

    def test_edit_file_passes(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            out = run_hook(muse_payload("edit_file", {"path": str(f), "old_text": "x", "new_text": "y"}))
            self.assertEqual(out, {})


if __name__ == "__main__":
    unittest.main()
