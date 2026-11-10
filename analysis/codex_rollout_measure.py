#!/usr/bin/env python3
"""Codex rollout bulk-read measurement (Sluice Phase 0, Codex leg).

Corpus: ~/workspace/user/corpus/public/codex-aletheia/, 53 headless
Codex CLI 0.141.0 rollouts (June 2026), record types session_meta /
event_msg / turn_context / response_item. Only response_item records
are tool calls; event_msg records are session events, not calls.

Method, mirroring ~/workspace/sluice/analysis/phase0_measure.py:
- Pair function_call_output to function_call by call_id (verified
  1:1 in this corpus: 3,035 calls, 3,035 outputs, no duplicate
  call_ids). custom_tool_call (apply_patch) is paired the same way
  but reported separately: its input is model-generated code, not
  a tool-result payload.
- Exec outputs carry a header ("Chunk ID / Wall time / Process
  exited / Original token count / Output:"). The body after
  "Output:" is what is counted for lines. Two token figures are
  kept apart and never pooled:
  * recorded tokens: the header's "Original token count". For
    untruncated outputs this equals ceil(body chars / 4) exactly
    (median ratio 1.0 over bulk outputs); for truncated outputs
    (max_output_tokens caps the body, e.g. ~10k tokens of body
    against a 140,939 recorded count for `rg --files`) it is the
    pre-truncation count. This is the headline token figure.
  * body chars/4: the truncated body's size, reported only as a
    cross-check.
  Body line counts are therefore LOWER BOUNDS for truncated
  outputs: an output already at 877 body lines was at least that
  big before truncation.
- Bulk = body lines >= threshold (default 350, same as Sluice).
  Threshold sensitivity is computed at 200 / 350 / 500 / 1000.

Command classification (per exec_command `cmd`, segments split
on ;, &&, ||, newlines outside quotes, as in check-codex.py):
- strict_read: an unpiped segment whose verb is cat / less / more /
  Get-Content / gc / type. These are what check-codex.py blocks
  when the file(s) total over threshold.
- head_tail_n: head / tail with an explicit -n over threshold.
  Also blocked by check-codex.py (Codex-only rule).
- gap_read: sed / awk / python -c open(...) segments. These are
  bulk reads check-codex.py does NOT parse (stated gap).
- other: everything else (rg / grep search, git diff, ls, test
  runners, builds, servers). Bulk output here is NOT a bulk read:
  Sluice must not block test logs or diffs, and rg --files output
  is a file listing, not file content.

Adapter simulation is therefore output-side, not file-side: a
call is counted "would-block" when it is a strict_read or
head_tail_n call AND its (truncated, lower-bound) body is bulk.
The proxy assumption is stated in the report: for cat/head the
output lines approximate the file size; for truncated outputs
the true size is larger, so would-block is a lower bound, not
an overcount. Files do not exist on this VM (rollout cwd is
/workspace), so the adapter itself cannot be run against them;
its file-size logic is not re-executed, only its command
classification is mirrored here.

write_stdin outputs (52) are polls of already-running exec
sessions, not new calls: they are counted separately and never
added to exec totals, to avoid double-counting chunked output.
MCP tools in this corpus (context7 resolve_library_id /
query_docs, 8 calls) are documentation lookups, not filesystem
reads, and are counted as other.

Output: codex_rollout_results.json next to this script, plus a
human report written separately (CODEX_ROLLOUT_REPORT.md).
The results also carry the Nov 9 additions: sed-rule threshold
sensitivity (adapter's own window math), the first-token verb
breakdown, and the per-session bulk-share histogram.
"""
from __future__ import annotations

import glob
import json
import math
import os
import re
import shlex
from collections import Counter, defaultdict

CORPUS = os.path.expanduser(
    "~/workspace/user/corpus/public/codex-aletheia/*.jsonl")
OUT = os.path.join(os.path.dirname(__file__), "codex_rollout_results.json")
THRESHOLDS = (200, 350, 500, 1000)
READ_VERBS = {"cat", "less", "more", "get-content", "gc", "type"}
HEAD_TAIL = {"head", "tail"}


