CLI Usage

Installation
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

Core commands
- init — Initialize agent from a manifest
- chat — Interactive chat with slash commands
- status — Show agent status and recent memory/events
- loop — Run an autonomous loop for N iterations
- semi — Run a semi‑autonomous loop with plugin gating and early‑stop
- fork — Fork an existing agent’s persona/state
- swap — Swap an agent’s persona by id/path/tag
- evolve — Mutate persona per rules (optionally adopt)
- introspect — Memory metrics and optional auto-adaptation
- personas — List/search personas
- cluster — Show/refresh cluster index
- cluster-test — Run ring/mesh/MoE with logs
- analyze — Analyze a run JSON (fairness/TPS)
- test — Offline test harness (mock/real Ollama)
- yson-validate — Validate and inspect a YSON file
- yson-run-swarm — Run a swarm cluster from a YSON swarm file
- ysonx-convert — Convert .json/.yson to .ysonx
- encode-manifest / decode-manifest — Fractal envelope tools
- ingest / ingest-batch — Append memory lines (optionally seeding retrieval)
- reindex — Rebuild per‑agent IVF index in fmm.json
- crawl — Non‑interactive BFS crawl + indexer + JSON export
- exec — Run a single slash command (e.g., `/find ...`, `/open N`)

Non‑interactive crawl
```bash
qjson-agents crawl \
  --seeds https://example.com https://example.org \
  --depth 1 --pages 20 --rate 1.0 \
  --allowed-domain example.com --allowed-domain example.org \
  --id Lila-v∞
```
Outputs: `state/<id>/crawl/crawl_YYYYMMDD-HHMMSS.json` and indexes all pages into the agent’s Fractal Memory + retrieval DB.

Per‑page JSON export
```bash
qjson-agents crawl --seeds https://example.com --depth 1 --pages 10 \
  --export-json ./crawl_outlines/ --id Lila-v∞
```
Writes one DocOutline JSON per page into `./crawl_outlines/`.

Exec a slash command without chat
```bash
qjson-agents exec "/find https://example.com depth=1 pages=5 export=./out" --id Lila-v∞
qjson-agents exec "/find fractal ai mode=online"
qjson-agents exec "/open 1" --id Lila-v∞
```

Retrieval (optional)
- Works with SQLite + Ollama embeddings (no external DB). If Ollama is down, a deterministic hash embedding keeps features usable by default. Enable transformers only when `QJSON_EMBED_MODE=transformers` is set.
- IVF/FMM acceleration: FAISS‑like IVF index persisted per agent in `state/<id>/fmm.json` — build with `qjson-agents reindex --id <AGENT> --k 64 --iters 3`.
- Enable globally via env or per-session via chat slash commands or the menu.
- Hybrid search combines cosine similarity with optional TF-IDF re-ranking and a freshness boost.

Chat flags
- --id, --manifest, --model, --max-tokens
- --allow-yson-exec (explicitly allow YSON logic blocks)
- --allow-logic (enable persona on_message)
- --logic-mode assist|replace (anchor the LLM or replace it)
- -c/--once "PROMPT" to send a single prompt and exit (use --model mock-llm for local testing)

Slash commands (highlights)
- /scan, /inject, /inject_py, /inject_mem
- /include_sys on|off|N|auto, /include_as system|user, /include_cap N, /show_sys N
- /stream on|off, /preflight <TEXT>
- /allow_logic on|off, /logic_mode assist|replace, /logic_ping <TEXT>
- /retrieval on|off|once [QUERY]|k=<N>|decay=<F>|min=<F>|ivf=<on|off>|ivf_k=<K>|nprobe=<N>|thresh=<N>|hybrid=<none|tfidf>|tfidf_weight=<F>|fresh_boost=<F>
  - Toggle retrieval, arm next turn with optional QUERY, and tune IVF and hybrid search.
