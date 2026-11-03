"""Phase 0 measurement for Sluice.

Corpus: trace-commons Claude Code sessions, 28 files, public, real Claude Code
JSONL (~/workspace/user/corpus/public/trace-commons/sessions/claude_code/).
NOT Yuriy's own recent sessions: this VM has no ~/.claude/projects and no
recent Yuriy JSONL drop, so this is a proxy corpus, stated in the report.

Method (reproducible, no tokenizer, no paid calls):
- Tool results are paired to tool calls by tool_use_id in file order.
- Token estimate = ceil(chars / 4) for the result / generated text.
  Labelled ESTIMATE everywhere; it is not a measured tokenizer count.
- Bulk = result with >= THRESHOLD lines (default 350), matching the hook
  threshold in the spec. A Read with an explicit limit <= threshold is
  targeted and its result is small by construction; the line count is
  the ground truth, not the limit field.
- Bash/PowerShell "read-like" = command contains a standalone
  cat/head/tail/less/more/Get-Content/gc/type token. Piped commands
  are still counted here for measurement (the hook passes piped /
  targeted ones through); the bulk subset is the hookable subset.
- Session usage fields are NOT summed: in these files the usage block
  repeats across consecutive assistant records, so a sum would double
  count. That is why the primary denominator is tool-result payload,
  and why Sluice's meter measures at delegation time instead.
"""
import json, glob, math, re, sys
from collections import Counter, defaultdict
from pathlib import Path

THRESHOLDS = [200, 350, 500, 1000]
READ_RE = re.compile(r'(?<![\w.-])(cat|head|tail|less|more|Get-Content|gc|type)(?![\w.-])', re.I)

def est(text):
    return math.ceil(len(text) / 4) if text else 0

def result_text(block):
    c = block.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = []
        for x in c:
            if isinstance(x, dict):
                if x.get("type") == "text":
                    parts.append(x.get("text") or "")
                elif "text" in x:
                    parts.append(str(x["text"]))
            elif isinstance(x, str):
                parts.append(x)
        return "\n".join(parts)
    return ""

