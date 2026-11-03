"""Worker client tests against a local mock OpenAI-compatible server ($0)."""
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sluice.worker import call_worker, resolve_config
import os


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        body = json.dumps({
            "choices": [{"message": {"content": "- AlphaCheck (class, line 12)"}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 50, "total_tokens": 1050},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class TestWorkerClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_call_returns_measured_usage_and_dollars_only_with_prices(self):
        os.environ.update({
            "SLUICE_BASE_URL": f"http://127.0.0.1:{self.port}/v1",
            "SLUICE_MODEL": "mock-model",
            "SLUICE_API_KEY": "test",
            "SLUICE_PRICE_INPUT_PER_1M": "0.10",
            "SLUICE_PRICE_OUTPUT_PER_1M": "0.20",
        })
        result = call_worker("system", "user")
        self.assertIn("AlphaCheck", result["text"])
        self.assertEqual(result["worker_tokens"], 1050)
        self.assertAlmostEqual(result["worker_dollars"], 1000 * 0.10 / 1e6 + 50 * 0.20 / 1e6)

    def test_no_prices_means_dollars_unknown_not_zero(self):
        os.environ.pop("SLUICE_PRICE_INPUT_PER_1M", None)
        os.environ.pop("SLUICE_PRICE_OUTPUT_PER_1M", None)
        os.environ.update({
            "SLUICE_BASE_URL": f"http://127.0.0.1:{self.port}/v1",
            "SLUICE_MODEL": "mock-model",
            "SLUICE_API_KEY": "test",
        })
        result = call_worker("system", "user")
        self.assertIsNone(result["worker_dollars"])


if __name__ == "__main__":
    unittest.main()


class ResponsesHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        body = json.dumps({
            "output": [{"content": [{"type": "output_text", "text": "- BetaCheck (class, line 40)"}]}],
            "usage": {"input_tokens": 2000, "output_tokens": 40, "total_tokens": 2040},
            "status": "completed",
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class TestWorkerResponsesStyle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), ResponsesHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_responses_shape_parses_output_text_and_usage(self):
        os.environ.update({
            "SLUICE_BASE_URL": f"http://127.0.0.1:{self.port}/v1",
            "SLUICE_MODEL": "mock-model",
            "SLUICE_API_KEY": "test",
            "SLUICE_API_STYLE": "responses",
            "SLUICE_MAX_OUTPUT_TOKENS": "1024",
        })
        try:
            result = call_worker("system", "user")
        finally:
            os.environ.pop("SLUICE_API_STYLE", None)
            os.environ.pop("SLUICE_MAX_OUTPUT_TOKENS", None)
        self.assertIn("BetaCheck", result["text"])
        self.assertEqual(result["worker_tokens"], 2040)
