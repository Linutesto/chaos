Code Modules

High‑level
- qjson_agents/cli.py — CLI implementation and interactive chat loop
- qjson_agents/menu.py — Text UI wrapping CLI subcommands
- qjson_agents/plugins/langsearch_crawler.py — Web search + crawl slash command: LangSearch/Googlesearch search, BFS crawl mode, injection + caching, indexing

Details: cli.py
- Subcommands: init, chat, loop, status, fork, models, crawl, exec, ingest, ingest-batch, reindex, test, cluster, analyze, personas, swap, evolve, introspect, cluster-test, encode/decode-manifest, ysonx-convert, ysonx-swarm-launch, menu, yson-validate, yson-run-swarm
- Unified /find engine: online/local search; BFS crawl when passed URLs; persists result cache and prints top‑k honoring QJSON_WEB_TOPK; optional post-search fetch/index
- /open N [ingest] [raw|text]: fetch and inject page content; outline extraction by default; raw option injects HTML. Ingest indexes HTML→outline when possible; otherwise raw text into memory+retrieval
- One‑shot injection keys: QJSON_WEBSEARCH_RESULTS_ONCE, QJSON_WEBRESULTS_CACHE, QJSON_WEBOPEN_TEXT_ONCE; persisted to env store so exec flows can reuse
- Engine mode persistence: /engine online|local saves QJSON_ENGINE_DEFAULT via env store

Agent core
- qjson_agents/agent.py — Agent class: prompt assembly, logging, forking, persona swap/evolve, introspection
- qjson_agents/ollama_client.py — Minimal HTTP client for Ollama /api/chat and /api/tags (streaming + non‑streaming)
- qjson_agents/memory.py — State directory helpers, append_jsonl, efficient tail, incremental index counters
- qjson_agents/fmm_store.py — PersistentFractalMemory with batched writes, per‑agent shared instances

Details: agent.py
- Builds messages from: system prompt (tiny mode optional) + extra_system + extra_context + history tails
- Optional retrieval injection with logged preview; acknowledges via QJSON_RETRIEVAL_ACK
- Accepts web search injection (results block) and full page injection (webopen); acknowledges via QJSON_WEB_ACK
- Logs user/assistant, updates cluster index, and inserts chat lines into retrieval DB when enabled
- Supports chat_turn_stream with partial output callback

Personas & types
- qjson_agents/qjson_types.py — Manifest normalization, load/save (+ fractal envelope), persona scanning
- qjson_agents/yson.py — YSON/YSON‑X parsing: meta headers, JSON/YAML/JSON5‑like body, logic extraction (gated), yson→manifest, swarm helpers
- qjson_agents/logic/common_utils.py — Summarization, tasks extraction, memory snippet, style wrapper
- qjson_agents/logic/persona_runtime.py — on_start/on_message entrypoints used by personas

Details: yson.py
- load_yson(path) returns { meta, body }; meta parsed from header pragmas (#@version, #@source, etc.)
- yson_to_manifest: normalize keys (identity, runtime, goals, persona_style), validate, and return a canonical manifest dict
- synthesize_manifest_from_yson_name: convenience helper for swarm agents in yson-run-swarm

Ingestion and tools
- qjson_agents/ingest_manager.py — /scan, /inject, /inject_py, /inject_mem (parallel file read, sequential append, FMM/event updates)
- qjson_agents/retrieval.py — Minimal RAG: SQLite + Ollama embeddings, cosine search, time‑decay, optional TF‑IDF hybrid + freshness boost, min‑score cutoff; API: add_memory/add_batch/search_memory/inject_for_prompt
  - FAISS‑like IVF index stored inside fmm.json (no extra deps) for candidate selection; fast‑fail embeddings with timeouts and fallback to hash; scan caps avoid full‑table loads when no index is present.
  - Env: QJSON_RETR_USE_FMM, QJSON_RETR_IVF_K, QJSON_RETR_IVF_NPROBE, QJSON_EMBED_TIMEOUT, QJSON_EMBED_MODE, QJSON_RETR_SCAN_MAX, QJSON_RETR_RECENT_LIMIT, QJSON_RETRIEVAL_HYBRID, QJSON_RETRIEVAL_TFIDF_WEIGHT, QJSON_RETRIEVAL_FRESH_BOOST.
- ysonx_cli.py, ysonx_swarm.py — experimental YSON‑X tools and synthetic swarm

Details: retrieval.py
- Tables: vectors (id, agent_id, ts, text, meta JSON, vec BLOB), ivf metadata persisted in fmm.json
- Scoring: cosine + optional TF‑IDF hybrid + freshness; min‑score cutoff; optional MMR (roadmap)
- inject_for_prompt builds a compact block labeled “Retrieved long‑term memory”

Web stack
- qjson_agents/web_outliner.py — HTML→DocOutline: title, subtitle, H1–H6 sections, dates; boilerplate removal via class/id heuristics
- qjson_agents/web_crawler.py — BFS crawler with robots.txt, per‑host rate limiting, dedup, depth/pages caps
- qjson_agents/web_indexer.py — Upsert crawled content into Fractal Memory + retrieval DB (chunking and metadata)
- qjson_agents/web_ranker.py — Hybrid search wrapper reusing retrieval; normalized blending for agent use

Details: web_outliner.py
- html.parser‑based, zero‑deps; collects <title>, <meta>, H1–H6, nearest H2 after first H1 as subtitle, and dates via <time> and regex
- Filters “nav/menu/footer/sidebar/cookie/subscribe” elements by class/id heuristics
- Returns {url, title, subtitle, sections[{level,title,text,anchors}], dates, lang}

Swarm and analysis
- CLI: cmd_cluster_test — ring/mesh/MoE runs, TF‑IDF router with cooldown + persistent weights, fairness metrics, JSON/TXT logs
- CLI: cmd_reindex — build/update per‑agent IVF index in fmm.json
- CLI: cmd_analyze — tokens/sec, non‑empty ratio, per‑agent TPS, MoE distributions, comparative fairness

Security & envelope
- qjson_agents/fractal_codec.py — Experimental QJSON‑FE‑v1: PBKDF2‑HMAC key derivation, XOR stream, HMAC integrity; depth/fanout chunking

Auxiliary (present but not wired)
- qjson_agents/agent_runtime.py, qjson_agents/swap_protocol.py — Sample helpers (not required by CLI paths)
