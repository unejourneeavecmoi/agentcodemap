# Cost rule benchmark

Tokens an agent ingests per lookup task (tiktoken cl100k_base on real command output and file text). No model calls. OLD = read the whole map first (previous AGENTS.md wording). GREP = no map. RULE = the cost rule.

## electron-app  (228 files, 1280 symbols, 8412 edges)

Old single-file map: 19,155 tokens. New overview: 2,198. Index: 16,957.

| Task | OLD | GREP | RULE | RULE vs OLD | RULE vs GREP | Note |
|---|---:|---:|---:|---:|---:|---|
| Orient: what are the main parts of this codebase? | 19,155 | 25,297 | 2,198 | 89% | 91% | hub file for GREP: src/main/main.js |
| Find where `readFrontmatter` is defined and read it | 19,732 | 621 | 701 | 96% | -13% | grep hits: 3 lines; query output: 401 chars |
| Who calls `readFrontmatter`? Open the first 10 call sites | 19,502 | 850 | 980 | 95% | -15% | explain lists 1 callers; grep gives 3 hits |
| What is in `src/renderer/app.js`? | 19,155 | 104,625 | 4,091 | 79% | 96% | file is 7000 lines, 390 symbols |
| Find the UI string "Open a folder first." | 19,518 | 363 | 363 | 98% | 0% | rule says grep: identical to GREP by design |
| How is `readFrontmatter` connected to `match`? | 19,155 | 135,769 | 16 | 100% | 100% | GREP: both greps plus both defining files read whole |
| **All tasks, map re-read each time** | 116,217 | 267,525 | 8,349 | 93% | 97% | |
| **All tasks, one session (map read once)** | 20,442 | 267,525 | 8,349 | 59% | 97% | |

## php-js-webapp  (133 files, 858 symbols, 616 edges)

Old single-file map: 14,560 tokens. New overview: 4,380. Index: 10,180.

| Task | OLD | GREP | RULE | RULE vs OLD | RULE vs GREP | Note |
|---|---:|---:|---:|---:|---:|---|
| Orient: what are the main parts of this codebase? | 14,560 | 12,361 | 4,380 | 70% | 65% | hub file for GREP: public/assets/js/app.js |
| Find where `clubDetailHtml` is defined and read it | 16,281 | 1,891 | 1,846 | 89% | 2% | grep hits: 5 lines; query output: 401 chars |
| Who calls `clubDetailHtml`? Open the first 10 call sites | 16,370 | 3,211 | 2,159 | 87% | 33% | explain lists 3 callers; grep gives 5 hits |
| What is in `config/schema.sql`? | 14,560 | 4,658 | 3,162 | 78% | 32% | file is 422 lines, 286 symbols |
| Find the UI string "Clubs near you" | 15,250 | 690 | 690 | 95% | 0% | rule says grep: identical to GREP by design |
| How is `clubDetailHtml` connected to `season_tables`? | 14,560 | 15,969 | 25 | 100% | 100% | GREP: both greps plus both defining files read whole |
| **All tasks, map re-read each time** | 91,581 | 38,780 | 12,262 | 87% | 68% | |
| **All tasks, one session (map read once)** | 18,781 | 38,780 | 12,262 | 35% | 68% | |

## react-app  (26 files, 126 symbols, 302 edges)

Old single-file map: 2,567 tokens. New overview: 1,551. Index: 1,016.

| Task | OLD | GREP | RULE | RULE vs OLD | RULE vs GREP | Note |
|---|---:|---:|---:|---:|---:|---|
| Orient: what are the main parts of this codebase? | 2,567 | 30,658 | 1,551 | 40% | 95% | hub file for GREP: app.jsx |
| Find where `AppRoot` is defined and read it | 3,213 | 4,839 | 774 | 76% | 84% | grep hits: 136 lines; query output: 403 chars |
| Who calls `AppRoot`? Open the first 10 call sites | 2,567 | 7,002 | 627 | 76% | 91% | explain lists 0 callers; grep gives 136 hits |
| What is in `backend/database/schema.sql`? | 2,567 | 915 | 629 | 75% | 31% | file is 94 lines, 59 symbols |
| Find the UI string "Delete this box and all its items?" | 2,862 | 295 | 295 | 90% | 0% | rule says grep: identical to GREP by design |
| How is `AppRoot` connected to `create_single_label`? | 2,567 | 36,940 | 231 | 91% | 99% | GREP: both greps plus both defining files read whole |
| **All tasks, map re-read each time** | 16,343 | 80,649 | 4,107 | 75% | 95% | |
| **All tasks, one session (map read once)** | 3,508 | 80,649 | 4,107 | -17% | 95% | |

## php-site  (45 files, 207 symbols, 315 edges)

Old single-file map: 4,818 tokens. New overview: 2,060. Index: 2,758.

| Task | OLD | GREP | RULE | RULE vs OLD | RULE vs GREP | Note |
|---|---:|---:|---:|---:|---:|---|
| Orient: what are the main parts of this codebase? | 4,818 | 2,787 | 2,060 | 57% | 26% | hub file for GREP: python/parse_statement.py |
| Find where `from_text` is defined and read it | 5,438 | 650 | 744 | 86% | -14% | grep hits: 2 lines; query output: 398 chars |
| Who calls `from_text`? Open the first 10 call sites | 5,113 | 624 | 600 | 88% | 4% | explain lists 1 callers; grep gives 2 hits |
| What is in `httpdocs/index.php`? | 4,818 | 7,290 | 356 | 93% | 95% | file is 544 lines, 32 symbols |
| Find the UI string "No files received." | 5,058 | 240 | 240 | 95% | 0% | rule says grep: identical to GREP by design |
| How is `from_text` connected to `renderHeatmap`? | 4,818 | 6,182 | 26 | 99% | 100% | GREP: both greps plus both defining files read whole |
| **All tasks, map re-read each time** | 30,063 | 17,773 | 4,026 | 87% | 77% | |
| **All tasks, one session (map read once)** | 5,973 | 17,773 | 4,026 | 33% | 77% | |

## Assumptions

- Grep output capped at 250 lines, as the Grep tool does by default.
- After locating a definition the agent reads 10 lines before and 50 after it, in every strategy.
- For callers the agent opens at most 10 sites, 30 lines each, in every strategy.
- Literal-string tasks are identical under GREP and RULE by design: the rule sends those to grep.
- OLD charges the full map on every task in the per-task rows; the session row charges it once.
- Tasks are picked automatically per project: the top hub symbol, the file with most symbols, a UI-looking string.
