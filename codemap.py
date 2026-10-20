#!/usr/bin/env python3
"""codemap - build a token-efficient knowledge map of any codebase for AI agents.
https://agentcodemap.com
Copyright 2026 AgentCodeMap. Licensed under the Apache License, Version 2.0 (see LICENSE).

Deterministic local parsing only: no LLM, no network, no visualization.

Usage:
  python codemap.py <path>              build map -> codemap-out/ (map.json, CODE_MAP.md, CODE_MAP_INDEX.md)
  python codemap.py query "term"        find nodes + their connections
  python codemap.py explain <Name>      full detail for one symbol
  python codemap.py file <path-part>    symbols of one file with line numbers
  python codemap.py path <A> <B>        shortest connection between two symbols
  python codemap.py stats               summary of the current map
  python codemap.py check               verify the map is fresh (exit 1 if stale)
  python codemap.py watch               keep the map live (no git needed; Ctrl+C stops)
  python codemap.py hook install        auto-rebuild map on commit/pull/checkout (git)
  python codemap.py hook uninstall      remove the git hooks
"""

import ast
import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict, deque

SCHEMA_VERSION = 2
CACHE_VERSION = 2
OUT_DIR = "codemap-out"
SKIP_FILES = {"codemap.py"}  # the tool itself is not project code
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "vendor", "dist", "build", "out", "target", ".idea", ".vscode",
    "codemap-out", "graphify-out", ".next", ".nuxt", "coverage",
    ".mypy_cache", ".pytest_cache", "bower_components",
}
BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".tar",
    ".exe", ".dll", ".so", ".bin", ".woff", ".woff2", ".ttf", ".eot",
    ".mp3", ".mp4", ".avi", ".mov", ".pyc", ".class", ".jar", ".wasm",
    ".map", ".lock", ".min.js", ".db", ".sqlite",
}

LANG_BY_EXT = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".mjs": "javascript",
    ".cjs": "javascript", ".php": "php", ".inc": "php",
    ".java": "java", ".cs": "csharp", ".go": "go", ".rb": "ruby",
    ".rs": "rust", ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp",
    ".hpp": "cpp", ".hh": "cpp", ".swift": "swift", ".kt": "kotlin",
    ".scala": "scala", ".sh": "shell", ".bash": "shell", ".ps1": "powershell",
    ".lua": "lua", ".pl": "perl", ".r": "r", ".sql": "sql", ".html": "html",
}

EDGE_KINDS = ("imports", "calls", "inherits", "defines", "references")


def scan_files(root):
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if fn in SKIP_FILES:
                continue
            if ext in BINARY_EXT or fn.startswith("."):
                continue
            lang = LANG_BY_EXT.get(ext)
            if not lang:
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            try:
                size = os.path.getsize(full)
                if size > 2_000_000:
                    continue
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    src = f.read()
            except OSError:
                continue
            files.append({"rel": rel, "lang": lang, "src": src, "size": size,
                          "hash": file_hash(src)})
    return files


def file_hash(src):
    return hashlib.sha1(src.encode("utf-8", "replace")).hexdigest()[:12]


def make_line_finder(src):
    import bisect
    nl = [i for i, c in enumerate(src) if c == "\n"]

    def line(pos):
        return bisect.bisect_right(nl, pos) + 1
    return line


# ---------------- python extractor (real AST) ----------------

def extract_python(f):
    symbols, edges = [], []
    try:
        tree = ast.parse(f["src"])
    except SyntaxError:
        return extract_generic(f)

    def qualname(name, parents):
        return ".".join(parents + [name]) if parents else name

    def walk(node, parents):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qn = qualname(child.name, parents)
                symbols.append({"name": qn, "kind": "method" if parents else "function",
                                "line": child.lineno, "file": f["rel"]})
                for call in collect_calls(child):
                    edges.append({"src": qn, "dst": call, "kind": "calls", "tag": "EXTRACTED"})
                walk(child, parents + [child.name])
            elif isinstance(child, ast.ClassDef):
                qn = qualname(child.name, parents)
                symbols.append({"name": qn, "kind": "class", "line": child.lineno, "file": f["rel"]})
                for base in child.bases:
                    bn = base_name(base)
                    if bn:
                        edges.append({"src": qn, "dst": bn, "kind": "inherits", "tag": "EXTRACTED"})
                walk(child, parents + [child.name])
            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                for imp in imports_of(child):
                    edges.append({"src": imp, "dst_file_hint": imp, "kind": "imports", "tag": "EXTRACTED"})
                walk(child, parents)
            else:
                walk(child, parents)

    walk(tree, [])
    return symbols, edges


def collect_calls(func_node):
    names = set()
    for n in ast.walk(func_node):
        if isinstance(n, ast.Call):
            fn = n.func
            if isinstance(fn, ast.Name):
                names.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                names.add(fn.attr)
    return names


def base_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def imports_of(node):
    if isinstance(node, ast.Import):
        return [a.name for a in node.names]
    if isinstance(node, ast.ImportFrom):
        return [node.module] if node.module else []
    return []


# ---------------- regex extractors for other languages ----------------

