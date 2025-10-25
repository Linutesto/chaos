Environment Variables Catalog

This file lists the environment variables recognized by qjson-agents, grouped by area. Defaults apply unless otherwise stated. All values are strings unless documented otherwise.

Global
- QJSON_AGENTS_HOME — Base directory for state (default ./state). Affects per‑agent state paths and retrieval DB path.
- QJSON_TINY_SYSTEM=1 — Use a minimal system prompt to reduce prompt bloat.
- QJSON_SHOW_CONTEXT=1|0 — Print a one‑line context summary in chat (web results/page/retrieval hits). Default 1 (enabled).

Engine / Search
- QJSON_ENGINE_DEFAULT=online|local — Default mode for /find.
- QJSON_LOCAL_SEARCH_ROOTS — os.pathsep‑separated list of directories to scan when using local search mode.
- QJSON_LOCAL_SEARCH_SKIP_DIRS — comma‑separated dir names to skip during local search fallback.
- QJSON_LOCAL_SEARCH_MAX_FILES — Max files to scan in fallback (default 5000).
- LANGSEARCH_API_KEY — Enables LangSearch web search in /find and plugin /crawl.
- QJSON_WEB_TOPK — How many search results to inject/list (default 5).
- QJSON_FIND_FETCH=1|0 — After online search, fetch/index top‑N pages (default 1).
- QJSON_FIND_FETCH_TOP_N — How many top results to fetch into the index (default 1).

Web Fetch & Injection (/open)
- QJSON_WEBOPEN_TIMEOUT — Per‑page fetch timeout in seconds (default 6).
- QJSON_WEBOPEN_MAX_BYTES — Max bytes read when fetching a page (default 204800).
- QJSON_WEBOPEN_CAP — Max characters injected for a page (default 12000).
- QJSON_WEBOPEN_DEFAULT=text|raw — Default /open mode; text attempts outline extraction (default text).
- QJSON_WEBOPEN_MODE_ONCE=text|raw — One‑shot override used by /open N raw|text; cleared automatically.
- QJSON_WEBOPEN_HEADER — Header label used when arming a page for injection (overridden by helpers as needed).
- QJSON_WEB_ACK=1 — Append a short acknowledgement to the model’s reply when web content was used.

Web Crawler & Indexer
- QJSON_CRAWL_RATE — Requests per second per host (default 1.0).

Retrieval / RAG
- QJSON_RETRIEVAL=1 — Enable retrieval injection for chat.
- QJSON_RETRIEVAL_TOPK — Top‑k retrieval (default 6).
- QJSON_RETRIEVAL_DECAY — Time‑decay lambda for aging memories (default 0.0).
- QJSON_RETRIEVAL_MINSCORE — Minimum score threshold to include a hit (default 0.25).
- QJSON_RETRIEVAL_NOTE=1 — Add a short “retrieval protocol” note to the system prompt.
- QJSON_RETRIEVAL_ONCE=1 — Arm one‑shot retrieval for the next prompt.
- QJSON_RETRIEVAL_QUERY_HINT — Optional query override for the next retrieval.
- QJSON_RETRIEVAL_LOG=1 — Insert USER/ASSISTANT lines into the retrieval DB for post‑hoc analysis.

Embeddings Backend
- QJSON_EMBED_MODE=ollama|hash|transformers — Choose embedding backend (default ollama; hash fallback used automatically when Ollama is unavailable).
- QJSON_EMBED_URL — Ollama embeddings endpoint (default http://127.0.0.1:11434/api/embeddings).
- QJSON_EMBED_MODEL — Ollama embedding model (default nomic-embed-text).
- QJSON_EMBED_DIM — Expected embedding dimension (default 768).
- QJSON_EMBED_TIMEOUT — Timeout (seconds) for embedding calls (default 6.0).

Retrieval Acceleration (IVF/FMM)
- QJSON_RETR_USE_FMM=1 — Enable FAISS‑like IVF index usage in fmm.json.
- QJSON_RETR_IVF_K — Number of centroids/clusters (default 64).
- QJSON_RETR_IVF_NPROBE — Clusters probed per query (default 4).
- QJSON_RETR_REINDEX_THRESHOLD — Size threshold for automatic reindexing (optional; build via CLI for control).

Retrieval Scan Caps (when IVF is disabled/unavailable)
- QJSON_RETR_SCAN_MAX — Max collection size before falling back to recent subset (default 5000).
- QJSON_RETR_RECENT_LIMIT — Recent items considered when limited (default 2000).

Chat Inclusion & Prompt Shaping
- QJSON_INCLUDE_CAP — Cap total characters included when injecting system memory via /include_sys (default 12000).
- QJSON_INCLUDE_MAX_MSGS — Max number of system messages included (default 8).

Models & Ollama
- OLLAMA_BASE_URL — Base URL for Ollama (default http://localhost:11434).
- QJSON_DEFAULT_NUM_PREDICT — Default num_predict override when not set by manifest/CLI.
- QJSON_MAX_TOKENS — Runtime override for num_predict.
- QJSON_DEBUG_OLLAMA=1 — Print a one‑liner before each Ollama call (model, message count, num_predict).

Logic / Safety Gates
- QJSON_ALLOW_YSON_EXEC=1 — Allow executing Python logic blocks embedded in YSON (unsafe; defaults to off/SAFE_MODE).
- QJSON_ALLOW_LOGIC=1 — Enable persona logic entrypoints (on_message; defaults to off).
- QJSON_LOGIC_MODE=assist|replace — Assist anchors LLM; replace bypasses the model and returns the hook output.

One‑shot Injection Keys (set by commands internally)
- QJSON_WEBSEARCH_RESULTS_ONCE — JSON list of search results to inject on the next turn.
- QJSON_WEBRESULTS_CACHE — Sticky cache of last results for /open.
- QJSON_INJECT_HITS_ONCE — JSON array of retrieval hits to inject on the next turn (debug/experiments).

