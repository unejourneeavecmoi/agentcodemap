"""Dry-run benchmark: how many tokens does an agent ingest per lookup task under three
ways of working, measured on real projects with real command output.

  OLD   the previous AGENTS.md wording: read CODE_MAP.md whole (index included), then open code
  GREP  no map at all: grep + open files
  RULE  the cost rule: query/explain/file/path for symbols, grep for literal strings,
        overview only when orienting, never the full index

Nothing is sent to a model. Token counts are tiktoken cl100k_base on the exact text an agent
would receive.

Run:  python cost_rule_benchmark.py [--tokenizer NAME] <project> [<project> ...]

--tokenizer picks how tokens are counted (default cl100k_base):
  cl100k_base | o200k_base   tiktoken encodings (pip install tiktoken). cl100k is the
                             usual proxy for Claude, whose tokenizer is not public.
  hf:<repo>                  any Hugging Face tokenizer (pip install transformers), e.g.
                             hf:deepseek-ai/DeepSeek-V3  hf:zai-org/GLM-4.5  hf:Qwen/Qwen3-8B
  chars4                     no dependencies: characters / 4, a rough estimate

Writes cost_rule_report[_<tag>].md and .html next to this script; the tag is the
tokenizer name when it is not the default.
"""
import html
import importlib.util
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CODEMAP = os.path.join(HERE, "codemap.py")   # the tool beside this script; projects need no copy
spec = importlib.util.spec_from_file_location("codemap", CODEMAP)
cm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cm)

TOKENIZER = "cl100k_base"
_count = None


def make_counter(name):
    """Return (label, function text -> token count) for a tokenizer name."""
    if name == "chars4":
        return "characters / 4 (estimate)", lambda s: (len(s) + 3) // 4
    if name.startswith("hf:"):
        from transformers import AutoTokenizer  # pip install transformers
        repo = name[3:]
        t = AutoTokenizer.from_pretrained(repo, trust_remote_code=True)
        return f"Hugging Face tokenizer {repo}", lambda s: len(t.encode(s, add_special_tokens=False))
    import tiktoken  # pip install tiktoken
    enc = tiktoken.get_encoding(name)
    return f"tiktoken {name}", lambda s: len(enc.encode(s, disallowed_special=()))


def tok(s):
    global _count
    if _count is None:
        _count = make_counter(TOKENIZER)[1]
    return _count(s or "")


GREP_LINE_CAP = 250      # the Grep tool returns at most 250 lines by default
CALLER_CAP = 10          # how many call sites an agent would realistically open
DEF_WINDOW = (10, 50)    # lines before/after a definition the agent reads
CALL_WINDOW = (10, 20)
LIT_WINDOW = (10, 10)


def read(path):
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def window(proj, rel, line, before, after):
    try:
        lines = read(os.path.join(proj, rel)).splitlines()
    except OSError:
        return ""
    s = max(0, line - 1 - before)
    return "\n".join(lines[s:line - 1 + after])


def code_files(proj):
    out = []
    for dirpath, dirnames, filenames in os.walk(proj):
        dirnames[:] = [d for d in dirnames if d not in cm.SKIP_DIRS]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if fn in cm.SKIP_FILES:
                continue
            if ext in cm.LANG_BY_EXT and ext not in cm.BINARY_EXT:
                p = os.path.join(dirpath, fn)
                if os.path.getsize(p) <= 2 * 1024 * 1024:
                    out.append(os.path.relpath(p, proj).replace("\\", "/"))
    return sorted(out)


def grep(proj, needle, files):
    """Simulated `grep -rn needle` over the project's code files (same skip rules as codemap)."""
    hits, lines = [], []
    for rel in files:
        try:
            src = read(os.path.join(proj, rel))
        except OSError:
            continue
        for i, l in enumerate(src.splitlines(), 1):
            if needle in l:
                hits.append((rel, i))
                lines.append(f"{rel}:{i}:{l.strip()[:200]}")
    total = len(lines)
    text = "\n".join(lines[:GREP_LINE_CAP])
    if total > GREP_LINE_CAP:
        text += f"\n[{total - GREP_LINE_CAP} more lines truncated]"
    return text, hits


