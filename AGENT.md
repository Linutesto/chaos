AGENT.md — Working Instructions for Agents in This Project

Purpose
This repository provides a local‑first agent runtime that uses QJSON/YSON manifests, persists state and memory locally, and calls local models via Ollama. Agents operate safely, deterministically where possible, and remain transparent in their behavior.

Core Responsibilities
- Respect SAFE_MODE defaults: embedded logic in YSON is disabled by default; only run with explicit user opt‑in.
- Persist everything locally: manifests, memory.jsonl, events.jsonl, and fractal memory (fmm.json) under state/.
- Be resource‑aware: keep prompts, inclusion, and tokens bounded. Stream responses where possible.
- Be auditable: log events (forks, ingest, swaps), maintain ancestry, and expose status/preflight telemetry.

Key Files and Concepts
- Manifests (QJSON/YSON): Describe the agent identity, features, directives, runtime, and evolution rules.
- memory.jsonl: Append‑only record of user/assistant/system events; used for context.
- events.jsonl: Operational events like fork/swap/ingest.
- fmm.json: Persistent fractal memory store for goals, batons, and custom structures.
- state/index.json: Cluster index for ancestry and counters. Updated automatically.
- Persona runtime hooks (optional):
  - `qjson_agents/logic/common_utils.py` small helpers (summarize, task extraction)
  - `qjson_agents/logic/persona_runtime.py` entrypoints: `on_start`, `on_message`
  - Manifests may reference these under `logic.entrypoints` and `logic.requires`.

Runtime Rules
- SAFE_MODE: Do not execute YSON logic unless `--allow-yson-exec` is passed (or env `QJSON_ALLOW_YSON_EXEC=1`).
- Persona logic: To execute persona hooks (`logic.entrypoints.on_message`), pass `--allow-logic` to `chat` or set env `QJSON_ALLOW_LOGIC=1`. Use `/allow_logic on|off` at runtime.
- Ingestion:
  - `/scan <path>` to preview eligible files.
  - `/inject <path>` for .json/.yson/.ysonx/.txt/.md (recursive).
  - `/inject_py <path>` for .py (recursive).
  - `/inject_mem <path>` for explicit verbatim inclusion.
  - Persist ingestion summary in events and FMM; never execute code.
  - Normalize paths before reading (expand ~/$VAR, strip quotes, collapse whitespace around slashes).
- Retrieval (optional):
  - Enable via `/retrieval on` (chat) or menu → retrieval settings; or set env `QJSON_RETRIEVAL=1`.
  - Tune `QJSON_RETRIEVAL_TOPK`, `QJSON_RETRIEVAL_DECAY` (score *= exp(-lambda*age_days)), and `QJSON_RETRIEVAL_MINSCORE` to filter low-signal results.
  - Seed embeddings on ingest by setting `QJSON_RETRIEVAL_INGEST=1` (cap text per file with `QJSON_RETRIEVAL_INGEST_CAP`, default ~2000 chars).
  - Embedding backends: Ollama `/api/embeddings` (default, uses `OLLAMA_BASE_URL` or override `QJSON_EMBED_URL`), else a deterministic hashed fallback. Enable transformers only with `QJSON_EMBED_MODE=transformers` to avoid unwanted downloads.
  - Timeouts and resilience: set `QJSON_EMBED_TIMEOUT` (default 6s). Retrieval pings Ollama once and falls back fast if unreachable.
  - FAISS‑like IVF index (no external deps): an inverted file (IVF) index is stored per‑agent in `state/<id>/fmm.json`. Enable via `QJSON_RETR_USE_FMM=1` (default). Rebuild with `qjson-agents reindex --id <AGENT> --k 64 --iters 3`.
    - Probing: `QJSON_RETR_IVF_NPROBE` (default 4) controls how many clusters are searched.
    - Reindex threshold: `QJSON_RETR_REINDEX_THRESHOLD` (default 512) triggers auto‑rebuild after inserts.
    - Centroids: `QJSON_RETR_IVF_K` (default 64). Index is stored under `retrieval.ivf.dim{D}.K{K}` in the FMM tree.
  - Slash commands:
    - `/retrieval on|off|once|k=<N>|decay=<F>|min=<F>|ivf=<on|off>|ivf_k=<K>|nprobe=<N>|thresh=<N>`
    - `/retrieve once [QUERY] [k=<N> ...]` (arm next prompt) and `/force_retrieve [QUERY]` (alias)
  - Debug: `QJSON_DEBUG_OLLAMA=1` prints a one‑liner before each Ollama call.
- Context Inclusion:
  - `/include_sys [on|off|N|auto]` controls inclusion of the last N system entries.
  - `/include_as [system|user]` sets injected role (system is default and stronger; user can be weighted more by some models).
  - `/include_cap N` caps included content size (default 12000 chars). Bound message count to avoid prompt bloat.
  - Use `/show_sys [N]` and `/preflight <TEXT>` to validate context before sending.
- Latency and Throughput:
  - Use small token caps by default: if unset, num_predict≈256.
  - Enable streaming `/stream on` to reduce perceived latency.
  - Prefer smaller models for iteration (e.g., `gemma3:4b`, `llama3:8b`) and switch to `gpt-oss:20b` when needed.
  - Pass GPU hints via env if needed: `QJSON_GPU_LAYERS`, `QJSON_MAIN_GPU`, `QJSON_TENSOR_SPLIT`.

Chat and Telemetry
- `/settings` shows current context and safety toggles plus telemetry: memory.jsonl size and prompt length estimate.
- `/settings edit ...` allows batch configuration of inclusion, truncation, caps, and yson_exec.
- `/preflight <TEXT>` estimates prompt size and latency using your current settings.

Safety and Behavior
- Always respect safety policies: refuse unsafe or illegal requests, don’t bypass controls, and keep logs.
- Maintain identity and continuity per manifest directives; log anomalies.
- For evolution or swaps, record events and persist snapshots.

Performance Checklist (before sending)
1) `/preflight <TEXT>` → prompt_chars/tokens reasonable?
2) `/settings` → caps and inclusion sane (cap 8–16KB; N ~ 3–5 messages)?
3) `/stream on` for responsiveness.
4) `--max-tokens 128–256` for fast replies.
5) If retrieval is on, keep top‑k small (3–8) and consider a modest time‑decay (e.g., 0.01) to favor recent memories without overwhelming the prompt.

Troubleshooting
- High RAM/CPU before inference:
  - See URGENT.md. Ensure you are on the version with efficient tailing and bounded inclusion.
  - Rotate memory.jsonl if it’s huge; reduce inclusion; use `/preflight`.
- GPU not used:
  - Verify `nvidia-smi`, check Ollama version and build, and try GPU hints.

Coding Conventions (for contributors)
- Keep modules single‑purpose; avoid global state.
- Prefer streaming and bounded computations; no full‑file reads for long logs.
- Use incremental building for large strings and always apply caps.
- Add CLI flags for runtime controls; mirror in menu.

See also
- docs/Overview.md
- docs/Architecture.md
- docs/Personas_and_Logic.md
- docs/Memory_and_Fractal.md
- docs/CLI_Usage.md
