# Sluice

A Portal-free, hook-enforced, provider-agnostic token saver for Claude
Code, Codex CLI, and Muse Code, where the savings measurement ships with the tool.

Spotify proved the pattern (shunt bulk reads and boilerplate generation
to a cheap worker, enforced by hooks, instead of letting the coordinator
absorb them). This repo makes it installable without a platform
instance, and honest about its own savings: every "avoided" figure is
labelled an estimate and is never printed without the measured pair
(coordinator tokens, worker tokens and worker dollars) beside it.

No platform, no server, no telemetry. Local-first, nothing phones home.

## Measured table first

### Phase 0: bulk-read share (proxy corpus, estimates labelled)

Full report: `analysis/PHASE0_REPORT.md`, script:
`analysis/phase0_measure.py`, raw output: `analysis/phase0_results.json`.

| Quantity | Value |
|---|---|
| Corpus | trace-commons Claude Code, 28 sessions, public, real JSONL |
| Tool results measured | 4,262 |
| All tool-result payload, estimated (chars/4) | 1,077,913 tokens |
| Read calls / Read results | 847 / 841 |
| Bulk Reads (>= 350 lines) | 39 calls, 4.6% of Read results |
| Bulk Read payload, estimated | 221,651 tokens |
| Bulk Read share of tool-result payload, estimated | **20.6%** |
| Strict hookable Bash/PowerShell cat segments | 87 calls |
| Bash/PowerShell bulk (>= 350 lines) | 0 calls, 0 tokens |
| Generated payload (Write + Edit), estimated | 702,690 tokens, 66.7% of tool_use payload |

Threshold sensitivity, bulk share of tool-result payload, estimated:
200 lines 33.6%, **350 lines 20.6%**, 500 lines 16.2%, 1000 lines 0.95%.
The 350 default captures the main mass; 1000 would miss almost all of it.

**Gap, stated here, not buried:** this VM has no `~/.claude/projects`
and no recent Yuriy Claude Code JSONL drop, so Phase 0 did NOT run
over Yuriy's own recent sessions. These are proxy numbers. The shipped
meter measures the real share in situ once installed, and a fresh
`~/.claude/projects` drop re-runs Phase 0 in minutes.

### Benchmark: stub worker ($0, NOT a live model)

`benchmarks/run_benchmarks.py`, output:
`benchmarks/benchmark_results.json`. The worker is a local mock server
that extracts identifiers deterministically from the numbered prompt,
so its accuracy is 100% by construction for the extraction task. This
proves plumbing, hooks, and meter arithmetic. It does not prove a live
model would do the same.

| Task | Before, estimated | Coordinator after, estimated | Coordinator-context savings | Identifier accuracy (stub) |
|---|---|---|---|---|
| BR1 checks fixture, 422 lines, 18 check classes | 3,185 tokens | 142 tokens | 95.5% | 100% (18/18) |
| BR2 model fixture, 475 lines, 4 model classes | 2,721 tokens | 31 tokens | 98.9% | 100% (4/4) |
| BR3 both files, 23 classes | 5,906 tokens | 173 tokens | 97.1% | 100% (23/23) |
| Mean, stub | | | **97.2%** | **100%** |

| Quality gate | Result |
|---|---|
| Code-write CW1: generated module passes its 3 tests, stdout contains no code | PASS (3/3) |
| Targeted flows unchanged with hooks on (small Read, limit/offset Read, small cat, piped cat, head, plain Bash) | PASS (7/7) |
| Hook overhead, p95 | 39.6 ms (small Read pass), 39.9 ms (large Read block) — Python startup dominates; under the 100 ms bar |
| Tests | 17/17 (`python3 -m unittest discover -s tests`) |

### Live benchmark: PASS (measured, 2026-11-03)

Model: `muse-spark-1.3-contributor` via the stored Meta credential,
Responses API style, output cap 1024 tokens. Script:
`benchmarks/run_live_benchmark.py`, output:
`benchmarks/live_benchmark_results.json`, meter:
`benchmarks/live_meter.jsonl`. Cap approved: $0.05. Measured spend
on the reported run: **$0.002021**.

| Task | Before, estimated | Coordinator after, estimated | Coordinator-context savings | Identifier accuracy (live) | Line accuracy (live, secondary) | Worker tokens, measured | Worker dollars, measured |
|---|---|---|---|---|---|---|---|
| BR1 checks fixture | 3,185 tokens | 131 tokens | 95.9% | 100% (18/18) | 100% | 4,672 | $0.000521 |
| BR2 model fixture | 2,721 tokens | 30 tokens | 98.9% | 100% (4/4) | 100% | 4,097 | $0.000446 |
| BR3 both files | 5,906 tokens | 292 tokens | 95.0% | 100% (23/23) | 95.7% (22/23) | 8,491 | $0.000924 |
| Mean, live | | | **96.6%** | **100%** | 98.6% | | |
| CW1 code-write | | | | Tests 3/3, stdout contains no code | | 790 | $0.000131 |

