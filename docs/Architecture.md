Architecture

Layers
- Persona layer: QJSON/YSON manifests describe identity, roles, goals, runtime, and optional logic entrypoints.
- Agent layer: qjson_agents.agent.Agent wraps a manifest, builds prompts, logs memory/events, and calls Ollama.
- State layer: Append‑only JSONL (memory.jsonl, events.jsonl) + fractal memory tree (fmm.json) + index.json.
- Orchestration: CLI and menu implement chat flows, ingestion, cluster testing, and analysis.
- Retrieval (optional): SQLite + embeddings store augments prompts with small, relevant memory snippets per turn.
  - FAISS‑like IVF index (no extra deps) persisted inside the fractal store (fmm.json) for fast candidate selection.
  - Embedding backends are local‑first (Ollama) with timeouts and fallbacks (deterministic hash) to keep the loop responsive.
  - Hybrid search combines cosine similarity with optional TF-IDF re-ranking and a freshness boost.
- Web layer (optional): outliner, crawler, indexer for web pages
  - Outliner (web_outliner.py): HTML→DocOutline (title/subtitle/sections/dates/lang) with readability‑like heuristics and date regexes.
  - Crawler (web_crawler.py): BFS with robots.txt respect, per‑host rate limiting, dedup via content hash, depth/pages caps.
  - Indexer (web_indexer.py): chunk sections and upsert into Fractal Memory + retrieval DB; paths under `web/{host}/{YYYY}/{title}/...`.
  - Plugin/CLI: slash commands (`/find`, `/open`, `/crawl` via plugin) and non‑interactive `crawl` subcommand.

Data flow (single agent)
- init → normalize manifest → write state/<id>/manifest.json
- chat → optional logic anchor → assemble context (system + memory tails + optional retrieval block) → Ollama chat (non‑streaming/streaming) → log user/assistant to memory.jsonl → update fmm.json and index.json → store vectorized USER/ASSISTANT lines in SQLite (post‑call)
- status → tail memory/events efficiently without loading full files
- find/crawl → results injected as a compact system block for the next turn; `/open` injects a capped full page. Replies can append an acknowledgement tag when enabled.

Data flow (cluster)
- Load N manifests → create N Agent instances → schedule handoffs per topology:
  - ring: deterministic round‑robin baton
  - mesh: broadcast and aggregate last reply
  - moe: router scores experts by unigram+bigrams TF‑IDF overlap with baton, cooldown penalty, and persistent bias; summarizer aggregates
- Persist JSON transcript + TXT human log + router telemetry

Safety gates
- YSON logic execution is disabled by default (SAFE_MODE). Gate via --allow-yson-exec or QJSON_ALLOW_YSON_EXEC=1.
- Persona logic entrypoints are disabled by default. Gate via --allow-logic, /allow_logic, or QJSON_ALLOW_LOGIC=1.
- Minimal prompt mode (QJSON_TINY_SYSTEM=1) avoids brochure priming.
- Web safety: obey robots.txt, per‑host rate limits, strict caps on fetch size and injected chars; no script execution; local fallback search supports constrained environments.

Persistence and indexing
- Incremental counters: memory/events line counts update O(1) on each append.
- Debounced writes: index.json writes are rate‑limited to reduce churn.
- Fractal memory: Path‑like topics with accumulated data at leaves. Batched writes to fmm.json.
- IVF/FMM: Per‑agent inverted file (IVF) index under fmm.json accelerates retrieval; rebuild via `reindex` CLI. The index is automatically updated when new memories are added.
- Web index: crawled pages chunked and inserted into retrieval DB and Fractal Memory under domain/year/title paths with section‑level metadata and timestamps.
