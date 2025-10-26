Developer Guide

ASCII Architecture
```
 HTML → Outliner → DocOutline ┐
                               │  chunk → Retrieval (SQLite+vec) → search
              Crawler (BFS) ───┼→ Indexer ────────────────────────┤
                               │  write → Fractal Memory (fmm.json)
 Agent CLI/Menu → Slash cmds ──┘  inject (next turn) → LLM via Ollama
```

Plugin API mini‑spec (/crawl)
- Reads `QJSON_AGENT_ID` (set by CLI) to index crawled content into the active agent.
- Accepts either a query (web search) or URL(s) with optional `depth=` and `pages=` (BFS mode).
- Caches results to `QJSON_WEBRESULTS_CACHE` and arms one‑shot injection with `QJSON_WEBSEARCH_RESULTS_ONCE`.
- Optional `export=<out_dir>` writes one DocOutline JSON per page.

Testing plan (suggested)
- Unit:
  - Outliner: headings/sections/dates on fixture HTML.
  - URL normalizer and canonical handling (when implemented).
  - Dedup hashing and chunk boundaries.
- Integration:
  - Crawl a tiny fixture site (local http server), depth=1, pages≤N; assert K pages indexed and retrievable.
- Golden answers:
  - Q→A pairs against small fixture; assert top‑k retrieval includes expected chunks.

Local dev setup
- Python 3.10+
- `python -m venv .venv && source .venv/bin/activate`
- `pip install -e .`
- Optional: run `python menu.py` for a guided UI; otherwise use `qjson-agents` CLI directly.

Coding style
- Prefer small, composable helpers; keep imports local inside hot paths to reduce import cost for CLI startup.
- Avoid heavy dependencies; prefer stdlib (e.g., `html.parser` for outliner, `sqlite3` for retrieval).
- Keep text outputs concise; large blocks should be persisted to files (logs/state) instead of printed.

Adding a module
- Create under `qjson_agents/`; wire into CLI by importing in `cli.py` where needed.
- Add targeted unit tests in `tests/` following the patterns for webopen/crawl/search.
- Update docs: `docs/Modules.md` and any relevant pages.

Releasing
- Ensure `pyproject.toml` has the correct version.
- Regenerate `qjson_agents.egg-info` by reinstalling in editable mode if packaging.
- Tag and provide a changelog; do not include large logs or state directories in source releases.

CI validation modes
- Workflow: `.github/workflows/qjson-validate.yml` validates `state/*/fmm.json`, `logs/test_run_*.json`, and `logs/cluster_run_*.json`.
- Default behavior: strict on invalid files (fails the job), lenient on missing files (skips with a message).
- Make missing files strict: remove the `if compgen ...` guards so the step runs unconditionally (and fails if files aren’t present).
- Make invalid files warn-only: append `|| echo "warn: validation failed"` and `|| true` to each validate command.
- Example (warn-only):
  - `python -m qjson_agents.cli validate --dir logs --glob "cluster_run_*.json" --schema cluster-run || echo "warn: invalid cluster_run logs" || true`
- Keystone personas
- Added under `personas/` as YSONX manifests you can load with `--manifest`:
  - `personas/DevOpsAgent.ysonx` — devops/CI archetype. Use `/git_*`, `/fs_*`, `/py`, and optionally `/api_*`.
  - `personas/ResearchAgent.ysonx` — research archetype. Use `/api_*` (gated), `/kg` (Holistic‑Scribe), `/prism`.
  - `personas/SwarmLord.ysonx` — orchestrator archetype. Use `/forge` to create/manage child agents.

Multi‑plugin demo
- Script: `scripts/devops_workflow_demo.sh` spins up a temp git repo and runs:
  - `/git_diff` on a newly added file
  - `/fs_read` to preview it
  - `/py @file.py` to execute (QJSON_ALLOW_EXEC=1)
  - Optionally `/api_post` to a mock webhook when `QJSON_ALLOW_NET=1`
