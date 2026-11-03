---
name: bulk-read
description: Summarise large files through a cheap worker instead of reading them into coordinator context. Use when a Read or shell dump is blocked by Sluice, or before reading any file over the SLUICE_MIN_LINES threshold (default 350 lines). Do not use for targeted reads of small ranges.
---

# Bulk-read

When Sluice blocks a Read or a shell dump, do not try another route to
the full file (another Read, a different shell verb, a smaller chunk
that reassembles the whole file). That is the bypass the hooks exist
to close. Use this skill instead.

## Steps

1. State the exact question first, in one sentence. Vague questions
   ("summarise this file") get vague summaries. Good: "List every
   check class in this file, with its file line number and the
   condition it checks."
2. Run the bulk-read worker from the plugin directory:
   `python3 sluice/bulk_read.py --files <path> [<path>...] --question "<question>"`
   The worker is configured by environment only: `SLUICE_BASE_URL`,
   `SLUICE_MODEL`, `SLUICE_API_KEY` (see the repo README). If the
   worker is not configured, say so and stop; do not read the file
   yourself as a fallback, or the hook is meaningless.
3. Use only the worker's structured bullets to continue. Treat its
   names, types, and line numbers as the answer. If a bullet is
   ambiguous, ask the worker a narrower follow-up question about the
   same files, not a full read.
4. The worker appends a meter record (files, threshold decision,
   measured worker tokens/dollars, avoided estimate). Do not edit
   meter records by hand.

## Output contract (worker)

Structured bullets, exact names, types, and line numbers first,
nothing unasked. If the question cannot be answered from the files,
the worker says so in one line.

## Exclusions (shared with code-write)

No debugging, no architecture decisions, no safety-critical code,
no edits based on summaries. This skill summarises; it does not
decide, fix, or design.