- /engine [mode=online|local] — show/set default search mode; shorthand `/engine online|local` persists
- /find <QUERY or URL...> [mode=online|local depth=N pages=M export=DIR] — unified engine: online search (LangSearch→fallback), local file search, or BFS crawl for URLs; honors QJSON_WEB_TOPK (printed as k=K)
- /open N [ingest] [raw|text] — fetch full content of result N, inject for next turn; 'ingest' indexes page(s) into the agent (HTML→outline→index). Use 'raw' to inject HTML as-is, 'text' to force outline extraction.
- /setenv KEY=VALUE — set and persist a session env var (e.g., LANGSEARCH_API_KEY)
- /langsearch key <KEY> — set and persist LangSearch API key
- /engine_scope show|add|set|clear — configure local roots for offline search
- /truth on|off (inject a short locally‑truthful note)
-Plugin commands (built‑in)
- /fs_list [PATH] [glob=PAT] [max=N] — list files (roots: QJSON_FS_ROOTS); aliases: /fs_ls
- /fs_tree [PATH] [depth=N] [max=N] — recursive directory tree preview
- /fs_cd <PATH>, /fs_pwd — change/print current working directory (stateful per session)
- /fs_read|/fs_open <PATH> [max_bytes=N] — read file
- /fs_write <PATH> <TEXT|@file> [append=1] — gated by QJSON_FS_WRITE=1
- /fs_find <NAME or glob> [max=N] [base=PATH] — find files under base
- /py <CODE...>|@file.py — gated by QJSON_ALLOW_EXEC=1; timeout QJSON_EXEC_TIMEOUT
- /sql_open <PATH> [ro=1], /sql_tables, /sql_query <SQL> [max=N] [json=1], /sql_close — SQLite only; per‑process connection
- /git_status [short=1], /git_log [N], /git_diff [PATH] — read‑only; repo root via QJSON_GIT_ROOT
- /api_get <URL> [h:K=V...] [timeout=N] [max=N], /api_post <URL> body='{}' [...] — gated by QJSON_ALLOW_NET=1

Menu
- The text UI mirrors these flags interactively and caches small preferences.
- Agent Management → “retrieval settings” lets you enable retrieval, set top‑k/decay/min, IVF K/nprobe/reindex threshold, and seed embeddings on ingest. Settings persist and are applied to new sessions launched from the menu. You can also trigger an on‑demand IVF rebuild.
- Search & Crawl Settings → set default search mode (online/local), web top‑k, page fetch caps (timeout/max bytes/injected chars), crawl rate per host, and LangSearch API key. You can also launch a one‑shot non‑interactive crawl and clear cached results.
- Plugins & Tools → quick access to built‑in plugins:
  - File System: set roots, list/read/write (writes gated by QJSON_FS_WRITE)
  - Exec (Python): toggle QJSON_ALLOW_EXEC and run inline code or @file.py
  - Git: set repo root and run status/log/diff
  - Generic API: toggle QJSON_ALLOW_NET and run GET/POST
  - SQLite DB: open/tables/query/close using a stateful menu instance
  - Advanced: Forge (create/delegate/report), Prism (hats/auto), Holistic‑Scribe (/kg), Continuum (export/import), Meme‑Weaver (analyze/generate)

