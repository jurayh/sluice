#!/usr/bin/env python3
"""Scripted stub for Muse's meta provider (Responses API, SSE).

Lets a real `muse exec` session run end to end with no model, no
auth, and $0 cost, so the Sluice PreToolUse hook can be observed
firing inside a live session loop.

The SSE shape here is copied byte-for-byte in structure from one
approved capture call to the real API (POST /v1/responses,
muse-spark-1.3-contributor, "Say hi", 16 output tokens,
~$0.000004; saved at stub/real-sse.txt). The three things the
first stub got wrong, and that made Muse reject every stream
with a bare "decode" error, were:
  1. the real stream carries an `event: <type>` line before each
     `data:` line — data-only frames are rejected;
  2. every event carries a top-level `sequence_number`
     (0, 1, 2, ... per response), as a sibling of `type`;
  3. the Response object has an exact 22-key shape (no
     `metadata`, `text`, `previous_response_id`, `completed_at`,
     `user`, `max_tool_calls`, `status_details`; `created_at` is
     a float; `reasoning` is `{"effort": ...}` with no `summary`
     key; `service_tier` is "default"; `store` is true;
     `truncation` is "disabled"; `top_logprobs` is 0; `usage`
     appears only on the terminal event). The stream also emits
     `response.in_progress` after `response.created`, and the
     first output item is a `reasoning` item.

Endpoints
  GET  /muse-code/models  -> the real catalog shape (catalog.json,
                             fetched once from api.meta.ai; public
                             model metadata, no secrets)
  POST /responses         -> SSE stream of Responses API events.
                             Request N=1 emits a scripted function
                             call; later requests emit a final text
                             answer so the session ends.

Scenario (read fresh on every /responses request, so runs can
switch without restarting the server): scenario.txt beside this
script contains "big", "small", "text", or "created-only"
(absent = "big"). "big" = read_file on the 500-line
fixtures/big.py (hook must deny); "small" = read_file on the
40-line fixtures/small.py (hook must pass and the tool must
execute); "text" = a plain text answer (framing check);
"created-only" = only response.created, then close (diagnostic:
a decode error there means the created event itself is wrong).
The replay-* scenarios re-serve the captured real bytes in
real-sse.txt (verbatim, or mutated) and exist to bisect the SSE
shape; they are not part of a normal verification run.

Every request body is saved raw to requests/raw-NNN.json, and a
one-line summary to requests.log, so the tool result / denial
the session feeds back can be inspected after the run.

Usage (from this directory; the plugin must already be
installed and approved in the Muse home you run against — see
../README.md and analysis/MUSE_STUB_SESSION_REPORT.md):
  python3 stub_server.py 8765
  # in another shell:
  META_API_KEY=dummy-stub-key muse exec --provider meta \
    --base-url http://127.0.0.1:8765 --max-model-steps 4 --json \
    "Read the file at <repo>/adapters/muse/stub/fixtures/big.py and tell me what it contains."
"""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
# All paths are relative to this script, so the harness runs from
# a repo checkout anywhere. Runtime output (requests/, requests.log)
# lands here too and is gitignored.
BASE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(BASE, "fixtures")
CATALOG = os.path.join(BASE, "catalog.json")
SCENARIO = os.path.join(BASE, "scenario.txt")
LOGDIR = os.path.join(BASE, "requests")

_counter = {"n": 0}


def scenario():
    try:
        return open(SCENARIO).read().strip() or "big"
    except FileNotFoundError:
        return "big"


