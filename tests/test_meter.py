"""Meter tests: measured and estimate stay separate, never zero-filled."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sluice.meter import summarise


class TestMeter(unittest.TestCase):
    def test_report_keeps_estimate_labelled_and_unknown_as_null(self):
        records = [
            {"kind": "bulk-read", "coordinator_tokens_measured": 180, "worker_tokens_measured": 900,
             "worker_dollars_measured": 0.0002, "avoided_tokens_estimate": 5000},
            {"kind": "bulk-read", "coordinator_tokens_measured": None,
             "coordinator_summary_tokens_estimate": 120, "worker_tokens_measured": 400,
             "worker_dollars_measured": None, "avoided_tokens_estimate": 2000},
        ]
        s = summarise(records)
        # Coordinator-context saved = avoided - coordinator summary (180 + 120), NOT avoided - total tokens.
        self.assertEqual(s["coordinator_context_saved_estimate"], 7000 - 300)
        self.assertEqual(s["avoided_tokens_estimate"], 7000)
        self.assertAlmostEqual(s["coordinator_context_savings_ratio_estimate"], (7000 - 300) / 7000)

    def test_no_avoided_means_no_ratio(self):
        s = summarise([{"kind": "code-write", "coordinator_tokens_measured": 10, "worker_tokens_measured": 20}])
        self.assertIsNone(s["coordinator_context_savings_ratio_estimate"])


if __name__ == "__main__":
    unittest.main()
