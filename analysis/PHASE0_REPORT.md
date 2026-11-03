# Sluice Phase 0 report: is there enough bulk reading to shunt?

Date: 2026-11-02 (measurement run, this VM)
Corpus: trace-commons Claude Code sessions, 28 files, public, real Claude Code
JSONL at `~/workspace/user/corpus/public/trace-commons/sessions/claude_code/`.
Script: `analysis/phase0_measure.py`, output: `analysis/phase0_results.json`.

## The gap, stated first

This VM has no `~/.claude/projects` and no recent Yuriy Claude Code JSONL
drop, so Phase 0 could NOT run over Yuriy's own recent sessions as the
spec asked. The numbers below are a proxy corpus, not Yuriy's own
workload. The Optimal Misbehavior HTML transcripts on this machine
(Sep 2026, Yuriy's build sessions) were not measured: the existing
recovery parser truncates tool outputs to 512 characters, so a bulk
line count from that parse would be fabricated. A new parser for that
HTML, or a fresh `~/.claude/projects` drop, re-runs this measurement
in minutes, and the shipped meter measures Yuriy's real share in situ
once installed. Do not read the proxy table as Yuriy's personal table.

## Method

- Tool results paired to tool calls by `tool_use_id`, in file order.
- Token figure = ceil(chars / 4). This is an ESTIMATE, not a tokenizer
  count, and not a billed figure. It is labelled estimate everywhere.
- Bulk = a tool result with >= 350 lines, matching the hook threshold.
  A Read with an explicit limit <= 350 is targeted; its result is small
  by construction, and the result line count is the ground truth.
- Session `usage` fields were NOT summed. In these files the usage
  block repeats across consecutive assistant records, so a sum would
  double count. That is exactly why Sluice's meter measures at
  delegation time instead of summing session usage afterwards.
- Bash/PowerShell "read-like" for the headline: a command segment whose
  first token is `cat` / `less` / `more` / `Get-Content` / `gc` / `type`,
  unpiped. Piped `| tail -5` / `| head -20` and `head`/`tail` alone are
  targeted and pass the hook; they are excluded from the hookable count
  (the broad first pass found 451 read-word matches, most of them piped
  limits or words inside code strings, which is why the strict count is
  87, not 451).

## Measured table (proxy corpus, estimates labelled)

| Quantity | Value |
|---|---|
| Sessions | 28 |
| Tool results measured | 4,262 |
| All tool-result payload, estimated | 1,077,913 tokens |
| Read calls / Read results | 847 / 841 |
| Targeted Reads (explicit limit <= 350) | 448 |
| Unlimited Reads | 399 |
| Bulk Reads (>= 350 lines) | 39 calls, 4.6% of Read results |
| Bulk Read payload, estimated | 221,651 tokens |
| Bulk Read share of tool-result payload, estimated | 20.6% |
| Strict hookable Bash/PowerShell cat segments | 87 calls |
| Bash/PowerShell bulk (>= 350 lines) | 0 calls, 0 tokens |
| Combined bulk share at 350, estimated | 20.6% |
| Generated payload (Write content + Edit new_string), estimated | 702,690 tokens (Write 579,953 in 641 calls; Edit 122,737 in 972 calls) |
| Generated share of all tool_use payload, estimated | 66.7% |

Read result line buckets (841 Read results): error/empty 37, 1-49 lines
467, 50-199 lines 246, 200-349 lines 52, 350-999 lines 38, 1000+ lines 1.

Bulk share is concentrated, not diffuse: 12 of 28 sessions have any
bulk Read. The top sessions by bulk share are 65.0%, 48.4%, 42.8%,
36.1%, 35.3% of their own tool-result payload. The other 16 sessions
have none, so Sluice is a sometimes-tool: on bulk-heavy sessions it
matters, on others the hooks should be invisible.

## Threshold sensitivity (combined Read + Bash bulk, estimated share)

| Threshold | Bulk share of tool-result payload |
|---|---|
| 200 lines | 33.6% |
| 350 lines (default) | 20.6% |
| 500 lines | 16.2% |
| 1000 lines | 0.95% |

The 350 default is the right one for this corpus: 1000 would miss
almost all bulk Reads (only 1 result is over 1000 lines), while 200
would block a much larger, more routine set of reads. `SLUICE_MIN_LINES`
lets a user move it, and the sensitivity table is the reason to
re-measure on their own corpus before moving it far.

## What this does and does not establish

- Establishes: bulk Reads are a real, concentrated share (about a
  fifth of tool-result payload) in real Claude Code sessions, and the
  350-line threshold captures the main mass.
- Does NOT establish: Yuriy's own share, any dollar saving (the
  coordinator here may be subscription-billed, in which case token
  savings are not dollar savings), or that a cheap worker summary
  preserves the identifiers a coordinator needs. Those are the live
  benchmark's job, and they are still pending (see README kill
  criteria). The Bash bypass is real in form (87 unpiped cat segments)
  but contributed zero bulk tokens at 350 in this corpus, so the
  Bash hook closes a bypass, it is not the main saving.
- Generated payload (702,690 estimated tokens) is the larger pool, but
  it is not automatically savings: novel code still has to be generated
  somewhere. The code-write worker only saves when the worker is
  cheaper per token AND the coordinator never re-reads the output.
  The benchmark must prove that, not assume it.

## Verdict

PASS to build V1, on the proxy. If the bulk share had been small
(single digits at 350, diffuse, no concentration), the honest
conclusion would have been "not worth it for this workload" and this
table would have been the README. It is not small, so V1 proceeds,
with the live benchmark still required before any savings claim.