def split_segments(command: str) -> list[str]:
    segments, buf, quote = [], [], None
    i = 0
    while i < len(command):
        ch = command[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif command[i:i + 2] in ("&&", "||"):
            segments.append("".join(buf))
            buf = []
            i += 1
        elif ch in (";", "\n"):
            segments.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    segments.append("".join(buf))
    return [s.strip() for s in segments if s.strip()]


def tokens_of(segment: str) -> list[str]:
    try:
        return [t.strip('"').strip("'") for t in shlex.split(segment, posix=False)]
    except ValueError:
        return []


def head_tail_count(tokens: list[str]) -> int | None:
    i = 1
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("-n", "--lines"):
            if i + 1 < len(tokens):
                m = re.search(r"\d+", tokens[i + 1])
                return int(m.group()) if m else None
            return None
        m = re.match(r"^--lines=(\d+)", tok)
        if m:
            return int(m.group(1))
        m = re.match(r"^-n(\d+)$", tok)
        if m:
            return int(m.group(1))
        m = re.match(r"^-(\d+)$", tok)
        if m:
            return int(m.group(1))
        i += 1
    return None


def classify(cmd: str, threshold: int = 350) -> set[str]:
    """Command classes for one exec_command cmd string."""
    classes = set()
    if not isinstance(cmd, str) or not cmd:
        return classes
    for segment in split_segments(cmd):
        piped = "|" in segment
        tokens = tokens_of(segment)
        if not tokens:
            continue
        verb = tokens[0].lower()
        if verb in READ_VERBS and not piped:
            classes.add("strict_read")
        elif verb in HEAD_TAIL:
            wanted = head_tail_count(tokens)
            if wanted is not None and wanted > threshold and not piped:
                classes.add("head_tail_n")
        elif verb in ("sed", "awk"):
            classes.add("gap_read")
        elif verb in ("python", "python3", "python2") and (
            "open(" in segment or ".read(" in segment
        ):
            classes.add("gap_read")
    return classes


def body_of(output: str) -> tuple[str, int | None]:
    """(body after Output: header, recorded original token count)."""
    m = re.search(r"Original token count: (\d+)", output)
    recorded = int(m.group(1)) if m else None
    if "Output:\n" in output:
        return output.split("Output:\n", 1)[1], recorded
    return output, recorded


def line_count(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def sed_rule_sensitivity(exec_rows: list[dict]) -> dict:
    """Blocked calls/tokens per threshold under the shipped sed rule.

    Uses the adapter's own window math (adapters/codex/check-codex.py)
    with each window capped at an effectively-infinite file length,
    because the rollout files are not on disk: this is the explicit
    range-size sum, the same approximation as the Nov 4 simulation.
    Non-quiet sed (full dump) has no cases in this corpus, so it
    contributes nothing here; the shipped rule sizes those by file.
    Only -n windowed calls are counted; a call counts once even
    when several sed parts sum over the threshold.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "check_codex",
        os.path.join(os.path.dirname(__file__),
                     "..", "adapters", "codex", "check-codex.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    big = [10 ** 9]
    # Per call: summed explicit window size (uncapped), recorded
    # tokens, and recorded body lines.
    call_windows: list[tuple[int, int, int]] = []
    window_sizes: list[int] = []
    for row in exec_rows:
        total = 0
        sized = False
        for segment in mod.split_segments(row["cmd"]):
            tokens = mod.tokens_of(segment)
            parts, cur = [], []
            for tok in tokens:
                if tok == "|":
                    parts.append(cur)
                    cur = []
                else:
                    cur.append(tok)
            parts.append(cur)
            for idx, part in enumerate(parts):
                if not part or os.path.basename(part[0]).lower() != "sed":
                    continue
                if idx < len(parts) - 1:
                    continue  # piped onward: passes
                scripts, _files = mod.sed_scripts_and_files(part)
                if not mod.sed_quiet(part):
                    continue
                for s in scripts:
                    for a, b in mod._RANGE_RE.findall(s):
                        window_sizes.append(int(b) - int(a) + 1)
                    for a in mod._RANGE_DOLLAR_RE.findall(s):
                        window_sizes.append(10 ** 9)  # to end of file: unbounded here
                    for a in mod._SINGLE_RE.findall(s):
                        window_sizes.append(1)
                total += sum(
                    mod.sed_script_lines(s, big, per_file=True)
                    for s in scripts)
                sized = True
        if sized:
            call_windows.append(
                (total, row["recorded_tokens"] or 0, row["body_lines"]))
    out: dict = {
        "windows_total": len(window_sizes),
        "windows_over_350": sum(1 for w in window_sizes if 350 < w < 10 ** 9),
        "windows_unbounded_dollar": sum(1 for w in window_sizes if w >= 10 ** 9),
        "by_threshold": {},
    }
    for thr in THRESHOLDS:
        # (a) output-confirmed: window sum over threshold AND the
        # recorded body is itself bulk at that threshold (lower bound;
        # at 350 this reproduces the Nov 4 simulation's 102 calls).
        # (b) window-only: window sum over threshold regardless of
        # body (upper bound; overcounts windows that run past the
        # end of a short file, which the shipped rule caps).
        # The truth with real files lies between, closer to (a):
        # in this corpus windows match file sizes closely.
        blocked_b = [(t, tok) for t, tok, _ in call_windows if t > thr]
        blocked_a = [(t, tok) for t, tok, lines in call_windows
                     if t > thr and lines >= thr]
        out["by_threshold"][str(thr)] = {
            "blocked_calls_output_confirmed": len(blocked_a),
            "blocked_recorded_tokens_output_confirmed": sum(
                tok for _, tok in blocked_a),
            "blocked_calls_window_only": len(blocked_b),
            "blocked_recorded_tokens_window_only": sum(
                tok for _, tok in blocked_b),
        }
    return out


def main() -> None:
    files = sorted(glob.glob(CORPUS))
    calls: dict[str, dict] = {}
    outputs: dict[str, dict] = {}
    custom_calls: dict[str, dict] = {}
    custom_outputs: dict[str, dict] = {}
    raw_function_calls = 0
    for path in files:
        for line in open(path, encoding="utf-8"):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") != "response_item":
                continue
            pl = rec.get("payload", {})
            t = pl.get("type")
            if t == "function_call":
                raw_function_calls += 1
                calls[pl["call_id"]] = pl
            elif t == "function_call_output":
                outputs[pl["call_id"]] = pl
            elif t == "custom_tool_call":
                custom_calls[pl["call_id"]] = pl
            elif t == "custom_tool_call_output":
                custom_outputs[pl["call_id"]] = pl
    assert len(calls) == raw_function_calls, "duplicate function_call call_ids"
    assert set(calls) == set(outputs), "call/output pairing mismatch"

    exec_rows = []
    other_rows = []
    ws_rows = []
    for cid, call in calls.items():
        name = call.get("name")
        out = outputs[cid].get("output", "")
        if not isinstance(out, str):
            out = json.dumps(out)
        if name == "exec_command":
            try:
                args = json.loads(call.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}
            body, recorded = body_of(out)
            lines = line_count(body)
            row = {
                "call_id": cid,
                "cmd": args.get("cmd", ""),
                "classes": sorted(classify(args.get("cmd", ""))),
                "body_lines": lines,
                "body_chars": len(body),
                "body_tokens_est": math.ceil(len(body) / 4),
                "recorded_tokens": recorded,
                "truncated": recorded is not None
                and recorded > math.ceil(len(body) / 4) * 1.05,
            }
            exec_rows.append(row)
        elif name == "write_stdin":
            body, recorded = body_of(out)
            ws_rows.append({
                "body_lines": line_count(body),
                "body_chars": len(body),
                "recorded_tokens": recorded,
            })
        else:
            other_rows.append({
                "name": name,
                "output_lines": line_count(out),
                "output_chars": len(out),
                "output_tokens_est": math.ceil(len(out) / 4),
            })

    exec_total_recorded = sum(r["recorded_tokens"] or 0 for r in exec_rows)
    exec_total_body_est = sum(r["body_tokens_est"] for r in exec_rows)
    other_total_est = sum(
        r["output_tokens_est"] for r in other_rows
        if r["name"] != "view_image")
    view_image_rows = [r for r in other_rows if r["name"] == "view_image"]

    def bulk(rows, thr):
        return [r for r in rows if r["body_lines"] >= thr]

    per_session: dict[str, dict] = defaultdict(lambda: {
        "exec_calls": 0, "exec_bulk_calls": 0,
        "exec_recorded_tokens": 0, "exec_bulk_recorded_tokens": 0,
        "would_block_calls": 0, "would_block_tokens": 0,
        "gap_bulk_calls": 0, "gap_bulk_tokens": 0,
    })
    # Re-walk files for per-session attribution (call_id -> file).
    file_of_call: dict[str, str] = {}
    for path in files:
        base = os.path.basename(path)
        for line in open(path, encoding="utf-8"):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") == "response_item":
                pl = rec.get("payload", {})
                if pl.get("type") == "function_call" and pl.get("call_id"):
                    file_of_call[pl["call_id"]] = base
    for r in exec_rows:
        s = per_session[file_of_call.get(r["call_id"], "unknown")]
        s["exec_calls"] += 1
        s["exec_recorded_tokens"] += r["recorded_tokens"] or 0
        if r["body_lines"] >= 350:
            s["exec_bulk_calls"] += 1
            s["exec_bulk_recorded_tokens"] += r["recorded_tokens"] or 0
            cls = set(r["classes"])
            if cls & {"strict_read", "head_tail_n"}:
                s["would_block_calls"] += 1
                s["would_block_tokens"] += r["recorded_tokens"] or 0
            if "gap_read" in cls and not (cls & {"strict_read", "head_tail_n"}):
                s["gap_bulk_calls"] += 1
                s["gap_bulk_tokens"] += r["recorded_tokens"] or 0

    bulk350 = bulk(exec_rows, 350)
    would_block = [r for r in bulk350
                   if set(r["classes"]) & {"strict_read", "head_tail_n"}]
    gap_bulk = [r for r in bulk350
                if "gap_read" in r["classes"]
                and not (set(r["classes"]) & {"strict_read", "head_tail_n"})]
    other_bulk = [r for r in bulk350
                  if not r["classes"]]
    mixed_bulk = [r for r in bulk350
                  if r["classes"] and "gap_read" not in r["classes"]
                  and not (set(r["classes"]) & {"strict_read", "head_tail_n"})]

    verb_bulk = Counter()
    for r in bulk350:
        cmd = r["cmd"].strip()
        first = cmd.split()[0] if cmd.split() else ""
        verb_bulk[first] += 1

    sensitivity = {}
    for thr in THRESHOLDS:
        b = bulk(exec_rows, thr)
        sensitivity[str(thr)] = {
            "bulk_calls": len(b),
            "bulk_share_calls_pct": round(100 * len(b) / len(exec_rows), 1)
            if exec_rows else 0,
            "bulk_recorded_tokens": sum(r["recorded_tokens"] or 0 for r in b),
            "bulk_share_tokens_pct": round(
                100 * sum(r["recorded_tokens"] or 0 for r in b)
                / exec_total_recorded, 1) if exec_total_recorded else 0,
        }

    patch_input_tokens = 0
    for cid, pl in custom_calls.items():
        inp = pl.get("input", "")
        patch_input_tokens += math.ceil(len(inp) / 4)
    patch_output_tokens = 0
    for cid, pl in custom_outputs.items():
        out = pl.get("output", "")
        if not isinstance(out, str):
            out = json.dumps(out)
        patch_output_tokens += math.ceil(len(out) / 4)

    sessions_with_bulk = sum(1 for s in per_session.values()
                             if s["exec_bulk_calls"] > 0)
    sessions_with_would_block = sum(1 for s in per_session.values()
                                    if s["would_block_calls"] > 0)
    # Per-session bulk-share histogram (bulk recorded tokens as a
    # share of that session's exec recorded tokens).
    hist = Counter({"0%": 0, "1-10%": 0, "11-25%": 0, "26-50%": 0, ">50%": 0})
    for s in per_session.values():
        tot = s["exec_recorded_tokens"]
        share = (s["exec_bulk_recorded_tokens"] / tot) if tot else 0
        if share == 0:
            hist["0%"] += 1
        elif share <= 0.10:
            hist["1-10%"] += 1
        elif share <= 0.25:
            hist["11-25%"] += 1
        elif share <= 0.50:
            hist["26-50%"] += 1
        else:
            hist[">50%"] += 1
    # First-token verb breakdown for exec calls.
    verb_stats: dict[str, dict] = defaultdict(
        lambda: {"calls": 0, "bulk_calls": 0, "bulk_recorded_tokens": 0})
    for r in exec_rows:
        verb = r["cmd"].split()[0] if r["cmd"].split() else ""
        v = verb_stats[verb]
        v["calls"] += 1
        if r["body_lines"] >= 350:
            v["bulk_calls"] += 1
            v["bulk_recorded_tokens"] += r["recorded_tokens"] or 0
    verb_breakdown = sorted(
        ((verb, s["calls"], s["bulk_calls"], s["bulk_recorded_tokens"])
         for verb, s in verb_stats.items()),
        key=lambda t: -t[3])
    top_sessions = sorted(
        per_session.items(),
        key=lambda kv: kv[1]["exec_bulk_recorded_tokens"],
        reverse=True)[:5]
    top_sessions = [{
        "file": f,
        "exec_bulk_calls": s["exec_bulk_calls"],
        "exec_bulk_recorded_tokens": s["exec_bulk_recorded_tokens"],
        "would_block_calls": s["would_block_calls"],
    } for f, s in top_sessions]

    results = {
        "corpus": {"files": len(files),
                   "function_calls": len(calls),
                   "function_call_outputs": len(outputs),
                   "apply_patch_calls": len(custom_calls)},
        "exec": {
            "calls": len(exec_rows),
            "total_recorded_tokens": exec_total_recorded,
            "total_body_tokens_est": exec_total_body_est,
            "bulk_350_calls": len(bulk350),
            "bulk_350_share_calls_pct": round(100 * len(bulk350) / len(exec_rows), 1),
            "bulk_350_recorded_tokens": sum(r["recorded_tokens"] or 0 for r in bulk350),
            "bulk_350_share_tokens_pct": round(
                100 * sum(r["recorded_tokens"] or 0 for r in bulk350)
                / exec_total_recorded, 1),
            "would_block_calls": len(would_block),
            "would_block_recorded_tokens": sum(r["recorded_tokens"] or 0 for r in would_block),
            "would_block_share_of_bulk_tokens_pct": round(
                100 * sum(r["recorded_tokens"] or 0 for r in would_block)
                / sum(r["recorded_tokens"] or 0 for r in bulk350), 1)
            if bulk350 else 0,
            "gap_bulk_calls": len(gap_bulk),
            "gap_bulk_recorded_tokens": sum(r["recorded_tokens"] or 0 for r in gap_bulk),
            "other_bulk_calls": len(other_bulk) + len(mixed_bulk),
            "other_bulk_recorded_tokens": sum(
                r["recorded_tokens"] or 0 for r in other_bulk + mixed_bulk),
            "truncated_bulk_calls": sum(1 for r in bulk350 if r["truncated"]),
            "strict_read_total_calls": sum(
                1 for r in exec_rows if "strict_read" in r["classes"]),
            "head_tail_n_total_calls": sum(
                1 for r in exec_rows if "head_tail_n" in r["classes"]),
            "gap_read_total_calls": sum(
                1 for r in exec_rows if "gap_read" in r["classes"]),
            "bulk_verb_top": verb_bulk.most_common(12),
        },
        "threshold_sensitivity": sensitivity,
        "sed_rule_sensitivity": sed_rule_sensitivity(exec_rows),
        "verb_breakdown": verb_breakdown,
        "per_session_bulk_share_histogram": dict(hist),
        "other_tools": {
            "calls": len(other_rows),
            # view_image outputs are base64 PNG bytes, not text: their
            # chars/4 is not a token count, so they are excluded from
            # output_tokens_est and reported as chars only.
            "output_tokens_est": other_total_est,
            "view_image_calls": len(view_image_rows),
            "view_image_output_chars": sum(
                r["output_chars"] for r in view_image_rows),
            "by_name": Counter(r["name"] for r in other_rows).most_common(),
        },
        "write_stdin_excluded": {
            "calls": len(ws_rows),
            "total_lines": sum(r["body_lines"] for r in ws_rows),
            "total_recorded_tokens": sum(r["recorded_tokens"] or 0
                                         for r in ws_rows if r["recorded_tokens"]),
        },
        "apply_patch_generated": {
            "calls": len(custom_calls),
            "input_tokens_est": patch_input_tokens,
            "output_tokens_est": patch_output_tokens,
        },
        "per_session": {
            "sessions": len(per_session),
            "sessions_with_bulk_exec": sessions_with_bulk,
            "sessions_with_would_block": sessions_with_would_block,
            "top_by_bulk_tokens": top_sessions,
        },
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