def main():
    files = sorted(glob.glob("/home/hatch/workspace/user/corpus/public/trace-commons/sessions/claude_code/*.jsonl"))
    per_session = []
    total = Counter()
    buckets = Counter()
    read_calls = read_targeted = read_unlimited = 0
    bash_read_cmds = 0
    gen = Counter()
    all_tool_use_payload = 0
    for f in files:
        uses = {}  # id -> (name, input)
        s = Counter()
        for line in open(f, encoding="utf-8"):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("isSidechain") is True:
                continue
            if r.get("type") == "assistant":
                for b in (r.get("message") or {}).get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        uses[b.get("id")] = (b.get("name"), b.get("input") or {})
                        # generated payload
                        inp = b.get("input") or {}
                        if b.get("name") == "Write":
                            t = est(str(inp.get("content") or ""))
                            gen["write_tokens"] += t; gen["write_calls"] += 1
                            s["gen_tokens"] += t
                        elif b.get("name") == "Edit":
                            t = est(str(inp.get("new_string") or ""))
                            gen["edit_tokens"] += t; gen["edit_calls"] += 1
                            s["gen_tokens"] += t
                        all_tool_use_payload += est(json.dumps(inp, ensure_ascii=False))
                        if b.get("name") == "Read":
                            read_calls += 1; s["read_calls"] += 1
                            lim = inp.get("limit")
                            if isinstance(lim, (int, float)) and lim <= 350:
                                read_targeted += 1; s["read_targeted"] += 1
                            else:
                                read_unlimited += 1; s["read_unlimited"] += 1
                        if b.get("name") in ("Bash", "PowerShell"):
                            cmd = str((inp.get("command") or ""))
                            if READ_RE.search(cmd):
                                bash_read_cmds += 1; s["bash_read_cmds"] += 1
            if r.get("type") == "user":
                c = (r.get("message") or {}).get("content")
                if isinstance(c, list):
                    for b in c:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            name, inp = uses.get(b.get("tool_use_id"), (None, {}))
                            txt = result_text(b)
                            lines = txt.count("\n") + 1 if txt else 0
                            toks = est(txt)
                            s["result_tokens"] += toks; s["result_calls"] += 1
                            total["result_tokens"] += toks; total["result_calls"] += 1
                            if name == "Read":
                                # bucket by result lines
                                if lines == 0 or txt.startswith("File does not exist"):
                                    buckets["read_error_or_empty"] += 1
                                elif lines < 50: buckets["read_1_49"] += 1
                                elif lines < 200: buckets["read_50_199"] += 1
                                elif lines < 350: buckets["read_200_349"] += 1
                                elif lines < 1000: buckets["read_350_999"] += 1
                                else: buckets["read_1000_plus"] += 1
                                s["read_result_tokens"] += toks
                                if lines >= 350:
                                    s["read_bulk_tokens"] += toks; s["read_bulk_calls"] += 1
                                    total["read_bulk_tokens"] += toks; total["read_bulk_calls"] += 1
                                for th in THRESHOLDS:
                                    if lines >= th:
                                        total[f"read_bulk_tokens_{th}"] += toks
                            elif name in ("Bash", "PowerShell"):
                                cmd = str((inp.get("command") or ""))
                                if READ_RE.search(cmd):
                                    s["bash_read_result_tokens"] += toks
                                    if lines >= 350:
                                        s["bash_bulk_tokens"] += toks; s["bash_bulk_calls"] += 1
                                        total["bash_bulk_tokens"] += toks; total["bash_bulk_calls"] += 1
                                    for th in THRESHOLDS:
                                        if lines >= th:
                                            total[f"bash_bulk_tokens_{th}"] += toks
                            # per-threshold combined
                            if name == "Read" and lines >= 350:
                                s["bulk_tokens"] = s.get("bulk_tokens", 0) + toks
                            if name in ("Bash", "PowerShell") and READ_RE.search(str((inp.get("command") or ""))) and lines >= 350:
                                s["bulk_tokens"] = s.get("bulk_tokens", 0) + toks
        per_session.append((Path(f).stem, dict(s)))
    total["read_calls"] = read_calls; total["read_targeted"] = read_targeted; total["read_unlimited"] = read_unlimited
    total["bash_read_cmds"] = bash_read_cmds
    total["gen_tokens"] = gen["write_tokens"] + gen["edit_tokens"]
    total["gen_write_tokens"] = gen["write_tokens"]; total["gen_edit_tokens"] = gen["edit_tokens"]
    total["gen_write_calls"] = gen["write_calls"]; total["gen_edit_calls"] = gen["edit_calls"]
    total["all_tool_use_payload_est"] = all_tool_use_payload
    bulk = total["read_bulk_tokens"] + total["bash_bulk_tokens"]
    print(json.dumps({"sessions": len(files), "totals": dict(total), "buckets": dict(buckets),
                      "bulk_tokens_350": bulk,
                      "bulk_share_of_result_payload_pct": round(100*bulk/total["result_tokens"], 2) if total["result_tokens"] else 0,
                      "read_bulk_share_pct": round(100*total["read_bulk_tokens"]/total["result_tokens"], 2) if total["result_tokens"] else 0,
                      "bash_bulk_share_pct": round(100*total["bash_bulk_tokens"]/total["result_tokens"], 2) if total["result_tokens"] else 0,
                      "threshold_sensitivity_pct": {str(th): round(100*(total[f"read_bulk_tokens_{th}"]+total[f"bash_bulk_tokens_{th}"])/total["result_tokens"], 2) for th in THRESHOLDS},
                      "gen_share_of_tool_use_payload_pct": round(100*total["gen_tokens"]/all_tool_use_payload, 2) if all_tool_use_payload else 0,
                      }, indent=2))
    # per-session bulk share, sorted
    print("\nPER SESSION (bulk_tokens, result_tokens, bulk_pct, read_bulk_calls, bash_bulk_calls):")
    for stem, s in sorted(per_session, key=lambda x: -x[1].get("bulk_tokens", 0)):
        rt = s.get("result_tokens", 0); bt = s.get("bulk_tokens", 0)
        print(f"{stem} bulk={bt} result={rt} pct={round(100*bt/rt,1) if rt else 0} read_bulk_calls={s.get('read_bulk_calls',0)} bash_bulk_calls={s.get('bash_bulk_calls',0)} read_calls={s.get('read_calls',0)}")
    Path("/home/hatch/workspace/sluice/analysis/phase0_results.json").write_text(json.dumps({"sessions": len(files), "totals": dict(total), "buckets": dict(buckets), "per_session": per_session}, indent=2))
    print("\nWrote analysis/phase0_results.json")

if __name__ == "__main__":
    main()
