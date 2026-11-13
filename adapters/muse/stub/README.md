# Muse stub-model session harness

A scripted stand-in for Muse's meta provider, so a real `muse exec`
session can run end to end with no model, no auth, and $0 cost — and
the Sluice PreToolUse hook can be observed firing inside a live
session loop instead of only in the offline hook-test harness.

## What is here

- `stub_server.py` — the stub. Serves the model catalog and scripted
  Responses API (SSE) streams on 127.0.0.1:8765.
- `fixtures/big.py` (500 lines), `fixtures/small.py` (40 lines) — the
  files the scripted model "reads". Big must be denied, small must
  pass and execute.
- `catalog.json` — the real model catalog shape, fetched once from
  `api.meta.ai`; public model metadata, no secrets.
- `real-sse.txt` — one approved capture call to the real API
  (`muse-spark-1.3-contributor`, "Say hi", 16 output tokens,
  $0.0000042), saved verbatim. The replay-* scenarios re-serve these
  bytes; they exist to bisect the SSE shape and are not part of a
  normal verification run.

No secrets anywhere in this directory. The only credential involved
is the dummy `META_API_KEY=dummy-stub-key` the client requires to
start against a local base URL.

## Run it

The Sluice plugin must already be installed and approved in the Muse
home you run against (see `../README.md`).

```sh
# Terminal 1: start the stub (scenario defaults to "big").
python3 stub_server.py 8765

# Terminal 2: the big-read session (hook must deny).
META_API_KEY=dummy-stub-key muse exec --provider meta \
  --base-url http://127.0.0.1:8765 --max-model-steps 4 --json \
  "Read the file at <repo>/adapters/muse/stub/fixtures/big.py and tell me what it contains."

# Then the control: small read must pass and execute.
echo small > scenario.txt
META_API_KEY=dummy-stub-key muse exec --provider meta \
  --base-url http://127.0.0.1:8765 --max-model-steps 4 --json \
  "Read the file at <repo>/adapters/muse/stub/fixtures/small.py and tell me what it contains."
```

Scenario is read fresh from `scenario.txt` on every `/responses`
request, so runs switch without restarting the server. Scenarios:
`big`, `small`, `text` (framing check), `created-only`
(diagnostic), `replay`, `replay-mut`, `replay-completed`,
`replay-msg`, `replay-msg-min`.

Restart the server before each verification run: the turn counter
is global, the client's parallel reminder calls consume turns too,
and the function-call scenarios only fire on turn 1, so a stale
counter silently serves plain text instead of the tool call.

## Check the result

Every request body is saved raw to `requests/raw-NNN.json` (gitignored
runtime output). In the big run, the follow-up request's
`function_call_output` must be the hook denial, and no big.py content
may appear in any request. In the small run, the tool result must be
the file's numbered lines and no "Blocked by Sluice" may appear.

## What it proves, and what it does not

Verified Nov 11, 2026 against Muse Code 1.4.15: the 500-line read is
denied in-session with the bulk-read redirect and no content leaks;
the 40-line read executes. That is the enforcement half only. It
does not prove a real model follows the deny redirect — that half is
covered by the live benchmark (96.6% coordinator-context savings,
100% identifier accuracy, $0.002 measured). Full write-up, including
how the SSE shape was reverse-engineered from the capture, is in
`../../analysis/MUSE_STUB_SESSION_REPORT.md`.
