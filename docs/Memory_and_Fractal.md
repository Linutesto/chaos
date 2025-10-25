Fractal QFP Core and Persistence

Overview
- The Fractal QFP Core in this runtime is a pragmatic combination of:
  1) Append‑only conversational memory (JSONL)
  2) Operational events (JSONL)
  3) A hierarchical “fractal” memory tree (JSON)
  4) A compact cluster index (JSON)

Files under state/<agent_id>/
- manifest.json — normalized manifest snapshot used by the agent
- memory.jsonl — append‑only conversation and system messages (role, content, meta)
- events.jsonl — operational events (fork, ingest, swap, loop, moe handoffs, etc.)
- fmm.json — Persistent fractal memory tree (topic‑path nodes with __data__ lists)
- evolutions/ — optional persona snapshots from self‑mutation

Retrieval store (optional)
- Separate from JSONL/FMM, a lightweight vector store persists under a single SQLite file (default `state/retrieval.sqlite3` if `QJSON_AGENTS_HOME` is set, else `~/.qjson/memory.sqlite3`).
- Embeddings via Ollama (fast‑fail with short timeouts); fallback to deterministic hash by default. Enable sentence‑transformers only via `QJSON_EMBED_MODE=transformers`.
- Used to inject a compact “Retrieved long‑term memory” block into the system context per turn when enabled.
- Hybrid search combines cosine similarity with optional TF-IDF re-ranking and a freshness boost.

IVF index in the fractal store (FAISS‑like)
- For acceleration without extra dependencies, an inverted file (IVF) index is persisted per agent under `state/<id>/fmm.json` at `retrieval.ivf.dim{D}.K{K}`.
- Build/update explicitly via CLI: `qjson-agents reindex --id <AGENT> --k 64 --iters 3`.
- The index is automatically updated when new memories are added.
- Tunables (env): `QJSON_RETR_IVF_K`, `QJSON_RETR_IVF_NPROBE`, `QJSON_RETR_USE_FMM=1`.

JSONL memory and events
- Simple one‑line JSON objects; efficient tails read from the end by blocks.
- Incremental index counters are bumped on each append (O(1)) to keep state/index.json current.

Examples
memory.jsonl
```
{"ts": 1730000000.123, "role": "user", "content": "Summarize this page", "meta": {"model": "gemma3:4b"}}
{"ts": 1730000001.456, "role": "assistant", "content": "Here is a concise summary...", "meta": {"model": "gemma3:4b", "options": {"num_predict": 256}}}
{"ts": 1730000002.789, "role": "system", "content": "[web-open] Title\n\n...outline text...", "meta": {"source": "open_ingest", "url": "https://example.com"}}
```

events.jsonl
```
{"ts": 1730000100.111, "type": "fork", "meta": {"child_id": "Agent-child1"}}
{"ts": 1730000112.222, "type": "websearch_inject", "meta": {"results": 5}}
{"ts": 1730000123.333, "type": "webopen_inject", "meta": {"chars": 12000}}
```

Fractal memory store (fmm.json)
- Path structure: fmm.insert(["chat", role, topic], data) creates nested nodes and appends under __data__.
- Batched persistence: Inserts mark the store dirty; writes flush every N inserts or after a small timeout.
- Shared instance: Per‑agent in‑process cache avoids reloading on every write.

Example (excerpt)
```
{
  "chat": {
    "assistant": {
      "summaries": {
        "__data__": [
          {"ts": 1730000001.456, "text": "concise summary", "topic": "web-open"}
        ]
      }
    }
  },
  "retrieval": {
    "ivf": {
      "dim768": {
        "K64": {"nprobe": 4, "centroids": "..."}
      }
    }
  }
}
```

Retrieval DB (SQLite) — schema (simplified)
```
vectors(id INTEGER PRIMARY KEY, agent_id TEXT, ts REAL, text TEXT, meta TEXT, vec BLOB)
```

Cluster index (state/index.json)
- Global map of agent id → parent, manifest path, and counters.
- Debounced writes limit churn; refresh is available on demand via CLI.

Fractal envelopes (QJSON‑FE‑v1)
- For manifests you want to ship privately: qjson_agents/fractal_codec.py implements a simple envelope:
  - PBKDF2‑HMAC(SHA‑256) key derivation from passphrase + random salt
  - Per‑block XOR stream keystream via HMAC counter mode
  - HMAC over ciphertext blocks for integrity
  - depth/fanout chunking splits plaintext before encrypting for a “fractal” layout
- Encode/decode via CLI (encode-manifest / decode-manifest). Intended for research/obfuscation, not strong cryptography.

Why a fractal store?
- Flat JSONL is perfect for chronological auditability; hierarchical accumulation unlocks retrieval by theme/topic and supports structured analytics (e.g., Moe baton summaries, per‑role chat stats).
- Combined, they capture both temporal reality (what happened) and semantic aggregation (why it matters) — essential for self‑refinement.
