# Codex rollout bulk-read analysis (Sluice Phase 0, Codex leg)

Script: `codex_rollout_measure.py` in this directory.
Results: `codex_rollout_results.json` in this directory.
Corpus: 53 headless Codex CLI 0.141.0 rollouts, June 2026,
`~/workspace/user/corpus/public/codex-aletheia/`.
Run: Nov 4, 2026, $0, local script only.

## Method (and where it differs from the Claude Code Phase 0)

- Only `response_item` records are tool calls. `event_msg`
  records are session events, not calls. `function_call_output`
  pairs to `function_call` by `call_id`: verified 1:1, 3,035
  calls to 3,035 outputs, no duplicate call_ids.
- Exec outputs carry a header (`Chunk ID / Wall time / Process
  exited / Original token count / Output:`). Lines are counted
  on the body after `Output:`. Two token figures are kept apart:
  recorded tokens (the header's original count) are the headline
  figure; body chars/4 is a cross-check only. For untruncated
  outputs they are identical (median ratio 1.0 over bulk
  outputs). For truncated outputs (body capped by
  `max_output_tokens`, e.g. ~10k body tokens against a 140,939
  recorded count for `rg --files`) the recorded count is the
  pre-truncation size, and body lines are a LOWER BOUND.
- Bulk = body lines >= 350, the Sluice default.
- `write_stdin` outputs (52) are polls of already-running exec
  sessions, not new calls: counted separately, never added to
  exec totals.
- `view_image` outputs (195) are base64 PNG bytes (89,482,954
  chars): their chars/4 is not a token count, so they are
  excluded from all token totals and reported as chars only.
- `apply_patch` input is model-generated code, not a tool-result
  payload: reported separately, never pooled with exec tokens.
- Adapter simulation is output-side, not file-side: a call is
  counted "would-block" when it is a strict cat/less/more or
  `head`/`tail -n` call AND its (truncated, lower-bound) body
  is bulk. Rollout files do not exist on this VM (cwd is
  `/workspace`), so the adapter's file-size check cannot be
  re-executed; for cat/head, output lines approximate file size,
  so would-block is a lower bound, not an overcount.

## Headline

| | Calls | Recorded tokens |
| --- | --- | --- |
| exec_command, all | 2,487 | 1,668,420 |
| exec bulk (>= 350 body lines) | 113 (4.5%) | 598,461 (35.9% of exec) |
| of which the shipped Codex adapter would block | **0 (0%)** | **0** |
| of which are the sed/awk gap (see below) | 96 (85.0% of bulk calls) | 260,048 (43.5% of bulk tokens, 15.6% of all exec tokens) |
| of which are other bulk output (not reads) | 17 | 338,413 (56.5% of bulk tokens) |

## The finding that matters

The shipped Codex adapter would block nothing in these 53
sessions. That is not a classification bug, it is the workload:

- Only **11 cat calls in the whole corpus, largest 89 lines**,
  and **0 head/tail -n calls**. The cat rule and the head rule
  simply have nothing to bite on here.
- The bulk read path in this corpus is **`sed -n` windows**:
  644 gap-classified (sed/awk/python) exec calls in total, 96
  of them bulk. Bulk-output verbs: sed 96, rg 6, nl 6 (nl piped
  into sed), yarn 3, git 1, forge 1.
- Sed windows are mostly targeted: 749 `sed -n 'A,Bp'`
  windows in total, 630 of them <= 350 lines. A range-size rule
  at 350 would preserve those 630 and block the 119 windows
  over 350 (94 in 351–500, 25 in 501–1000). A few bulk calls are
  chains of targeted windows (e.g. 111 + 101 + 131 + ... lines
  in one command, 449 total), so the rule should sum window
  sizes per command, the way the cat rule sums file lines per
  call — otherwise chained windows slip through per-window.
- The other bulk tokens must NOT be blocked: the largest bulk
  outputs are truncated `rg --files` file listings (140,939 and
  67,065 recorded tokens, ~10k body tokens each), `rg -n`
  searches, a `git diff`, and test-runner logs. A file listing
  is not file content, and blocking test logs or diffs would
  break the workflow. Bulk output is not bulk reading, and this
  corpus is the proof: 56.5% of bulk exec tokens are not reads
  at all.

## Per-session

- 53 files: 52 sessions with exec calls, 1 with no tool calls
  at all (messages/reasoning/tool schemas only).
- 40 of 52 exec sessions have at least one bulk exec output;
  **0 have a would-block call**.
- Do not rank sessions by bulk tokens alone: the top session
  (148,064 bulk recorded tokens) is dominated by a single
  truncated `rg --files` listing, not by reads.

## Threshold sensitivity (exec outputs, recorded tokens)

| Threshold | Bulk calls | Share of exec calls | Bulk recorded tokens | Share of exec tokens |
| --- | --- | --- | --- | --- |
| 200 lines | 375 | 15.1% | 1,155,175 | 69.2% |
| **350 lines** | **113** | **4.5%** | **598,461** | **35.9%** |
| 500 lines | 32 | 1.3% | 330,352 | 19.8% |
| 1000 lines | 1 | 0.0% | 10,510 | 0.6% |

## Separately, not pooled

- apply_patch generated code: 1,033 calls, ~972,535 estimated
  tokens of patch input (model output, not coordinator input
  from a tool result), 28,748 of patch output.
- write_stdin polls (excluded): 52 calls, 723 body lines,
  7,960 recorded tokens.
- view_image (excluded from tokens): 195 calls, 89,482,954
  chars of base64 PNG.
- MCP in this corpus: 8 calls, all context7 documentation
  lookups (resolve_library_id / query_docs), no MCP filesystem
  reads — so the adapter's MCP-read rule is untested here.

## Verdict and recommendation

For this corpus, Sluice-as-shipped for Codex saves ~0
coordinator tokens: the cat/head rules cover a read path
these agents do not use, and the sed path they do use is the
adapter's stated gap. With a sed range rule (sum `sed -n`
window sizes per command; block over 350, pass at or under),
the adapter would redirect 96 bulk calls / 260,048 recorded
tokens of read output in this corpus — before worker cost and
summary size, so that is a coordinator-context figure, not a
net saving claim, under the meter's honesty rule.

