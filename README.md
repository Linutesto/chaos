<p align="center">
  <img src="assets/banner.svg" alt="QJSON Agents — Local, Inspectable, Fractal‑Memory Agents" width="880"/>
</p>

QJSON Agents — Local, Inspectable, Fractal‑Memory Agents ✨

Local‑first agents with explicit personas, deterministic state, optional logic hooks, and multi‑agent orchestration over Ollama.

Highlights
- Pure‑Python, dependency‑light; easy to read and audit
- QJSON/YSON(X) personas with optional logic entrypoints (on_message)
- Append‑only JSONL memory + hierarchical fractal memory (fmm.json)
- Efficient indexing, tails, and cluster orchestration (ring/mesh/MoE)
- Optional retrieval: SQLite + embeddings to inject compact, relevant memories per turn (no external DB needed)
  - FAISS‑like acceleration without extra deps: IVF index persisted in the fractal store (fmm.json).
  - Tunable via env, slash, or menu: top‑k, time‑decay, min‑score cutoff, IVF K/nprobe, optional TF‑IDF hybrid re‑rank, and ingest seeding.
- Web search & crawl: outliner + crawler + indexer to bring web pages into memory safely
  - /find and /open: find results and fetch capped page content; inject into next turn with acknowledgements
  - /crawl (plugin or subcommand): BFS crawl URLs with robots/rate limits; save manifest, index pages into Fractal Memory + retrieval
  - Non‑interactive: `qjson-agents crawl --seeds ... --depth ... --pages ...` saves a crawl manifest and indexes without entering chat

Important
- See URGENT.md for fixes addressing pre‑inference RAM/CPU spikes: bounded inclusion, efficient tails, and batching.

Prerequisites
- Python 3.10+
- Ollama running at http://localhost:11434 (defaults)

Get Started in 30s
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
# quick demo (set your docs folder if you have one)
AGENT_ID=HealthcareDemo DOCS_DIR=./demo/healthcare_docs bash scripts/healthcare_demo.sh || true
```

Install
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

Quickstart

1. `pip install -e .`
2. `qjson-agents init` (creates data dirs)
3. `qjson-agents /find "topic"`
4. `qjson-agents /open 1`
5. `qjson-agents /crawl https://example.com depth=1 pages=10`
6. Ask: “Extract the timeline.”