| Kill criterion (pre-registered) | Bar | Live result |
|---|---|---|
| Mean bulk-read coordinator-context savings on BR1-BR3 | >= 50% | **PASS, 96.6%** |
| Summary identifier accuracy on BR1-BR3 | >= 90% | **PASS, 100%** |
| Hook overhead exceeds savings on typical reads | p95 < 100 ms and bulk savings in thousands of tokens | PASS on time (p95 ~40 ms, stub) and savings (live, above) |

Notes, kept honest:
- BR3's one line miss: TaskSample cited as line 28, actual line 27
  (off by one, multi-file task). Name accuracy is unaffected, and
  line accuracy is a secondary figure, not a kill bar.
- The first live attempt produced correct summaries and passing
  code-write tests, but worker tokens and dollars came back null:
  the worker normalised only chat-completions usage keys
  (`prompt_tokens`/`completion_tokens`), not Responses keys
  (`input_tokens`/`output_tokens`). That bug was fixed in v0.1.1
  (worker + a mock test using Responses usage keys), and the run
  above is the re-run with provider-measured usage. The first
  attempt's spend was therefore unmeasured, estimated at about
  $0.002 from similar token counts, so combined spend across both
  attempts is about $0.004, still well under the $0.05 cap — but
  only the $0.002021 above is claimed as measured.
- Worker dollars are provider-measured usage at contributor rates
  ($0.10 input / $0.20 output per 1M). Coordinator dollars are not
  claimed: if the coordinator is subscription-billed, these token
  savings are not dollar savings.

### The honesty correction the stub run forced

Total tokens go UP with a shunt, by design: the worker reads the full
file, so worker input + worker output + coordinator summary exceeds
the direct-read tokens. In the stub run: avoided 11,868 tokens
(estimate), coordinator summary 391 tokens (estimate), worker
14,625 tokens (mock usage) — coordinator-context saved 11,477 tokens
(estimate, 96.7%), total tokens higher. The saving is therefore in
coordinator context, and in dollars only when the worker is cheaper
per token than the coordinator. If the coordinator is
subscription-billed, token savings are not dollar savings, and this
README does not claim they are. The meter enforces this distinction
in code: it reports coordinator-context savings, worker dollars
measured, and avoided as an estimate, together, never alone.

## What v1 is

- Two PreToolUse hooks. `check-file-size`: blocks a Read over the
  threshold (default 350 lines, `SLUICE_MIN_LINES` override) and
  redirects to the bulk-read skill; targeted reads with
  offset/limit pass untouched. `check-bash-read`: catches unpiped
  `cat` / `less` / `more` / `Get-Content` / `gc` / `type` against
  files totalling over the threshold; piped and targeted commands
  pass through, closing the shell bypass.
- Two workers. `bulk-read`: files plus a question in, structured
  bullets out — exact names, types, and line numbers first, nothing
  unasked. Lines are numbered in the worker prompt so the worker
  cites numbers instead of counting them. `code-write`: spec plus a
  reference file in, code only out, written straight to disk; the
  coordinator never sees the generated code (stdout is a JSON summary
  only). Both workers carry the same exclusion list: no debugging,
  no architecture decisions, no safety-critical code, no edits based
  on summaries. `code-write --task-type debug|architecture|safety-critical`
  is refused by the script itself.
- Provider-agnostic worker backend: one small client speaking
  OpenAI-compatible chat completions, configured by environment
  (provider, model, key). Documented options include Gemini Flash, a
  mini-class model, a local Ollama endpoint, and the Meta contributor
  tier. Keys live in env vars only, never in the repo. No platform,
  no server, no telemetry.
- The meter: every delegation appends a record (files, threshold
  decision, coordinator tokens actually consumed when known, worker
  tokens and worker dollars). `python3 -m sluice.meter report` prints
  totals and the coordinator-context savings ratio. Honesty rule,
  enforced in code: the "avoided" figure is labelled an estimate
  (direct-read cost approximated from file size), while coordinator
  and worker figures are measured. The README never prints the
  estimate without the measured pair beside it.

## Install

Claude Code plugin marketplace (one marketplace add plus one install).
This tree is push-ready; the repo itself is created by the owner, so
replace the placeholder after creation, or install from a local clone:

```
claude plugin marketplace add <owner>/sluice
claude plugin install sluice
```

Local, before the repo exists:

```
git clone <repo-url> sluice
claude plugin marketplace add ./sluice
claude plugin install sluice
```

Plugin layout: `plugins/sluice/` holds `.claude-plugin/plugin.json`,
`hooks/hooks.json`, `hooks/check-file-size.py`,
`hooks/check-bash-read.py`, `skills/bulk-read/SKILL.md`,
`skills/code-write/SKILL.md`. The worker code in `sluice/` is at the
repo root so it can also run standalone:
`python3 sluice/bulk_read.py --files a.py --question "..."`.

## Codex CLI (v0.3.1)