def cmd(proj, *args):
    r = subprocess.run([sys.executable, CODEMAP, *args], cwd=proj, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return r.stdout


def pick_literal(proj, rel_candidates):
    # sentence-shaped UI text: Capitalised word, then 2+ lowercase words, optional end mark.
    # Excludes CSS font lists, paths and code-ish strings.
    pat = re.compile(r"""["'](?!.*(?:serif|Mono|px|http|\\|/))([A-Z][a-z]+(?: [a-z]+){2,8}[.!?]?)["']""")
    for rel in rel_candidates:
        try:
            m = pat.search(read(os.path.join(proj, rel)))
        except OSError:
            continue
        if m:
            return m.group(1)
    return None


def bench(proj):
    proj = os.path.abspath(proj)
    name = os.path.basename(proj)
    out = os.path.join(proj, cm.OUT_DIR)
    subprocess.run([sys.executable, CODEMAP, "."], cwd=proj, capture_output=True)
    graph = json.load(io.open(os.path.join(out, "map.json"), encoding="utf-8"))
    nodes = graph["nodes"]
    overview = read(os.path.join(out, "CODE_MAP.md"))
    index = read(os.path.join(out, "CODE_MAP_INDEX.md"))
    old_map = overview + "\n" + index          # what the single-file CODE_MAP.md used to be
    files = code_files(proj)

    by_file = {}
    for n in nodes:
        if n["kind"] != "file":
            by_file.setdefault(n["file"], []).append(n)
    big_file = max(by_file, key=lambda f: len(by_file[f]))

    # hubs: project-defined names only, skipping builtin/library-ish names that any
    # project would hit (join, push, get...) so the grep comparison is not a strawman
    generic = set(cm.JS_BUILTIN) | {
        "join", "split", "push", "get", "set", "map", "filter", "then", "resolve", "reject",
        "send", "exec", "some", "sort", "slice", "trim", "init", "load", "save", "run", "main",
        "render", "update", "close", "open", "start", "stop", "add", "remove", "find", "query",
    }
    hubs = [n for n in nodes if n["kind"] in ("function", "class", "method")
            and "." not in n["name"] and len(n["name"]) >= 5 and n["name"] not in generic
            and n["name"].lower() not in generic]
    hub = hubs[0]
    other = next((h for h in hubs[1:] if h["file"] != hub["file"]), hubs[1])
    hub_file_text = read(os.path.join(proj, hub["file"]))
    big_file_text = read(os.path.join(proj, big_file))

    literal = pick_literal(proj, [big_file, hub["file"]] + files[:50])

    tasks = []

    # T1 orientation
    listing = "\n".join(files)
    tasks.append(("Orient: what are the main parts of this codebase?", {
        "OLD": tok(old_map),
        "GREP": tok(listing) + tok(hub_file_text),
        "RULE": tok(overview),
    }, f"hub file for GREP: {hub['file']}"))

    # T2 definition
    g_text, g_hits = grep(proj, hub["name"], files)
    q_text = cmd(proj, "query", hub["name"])
    w = window(proj, hub["file"], hub["line"], *DEF_WINDOW)
    tasks.append((f"Find where `{hub['name']}` is defined and read it", {
        "OLD": tok(old_map) + tok(w),
        "GREP": tok(g_text) + tok(w),
        "RULE": tok(q_text) + tok(w),
    }, f"grep hits: {len(g_hits)} lines; query output: {len(q_text)} chars"))

    # T3 callers
    e_text = cmd(proj, "explain", hub["name"])
    callers = [e for e in graph["edges"] if e["dst"] == hub["name"] and e["kind"] == "calls"][:CALLER_CAP]
    pos = {n["name"]: n for n in nodes}
    cw = sum(tok(window(proj, pos[e["src"]]["file"], pos[e["src"]]["line"], *CALL_WINDOW))
             for e in callers if e["src"] in pos)
    gw = sum(tok(window(proj, rel, ln, *CALL_WINDOW)) for rel, ln in g_hits[:CALLER_CAP])
    tasks.append((f"Who calls `{hub['name']}`? Open the first {CALLER_CAP} call sites", {
        "OLD": tok(old_map) + cw,
        "GREP": tok(g_text) + gw,
        "RULE": tok(e_text) + cw,
    }, f"explain lists {len(callers)} callers; grep gives {len(g_hits)} hits"))

    # T4 file shape
    f_text = cmd(proj, "file", big_file)
    tasks.append((f"What is in `{big_file}`?", {
        "OLD": tok(old_map),
        "GREP": tok(big_file_text),
        "RULE": tok(f_text),
    }, f"file is {len(big_file_text.splitlines())} lines, {len(by_file[big_file])} symbols"))

    # T5 literal string
    if literal:
        l_text, l_hits = grep(proj, literal, files)
        lw = tok(window(proj, l_hits[0][0], l_hits[0][1], *LIT_WINDOW)) if l_hits else 0
        tasks.append((f"Find the UI string \"{literal[:40]}\"", {
            "OLD": tok(old_map) + tok(l_text) + lw,
            "GREP": tok(l_text) + lw,
            "RULE": tok(l_text) + lw,
        }, "rule says grep: identical to GREP by design"))

    # T6 coupling
    p_text = cmd(proj, "path", hub["name"], other["name"])
    if "No path" in p_text or not p_text.strip():
        p_text += cmd(proj, "explain", other["name"])
    g2_text, _ = grep(proj, other["name"], files)
    other_file_text = read(os.path.join(proj, other["file"]))
    tasks.append((f"How is `{hub['name']}` connected to `{other['name']}`?", {
        "OLD": tok(old_map),
        "GREP": tok(g_text) + tok(g2_text) + tok(hub_file_text) + tok(other_file_text),
        "RULE": tok(p_text),
    }, "GREP: both greps plus both defining files read whole"))

    s = graph["stats"]
    return {
        "name": name, "stats": s, "tasks": tasks,
        "old_map_tok": tok(old_map), "overview_tok": tok(overview), "index_tok": tok(index),
    }


def summarize(r):
    tot = {k: sum(t[1][k] for t in r["tasks"]) for k in ("OLD", "GREP", "RULE")}
    # session view: OLD reads the map once per session, not once per task
    n_map_reads = sum(1 for t in r["tasks"] if t[1]["OLD"] >= r["old_map_tok"])
    sess = dict(tot)
    sess["OLD"] = tot["OLD"] - (n_map_reads - 1) * r["old_map_tok"]
    return tot, sess


def pct(a, b):
    return f"{(1 - a / b) * 100:+.0f}%".replace("+", "-") if b else "n/a"


def saving(rule, other):
    return f"{(1 - rule / other) * 100:.0f}%" if other else "n/a"


def md_report(results):
    label = make_counter(TOKENIZER)[0]
    L = ["# Cost rule benchmark", "",
         f"Tokens an agent ingests per lookup task ({label}, on real command output and file text). "
         "No model calls. OLD = read the whole map first (previous AGENTS.md wording). GREP = no map. "
         "RULE = the cost rule.", ""]
    for r in results:
        s = r["stats"]
        L += [f"## {r['name']}  ({s['files']} files, {s['symbols']} symbols, {s['edges']} edges)", "",
              f"Old single-file map: {r['old_map_tok']:,} tokens. New overview: {r['overview_tok']:,}. Index: {r['index_tok']:,}.", "",
              "| Task | OLD | GREP | RULE | RULE vs OLD | RULE vs GREP | Note |", "|---|---:|---:|---:|---:|---:|---|"]
        for title, c, note in r["tasks"]:
            L.append(f"| {title} | {c['OLD']:,} | {c['GREP']:,} | {c['RULE']:,} | "
                     f"{saving(c['RULE'], c['OLD'])} | {saving(c['RULE'], c['GREP'])} | {note} |")
        tot, sess = summarize(r)
        L.append(f"| **All tasks, map re-read each time** | {tot['OLD']:,} | {tot['GREP']:,} | {tot['RULE']:,} | "
                 f"{saving(tot['RULE'], tot['OLD'])} | {saving(tot['RULE'], tot['GREP'])} | |")
        L.append(f"| **All tasks, one session (map read once)** | {sess['OLD']:,} | {sess['GREP']:,} | {sess['RULE']:,} | "
                 f"{saving(sess['RULE'], sess['OLD'])} | {saving(sess['RULE'], sess['GREP'])} | |")
        L.append("")
    L += ["## Assumptions", "",
          f"- Grep output capped at {GREP_LINE_CAP} lines, as the Grep tool does by default.",
          f"- After locating a definition the agent reads {DEF_WINDOW[0]} lines before and {DEF_WINDOW[1]} after it, in every strategy.",
          f"- For callers the agent opens at most {CALLER_CAP} sites, {sum(CALL_WINDOW)} lines each, in every strategy.",
          "- Literal-string tasks are identical under GREP and RULE by design: the rule sends those to grep.",
          "- OLD charges the full map on every task in the per-task rows; the session row charges it once.",
          "- Tasks are picked automatically per project: the top hub symbol, the file with most symbols, a UI-looking string.",
          ""]
    return "\n".join(L)


def html_report(md):
    # minimal markdown-to-html for headings, tables, bullets, paragraphs
    out, in_table, in_list = [], False, False
    for line in md.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set(line.replace("|", "").strip()) <= set("-: "):
                continue
            if not in_table:
                out.append("<table>"); in_table = True
                out.append("<tr>" + "".join(f"<th>{inline(c)}</th>" for c in cells) + "</tr>")
            else:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>"); in_table = False
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append(f"<li>{inline(line[2:])}</li>"); continue
        if in_list:
            out.append("</ul>"); in_list = False
        if line.startswith("# "):
            out.append(f"<h1>{inline(line[2:])}</h1>")
        elif line.startswith("## "):
            out.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.strip():
            out.append(f"<p>{inline(line)}</p>")
    if in_table:
        out.append("</table>")
    if in_list:
        out.append("</ul>")
    css = ("body{font:15px/1.5 system-ui,sans-serif;max-width:1100px;margin:40px auto;padding:0 20px;color:#222}"
           "table{border-collapse:collapse;margin:12px 0 24px;width:100%}th,td{border:1px solid #ddd;padding:6px 10px;"
           "text-align:left;vertical-align:top}td:nth-child(n+2):nth-child(-n+6){text-align:right;white-space:nowrap}"
           "th{background:#f4f4f4}code{background:#f4f4f4;padding:1px 4px;border-radius:3px}h2{margin-top:36px}")
    return f"<!doctype html><meta charset='utf-8'><title>Cost rule benchmark</title><style>{css}</style>" + "\n".join(out)


def inline(s):
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    return s


def main():
    global TOKENIZER
    args = sys.argv[1:]
    if "--tokenizer" in args:
        i = args.index("--tokenizer")
        if i + 1 >= len(args):
            print(__doc__); sys.exit(1)
        TOKENIZER = args[i + 1]
        del args[i:i + 2]
    projects = args
    if not projects:
        print(__doc__); sys.exit(1)
    try:
        make_counter(TOKENIZER)
    except Exception as e:  # missing package or unknown name: say so before the long run
        sys.stderr.write(f"Cannot load tokenizer '{TOKENIZER}': {e}\n")
        sys.exit(2)
    results = [bench(p) for p in projects]
    md = md_report(results)
    tag = "" if TOKENIZER == "cl100k_base" else "_" + re.sub(r"[^A-Za-z0-9.-]+", "-", TOKENIZER.replace("hf:", ""))
    io.open(os.path.join(HERE, f"cost_rule_report{tag}.md"), "w", encoding="utf-8", newline="\n").write(md)
    io.open(os.path.join(HERE, f"cost_rule_report{tag}.html"), "w", encoding="utf-8", newline="\n").write(html_report(md))
    print(md)


if __name__ == "__main__":
    main()
