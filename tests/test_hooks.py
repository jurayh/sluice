"""Hook tests: block bulk, pass targeted. No network, no model calls."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / "plugins" / "sluice" / "hooks"


def run_hook(script, payload):
    proc = subprocess.run(
        [sys.executable, str(HOOKS / script)],
        input=json.dumps(payload).encode(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
    )
    assert proc.returncode == 0, proc.stderr.decode()
    out = proc.stdout.decode().strip()
    return json.loads(out) if out else {}


def write_lines(path, n):
    path.write_text("".join(f"line {i}\n" for i in range(n)))


class TestCheckFileSize(unittest.TestCase):
    def test_small_file_passes(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "small.py"; write_lines(f, 40)
            self.assertEqual(run_hook("check-file-size.py", {"tool_name": "Read", "tool_input": {"file_path": str(f)}}), {})

    def test_large_file_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            out = run_hook("check-file-size.py", {"tool_name": "Read", "tool_input": {"file_path": str(f)}})
            self.assertEqual(out.get("decision"), "block")
            self.assertIn("500", out.get("reason", ""))

    def test_targeted_limit_passes_on_large_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            out = run_hook("check-file-size.py", {"tool_name": "Read", "tool_input": {"file_path": str(f), "limit": 50}})
            self.assertEqual(out, {})

    def test_offset_limit_passes_when_limit_small(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            out = run_hook("check-file-size.py", {"tool_name": "Read", "tool_input": {"file_path": str(f), "offset": 100, "limit": 50}})
            self.assertEqual(out, {})

    def test_missing_file_passes(self):
        out = run_hook("check-file-size.py", {"tool_name": "Read", "tool_input": {"file_path": "/nonexistent-xyz/file.py"}})
        self.assertEqual(out, {})

    def test_non_read_tool_passes(self):
        out = run_hook("check-file-size.py", {"tool_name": "Bash", "tool_input": {"command": "ls"}})
        self.assertEqual(out, {})

    def test_threshold_override(self):
        import os
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "mid.py"; write_lines(f, 400)
            env = dict(os.environ, SLUICE_MIN_LINES="500")
            proc = subprocess.run([sys.executable, str(HOOKS / "check-file-size.py")],
                                  input=json.dumps({"tool_name": "Read", "tool_input": {"file_path": str(f)}}).encode(),
                                  stdout=subprocess.PIPE, env=env, timeout=10)
            self.assertEqual(proc.stdout.decode().strip(), "")


class TestCheckBashRead(unittest.TestCase):
    def test_cat_large_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            out = run_hook("check-bash-read.py", {"tool_name": "Bash", "tool_input": {"command": f"cat {f}"}})
            self.assertEqual(out.get("decision"), "block")

    def test_cat_small_passes(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "small.py"; write_lines(f, 40)
            out = run_hook("check-bash-read.py", {"tool_name": "Bash", "tool_input": {"command": f"cat {f}"}})
            self.assertEqual(out, {})

    def test_piped_cat_passes(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            out = run_hook("check-bash-read.py", {"tool_name": "Bash", "tool_input": {"command": f"cat {f} | head -20"}})
            self.assertEqual(out, {})

    def test_head_alone_passes(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            out = run_hook("check-bash-read.py", {"tool_name": "Bash", "tool_input": {"command": f"head {f}"}})
            self.assertEqual(out, {})

    def test_non_read_bash_passes(self):
        out = run_hook("check-bash-read.py", {"tool_name": "Bash", "tool_input": {"command": "python -m pytest -q"}})
        self.assertEqual(out, {})


if __name__ == "__main__":
    unittest.main()