Badges
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)
![Local-first](https://img.shields.io/badge/local--first-true-brightgreen)
![No external deps (core)](https://img.shields.io/badge/external%20deps%20(core)-none-lightgrey)
[![Validate](https://github.com/Linutesto/chaos/actions/workflows/qjson-validate.yml/badge.svg)](https://github.com/Linutesto/chaos/actions/workflows/qjson-validate.yml)

FAQ/Troubleshooting
- **403 or empty page?** → try `--ua` / disable JS; check robots; increase `QJSON_WEBOPEN_TIMEOUT`.
- **Duplicates in index?** → canonical URL + SHA1 dedup note.

Documentation
- docs/Overview.md — what’s inside and why it matters
- docs/Architecture.md — runtime layers and flows
- docs/Modules.md — module‑by‑module map
- docs/Personas_and_Logic.md — manifests and logic hooks
- docs/Memory_and_Fractal.md — fractal QFP core: memory, events, fmm, envelopes
- docs/Swarm_and_Router.md — ring/mesh/MoE, router and fairness
- docs/CLI_Usage.md — commands, flags, slash commands, menu, env
- docs/Security_Performance.md — SAFE_MODE, logic gates, perf
 - docs/FAQ.md — common issues and fixes
 - docs/Ranking_and_RAG.md — hybrid ranking knobs and scoring
 - docs/Developer_Guide.md — architecture ASCII, plugin API, test plan
 - docs/ENV_VARS.md — comprehensive environment variables
  - docs/Plugin_API.md — writing your own plugins
  - docs/Data_Formats.md — data formats for fmm.json and run JSON

Quick CI validation
```bash
# Validate cluster run logs in CI
qjson-agents validate --schema cluster-run --dir logs --glob "cluster_run_*.json"
```
 - market.md — market brief
 - analysis.md — technical analysis

Why QJSON Agents
- Local-first and inspectable: JSONL logs and fractal memory you can diff.
- Deterministic personas: manifests + optional logic hooks (assist/replace modes).
- Practical retrieval: SQLite + IVF acceleration without heavy dependencies.
- Built-in web tooling: safe outliner, crawler, and one-shot injections.

Use cases
- Internal SOP/QMS assistants with traceable sources and local indexing.
- Research companions: crawl, summarize, and extract structured timelines.
- Labs and pilots: deterministic experiments with ring/mesh/MoE orchestration.

Comparison (vs typical RAG stacks)
- Storage: uses JSONL + fractal fmm.json (inspectable) vs external vector DBs.
- Retrieval: SQLite + IVF-in-fmm (no extra services) vs heavy faiss/pgvector ops.
- Reproducibility: append-only logs + deterministic personas vs opaque pipelines.
- Web ingestion: built-in outliner/crawler with safety knobs vs ad-hoc scripts.
- Footprint: pure-Python, minimal deps vs multi-service infra and drivers.
- Privacy: local-first by default; network optional and explicit.

Persona runtime (drop‑in)
- Hooks live in:
  - qjson_agents/logic/common_utils.py
  - qjson_agents/logic/persona_runtime.py
- Wire from the manifest:
```json
"logic": {
  "entrypoints": {
    "on_start": "qjson_agents.logic.persona_runtime:on_start",
    "on_message": "qjson_agents.logic.persona_runtime:on_message"
  },
  "requires": ["qjson_agents.logic.common_utils"]
}
```
- Enable in chat:
```bash
qjson-agents chat --id HookProbe \
  --manifest personas/HookProbe.json --model gpt-oss:20b \
  --allow-logic --logic-mode assist
```

State layout (per agent)
- state/<agent_id>/manifest.json — normalized manifest snapshot
- state/<agent_id>/memory.jsonl — append‑only conversation and system messages
- state/<agent_id>/events.jsonl — operational events
- state/<agent_id>/fmm.json — fractal memory (hierarchical tree with __data__)
- state/index.json — cluster index (parents, counters)

Why it could change how we build agents
- Personas become code: logic hooks transform personas from static prompts into runtime policies.
- Memory becomes durable: JSONL + fractal tree make inspection and post‑hoc analysis trivial.
- Orchestration becomes testable: ring/mesh/MoE + fairness metrics provide repeatable swarm experiments.
- Everything is local: better privacy, debuggability, and cost control.

Env vars
- OLLAMA_BASE_URL (default http://localhost:11434)
- QJSON_AGENTS_HOME (default ./state)
- QJSON_ALLOW_LOGIC=1, QJSON_LOGIC_MODE=assist|replace
- QJSON_TINY_SYSTEM=1 (lean system prompt)
- QJSON_ALLOW_YSON_EXEC=1 (unsafe; enables YSON logic blocks)
- Retrieval (optional):
  - QJSON_RETRIEVAL=1, QJSON_RETRIEVAL_TOPK, QJSON_RETRIEVAL_DECAY, QJSON_RETRIEVAL_MINSCORE
  - QJSON_RETRIEVAL_INGEST=1, QJSON_RETRIEVAL_INGEST_CAP (seed embeddings on ingest)
  - QJSON_EMBED_URL, QJSON_EMBED_MODEL, QJSON_EMBED_DIM, QJSON_EMBED_TIMEOUT (default 6s)
  - IVF/FMM: QJSON_RETR_USE_FMM=1, QJSON_RETR_IVF_K=64, QJSON_RETR_IVF_NPROBE=4, QJSON_RETR_REINDEX_THRESHOLD
  - Scan caps: QJSON_RETR_SCAN_MAX (default 5000), QJSON_RETR_RECENT_LIMIT (default 2000)
  - Embedding mode: QJSON_EMBED_MODE=ollama|hash|transformers (transformers only if explicitly set)
  - Debug: QJSON_DEBUG_OLLAMA=1 to print a one‑liner before each Ollama call
- Web (optional):
  - LANGSEARCH_API_KEY (LangSearch for /crawl search mode)
  - QJSON_WEB_TOPK, QJSON_WEB_ACK
- QJSON_WEBOPEN_TIMEOUT, QJSON_WEBOPEN_MAX_BYTES, QJSON_WEBOPEN_CAP
- QJSON_WEBOPEN_DEFAULT (text|raw; default text)
  - QJSON_CRAWL_RATE (req/s per host)
  - Local fallback for /find: QJSON_LOCAL_SEARCH_ROOTS, QJSON_LOCAL_SEARCH_SKIP_DIRS, QJSON_LOCAL_SEARCH_MAX_FILES

Retrieval + IVF quick notes
- Build IVF index once for an agent: `qjson-agents reindex --id <AGENT> --k 64 --iters 3`.
- In chat, use `/retrieve once <QUERY>` or `/force_retrieve <QUERY>` to force injection on the next turn.
- Tune IVF in chat: `/retrieval ivf=on ivf_k=64 nprobe=6`.
