---
name: code-write
description: Generate boilerplate or implementation code through a cheap worker that writes straight to disk, so the coordinator never sees the generated code. Use for new modules and large routine implementations from a spec plus a reference file. Never use for debugging, architecture decisions, safety-critical code, or edits based on summaries.
---

# Code-write

Use this skill when a new file (or a large new section) would
otherwise be generated in coordinator context and then re-read.

## Steps

1. Write a short spec file first: what the module must do, its public
   names, its inputs and outputs, and the tests it must pass. Pick
   one reference file that shows the codebase's conventions.
2. Run the code-write worker from the plugin directory:
   `python3 sluice/code_write.py --spec <spec.md> --reference <ref.py> --out <new_file.py>`
   The worker writes the code straight to `--out` and prints only a
   small JSON summary (path, lines, bytes, measured worker tokens).
   The generated code is not in the coordinator's context and must
   not be pasted back into it.
3. Run the repo's existing tests against the new file. If tests
   fail, fix the spec or the reference and re-run the worker; do not
   debug the generated code in coordinator context by reading it
   wholesale, or the saving is lost. Small targeted reads of failing
   lines are fine.
4. The worker appends a meter record. Do not edit meter records
   by hand.

## Exclusions (shared with bulk-read)

No debugging, no architecture decisions, no safety-critical code,
no edits based on summaries. If the task is one of those, do it in
coordinator context and do not use this skill. `--task-type` values
`debug`, `architecture`, and `safety-critical` are refused by the
worker script itself.
