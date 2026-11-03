"""Codex adapter tests: Codex-shaped payloads, no network, no model calls.

Payload shapes follow the official Codex hooks docs (PreToolUse:
tool_name + tool_input; Bash uses tool_input.command; MCP tools send
their arguments as tool_input). The live Codex session check is still
owed: these tests prove the adapter against the documented shapes,
not against a real authenticated Codex run.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "adapters" / "codex" / "check-codex.py"


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


def codex_payload(tool_name, tool_input, cwd=None):
    payload = {
        "session_id": "thr_test",
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_use_id": "call_test",
        "tool_input": tool_input,
    }
    if cwd:
        payload["cwd"] = cwd
    return payload


class TestCodexBash(unittest.TestCase):
    def test_cat_large_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            out = run_hook(codex_payload("Bash", {"command": f"cat {f}"}))
            self.assertEqual(out.get("decision"), "block")
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_cat_small_passes(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "small.py"; write_lines(f, 40)
            self.assertEqual(run_hook(codex_payload("Bash", {"command": f"cat {f}"})), {})

    def test_piped_cat_passes(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            self.assertEqual(run_hook(codex_payload("Bash", {"command": f"cat {f} | head -20"})), {})

    def test_head_bare_passes(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            self.assertEqual(run_hook(codex_payload("Bash", {"command": f"head {f}"})), {})

    def test_head_n_large_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            out = run_hook(codex_payload("Bash", {"command": f"head -n 1000 {f}"}))
            self.assertEqual(out.get("decision"), "block")

    def test_head_n_small_passes(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            self.assertEqual(run_hook(codex_payload("Bash", {"command": f"head -n 20 {f}"})), {})

    def test_command_list_form(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            out = run_hook(codex_payload("Bash", {"command": ["cat", str(f)]}))
            self.assertEqual(out.get("decision"), "block")

    def test_relative_path_resolves_against_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            out = run_hook(codex_payload("Bash", {"command": "cat large.py"}, cwd=d))
            self.assertEqual(out.get("decision"), "block")

    def test_apply_patch_passes(self):
        out = run_hook(codex_payload("apply_patch", {"command": "*** Begin Patch\n*** Update File: a.py\n@@\n+line\n*** End Patch"}))
        self.assertEqual(out, {})

    def test_unified_exec_write_stdin_ignored(self):
        # write_stdin never re-runs PreToolUse in Codex; the adapter
        # passes it even if a matching group were registered.
        out = run_hook(codex_payload("write_stdin", {"command": "cat large.py"}))
        self.assertEqual(out, {})


class TestCodexRead(unittest.TestCase):
    def test_mcp_read_large_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            out = run_hook(codex_payload("mcp__filesystem__read_text_file", {"path": str(f)}))
            self.assertEqual(out.get("decision"), "block")

    def test_mcp_read_targeted_passes(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            out = run_hook(codex_payload("mcp__filesystem__read_text_file", {"path": str(f), "limit": 50}))
            self.assertEqual(out, {})

    def test_mcp_read_multiple_files_total_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.py"; write_lines(a, 200)
            b = Path(d) / "b.py"; write_lines(b, 200)
            out = run_hook(codex_payload("mcp__filesystem__read_multiple_files", {"paths": [str(a), str(b)]}))
            self.assertEqual(out.get("decision"), "block")

    def test_mcp_read_unidentified_passes(self):
        out = run_hook(codex_payload("mcp__filesystem__read_text_file", {"uri": "file:///x.py"}))
        self.assertEqual(out, {})

    def test_read_file_tool_large_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            out = run_hook(codex_payload("read_file", {"path": str(f)}))
            self.assertEqual(out.get("decision"), "block")

    def test_non_pretool_event_passes(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "large.py"; write_lines(f, 500)
            payload = codex_payload("Bash", {"command": f"cat {f}"})
            payload["hook_event_name"] = "PostToolUse"
            self.assertEqual(run_hook(payload), {})

    def test_unparseable_passes(self):
        proc = subprocess.run([sys.executable, str(SCRIPT)], input=b"not json",
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.decode().strip(), "")


if __name__ == "__main__":
    unittest.main()
