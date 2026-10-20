<!-- codemap:start -->
## Code map (codemap)

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
  changes: `python codemap.py .`
<!-- codemap:end -->
