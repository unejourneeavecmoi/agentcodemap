# Agent Code Map

A token-saving code map for AI coding agents. One Python file, no dependencies,
no LLM, no network. It parses a codebase locally and writes a small map that
agents query instead of grepping and reading files whole.

Measured on four real projects: **68–97% fewer tokens per lookup session** than
exploring with grep, and 33–59% fewer than reading a full map first. Details
and method in [cost_rule_report.md](cost_rule_report.md).

Website: [agentcodemap.com](https://agentcodemap.com) · Author: [@biggab123](https://x.com/biggab123)

---

## Quick start

```
copy codemap.py into the project folder
python codemap.py .
```

That builds `codemap-out/` and writes (or patches) an `AGENTS.md` in the
project root, so Claude Code, Codex, Cursor, opencode and any other agent that
reads `AGENTS.md` is told how to use the map. From then on:

```
python codemap.py query "auth"        what exists for a topic, with call edges
python codemap.py explain UserService who calls / inherits / imports one symbol
python codemap.py file acp-composer   one file's symbols with line numbers
python codemap.py path main slugify   shortest chain between two symbols
```

Every read command checks file hashes first and rebuilds the map if code
changed, so it is never stale. Rebuilds are incremental and take well under a
second on a mid-sized project.

Supports Python (real AST), JavaScript/TypeScript, PHP, SQL, HTML, plus
regex-level extraction for Java, C#, Go, Ruby, Rust, C/C++ and others.

---

## Why it saves tokens

An agent exploring by grep reads whole files to understand them. A 7,000-line
`app.js` is about 100k tokens. The map answers the same questions in a few
hundred tokens:

| Looking for | Cheapest move | Typical size |
|---|---|---|
| A function, class, file or concept | `python codemap.py query "<term>"` | ~1 KB, with call edges |
| One file's shape | `python codemap.py file <path-part>` | a few hundred bytes |
| Who calls / inherits what | `explain <Name>`, `path <A> <B>` | ~1 KB |
| A literal string (UI label, error text, config key) | plain grep, the map does not index text | ~300 bytes |
| The big picture | read `codemap-out/CODE_MAP.md` whole | under 10 KB |
| Never | read `codemap-out/CODE_MAP_INDEX.md` whole | 50 KB+ on a mid-sized project |

This cost rule is what the generated `AGENTS.md` section tells agents. Two
honest caveats from the benchmark: a name that is unique in the codebase is a
little cheaper to grep than to query, and on a very small project (under about
30 files) reading the overview whole is already cheap.

### Benchmark

Tokens an agent ingests across six typical lookup tasks in one session, counted
with tiktoken on real command output and file text. No model calls.

| Project | Read whole map first | Grep only | Cost rule |
|---|---:|---:|---:|
| Electron app, 228 files | 20,442 | 267,525 | 8,349 |
| PHP/JS web app, 133 files | 18,781 | 38,780 | 12,262 |
| PHP site, 45 files | 5,973 | 17,773 | 4,026 |
| React app, 26 files | 3,508 | 80,649 | 4,107 |

Reproduce on your own projects:

```
pip install tiktoken
python cost_rule_benchmark.py <project> [<project> ...]
```

---

## What gets written

| File | What it is |
|---|---|
| `codemap-out/CODE_MAP.md` | Short overview (under ~10 KB): hubs, HTTP routes, DB schema, modules by directory, where to look next. Safe for an agent to read whole |
| `codemap-out/CODE_MAP_INDEX.md` | The big part: per-file symbol index with line numbers and cross-file edges. Agents grep it or use `file`/`query`, never read it whole |
| `codemap-out/map.json` | The full graph (nodes, edges, per-file cache) used by the query commands |
| `codemap-out/AGENTS_MAP.md` | Short instructions for agents on how to use the map |
| `AGENTS.md` (project root) | A section between `<!-- codemap:start -->` and `<!-- codemap:end -->` markers, refreshed on every build |

Add `codemap-out/` to `.gitignore` if you want the map always local-fresh, or
commit it to ship a map with the repo.

---

## Commands

### `query "term"` — find nodes and their connections

Free-text search across the whole graph: symbol names (partial matches too),
file paths, HTTP routes, DOM element ids and DB table names. Each hit shows its
kind, `file:line` and up to 8 connections, tagged `EXTRACTED` (explicit in
source) or `INFERRED` (resolved by codemap). Exit code `4` means no matches.

```
$ python codemap.py query "account"
Matches for 'account': 11
  #accountSwitcher (element) app/views/layout.php:56 - 0 connections
  /api/accounts (route) httpdocs/index.php:185 - 0 connections
  accounts (table) migrations/001_accounts.sql:5 - 0 connections
```

### `explain <Name>` — one symbol in detail

Exact name or unique partial match. Prints kind, location, degree and up to 50
connections sorted by edge type. Exit `3` = ambiguous (candidates listed),
`4` = no such node.

```
$ python codemap.py explain Admin
Node: Admin
  Kind:       class
  Location:   app.py:13
  Degree:     2
Connections (2):
  --> main [calls] [EXTRACTED]
  --| User [inherits] [EXTRACTED]
```

### `file <path-part>` — one file's symbols

Every symbol in one file with kind and line number. Any fragment of the path
works; if it matches more than one file the candidates are listed (exit `3`).

```
$ python codemap.py file acp-composer
src/renderer/acp-composer.mjs [javascript] - 10 symbols
     11  function  esc
     13  function  createComposer
     49  function  grow
```

### `path <A> <B>` — shortest connection

Breadth-first search, printed hop by hop. Language builtins are excluded as
intermediate hops. Node ids like `file:src/app.py` work too.

```
$ python codemap.py path main slugify
Shortest path (2 hops):
  main --calls--> Admin.promote --calls--> slugify
```

### `stats`, `check`, `watch`, `hook`

```
python codemap.py stats               files / symbols / edges summary
python codemap.py check               freshness test, no rebuild (exit 1 = stale)
python codemap.py watch [seconds]     keep the map live in the background
python codemap.py hook install        git post-commit / post-merge / post-checkout hooks
python codemap.py hook uninstall      remove them
```

`watch` and the git hooks also keep `CODE_MAP.md` itself fresh, which covers
the one case self-healing cannot: an agent reading the file directly instead
of using the commands.

---

## Using it with Claude Code everywhere

Each project gets its own `AGENTS.md` section automatically. To carry the cost
rule into every project without per-project setup, put this in
`~/.claude/CLAUDE.md`:

```markdown
## Code map cost rule (projects that contain `codemap.py` and `codemap-out/`)

- Function, class, file or concept: `python codemap.py query "<term>"` first,
  then `explain <Name>`, `path <A> <B>`, or `file <path-part>`. Only then open
  the lines it points to.
- Literal string (UI label, error text, config key): grep directly.
- `codemap-out/CODE_MAP.md` is fine to read whole. `CODE_MAP_INDEX.md` is not:
  grep it or use the commands.
- Under about 30 files, reading `CODE_MAP.md` whole is already cheap.
- Rebuild by hand only after big changes: `python codemap.py .`
```

---

## Skipped automatically

`codemap.py` itself, `node_modules`, `vendor`, `.git`, `dist`, `build`,
`codemap-out`, binary and image files, and anything over 2 MB per file.

---

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). If you build
on this, keep the NOTICE file with your distribution and a link back to
[agentcodemap.com](https://agentcodemap.com) is appreciated.