class Stream:
    """One /responses SSE stream: sequence numbers restart at 0
    per response, exactly as the real gateway numbers them."""

    def __init__(self, resp_id, req):
        self.resp_id = resp_id
        self.req = req or {}
        self.seq = 0
        self.created_at = float(int(time.time()))

    def event(self, obj):
        # Alphabetical key order, as the gateway emits it:
        # payload first, sequence_number next, type last.
        ordered = {}
        for k in sorted(obj.keys()):
            if k != "type":
                ordered[k] = obj[k]
        ordered["sequence_number"] = self.seq
        ordered["type"] = obj["type"]
        self.seq += 1
        return (f"event: {obj['type']}\n"
                f"data: {json.dumps(ordered, separators=(',', ':'))}\n\n").encode()

    def response_obj(self, status, output, usage=None,
                     incomplete_details=None):
        # Exact 22-key shape from the capture (plus usage only on
        # the terminal event). created_at is a float; reasoning
        # carries effort only.
        effort = "max"
        try:
            effort = self.req.get("reasoning", {}).get("effort") or "max"
        except Exception:
            pass
        obj = {"background": False, "created_at": self.created_at,
               "error": None, "id": self.resp_id,
               "incomplete_details": incomplete_details,
               "instructions": None,
               "max_output_tokens": self.req.get("max_output_tokens"),
               "model": "muse-spark-1.3-contributor",
               "object": "response", "output": output,
               "parallel_tool_calls": True,
               "reasoning": {"effort": effort},
               "service_tier": "default", "status": status,
               "store": True, "temperature": 1.0,
               "tool_choice": "auto",
               # The capture had no tools in its request, so its
               # response echoed []. Echoing Muse's 27-sub-tool
               # namespace array here is untested ground truth and
               # a suspect in the decode failures: the client may
               # parse response.tools as function tools, where a
               # "namespace" entry is invalid. Send [] until the
               # stream decodes.
               "tools": [],
               "top_logprobs": 0, "top_p": 1.0,
               "truncation": "disabled"}
        if usage is not None:
            obj["usage"] = usage
        return obj

    def open_events(self):
        yield self.event({"type": "response.created",
                          "response": self.response_obj("in_progress", [])})
        yield self.event({"type": "response.in_progress",
                          "response": self.response_obj("in_progress", [])})

    def reasoning_item(self):
        # The real model emits a reasoning item first whenever
        # reasoning is enabled; encrypted_content is opaque to
        # the client, so well-formed base64url bytes stand in
        # for it (see the report for why the shape matters).
        item = {"id": f"rs_{self.resp_id}:rs_stub1",
                "status": "in_progress", "summary": [],
                "type": "reasoning"}
        yield self.event({"type": "response.output_item.added",
                          "output_index": 0, "item": item})
        # encrypted_content must be well-formed base64url: the
        # client validates the shape (a short ASCII placeholder
        # fails as malformed response data). Random bytes encoded
        # the same way, same order of length as the real capture.
        import base64
        fake = base64.urlsafe_b64encode(
            bytes(range(256)) * 5).decode().rstrip("=")
        # Match the capture exactly: the only observed
        # reasoning done item has status "incomplete".
        done = dict(item, status="incomplete",
                    encrypted_content=fake)
        yield self.event({"type": "response.output_item.done",
                          "output_index": 0, "item": done})
        return done

    def close(self, output, usage):
        yield self.event({"type": "response.completed",
                          "response": self.response_obj(
                              "completed", output, usage=usage)})
        yield b"data: [DONE]\n\n"

    def function_call(self, call_id, name, arguments):
        yield from self.open_events()
        reasoned = yield from self.reasoning_item()
        output = [reasoned]
        args = json.dumps(arguments)
        item = {"type": "function_call", "id": "fc_stub",
                "call_id": call_id, "name": name, "arguments": "",
                "status": "in_progress"}
        yield self.event({"type": "response.output_item.added",
                          "output_index": 1, "item": item})
        half = len(args) // 2
        for part in (args[:half], args[half:]):
            yield self.event({"type": "response.function_call_arguments.delta",
                              "item_id": "fc_stub", "output_index": 1,
                              "delta": part})
        yield self.event({"type": "response.function_call_arguments.done",
                          "item_id": "fc_stub", "output_index": 1,
                          "arguments": args})
        done_item = dict(item, arguments=args, status="completed")
        yield self.event({"type": "response.output_item.done",
                          "output_index": 1, "item": done_item})
        output.append(done_item)
        usage = {"input_tokens": 100, "output_tokens": 40,
                 "total_tokens": 140,
                 "input_tokens_details": {"cached_tokens": 0},
                 "output_tokens_details": {"reasoning_tokens": 0}}
        yield from self.close(output, usage)

    def message_events_minimal(self, text):
        # Minimal message: added then done, no delta/part events.
        # Bisect helper for replay-msg: if this works and the full
        # message_events doesn't, the fault is in a sub-event.
        item = {"type": "message", "id": "msg_stub", "role": "assistant",
                "status": "in_progress", "content": []}
        yield self.event({"type": "response.output_item.added",
                          "output_index": 1, "item": item})
        done_item = {"type": "message", "id": "msg_stub",
                     "role": "assistant", "status": "completed",
                     "content": [{"type": "output_text",
                                  "annotations": [], "text": text}]}
        yield self.event({"type": "response.output_item.done",
                          "output_index": 1, "item": done_item})
        return done_item

    def message_events(self, text):
        # At added time the message item carries an empty
        # content list; the part arrives with content_part.added.
        # (Sending a part with empty text here made the client
        # report the whole response malformed.)
        item = {"type": "message", "id": "msg_stub", "role": "assistant",
                "status": "in_progress", "content": []}
        yield self.event({"type": "response.output_item.added",
                          "output_index": 1, "item": item})
        yield self.event({"type": "response.content_part.added",
                          "item_id": "msg_stub", "output_index": 1,
                          "content_index": 0,
                          "part": {"type": "output_text",
                                   "annotations": [], "text": ""}})
        yield self.event({"type": "response.output_text.delta",
                          "item_id": "msg_stub", "output_index": 1,
                          "content_index": 0, "delta": text})
        yield self.event({"type": "response.output_text.done",
                          "item_id": "msg_stub", "output_index": 1,
                          "content_index": 0, "text": text})
        yield self.event({"type": "response.content_part.done",
                          "item_id": "msg_stub", "output_index": 1,
                          "content_index": 0,
                          "part": {"type": "output_text",
                                   "annotations": [], "text": text}})
        done_item = {"type": "message", "id": "msg_stub",
                     "role": "assistant", "status": "completed",
                     "content": [{"type": "output_text",
                                  "annotations": [], "text": text}]}
        yield self.event({"type": "response.output_item.done",
                          "output_index": 1, "item": done_item})
        return done_item

    def text(self, text):
        yield from self.open_events()
        reasoned = yield from self.reasoning_item()
        output = [reasoned]
        done_item = yield from self.message_events(text)
        output.append(done_item)
        usage = {"input_tokens": 100, "output_tokens": 10,
                 "total_tokens": 110,
                 "input_tokens_details": {"cached_tokens": 0},
                 "output_tokens_details": {"reasoning_tokens": 0}}
        yield from self.close(output, usage)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        # Count only /responses turns; the catalog GET must not
        # consume turn 1.
        is_turn = self.path == "/responses" and self.command == "POST"
        if is_turn:
            _counter["n"] += 1
        n = _counter["n"]
        os.makedirs(LOGDIR, exist_ok=True)
        with open(os.path.join(LOGDIR, f"raw-{n:03d}.json"), "wb") as f:
            f.write(body)
        with open(os.path.join(BASE, "requests.log"), "a") as f:
            f.write(f"=== #{n} {self.command} {self.path} "
                    f"({len(body)} bytes)\n")

        if self.path.startswith("/muse-code/models"):
            with open(CATALOG, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if self.path == "/responses" and self.command == "POST":
            sc = scenario()
            try:
                req = json.loads(body)
            except Exception:
                req = {}
            resp_id = f"resp_stub_{n}"
            stream = Stream(resp_id, req)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if sc == "replay-completed":
                # Bisect: real events verbatim, except the terminal
                # response.incomplete is replaced by a completed
                # event built from the same response object (status
                # completed, incomplete_details null). If this fails,
                # my completed-event construction is the problem;
                # if it works, the fault is in my message item.
                with open(os.path.join(BASE, "real-sse.txt"), "rb") as f:
                    raw = f.read().decode()
                blocks = []
                for block in raw.strip().split("\n\n"):
                    lines = block.splitlines()
                    ev = next((ln[7:] for ln in lines
                               if ln.startswith("event: ")), None)
                    data = next((ln[6:] for ln in lines
                                 if ln.startswith("data: ")), None)
                    if ev == "response.incomplete":
                        d = json.loads(data)
                        r = d["response"]
                        r["status"] = "completed"
                        r["incomplete_details"] = None
                        d["type"] = "response.completed"
                        data = json.dumps(d, separators=(",", ":"))
                        block = (f"event: response.completed\n"
                                 f"data: {data}")
                    blocks.append(block)
                self.wfile.write(("\n\n".join(blocks) + "\n\n").encode())
                self.wfile.flush()
                return
            elif sc in ("replay-msg", "replay-msg-min"):
                # Real events, then MY message-item events, then a
                # completed event whose output is [real reasoning,
                # my message]. If this fails, my message item is
                # the problem; if it works, the fault is my
                # reasoning item (fake encrypted_content) or my
                # created/in_progress/response_obj.
                with open(os.path.join(BASE, "real-sse.txt"), "rb") as f:
                    raw = f.read().decode()
                blocks = raw.strip().split("\n\n")
                # Drop the terminal incomplete event and [DONE];
                # keep created, in_progress, reasoning added/done.
                head = blocks[:4]
                real_reason = None
                for b in head:
                    data = next((ln[6:] for ln in b.splitlines()
                                 if ln.startswith("data: ")), None)
                    d = json.loads(data)
                    if d.get("type") == "response.output_item.done":
                        real_reason = d["item"]
                # The real stream's sequence is 0..3; continue it.
                stream = Stream("resp_6af51f4e9ea5ae0af4004b12", {})
                stream.seq = 4
                fn = (stream.message_events_minimal if sc == "replay-msg-min"
                      else stream.message_events)
                msg_events = list(fn("Hello."))
                # Rebuild the completed event from the real
                # incomplete response object.
                inc = json.loads(next(
                    ln[6:] for ln in blocks[4].splitlines()
                    if ln.startswith("data: ")))
                r = inc["response"]
                r["status"] = "completed"
                r["incomplete_details"] = None
                r["output"] = [real_reason,
                               {"type": "message", "id": "msg_stub",
                                "role": "assistant",
                                "status": "completed",
                                "content": [{"type": "output_text",
                                             "annotations": [],
                                             "text": "Hello."}]}]
                comp = {"response": r, "sequence_number": 10,
                        "type": "response.completed"}
                tail = (f"event: response.completed\n"
                        f"data: {json.dumps(comp, separators=(',', ':'))}")
                # Chunks already end with "\n\n"; concatenate
                # them directly. Joining with "\n\n" would insert
                # blank lines that parse as empty events, and the
                # client rejects an event with no type field.
                out = "".join(
                    [b + "\n\n" for b in head]
                    + [e.decode() for e in msg_events]
                    + [tail + "\n\n", "data: [DONE]\n\n"])
                self.wfile.write(out.encode())
                self.wfile.flush()
                return
            elif sc in ("replay", "replay-mut"):
                # "replay" serves the REAL captured bytes verbatim
                # (decodes fine). "replay-mut" re-emits the same
                # events with my stub's values substituted (stub
                # response id, reasoning effort max, max_output
                # 128000): if that still decodes, those values are
                # innocent and the difference is framing/whitespace;
                # if it fails, one of them is the culprit.
                with open(os.path.join(BASE, "real-sse.txt"), "rb") as f:
                    raw = f.read()
                if sc == "replay-mut":
                    out = []
                    for block in raw.decode().strip().split("\n\n"):
                        lines = block.splitlines()
                        ev = next((ln[7:] for ln in lines
                                   if ln.startswith("event: ")), None)
                        data = next((ln[6:] for ln in lines
                                     if ln.startswith("data: ")), None)
                        if data is None or data == "[DONE]":
                            out.append(block)
                            continue
                        d = json.loads(data)
                        r = d.get("response")
                        if r is not None:
                            r["id"] = "resp_stub_1"
                            r["max_output_tokens"] = 128000
                            if isinstance(r.get("reasoning"), dict):
                                r["reasoning"]["effort"] = "max"
                        it = d.get("item")
                        if it is not None and it.get("type") == "reasoning":
                            it["id"] = "rs_resp_stub_1:rs_stub1"
                        out.append(f"event: {ev}\n"
                                   f"data: {json.dumps(d, separators=(',', ':'))}")
                    raw = ("\n\n".join(out) + "\n\n").encode()
                self.wfile.write(raw)
                self.wfile.flush()
                return
            elif sc == "created-only":
                events = list(stream.open_events())[:1]
            elif sc == "text":
                events = stream.text("Hello.")
            elif n == 1:
                target = "big.py" if sc == "big" else "small.py"
                events = stream.function_call(
                    "call_stub1", "muse.read_file",
                    {"path": os.path.join(FIX, target)})
            elif n == 2:
                events = stream.text(
                    "The read was blocked by the Sluice hook, so I "
                    "used the bulk-read skill instead. Done.")
            else:
                events = stream.text("Done.")
            for chunk in events:
                self.wfile.write(chunk)
                self.wfile.flush()
            return

        data = b'{"error": "stub: unknown route"}'
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = _handle
    do_POST = _handle


if __name__ == "__main__":
    print(f"scripted stub on 127.0.0.1:{PORT} (scenario file: {SCENARIO})",
          flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