Codex has no native Read tool, so there is no Read hook to port:
a Codex agent reads through the shell or an MCP filesystem tool.
`adapters/codex/check-codex.py` is one PreToolUse script for that
surface: unpiped `cat` / `less` / `more` / `Get-Content` / `gc` /
`type` over the threshold, `head` / `tail` with an explicit `-n`
over the threshold (Codex-only: the shell IS the read path here),
`sed -n` windows whose sizes sum over the threshold (v0.3.1: the
rollout analysis showed `sed` windows, not `cat`, are the bulk-read
path in Codex sessions), and read-shaped / MCP read tools with a
path argument and no targeted limit. Workers, meter, and skills are
unchanged.

Install is manual (no Codex plugin bundle yet): copy the script to
`~/.codex/hooks/`, merge `adapters/codex/hooks.json` into
`~/.codex/hooks.json`, copy the two skills into
`~/.codex/skills/`, and trust the hooks in Codex with `/hooks`.
Full steps, and the honest gaps (`awk` / `python -c`
reads, server-dependent MCP argument names, hosted tools, and the
still-owed live authenticated Codex session check), are in
`adapters/codex/README.md`.

## Configuration

| Variable | Meaning |
|---|---|
| `SLUICE_MIN_LINES` | Hook threshold in lines. Default 350. |
| `SLUICE_BASE_URL` | OpenAI-compatible base URL. Required unless the provider has a built-in one (OpenAI, Gemini, Ollama). The Meta contributor tier has no guessed URL here: set it explicitly to your provider's OpenAI-compatible endpoint. |
| `SLUICE_MODEL` | Worker model id. No default is guessed; the worker refuses to call without one. Examples to set explicitly: a mini-class model id, Gemini Flash, a local Ollama model id, or a Meta contributor-tier id. |
| `SLUICE_API_KEY` | Worker key. Fallbacks if unset: `OPENAI_API_KEY`, `GEMINI_API_KEY` / `GOOGLE_API_KEY`, `META_MODEL_API_KEY`. Ollama on localhost needs no key. |
| `SLUICE_PROVIDER` | Informational: `openai`, `gemini`, `ollama`, `meta`, `custom`. Selects the base-URL fallback and key fallback only. |
| `SLUICE_PRICE_INPUT_PER_1M`, `SLUICE_PRICE_OUTPUT_PER_1M` | Dollars per 1M tokens, for worker dollar reporting. If unset, worker dollars are unknown (null), never 0. For the Meta contributor tier, the documented rates are $0.10 input / $0.20 output per 1M tokens; set those explicitly if that is your worker. |
| `SLUICE_METER_FILE` | Meter file override. Default `~/.sluice/meter.jsonl`. |

Check the worker without paying anything:

```
python3 sluice/bulk_read.py --files benchmarks/fixtures/checks_fixture.py \
  --question "List every check class, with its line number." --dry-run
```

`--dry-run` prints the prompt and estimates and makes no call.

## Use

Blocked Read example: the hook returns a deny with the bulk-read
skill as the redirect. Run the skill's command, use only its bullets,
and do not reassemble the file through smaller reads or another shell
verb. Targeted reads (limit <= threshold, offset + limit, small
files, piped shell reads, `head` alone) pass untouched, verified by
the 7 targeted flows in the benchmark.

Code-write example:

```
python3 sluice/code_write.py --spec spec.md --reference ref.py --out new_module.py
```

Then run the repo's existing tests against `new_module.py`. If they
fail, fix the spec or reference and re-run; do not debug the generated
code by reading it wholesale, or the saving is lost.

Meter:

```
python3 -m sluice.meter report
python3 -m sluice.meter record --kind bulk-read --file a.py --avoided-estimate 5000 --worker-tokens 900
```

## Muse Code (v0.3.0)

Muse Code's tools are lowercase snake_case (`bash`,
`read_file`), so `adapters/muse/check-muse.py` is one PreToolUse
script for those two names: shell reads and `head` / `tail -n`
over the threshold, and unbounded `read_file` calls over the
threshold; windows and limits <= threshold pass. It ships as a
native plugin bundle (`adapters/muse/plugin/`, install with
`muse plugins install … --scope user`, then approve), or as a
project `.muse/hooks.json` pair. Verified on this VM against
Muse Code 1.4.14 itself: plugin validation clean, and Muse's
own offline `muse plugins hook test` harness passes 9/9 cases
(block big cat / `head -n 1000` / big read; pass small, piped,
bare head, windowed read, edit). One harness quirk: in 1.4.14
the fixture's `stdin` must be a JSON object, not a string.
A live real-model session check is still owed, as for the
other hosts. Full steps and gaps are in
`adapters/muse/README.md`.

## Out of scope

Subagent routing, editing delegation, reasoning delegation, a team
server, and any hosted component. (Codex support was out of scope
for v1 and landed in v0.2.0; Muse Code landed in v0.3.0.)

## Development

```
python3 -m unittest discover -s tests        # 46 tests, $0
python3 benchmarks/run_benchmarks.py         # stub benchmark, $0, local mock server
python3 analysis/phase0_measure.py           # Phase 0, $0, trace-commons corpus
```

No dependencies beyond the Python standard library. No paid model
calls in tests or the stub benchmark; the live benchmark is a
separate, approval-gated run (see the table above).

## Licence

MIT, see `LICENSE`.