Recommendation: build the sed range rule as the Codex
adapter's next change, with tests mirroring this corpus
(targeted windows pass, over-threshold and chained windows
block, `rg`/`git diff`/test logs untouched). Do not broaden
the rule to rg, diff, or test output to chase the other
56.5% of bulk tokens — that would block non-reads.

Status: BUILT Nov 4, 2026, as Sluice v0.3.1
(`adapters/codex/check-codex.py`, 19 new tests in
`tests/test_codex_hook.py`, full suite 65/65). One-off
simulation applying the rule's window math to the corpus
commands (`/tmp/sim_sed_coverage.py`, explicit range sizes,
no file capping since the files are not on disk): **102 bulk
calls / 288,248 recorded tokens would block** — the 96 gap
calls plus the 6 `nl | sed` calls the gap count classed
under `nl`. All 102 have explicit `A,Bp` windows summing
over 350; none need `$`/pattern sizing. With file capping
(the shipped rule caps each window at the file's actual
length) that count can only stay flat or drop slightly for
short files.

## Limits

- June 2026, CLI 0.141.0, headless stacked-task rollouts:
  not interactive sessions, and not Yuriy's own sessions.
  His personal bulk share is still the open Phase 0 gap.
- Output-side proxy (see Method): file sizes were not on
  disk, and truncated outputs make line counts lower bounds.
- The 350 threshold aligns with this corpus's own window
  habit (630 of 749 sed windows <= 350), but that is
  descriptive, not a proof the threshold is optimal for other
  workloads.
