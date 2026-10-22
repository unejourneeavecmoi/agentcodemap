<a href="https://agentcodemap.com"><img src="https://agentcodemap.com/assets/readme-hero.jpg" alt="Agent Code Map: Your AI reads too much. Give it a map." width="100%"></a>

<p align="center">
  <a href="https://agentcodemap.com"><img src="https://img.shields.io/badge/agentcodemap.com-2a5fe0?style=for-the-badge&logoColor=white" alt="Website"></a>
  <a href="codemap.py"><img src="https://img.shields.io/badge/one%20file-codemap.py-3f73f5?style=for-the-badge" alt="One file"></a>
  <a href="codemap.py"><img src="https://img.shields.io/badge/python-3.8%2B-2f6b3c?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+"></a>
  <a href="codemap.py"><img src="https://img.shields.io/badge/dependencies-none-8db0ff?style=for-the-badge" alt="Zero dependencies"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-555?style=for-the-badge" alt="Apache-2.0"></a>
  <a href="https://buymeacoffee.com/losingnumbers"><img src="https://img.shields.io/badge/buy%20me%20a%20coffee-%E2%98%95-ffdd00?style=for-the-badge&logoColor=black" alt="Buy me a coffee"></a>
</p>

# Your AI reads too much. Give it a map.

Put **one file** in your project folder and type **one line**. From then on
your coding AI reads a small map of your code instead of whole files. Same
answers, up to **97% less reading**, and a smaller bill every month.

Free. Works with Claude Code, Codex, Cursor and opencode. Nothing leaves your
computer.

## Three steps. The first two take a minute.

**1. Put one file in your folder.**
Download [`codemap.py`](codemap.py) and drop it into the folder your project
lives in. That is the entire install. No account, no packages.

**2. Type one line.**

```
python codemap.py .
```

About a second later there is a small map of your code: what is in each file,
and which function calls which. It redraws itself whenever your code changes.

**3. Your AI reads the map, not the whole book.**
Claude Code, Codex, Cursor and opencode should find the map by themselves, or
just tell them to read and execute `AGENTS.md`, which is created in the root
folder.

## A map is a lot smaller than the book.

AI companies charge for every word the AI reads, counted in tokens. Fewer
tokens read, smaller bill. One real question, answered two ways, on a 228-file
app:

> *"What is in `app.js`?"* (a 7,000-line file)

| | Tokens read |
|---|---:|
| Without the map: the AI opens the whole file | **104,625** |
| With the map: one line per function, with its line number | **4,091** |

![One question, two answers](https://agentcodemap.com/assets/chart-one-file.svg)

Another one: *"How is `readFrontmatter` connected to `match`?"* Without the
map the AI reads two whole files, 135,769 tokens. The map answers in 16:

```
$ python codemap.py path readFrontmatter match
Shortest path (1 hops):
  readFrontmatter --calls--> match
```

## What it saved on four real projects.

One normal working session each: find a thing, see who uses it, look inside a
file, connect two functions. Same questions, with and without the map.

![Tokens per session on four projects](https://agentcodemap.com/assets/chart-session-tokens.svg)

| Project | Files | Without the map | With the map | Saving |
|---|---:|---:|---:|---:|
| Electron app | 228 | 267,525 | 8,349 | **97%** |
| React app | 26 | 80,649 | 4,107 | **95%** |
| PHP site | 45 | 17,773 | 4,026 | **77%** |
| PHP/JS web app | 133 | 38,780 | 12,262 | **68%** |

The saving is the same on every model. The same 133-file project counted with
four tokenizers saves 68 to 69 percent each time; only the price per token
differs.

![Same project, four tokenizers](https://agentcodemap.com/assets/chart-same-saving.svg)

## Your bill, roughly.

What one session of six lookups costs at each model's list price for input,
without the map and with it. Try your own numbers with the calculator on
[agentcodemap.com](https://agentcodemap.com/#bill).

![What one session costs per model](https://agentcodemap.com/assets/chart-dollars.svg)

| Model | Input price, per 1M | Session, no map | Session, with map | Saving |
|---|---:|---:|---:|---:|
| Claude Fable 5.1 | $10.00 | 38,780 | 12,262 | 68% |
| GPT-6 Astra | $10.00 | 39,823 | 12,337 | 69% |
| GLM-5.3 | $1.40 | 38,801 | 12,403 | 68% |
| DeepSeek V4 Pro | $1.32 peak | 41,978 | 13,193 | 69% |

Prices, sources and the dates they were checked are listed on
[agentcodemap.com](https://agentcodemap.com/#bill). Dollar figures are tokens
read times the list price for input, nothing else.

## Questions people ask.

**Does it send my code anywhere?**
No. It is one Python file with no dependencies, no AI inside it and no
network calls. You can read the whole file before you run it.

**What does it write?**
A `codemap-out/` folder with a two-page overview (`CODE_MAP.md`), an index of
every function with its line number (`CODE_MAP_INDEX.md`), the graph the
commands query (`map.json`), and a short note in your `AGENTS.md`. Commit the
folder or ignore it; both work.

**Which languages and which AIs?**
Python, JavaScript, TypeScript, PHP, SQL and HTML properly; Java, C#, Go,
Ruby, Rust, C and C++ at a lighter level. Any AI that reads `AGENTS.md`.

**Does the map go stale?**
No. Every time it is asked something it checks which files changed and redraws
only those, usually in well under a second.

**Where does it not help?**
Searching for a literal piece of text still goes through normal search; the
map does not store text. Tiny projects under about 30 files save little. One
flat scraper script in the benchmark saved only 28 percent. The map pays most
where files are big and connected.

## The four questions your AI will ask the map

```
python codemap.py query "auth"        what exists for a topic, with call edges
python codemap.py explain UserService who calls / inherits / imports one symbol
python codemap.py file acp-composer   one file's symbols with line numbers
python codemap.py path main slugify   shortest chain between two symbols
```

And a few more for you:

```
python codemap.py stats               files / symbols / edges summary
python codemap.py check               freshness test, no rebuild (exit 1 = stale)
python codemap.py watch [seconds]     keep the map live in the background
python codemap.py hook install        git hooks that rebuild after commit, merge, checkout
```

To carry the habit into every project with Claude Code, add this to your
`~/.claude/CLAUDE.md`:

```markdown
## Code map cost rule (projects that contain `codemap.py` and `codemap-out/`)

- Function, class, file or concept: `python codemap.py query "<term>"` first,
  then `explain <Name>`, `path <A> <B>`, or `file <path-part>`. Only then open
  the lines it points to.
- Literal string (UI label, error text, config key): grep directly.
- `codemap-out/CODE_MAP.md` is fine to read whole. `CODE_MAP_INDEX.md` is not.
- Rebuild by hand only after big changes: `python codemap.py .`
```

## Behind the numbers

Everything above was counted on real command output and file text with each
model's tokenizer, with no AI calls. The method and the per-task tables are in
[`benchmark/cost_rule_report.md`](benchmark/cost_rule_report.md).

The charts above are served from [agentcodemap.com](https://agentcodemap.com).

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). If it trims
your bill, [buy me a coffee](https://buymeacoffee.com/losingnumbers).
Made by [@biggab123](https://x.com/biggab123).
