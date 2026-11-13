# Muse stub-model session — Sluice hook fires inside a real session

**Date:** Wed 2026-11-11. **Muse Code:** 1.4.15. **Sluice plugin:** 0.3.2 (enabled/active/valid).
**Cost:** $0 for all stub sessions. One approved capture call to the real
API cost **$0.0000042** (26 tokens: 10 in, 16 out, at contributor rates
$0.10/$0.20 per 1M). No auth, no real model in any stub run.

## What this proves

The Sluice PreToolUse hook for Muse Code fires **inside a real Muse
session loop** — not just in the offline hook-test harness, which runs
the script but never a session. A scripted stub model (a local HTTP
server answering the meta provider's Responses API requests) issued a
`read_file` on a 500-line file; the session ran the hook, denied the
call, fed the denial back as the tool result, and completed. A
40-line read in the same setup passed the hook and executed normally.

This is the enforcement half only. It does **not** prove a real model
follows the deny redirect (that half is covered by the live benchmark:
96.6% coordinator-context savings, 100% identifier accuracy,
$0.002 measured). The stub's "model" is scripted, so no model
judgment is tested here.

## Results

| Run | Scenario | Outcome |
|---|---|---|
| `run-text9.jsonl` | Text only ("Hello.") | Session completed, 1 model call, 0 failed, final text "Hello." |
| `run-big.jsonl` | Turn 1: `muse.read_file` on `fixtures/big.py` (500 lines) | **Hook denied in-session.** Tool result fed back: `tool blocked by hook: Blocked by Sluice: read_file of .../fixtures/big.py (500 lines) totals 500 lines, over the 350-line threshold (SLUICE_MIN_LINES). Do not read the full file(s). Use the bulk-read skill instead...` Turn 2 completed. 2 model calls, 0 failed. |
| `run-small.jsonl` | Turn 1: `muse.read_file` on `fixtures/small.py` (40 lines) | **Hook passed, tool executed.** Tool result: `Read text file .../small.py` with numbered lines 1–40. No "Blocked by Sluice" anywhere in the log. 2 model calls, 0 failed. |

No-leak check on the big run: no big.py content appears in any request
the session made (`requests/raw-*.json` searched for file-content
markers; none found). The only file content that ever entered the
session was the 40-line small.py in the control run, where the read
was supposed to execute.

## How the stub works

`adapters/muse/stub/stub_server.py` (moved into the repo Nov 12,
2026; originally built under `~/workspace/muse-test-home/stub/`)
serves the model catalog and a scripted Responses API stream on
127.0.0.1:8765. Scenario is read fresh from `scenario.txt` on
every request: `big`, `small`, `text`, `created-only`, `replay`,
`replay-mut`, `replay-completed`, `replay-msg`, `replay-msg-min`.
Every request body is saved raw to `requests/raw-NNN.json`. Run
command:

```
META_API_KEY=dummy-stub-key muse exec --provider meta \
  --base-url http://127.0.0.1:8765 --max-model-steps 4 --json "<prompt>"
```

Run environment: `PATH` with the isolated Muse binary,
`XDG_CONFIG_HOME`/`XDG_DATA_HOME` under `~/workspace/muse-test-home/`,
`MUSE_NO_AUTO_UPDATE=1`. The workspace was untrusted in these runs
(no `--trust-workspace`); that did not block the hook. Note the
client also issues parallel skill-reminder, goal-reminder and
verify-reminder model calls against the stub; they are counted in
`requests/` but do not affect the main turn.

## Getting the SSE shape right (the hard part)

The first stub was rejected with a bare `decode` error on every
attempt, even for a stream containing only `response.created`. The
fixes, each isolated by a bisect against ground truth:

1. **One approved capture call.** `POST https://api.meta.ai/v1/responses`,
   `muse-spark-1.3-contributor`, input "Say hi", streaming, 16 output
   tokens, reasoning low, `include: ["reasoning.encrypted_content"]`.
   Saved verbatim at `stub/real-sse.txt` (5,367 bytes, 6 frames).
   The capture showed the real stream carries an `event: <type>` line
   before each `data:` line (data-only frames are rejected), a
   top-level `sequence_number` per event (0, 1, 2, ...), a
   `response.in_progress` event after `response.created`, and a
   reasoning output item first.
2. **Exact 22-key Response object** (no `metadata`, `text`,
   `previous_response_id`, `completed_at`, `user`, `max_tool_calls`,
   `status_details`; `created_at` a whole-second float; `reasoning`
   is `{"effort": ...}` with no `summary` key; `service_tier`
   "default"; `store` true; `truncation` "disabled"; `top_logprobs`
   0; `usage` only on the terminal event). Replaying the real bytes
   verbatim decoded on attempt 1; replaying them with stub values
   substituted (stub id, effort max, max_output_tokens 128000) also
   decoded — those values were innocent.
3. **`item_id` on `response.content_part.added` / `.done`.** The
   minimal message (added + done only) worked; the full message
   failed until `item_id` was added to the two content-part events.
   The other proven fixes: compact JSON separators and a whole-second
   `created_at`. Unproven but kept: the reasoning item's
   `encrypted_content` is well-formed base64url instead of a short
   ASCII placeholder (the placeholder failed, but so did the valid
   base64url before the `item_id` fix, so its necessity is not
   established).

Also recorded in the stub's docstring, so the next person does not
re-derive it.

## Verdict

**PASS.** The Muse adapter (v0.3.2) enforces the 350-line threshold
inside a live Muse session: bulk reads are denied with the bulk-read
redirect, targeted reads execute untouched, and no bulk content leaks
into the session. Remaining live-verification gap, unchanged: a hook
firing in a session driven by a **real** model, and the Claude Code
plugin manifest firing in real Claude Code — both still need Yuriy's
authenticated hosts.
