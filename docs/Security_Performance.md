Security and Performance

Safety
- SAFE_MODE: Embedded YSON logic is disabled by default; enable only when needed.
- Logic hooks: Persona on_message is opt‑in; enable via CLI or /allow_logic.
- Deterministic anchors: Keep prompts focused; avoid injecting entire documents.
- Web safety: Obey robots.txt; per‑host rate limiting (QJSON_CRAWL_RATE); capped fetch size (QJSON_WEBOPEN_MAX_BYTES) and injected chars (QJSON_WEBOPEN_CAP). No script execution or headless browser by default.

Performance
- Efficient tails: memory/events tails read from end (blocks), avoiding full‑file loads.
- Incremental counters: O(1) index updates on append.
- Debounced writes: index.json written at a modest cadence to reduce IO.
- Batched FMM: fmm.json flush every N inserts or by time.
- Caps: Inclusion character caps and max message count prevent prompt bloat (default ~12k chars, 8 msgs).
- Streaming: /stream on reduces perceived latency.
- Token caps: If unset, default num_predict ~256; override via CLI/env/manifest.
- Retrieval controls: keep top‑k small (e.g., 3–8) and set an ingest cap for embeddings (e.g., 2000 chars) to avoid unnecessary cost.
- Embeddings are local‑first: short timeouts and a one‑shot ping avoid long stalls when Ollama is unreachable; default fallback to hash keeps features usable.
- IVF/FMM index accelerates lookups without external dependencies; rebuild on demand via `reindex`.
- Scan caps guard against full‑table scans when no index is present (see QJSON_RETR_SCAN_MAX and QJSON_RETR_RECENT_LIMIT).
- Hybrid search (TF-IDF) is disabled by default but can be enabled for more accurate results at the cost of higher latency.
- Crawl/runtime caps: rate‑limit per host; limit depth/pages to keep crawls bounded; deduplicate by content hash.

Recommendations
- Use smaller models for iteration; reserve bigger models for final passes.
- Keep include_sys off unless you specifically need injected content.
- Use /preflight to estimate prompt/token sizes before sending.
- If retrieval is enabled, verify `/settings` and `/retrieval` to ensure the injected block remains compact and relevant.
- Use `QJSON_DEBUG_OLLAMA=1` during troubleshooting to print a one‑liner before each Ollama call.
- For web flows, keep QJSON_WEBOPEN_MAX_BYTES small (≤200KB), set QJSON_WEBOPEN_TIMEOUT modestly (≈6s), and limit QJSON_WEB_TOPK to reduce prompt bloat.

Threat model (pragmatic)
- No remote code execution through fetched content: pages are fetched as bytes and parsed as text; no JS execution or headless browser.
- Logic execution is gated and local; never enable `--allow-yson-exec` on untrusted personas.
- Retrieval DB is a local SQLite file; no external DB credentials are used by default.
- Network calls: Ollama and (optionally) LangSearch; ensure you trust the local model server and API endpoints.

Profiling tips
- Use the offline `test` harness for reproducible runs and stable comparisons (avoid network noise).
- Enable `QJSON_DEBUG_OLLAMA=1` to correlate prompt sizes with call latency.
- Inspect `logs/*.{json,txt,log}` for timing and counts; use `analyze` to compare fairness and throughput across runs.