JS_IMPORT = re.compile(r"""(?:import\s+[^'"]*?from\s+['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)|import\(\s*['"]([^'"]+)['"]\s*\))""")
JS_CLASS = re.compile(r"(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)")
JS_FUNC = re.compile(r"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s+([A-Za-z_$][\w$]*)")
JS_CONST_FN = re.compile(r"(?:export\s+)?(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>")
JS_EXTENDS = re.compile(r"class\s+([A-Za-z_$][\w$]*)[^{]*extends\s+([A-Za-z_$][\w$.]*)")
JS_CALL = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\(")

JS_BUILTIN = {
    "if", "for", "while", "switch", "catch", "return", "function", "constructor",
    "require", "console", "new", "Object", "String", "Array", "Promise", "JSON",
    "Math", "setTimeout", "setInterval", "parseInt", "parseFloat", "Boolean",
    "Number", "Error", "TypeError", "window", "document", "super", "this",
    "module", "exports", "process", "Symbol", "Map", "Set", "Date", "RegExp",
}

PHP_CLASS = re.compile(r"(?:abstract\s+|final\s+)?class\s+([A-Za-z_]\w*)")
PHP_EXTENDS = re.compile(r"class\s+([A-Za-z_]\w*)[^{]*extends\s+([\\A-Za-z_]\w*)")
PHP_IMPLEMENTS = re.compile(r"class\s+([A-Za-z_]\w*)[^{]*implements\s+([\\A-Za-z_,\s]*)")
PHP_FUNC = re.compile(r"function\s+([A-Za-z_]\w*)\s*\(")
PHP_USE = re.compile(r"^use\s+([\\A-Za-z_][\\\w]*);", re.M)
PHP_NS = re.compile(r"^namespace\s+([\\A-Za-z_][\\\w]*);", re.M)

GENERIC_FUNC = {
    "java": re.compile(r"(?:public|private|protected|static|final|synchronized|\s)+[\w<>\[\], ]+?\s+(\w+)\s*\([^)]*\)\s*(?:throws\s+[\w, ]+\s*)?\{"),
    "go": re.compile(r"^func\s+(?:\([^)]*\)\s*)?(\w+)\s*\(", re.M),
    "ruby": re.compile(r"^\s*def\s+(\w+)", re.M),
    "rust": re.compile(r"(?:pub\s+)?(?:async\s+)?fn\s+(\w+)"),
    "c": re.compile(r"^[A-Za-z_][\w\s\*]*?(\w+)\s*\([^;]*\)\s*\{", re.M),
    "cpp": re.compile(r"^[A-Za-z_][\w\s\*:<>,&]*?(\w+)\s*\([^;]*\)\s*\{", re.M),
    "csharp": re.compile(r"(?:public|private|protected|internal|static|virtual|override|async|\s)+[\w<>\[\], ]+?\s+(\w+)\s*\([^)]*\)\s*\{"),
}
GENERIC_CLASS = {
    "java": re.compile(r"(?:public\s+|final\s+|abstract\s+)*class\s+(\w+)"),
    "csharp": re.compile(r"(?:public\s+|internal\s+|sealed\s+|abstract\s+|static\s+|partial\s+)*class\s+(\w+)"),
    "go": re.compile(r"^type\s+(\w+)\s+struct\s*\{", re.M),
    "ruby": re.compile(r"^\s*class\s+(\w+)", re.M),
    "rust": re.compile(r"(?:pub\s+)?(?:struct|enum|trait)\s+(\w+)"),
    "cpp": re.compile(r"\bclass\s+(\w+)"),
    "c": re.compile(r"\b(?:struct|typedef\s+struct)\s+(\w+)"),
}
GENERIC_IMPORT = {
    "java": re.compile(r"^import\s+([\w.]+);", re.M),
    "csharp": re.compile(r"^using\s+([\w.]+);", re.M),
    "go": re.compile(r'^\s*(?:import\s+([\w./"\s]+)|(\w+)\s+"([^"]+)")', re.M),
    "ruby": re.compile(r"^\s*require(?:_relative)?\s+['\"]([^'\"]+)", re.M),
    "rust": re.compile(r"^\s*use\s+([\w:]+)", re.M),
    "c": re.compile(r"^\s*#include\s+[\"<]([^\">]+)[\">]", re.M),
    "cpp": re.compile(r"^\s*#include\s+[\"<]([^\">]+)[\">]", re.M),
}


def extract_javascript(f):
    symbols, edges = [], []
    src = f["src"]
    line = make_line_finder(src)
    for m in JS_CLASS.finditer(src):
        symbols.append({"name": m.group(1), "kind": "class",
                        "line": line(m.start()), "file": f["rel"]})
    for m in JS_EXTENDS.finditer(src):
        edges.append({"src": m.group(1), "dst": m.group(2).split(".")[-1],
                      "kind": "inherits", "tag": "EXTRACTED"})
    for pat, kind in ((JS_FUNC, "function"), (JS_CONST_FN, "function")):
        for m in pat.finditer(src):
            if any(s["name"] == m.group(1) and s["kind"] == kind for s in symbols):
                continue
            symbols.append({"name": m.group(1), "kind": kind,
                            "line": line(m.start()), "file": f["rel"]})
    for m in JS_IMPORT.finditer(src):
        target = next(g for g in m.groups() if g)
        edges.append({"src": os.path.basename(f["rel"]), "dst_file_hint": target,
                      "kind": "imports", "tag": "EXTRACTED"})
    for m in JS_ROUTE.finditer(src):
        symbols.append({"name": f"{m.group(1).upper()} {m.group(2)}", "kind": "route",
                        "line": line(m.start()), "file": f["rel"]})

    spans = []
    for m in JS_CLASS.finditer(src):
        sp = body_span(src, m.start())
        if sp:
            spans.append((m.start(), sp[1], m.group(1)))
    for m in JS_FUNC.finditer(src):
        sp = body_span(src, m.start())
        if sp:
            spans.append((m.start(), sp[1], m.group(1)))
    for m in JS_CONST_FN.finditer(src):
        sp = body_span(src, m.start())
        if sp:
            spans.append((m.start(), sp[1], m.group(1)))
    spans.sort(key=lambda s: s[0])

    def owner_of(pos):
        best = None
        for start, end, name in spans:
            if start <= pos <= end:
                best = name
            if start > pos:
                break
        return best or os.path.basename(f["rel"])

    for m in JS_CALL.finditer(src):
        name = m.group(1)
        if name not in JS_BUILTIN:
            edges.append({"src": owner_of(m.start()), "dst": name,
                          "kind": "calls", "tag": "EXTRACTED"})
    return symbols, edges


def extract_php(f):
    symbols, edges = [], []
    src = f["src"]
    line = make_line_finder(src)
    ns = None
    m = PHP_NS.search(src)
    if m:
        ns = m.group(1)
    for m in PHP_CLASS.finditer(src):
        name = (ns + "\\" if ns else "") + m.group(1)
        symbols.append({"name": name, "kind": "class",
                        "line": line(m.start()), "file": f["rel"]})
    for m in PHP_EXTENDS.finditer(src):
        child = (ns + "\\" if ns else "") + m.group(1)
        edges.append({"src": child, "dst": m.group(2).split("\\")[-1],
                      "kind": "inherits", "tag": "EXTRACTED"})
    for m in PHP_IMPLEMENTS.finditer(src):
        child = (ns + "\\" if ns else "") + m.group(1)
        for iface in m.group(2).split(","):
            iface = iface.strip().split("\\")[-1]
            if iface:
                edges.append({"src": child, "dst": iface, "kind": "inherits", "tag": "EXTRACTED"})
    classes = [(m.start(), (ns + "\\" if ns else "") + m.group(1)) for m in PHP_CLASS.finditer(src)]
    for m in PHP_FUNC.finditer(src):
        line_start = src.rfind("\n", 0, m.start()) + 1
        indented = src[line_start:m.start()].strip() != ""
        owner = None
        if indented:
            for pos, cname in classes:
                if pos < m.start():
                    owner = cname
        name = (owner + "::" if owner else "") + m.group(1)
        if not any(s["name"] == name for s in symbols):
            symbols.append({"name": name, "kind": "method" if owner else "function",
                            "line": line(m.start()), "file": f["rel"]})
    for m in PHP_USE.finditer(src):
        edges.append({"src": os.path.basename(f["rel"]), "dst_file_hint": m.group(1),
                      "kind": "imports", "tag": "EXTRACTED"})
    for m in PHP_ROUTE.finditer(src):
        symbols.append({"name": m.group(1), "kind": "route",
                        "line": line(m.start()), "file": f["rel"]})
    return symbols, edges


def extract_generic(f):
    symbols, edges = [], []
    src = f["src"]
    line = make_line_finder(src)
    lang = f["lang"]
    for m in GENERIC_CLASS.get(lang, re.compile(r"\bclass\s+(\w+)")).finditer(src):
        symbols.append({"name": m.group(1), "kind": "class",
                        "line": line(m.start()), "file": f["rel"]})
    for m in GENERIC_FUNC.get(lang, re.compile(r"\bfunction\s+(\w+)")).finditer(src):
        if any(s["name"] == m.group(1) for s in symbols):
            continue
        symbols.append({"name": m.group(1), "kind": "function",
                        "line": line(m.start()), "file": f["rel"]})
    for m in GENERIC_IMPORT.get(lang, re.compile(r"^\s*(?:import|include)\s+['\"<]?([\w./-]+)", re.M)).finditer(src):
        edges.append({"src": os.path.basename(f["rel"]), "dst_file_hint": m.group(1),
                      "kind": "imports", "tag": "EXTRACTED"})
    return symbols, edges


PHP_ROUTE = re.compile(r"""\$path\s*={2,3}\s*['"](\/[A-Za-z0-9\/_.\-]*)['"]""")
JS_ROUTE = re.compile(r"""(?:app|router|api)\s*\.\s*(get|post|put|delete|patch|all)\s*\(\s*['"](\/[^'"]*)['"]""")
SQL_TABLE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\[]?(\w+)[`\]]?\s*\(", re.I)
HTML_ID = re.compile(r"""<([a-z][\w-]*)[^>]*?\bid=["']([A-Za-z][\w\-]*)["']""")
HTML_FORM = re.compile(r"""<form\b[^>]*?\bid=["']([A-Za-z][\w\-]*)["']""", re.I)


def body_span(src, start):
    i = src.find("{", start)
    if i == -1:
        return None
    depth = 0
    in_str = None
    j = i
    while j < len(src):
        c = src[j]
        if in_str:
            if c == "\\":
                j += 2
                continue
            if c == in_str:
                in_str = None
        elif c in "'\"`":
            in_str = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return (i, j)
        j += 1
    return (i, len(src))


def paren_span(src, start):
    i = src.find("(", start)
    if i == -1:
        return None
    depth = 0
    j = i
    while j < len(src):
        c = src[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return (i, j)
        j += 1
    return (i, len(src))


def extract_sql(f):
    symbols = []
    src = re.sub(r"--.*?$", "", f["src"], flags=re.M)
    line = make_line_finder(src)
    for m in SQL_TABLE.finditer(src):
        table = m.group(1)
        symbols.append({"name": table, "kind": "table",
                        "line": line(m.start()), "file": f["rel"]})
        span = paren_span(src, m.start())
        if span:
            body = src[span[0]:span[1]]
            for cm in re.finditer(r"^\s*[`\[]?(\w+)[`\]]?\s+(?:INT|VARCHAR|TEXT|DATE|TIMESTAMP|DECIMAL|BIGINT|CHAR|ENUM|BOOLEAN|TINYINT|FLOAT|DOUBLE|JSON|BLOB)", body, re.I | re.M):
                col = cm.group(1).upper()
                if col in ("PRIMARY", "KEY", "UNIQUE", "CONSTRAINT", "FOREIGN", "INDEX", "FULLTEXT", "SPATIAL", "CHECK"):
                    continue
                symbols.append({"name": f"{table}.{col}", "kind": "column",
                                "line": line(span[0] + cm.start()), "file": f["rel"]})
    return symbols, []


def extract_elements(f):
    symbols = []
    src = f["src"]
    if "<" not in src:
        return symbols, []
    line = make_line_finder(src)
    seen = set()
    for m in HTML_ID.finditer(src):
        eid = m.group(2)
        if eid in seen:
            continue
        seen.add(eid)
        if len(seen) > 40:
            break
        tag = m.group(1)
        symbols.append({"name": f"#{eid}", "kind": "form" if tag == "form" else "element",
                        "line": line(m.start()), "file": f["rel"]})
    return symbols, []


EXTRACTORS = {
    "python": extract_python,
    "javascript": extract_javascript,
    "typescript": extract_javascript,
    "php": extract_php,
    "sql": extract_sql,
    "html": extract_elements,
}





# ---------------- resolution + graph assembly ----------------

def build_file_index(files):
    by_module = {}
    by_basename = {}
    by_stem = {}
    for f in files:
        rel = f["rel"]
        by_basename[os.path.basename(rel)] = rel
        stem = os.path.splitext(os.path.basename(rel))[0]
        by_stem.setdefault(stem, []).append(rel)
        parts = rel.split("/")
        if parts[-1] in ("__init__.py", "index.js", "index.ts", "mod.rs"):
            by_module[".".join(parts[:-1]) if len(parts) > 1 else parts[0]] = rel
        elif rel.endswith(".py"):
            p = parts[:-1] + [os.path.splitext(parts[-1])[0]]
            by_module[".".join(p)] = rel
    return by_module, by_basename, by_stem


def resolve_edge(edge, origin, origin_lang, by_module, by_basename, by_stem,
                 all_symbol_names, sym_langs, by_lang_suffix, all_files_rel):
    hint = edge.pop("dst_file_hint", None)
    if hint:
        target = None
        cands = [
            by_module.get(hint),
            by_module.get(hint.replace("/", ".")),
            by_basename.get(os.path.basename(hint) + ".py"),
            by_basename.get(os.path.basename(hint)),
        ]
        for ext in (".js", ".ts", ".jsx", ".tsx", ".php", ".py", ".go", ".rb", ".rs"):
            base = os.path.basename(hint)
            if base.endswith(ext):
                cands.append(by_basename.get(base))
            else:
                cands.append(by_basename.get(base + ext))
        stem = os.path.splitext(os.path.basename(hint))[0]
        for c in by_stem.get(stem, []):
            cands.append(c)
        for c in cands:
            if c and c != origin:
                target = c
                break
        if target:
            edge["dst"] = "file:" + target
            edge["tag"] = "INFERRED" if target != hint else "EXTRACTED"
        else:
            return None
    dst = edge["dst"]
    if dst.startswith("file:") or dst.startswith(".") or dst.startswith("#"):
        return edge
    dst_lang = sym_langs.get(dst)
    if dst in all_symbol_names and (dst_lang is None or dst_lang == origin_lang):
        return edge
    if dst in all_files_rel:
        edge["dst"] = "file:" + dst
        return edge
    matches = by_lang_suffix.get(origin_lang, {}).get(dst.split(".")[-1], [])
    if len(matches) == 1:
        edge["dst"] = matches[0]
        edge["tag"] = "INFERRED"
        return edge
    if edge["kind"] == "calls":
        return None if dst in all_symbol_names else edge
    return None


def load_cache():
    path = os.path.join(OUT_DIR, "map.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            graph = json.load(fh)
        if graph.get("schema_version") == SCHEMA_VERSION:
            return graph.get("file_cache", {})
    except (OSError, ValueError):
        pass
    return {}


def build_graph(files, cache=None, quiet=False):
    cache = cache or {}
    all_symbols = []
    all_edges = []
    file_cache = {}
    reused = 0
    for f in files:
        rel, h = f["rel"], f["hash"]
        cached = cache.get(rel)
        if cached and cached.get("hash") == h and cached.get("v") == CACHE_VERSION:
            syms = [dict(s) for s in cached["symbols"]]
            edges = [dict(e) for e in cached["edges"]]
            reused += 1
        else:
            ex = EXTRACTORS.get(f["lang"], extract_generic)
            syms, edges = ex(f)
            if f["lang"] == "php":
                esyms, _ = extract_elements(f)
                syms.extend(esyms)
            syms = [{k: v for k, v in s.items()} for s in syms]
        f["src"] = None
        for s in syms:
            s["file"] = f["rel"]
        for e in edges:
            e["origin"] = f["rel"]
        file_cache[rel] = {"hash": h, "v": CACHE_VERSION, "symbols": syms, "edges": edges}
        all_symbols.extend(syms)
        all_edges.extend(edges)
    if reused:
        if not quiet:
            print(f"Incremental: reused {reused}/{len(files)} unchanged files")

    by_module, by_basename, by_stem = build_file_index(files)
    all_symbol_names = {s["name"] for s in all_symbols}
    all_files_rel = {f["rel"] for f in files}
    file_langs = {f["rel"]: f["lang"] for f in files}
    sym_langs = {}
    by_lang_suffix = defaultdict(lambda: defaultdict(list))
    for s in all_symbols:
        if s["name"] not in sym_langs:
            lang = file_langs.get(s["file"])
            sym_langs[s["name"]] = lang
            if lang:
                by_lang_suffix[lang][s["name"].split(".")[-1]].append(s["name"])

    seen_local = set()
    resolved = []
    for e in all_edges:
        key = (e["src"], e.get("dst") or e.get("dst_file_hint"), e["kind"])
        if key in seen_local:
            continue
        seen_local.add(key)
        origin = e.get("origin")
        r = resolve_edge(dict(e), origin, file_langs.get(origin), by_module,
                         by_basename, by_stem, all_symbol_names, sym_langs,
                         by_lang_suffix, all_files_rel)
        if r and r.get("dst") and r["dst"] != r["src"]:
            r.pop("origin", None)
            resolved.append(r)

    nodes = []
    node_ids = set()
    for s in all_symbols:
        nid = s["name"]
        if nid in node_ids:
            continue
        node_ids.add(nid)
        nodes.append(s)
    file_nodes = []
    for f in files:
        fid = "file:" + f["rel"]
        if fid not in node_ids:
            node_ids.add(fid)
            file_nodes.append({"name": fid, "kind": "file", "line": 0,
                               "file": f["rel"], "lang": f["lang"], "hash": f["hash"]})
    return nodes, file_nodes, resolved, file_cache


def degree_map(edges):
    deg = defaultdict(int)
    for e in edges:
        deg[e["src"]] += 1
        deg[e["dst"]] += 1
    return deg


def communities_by_dir(nodes):
    groups = defaultdict(list)
    for n in nodes:
        d = os.path.dirname(n["file"]) or "."
        groups[d].append(n["name"])
    return dict(groups)


# ---------------- outputs ----------------

def write_map_json(root, nodes, file_nodes, edges, file_cache):
    deg = degree_map(edges)
    graph = {
        "schema_version": SCHEMA_VERSION,
        "generator": "codemap",
        "root": root,
        "stats": {
            "files": len(file_nodes),
            "symbols": len(nodes),
            "edges": len(edges),
            "by_kind": dict(sorted(defaultdict_wrap(edges, "kind").items())),
        },
        "nodes": sorted(nodes, key=lambda n: -deg.get(n["name"], 0)),
        "files": file_nodes,
        "edges": edges,
        "file_cache": file_cache,
    }
    path = os.path.join(OUT_DIR, "map.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(graph, fh, indent=1)
    return path, graph


def defaultdict_wrap(items, key):
    d = defaultdict(int)
    for it in items:
        d[it[key]] += 1
    return d


def write_code_map_md(graph):
    deg = degree_map(graph["edges"])
    nodes = graph["nodes"]
    files = graph["files"]
    lines = []
    lines.append("# CODE_MAP")
    lines.append("")
    lines.append(f"Generated by codemap (schema v{SCHEMA_VERSION}). Short overview: safe to read whole. "
                 f"The full per-file index and edge list is in `CODE_MAP_INDEX.md` (large: grep it or use "
                 f"`python codemap.py file|query|explain|path`, do not read it whole). "
                 f"Node ids like `file:path/to/x.py` are files.")
    lines.append("")
    s = graph["stats"]
    lines.append(f"**{s['files']} files, {s['symbols']} symbols, {s['edges']} edges** "
                 f"({', '.join(f'{v} {k}' for k, v in s['by_kind'].items())})")
    lines.append("")

    lines.append("## Hubs (most-connected symbols)")
    lines.append("")
    for n in nodes[:25]:
        lines.append(f"- `{n['name']}` ({n['kind']}, {n['file']}:{n['line']}) - degree {deg.get(n['name'], 0)}")
    lines.append("")

    routes = [n for n in nodes if n["kind"] == "route"]
    if routes:
        lines.append("## Routes (HTTP endpoints)")
        lines.append("")
        for n in sorted(routes, key=lambda x: x["name"]):
            lines.append(f"- `{n['name']}` - {n['file']}:{n['line']}")
        lines.append("")

    tables = [n for n in nodes if n["kind"] == "table"]
    if tables:
        lines.append("## Database schema (from .sql files)")
        lines.append("")
        for n in sorted(tables, key=lambda x: x["name"]):
            cols = [c["name"].split(".", 1)[1] for c in nodes
                    if c["kind"] == "column" and c["name"].startswith(n["name"] + ".")]
            lines.append(f"- `{n['name']}` ({n['file']}:{n['line']}): {', '.join(cols) or '(no columns parsed)'}")
        lines.append("")

    groups = communities_by_dir([n for n in nodes if n["kind"] != "file"])
    lines.append("## Modules by directory")
    lines.append("")
    max_dirs = 150
    for i, d in enumerate(sorted(groups)):
        if i >= max_dirs:
            lines.append(f"- ... ({len(groups) - max_dirs} more directories, see map.json)")
            break
        syms = sorted(groups[d])
        shown = ", ".join(f"`{x}`" for x in syms[:40]) + (f" (+{len(syms)-40} more)" if len(syms) > 40 else "")
        lines.append(f"- **{d}/** ({len(syms)}): {shown}")
    lines.append("")

    lines.append("## Where next")
    lines.append("")
    lines.append("- One file's symbols with line numbers: `python codemap.py file <path-part>`")
    lines.append("- Topic search with call edges: `python codemap.py query \"<term>\"`")
    lines.append("- One symbol's neighbourhood: `python codemap.py explain <Name>`; coupling: `python codemap.py path <A> <B>`")
    lines.append("- Literal strings (UI text, error messages, config keys) are not indexed: grep for those.")
    lines.append(f"- Full index: `codemap-out/CODE_MAP_INDEX.md` ({len(files)} files, {len(graph['edges'])} edges). Grep it, never read it whole.")
    lines.append("")
    overview = "\n".join(lines)

    lines = []
    lines.append("# CODE_MAP_INDEX")
    lines.append("")
    lines.append("Per-file symbol index and cross-file edges, generated by codemap. This file is large: "
                 "grep it for a path or symbol, or use `python codemap.py file <path-part>` / `query`. "
                 "The short overview is `CODE_MAP.md`.")
    lines.append("")
    lines.append("## File index")
    lines.append("")
    by_file = defaultdict(list)
    for n in nodes:
        if n["kind"] != "file":
            by_file[n["file"]].append(n)
    max_files = 400
    sorted_files = sorted(files, key=lambda x: x["file"])
    for i, fn in enumerate(sorted_files):
        if i >= max_files:
            lines.append(f"- ... ({len(sorted_files) - max_files} more files, see map.json)")
            break
        rel = fn["file"]
        syms = sorted(by_file.get(rel, []), key=lambda x: x["line"])
        sym_str = ", ".join(f"{n['name']}:{n['line']}" for n in sorted(syms, key=lambda x: x["line"])[:30])
        if len(syms) > 30:
            sym_str += f" (+{len(syms)-30})"
        lines.append(f"- `{rel}` [{fn['lang']}] - {sym_str or '(no symbols)'}")
    lines.append("")

    lines.append("## Cross-file edges")
    lines.append("")
    sym_file = {n["name"]: n["file"] for n in nodes}
    by_kind = defaultdict(list)
    for e in graph["edges"]:
        by_kind[e["kind"]].append(e)
    for kind in EDGE_KINDS:
        es = by_kind.get(kind, [])
        if not es:
            continue
        cross = []
        for e in es:
            sf = sym_file.get(e["src"])
            df = sym_file.get(e["dst"])
            if e["src"].startswith("file:") or e["dst"].startswith("file:"):
                cross.append(e)
            elif sf and df and sf != df:
                cross.append(e)
        lines.append(f"### {kind} ({len(es)} total, {len(cross)} cross-file)")
        lines.append("")
        shown = 0
        for e in sorted(cross, key=lambda x: x["src"]):
            lines.append(f"- `{clean(e['src'])}` ({sf_of(e['src'], sym_file)}) -> "
                         f"`{clean(e['dst'])}` ({sf_of(e['dst'], sym_file)}) [{e['tag']}]")
            shown += 1
            if shown >= 150:
                lines.append(f"- ... ({len(cross) - shown} more in map.json)")
                break
        lines.append("")
    path = os.path.join(OUT_DIR, "CODE_MAP.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(overview)
    with open(os.path.join(OUT_DIR, "CODE_MAP_INDEX.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path


def clean(n):
    return n[5:] if n.startswith("file:") else n


def sf_of(name, sym_file):
    if name.startswith("file:"):
        return name[5:]
    f = sym_file.get(name)
    return f if f else "?"


AGENTS_START = "<!-- codemap:start -->"
AGENTS_END = "<!-- codemap:end -->"
AGENTS_SECTION = """## Code map (codemap)

This repo has a code map in `codemap-out/`. Pick the cheapest lookup:

- Function, class, file or concept: `python codemap.py query "<term>"` first. One
  short result with call edges, about the cost of a grep. Then `explain <Name>`
  or `path <A> <B>` to follow edges, and `file <path-part>` to list one file's
  symbols with line numbers. Only then open the lines it points to.
- Literal string (UI label, error text, config key): grep directly. The map
  indexes identifiers, not text.
- `codemap-out/CODE_MAP.md` is a short overview (hubs, routes, schema, modules).
  Reading it whole is fine. `codemap-out/CODE_MAP_INDEX.md` is the full per-file
  index and edge list: grep it, never read it whole.
- Commands self-heal when files change. Rebuild by hand only after big
  changes: `python codemap.py .`"""


def write_agents_hint(graph, root):
    path = os.path.join(OUT_DIR, "AGENTS_MAP.md")
    s = graph["stats"]
    body = f"""# Code map usage for agents

{AGENTS_SECTION}

Stats: {s['files']} files, {s['symbols']} symbols, {s['edges']} edges.
"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)

    root_hint = os.path.join(root, "AGENTS.md")
    block = AGENTS_START + "\n" + AGENTS_SECTION + "\n" + AGENTS_END
    try:
        existing = ""
        if os.path.exists(root_hint):
            with open(root_hint, "r", encoding="utf-8", errors="replace") as fh:
                existing = fh.read()
        if AGENTS_START in existing and AGENTS_END in existing:
            pre, rest = existing.split(AGENTS_START, 1)
            _, post = rest.split(AGENTS_END, 1)
            updated = pre + block + post
        elif "## Code map (codemap)" in existing:
            # section written by an older codemap: heading up to the next heading or EOF
            m = re.search(r"(?ms)^## Code map \(codemap\)\n.*?(?=^## |\Z)", existing)
            updated = existing[:m.start()] + block + "\n" + existing[m.end():]
        elif "codemap-out/" in existing:
            updated = existing  # hand-written mention: leave it alone
        elif existing.strip():
            updated = existing.rstrip("\n") + "\n\n" + block + "\n"
        else:
            updated = block + "\n"
        if updated != existing:
            with open(root_hint, "w", encoding="utf-8") as fh:
                fh.write(updated)
    except OSError:
        pass
    return path


# ---------------- query commands ----------------

def load_map(auto_refresh=True):
    path = os.path.join(OUT_DIR, "map.json")
    if not os.path.exists(path):
        sys.stderr.write(f"No map found at {path}. Run: python codemap.py <path>\n")
        sys.exit(2)
    if auto_refresh and map_is_stale():
        cmd_build(".", quiet=True)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def map_is_stale():
    graph = None
    try:
        with open(os.path.join(OUT_DIR, "map.json"), "r", encoding="utf-8") as fh:
            graph = json.load(fh)
    except (OSError, ValueError):
        return True
    if graph.get("schema_version") != SCHEMA_VERSION:
        return True
    mapped = {f["file"]: f.get("hash") for f in graph.get("files", [])}
    for dirpath, dirnames, filenames in os.walk("."):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if fn in SKIP_FILES:
                continue
            if ext not in LANG_BY_EXT or ext in BINARY_EXT:
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), ".").replace("\\", "/")
            try:
                with open(os.path.join(dirpath, fn), "r", encoding="utf-8", errors="replace") as fh:
                    h = file_hash(fh.read())
            except OSError:
                continue
            if mapped.get(rel) != h:
                return True
    return False


def adjacency(edges):
    adj = defaultdict(list)
    for e in edges:
        adj[e["src"]].append((e["dst"], e["kind"], e["tag"]))
        adj[e["dst"]].append((e["src"], e["kind"], e["tag"]))
    return adj


def find_nodes(graph, term):
    t = term.lower()
    return [n for n in graph["nodes"]
            if t == n["name"].lower() or t == clean(n["name"]).lower()
            or t in n["name"].lower() or t in n["file"].lower()]


def cmd_query(term):
    graph = load_map()
    matches = find_nodes(graph, term)
    if not matches:
        print(f"No nodes match '{term}'.")
        sys.exit(4)
    adj = adjacency(graph["edges"])
    print(f"Matches for '{term}': {len(matches)}")
    for n in matches[:15]:
        conns = adj.get(n["name"], [])
        print(f"\n  {n['name']} ({n['kind']}) {n['file']}:{n['line']} - {len(conns)} connections")
        for dst, kind, tag in conns[:8]:
            print(f"    {'-->' if True else ''} {dst} [{kind}] [{tag}]")
        if len(conns) > 8:
            print(f"    ... +{len(conns)-8} more")
    if len(matches) > 15:
        print(f"... +{len(matches)-15} more matches")


def cmd_file(term):
    graph = load_map()
    t = term.lower().replace("\\", "/").lstrip("./")
    files = [f for f in graph["files"] if t in f["file"].lower()]
    if not files:
        print(f"No files match '{term}'.")
        sys.exit(4)
    by_file = defaultdict(list)
    for n in graph["nodes"]:
        if n["kind"] != "file":
            by_file[n["file"]].append(n)
    exact = [f for f in files if f["file"].lower() == t or f["file"].lower().endswith("/" + t)]
    if len(files) > 1 and len(exact) != 1:
        print(f"Files matching '{term}': {len(files)}")
        for f in sorted(files, key=lambda x: x["file"])[:30]:
            print(f"  {f['file']} [{f['lang']}] - {len(by_file.get(f['file'], []))} symbols")
        if len(files) > 30:
            print(f"  ... +{len(files)-30} more")
        print("Give more of the path to pick one.")
        sys.exit(3)
    f = exact[0] if exact else files[0]
    syms = sorted(by_file.get(f["file"], []), key=lambda x: x["line"])
    print(f"{f['file']} [{f['lang']}] - {len(syms)} symbols")
    for n in syms:
        print(f"  {n['line']:>5}  {n['kind']:<9} {n['name']}")


def cmd_explain(name):
    graph = load_map()
    exact = [n for n in graph["nodes"] if n["name"].lower() == name.lower()
             or clean(n["name"]).lower() == name.lower()]
    if not exact:
        partial = find_nodes(graph, name)
        if len(partial) != 1:
            print(f"Ambiguous or unknown: '{name}'. Candidates:")
            for n in partial[:20]:
                print(f"  {n['name']} ({n['kind']}) {n['file']}:{n['line']}")
            sys.exit(3)
        exact = [partial[0]]
    n = exact[0]
    adj = adjacency(graph["edges"])
    conns = adj.get(n["name"], [])
    print(f"Node: {n['name']}")
    print(f"  Kind:       {n['kind']}")
    print(f"  Location:   {n['file']}:{n['line']}")
    print(f"  Degree:     {len(conns)}")
    if conns:
        print(f"\nConnections ({len(conns)}):")
        for dst, kind, tag in sorted(conns, key=lambda c: c[1])[:50]:
            print(f"  {'-->' if kind != 'inherits' else '--|'} {dst} [{kind}] [{tag}]")
        if len(conns) > 50:
            print(f"  ... +{len(conns)-50} more (see codemap-out/map.json)")


def cmd_path(a, b):
    graph = load_map()
    nodes_by_lower = {}
    for n in graph["nodes"]:
        nodes_by_lower.setdefault(n["name"].lower(), n["name"])
        nodes_by_lower.setdefault(clean(n["name"]).lower(), n["name"])
    start = nodes_by_lower.get(a.lower())
    end = nodes_by_lower.get(b.lower())
    if not start or not end:
        print(f"Unknown node(s): {a if not start else ''} {b if not end else ''}")
        sys.exit(4)
    adj = adjacency(graph["edges"])
    import builtins as _b
    noise = set(dir(_b)) | {"self", "cls", "super", "len", "print", "str", "int"}
    prev = {start: None}
    q = deque([start])
    while q:
        cur = q.popleft()
        if cur == end:
            break
        for dst, kind, tag in adj.get(cur, []):
            if dst not in prev and (dst == end or dst not in noise):
                prev[dst] = (cur, kind)
                q.append(dst)
    if end not in prev:
        print(f"No path between '{a}' and '{b}'.")
        sys.exit(4)
    hops = []
    cur = end
    while prev[cur] is not None:
        src, kind = prev[cur]
        hops.append((src, kind, cur))
        cur = src
    hops.reverse()
    print(f"Shortest path ({len(hops)} hops):")
    chain = hops[0][0]
    for src, kind, dst in hops:
        chain += f" --{kind}--> {dst}"
    print("  " + chain)


def cmd_stats():
    graph = load_map()
    s = graph["stats"]
    print(f"Files:   {s['files']}")
    print(f"Symbols: {s['symbols']}")
    print(f"Edges:   {s['edges']}")
    for k, v in s["by_kind"].items():
        print(f"  {k}: {v}")


def cmd_build(root, quiet=False):
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        sys.stderr.write(f"Not a directory: {root}\n")
        sys.exit(2)
    files = scan_files(root)
    if not files:
        sys.stderr.write("No code files found.\n")
        sys.exit(4)
    if not quiet:
        print(f"Scanning {len(files)} code files...")
    cache = load_cache()
    nodes, file_nodes, edges, file_cache = build_graph(files, cache, quiet=quiet)
    os.makedirs(OUT_DIR, exist_ok=True)
    _, graph = write_map_json(root, nodes, file_nodes, edges, file_cache)
    md = write_code_map_md(graph)
    hint = write_agents_hint(graph, root)
    if not quiet:
        s = graph["stats"]
        print(f"Done: {s['files']} files, {s['symbols']} symbols, {s['edges']} edges")
        print(f"  map:       {OUT_DIR}/map.json")
        print(f"  agent map: {md} (overview) + {OUT_DIR}/CODE_MAP_INDEX.md (full index)")
        print(f"  agent hint: {hint}")


def cmd_watch(interval=3):
    print(f"Watching for changes (every {interval}s). Ctrl+C to stop.")
    last = None
    while True:
        try:
            stale = map_is_stale()
            if stale:
                cmd_build(".", quiet=True)
                print(f"[{__import__('datetime').datetime.now():%H:%M:%S}] map rebuilt")
            last = stale
            time.sleep(interval)
        except KeyboardInterrupt:
            print("Stopped.")
            break


def cmd_check():
    graph = load_map(auto_refresh=False)
    stale = map_is_stale()
    if stale:
        print("STALE: files changed since the map was built. Run: python codemap.py .")
        sys.exit(1)
    print("FRESH: map matches the working tree.")


HOOK_MARKER = "# codemap auto-hook"
HOOK_BODY = f"""#!/bin/sh
{HOOK_MARKER}
# Rebuilds codemap-out/ after commits/merges/checkouts so agents always see a fresh map.
exec python codemap.py . >/dev/null 2>&1 &
"""


def cmd_hook(action):
    git = os.path.join(os.getcwd(), ".git")
    if not os.path.isdir(git):
        sys.stderr.write("Not a git repository (no .git/). Run: git init\n")
        sys.exit(2)
    hooks = {
        "post-commit": "after each commit",
        "post-merge": "after git pull",
        "post-checkout": "after branch switches",
    }
    if action == "install":
        for name, when in hooks.items():
            path = os.path.join(git, "hooks", name)
            existing = ""
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    existing = fh.read()
            if HOOK_MARKER in existing:
                print(f"  {name}: already installed")
                continue
            if existing.strip():
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write("\n" + HOOK_BODY)
                print(f"  {name}: appended ({when})")
            else:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(HOOK_BODY)
                os.chmod(path, 0o755)
                print(f"  {name}: installed ({when})")
        print("codemap will now rebuild automatically. "
              "Make sure codemap.py is in the repo (or on PATH) and commit codemap-out/ or leave it ignored.")
    elif action == "uninstall":
        for name in hooks:
            path = os.path.join(git, "hooks", name)
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines(keepends=True)
            out, skipping = [], False
            for ln in lines:
                if ln.rstrip("\n") == HOOK_MARKER:
                    skipping = True
                    continue
                if skipping:
                    skipping = ln.strip() != "" and not ln.startswith("#") and ln.rstrip("\n") != "exec python codemap.py . >/dev/null 2>&1 &"
                    if skipping:
                        continue
                    skipping = False
                    continue
                out.append(ln)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("".join(out))
            print(f"  {name}: removed")
    else:
        sys.stderr.write("Usage: codemap hook install|uninstall\n")
        sys.exit(1)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)
    cmd = args[0]
    if cmd in ("build", "map", "extract"):
        cmd_build(args[1] if len(args) > 1 else ".")
    elif cmd == "query" and len(args) > 1:
        cmd_query(" ".join(args[1:]))
    elif cmd == "explain" and len(args) > 1:
        cmd_explain(args[1])
    elif cmd == "file" and len(args) > 1:
        cmd_file(" ".join(args[1:]))
    elif cmd == "path" and len(args) > 2:
        cmd_path(args[1], args[2])
    elif cmd == "stats":
        cmd_stats()
    elif cmd == "check":
        cmd_check()
    elif cmd == "watch":
        cmd_watch(int(args[1]) if len(args) > 1 and args[1].isdigit() else 3)
    elif cmd == "hook" and len(args) > 1:
        cmd_hook(args[1])
    elif os.path.isdir(cmd):
        cmd_build(cmd)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()


