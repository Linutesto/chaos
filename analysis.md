QJSON Agents — Technical Analysis

Scope
This document summarizes the architecture, code quality, safety/performance posture, and recent enhancements (web search, crawl, indexing, and CLI/menu integration).

Architecture Overview
- Agent core (agent.py): prompt assembly (system + tails + injections), logging to JSONL, persona fork/swap/evolve, memory introspection.
- Memory & state (memory.py, fmm_store.py): efficient tails, event logging, fractal memory store (batched writes), cluster index counters.
- Retrieval (retrieval.py): SQLite + embeddings (Ollama/hash/transformers), cosine similarity, IVF‑like candidate selection in fmm.json, optional hybrid TF‑IDF rerank and freshness boost.
- Web stack:
  - Outliner (web_outliner.py): HTML→DocOutline with titles/subtitles/sections/dates; basic readability heuristics; regex date detection.
  - Crawler (web_crawler.py): BFS with robots.txt, per‑host rate limits, dedup via SHA‑1 of section text; depth/pages caps.
  - Indexer (web_indexer.py): chunk sections (~1000 chars; 150 overlap), upsert into retrieval DB and Fractal Memory under `web/{host}/{YYYY}/{title}/...`.
  - Ranker (web_ranker.py): normalized wrapper atop retrieval.search_memory.
- CLI (cli.py): subcommands (init/chat/ingest/reindex/test/cluster/analyze/personas/encode/decode/yson tools) plus new non‑interactive `crawl` command.
- Menu (menu.py): interactive launcher now includes Web & Crawl Settings (web top‑k, crawl rate, caps, API key) and a one‑shot crawl launcher.
- Plugin (plugins/langsearch_crawler.py): `/crawl` supports search mode (LangSearch/Googlesearch) and BFS mode for URLs; injects/caches results and indexes crawled pages.

Key Enhancements (web)
- Slash commands: /find, /open, /crawl (plugin), /setenv, /langsearch key, /engine_scope.
- Injection flow: results cached (QJSON_WEBRESULTS_CACHE) and one‑shot injected (QJSON_WEBSEARCH_RESULTS_ONCE); full pages injected via QJSON_WEBOPEN_TEXT_ONCE with strict caps.
- Acknowledgements: QJSON_WEB_ACK=1 appends “(used web results)” and/or “(used web page content)” to replies when applicable.
- Non‑interactive crawl: `qjson-agents crawl --seeds ... --depth ... --pages ... --rate ... --id ...` saves a crawl manifest and indexes pages without entering chat.

Safety & Performance
- Retrieval: bounded top‑k; time‑decay; IVF acceleration via fmm.json; fast‑fail embeddings.
- Web: robots.txt honored, per‑host rate limiting (QJSON_CRAWL_RATE), strict fetch and injection caps (QJSON_WEBOPEN_MAX_BYTES, QJSON_WEBOPEN_CAP), no script execution.
- Logging: append‑only JSONL for memory/events; cluster index counters; optional retrieval notes in system prompt.

Test Coverage (web features)
- Unit tests verify: unified search normalization and fallbacks; env‑based one‑shot injection; crawl fallback and caching; /open arming and injection.
- All added tests pass locally.

Quality Observations
- Code favors minimal deps and standard library—even for HTML parsing and crawling. This fits the project ethos but limits readability robustness on complex sites; acceptable for MVP.
- CLI is large but now more modular with helper functions and new subcommands; opportunities remain to split into submodules.
- Documentation updated to reflect new web and crawl features, envs, and menu options.

Roadmap Suggestions
- Add per‑page JSON exports during crawl (one outline JSON per page) and optional TSV logs for analytics.
- Optional readability extraction and content scoring heuristics for cleaner outlines.
- Headless fetch behind a flag for top‑N pages (budgeted) when JS is required.
- Cross‑encoder reranking (local) gated by env, or LLM pairwise preference with token budget.
- Richer PII scrubbing and domain allowlists/denylists stored per agent.
