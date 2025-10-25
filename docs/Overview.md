QJSON Agents — Overview

This project provides a local‑first agent runtime that unifies three pillars:
- Identity and persona manifests (QJSON, YSON, YSON‑X)
- Deterministic, append‑only state (JSONL memory + fractal memory tree)
- Lightweight inference orchestration over local models (Ollama)

Why this matters
- Predictable: Stateful agents run entirely on your machine with explicit safety gates.
- Inspectable: Memory and events are plaintext JSON lines; the fractal store is a simple JSON tree.
- Extensible: Personas can attach pure‑Python logic hooks for reasoning anchors, reducing hallucinations.
- Composable: Multi‑agent clusters/routers (ring/mesh/MoE) are included for experiments.

Core capabilities
- CLI
  - init, chat, loop, status, fork, swap, evolve, introspect, test, cluster, personas, analyze
  - yson‑tools (encode/decode/validate yson/ysonx), yson‑swarm (run a swarm from a YSON cluster file)
  - exec (run a single slash command without entering chat)
- Personas
  - JSON (canonical) or YSON/YSON‑X (human‑friendly)
  - Optional pure‑Python logic entrypoints (on_message) with assist/replace modes
  - Evolution rules and persona swap built‑in
- Memory & State
  - memory.jsonl + events.jsonl (append‑only) + fmm.json (hierarchical fractal store)
  - Efficient tails and O(1) counters; cluster index across agents
- Search / Crawl
  - Unified /find (online/local) + /open (raw|text)
  - Optional plugin /crawl (LangSearch+Googlesearch) with BFS mode and indexer
  - HTML→DocOutline outliner, safe caps on fetch and injection
- Retrieval (optional)
  - SQLite + embeddings with timeouts/fallbacks; hybrid TF‑IDF; freshness boost
  - IVF‑like index persisted in fmm.json (no extra dependencies)
- Swarm & Router
  - ring/mesh/MoE with TF‑IDF router, cooldown, and persistent weights
  - Structured logs and analysis tools (tokens/sec, fairness, MoE distribution)

Read next
- docs/Architecture.md — Runtime layers and flows
- docs/Modules.md — Code map per module
- docs/Personas_and_Logic.md — Manifests and logic entrypoints
- docs/Memory_and_Fractal.md — Fractal QFP Core, persistence formats, envelopes
- docs/Swarm_and_Router.md — Routers, fairness metrics, and logs
- docs/CLI_Usage.md — Commands, flags, and chat slash commands
- docs/Security_Performance.md — SAFE_MODE, logic gates, perf patterns
- docs/ENV_VARS.md — Comprehensive environment variable catalog
- docs/Plugin_API.md — Writing your own slash command plugins
 - docs/Data_Formats.md — Full schemas for fmm.json and run JSON