Env vars
- OLLAMA_BASE_URL=http://localhost:11434
- QJSON_AGENTS_HOME=./state
- QJSON_ALLOW_YSON_EXEC=1, QJSON_SAFE_MODE=0 (not recommended)
- QJSON_ALLOW_LOGIC=1, QJSON_LOGIC_MODE=assist|replace
- QJSON_TINY_SYSTEM=1 (lean system prompt)
- QJSON_INCLUDE_CAP, QJSON_INCLUDE_MAX_MSGS
- Retrieval:
  - QJSON_RETRIEVAL=1 (enable retrieval injection)
  - QJSON_RETRIEVAL_TOPK=6 (top‑k)
  - QJSON_RETRIEVAL_DECAY=0.0 (time‑decay lambda; score *= exp(-lambda*age_days))
  - QJSON_RETRIEVAL_MINSCORE=0.25 (minimum score to include a hit in the injected block)
  - QJSON_RETRIEVAL_NOTE=1 (append a short “Retrieval Protocol” note to the system prompt)
  - QJSON_RETRIEVAL_INGEST=1 (seed embeddings during /inject*), QJSON_RETRIEVAL_INGEST_CAP=2000 (chars per file to embed)
  - QJSON_EMBED_URL=http://127.0.0.1:11434/api/embeddings, QJSON_EMBED_MODEL=nomic-embed-text, QJSON_EMBED_DIM=768, QJSON_EMBED_TIMEOUT=6.0, QJSON_EMBED_MODE=ollama|hash|transformers
  - Optional hybrid/boost:
    - QJSON_RETRIEVAL_HYBRID=tfidf (combine TF‑IDF with embedding cosine)
    - QJSON_RETRIEVAL_TFIDF_WEIGHT=0.3 (weight for TF‑IDF term)
    - QJSON_RETRIEVAL_FRESH_BOOST=0.0 (freshness boost alpha; higher favors recent)
  - IVF/FMM acceleration:
    - QJSON_RETR_USE_FMM=1 (enable IVF index use)
    - QJSON_RETR_IVF_K=64 (number of centroids/clusters)
    - QJSON_RETR_IVF_NPROBE=4 (clusters probed per query)
    - QJSON_RETR_REINDEX_THRESHOLD (size threshold to rebuild index; use `reindex` command instead for control)
  - Scan caps (no IVF):
    - QJSON_RETR_SCAN_MAX=5000 (max collection size before falling back to recent subset)
    - QJSON_RETR_RECENT_LIMIT=2000 (recent items considered when limited)
  - Debug:
    - QJSON_DEBUG_OLLAMA=1 (print a one‑liner before each Ollama call)
Web/crawl
- LANGSEARCH_API_KEY=sk-... (LangSearch API key; used primarily for online /find)
- QJSON_WEB_TOPK=5 (number of web results to inject)
- QJSON_WEB_ACK=1 (append a short acknowledgement when web content is used)
- QJSON_WEBOPEN_TIMEOUT=6 (seconds to fetch a page)
- QJSON_WEBOPEN_MAX_BYTES=204800 (max bytes to read per page)
- QJSON_WEBOPEN_CAP=12000 (max characters injected for the page)
- QJSON_WEBOPEN_DEFAULT=text|raw (default /open mode; defaults to text/outline)
- QJSON_CRAWL_RATE=1.0 (requests per second per host)
- QJSON_LOCAL_SEARCH_ROOTS (os.pathsep‑separated paths for offline local search fallback)
- QJSON_LOCAL_SEARCH_SKIP_DIRS (comma‑separated dir names to skip in local fallback)
- QJSON_LOCAL_SEARCH_MAX_FILES=5000 (cap files scanned in local fallback)
 - QJSON_ENGINE_DEFAULT=online|local (default mode for /find)
- QJSON_FIND_FETCH=1 (fetch and index top pages after online search)
- QJSON_FIND_FETCH_TOP_N=1 (how many pages to fetch/index from top results)

Examples
- Online search and open outline text
  - `/engine online`
  - `/find sponge bob`
  - `/open 3 text`
- Local search across your workspace
  - `/engine_scope set ~/code:~/notes`
  - `/engine local`
  - `/find README.md`
  - `/open 1`
- Post‑search fetch and indexing
  - `QJSON_FIND_FETCH=1 QJSON_FIND_FETCH_TOP_N=2` then `/find topic`

Custom (semi‑autonomous) mode
```bash
# Allow only FS+Git+Exec+API plugins; stop early when the agent asks for more info
QJSON_PLUGIN_ALLOW="/fs_list,/fs_read,/fs_write,/git_status,/git_log,/git_diff,/py,/api_get,/api_post" \
QJSON_ALLOW_EXEC=1 \
qjson-agents semi --id DevOpsAgent \
  --manifest personas/DevOpsAgent.ysonx \
  --goal "Investigate new changes and report status" \
  --iterations 3 --delay 0.0 --stop-token "need more info" --model auto
```
