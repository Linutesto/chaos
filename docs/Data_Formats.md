Data Formats — fmm.json and Run JSON

This document describes the on‑disk JSON structures used by qjson-agents for persistent state and logged runs. The aim is to make them easy to inspect, transform, or load into external tools.

Schemas
- See `docs/schemas/` for JSON Schemas you can use to validate these files programmatically:
  - `docs/schemas/fmm.schema.json`
  - `docs/schemas/test_run.schema.json`
  - `docs/schemas/cluster_run.schema.json`

1) Fractal Memory Store — fmm.json
Overview
- One JSON file per agent at `state/<agent_id>/fmm.json`.
- A hierarchical tree (fractal) of topic paths. Every node is a JSON object; payloads are appended to a special `__data__` array at any level.
- Used for: structured notes (goals/runs/moe/baton), retrieval metadata (IVF index), and any ad‑hoc topics your tools write.

Node structure
```
Node := { <string>: Node, ..., "__data__"?: [Datum, ...] }

Datum := {
  "ts": <float seconds>,
  "text"?: <string>,
  "topic"?: <string>,
  "meta"?: <object>,
  ...  // tool-specific fields are allowed
}
```

Common top‑level topics (illustrative; your tools may write others)
- chat/…: persisted summaries, metrics, etc.
- goals/…: high‑level or per‑agent goals
- runs/<run_ts>: run metadata (e.g., from cluster/test harness)
- moe/baton: aggregated baton text across ticks
- retrieval/ivf: FAISS‑like IVF index metadata (see below)

IVF index metadata (FAISS‑like, persisted under fmm.json)
```
retrieval: {
  "ivf": {
    "dim<INT>": {
      "K<INT>": {
        "nprobe": <int>,
        "centroids": <string or array>,
        // additional tool-specific fields
      }
    }
  }
}
```

Example excerpt
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
  "moe": {
    "baton": {
      "__data__": [
        {"ts": 1730002000.0, "text": "Cluster consensus baton at tick 12"}
      ]
    }
  },
  "retrieval": {
    "ivf": {"dim768": {"K64": {"nprobe": 4, "centroids": "..."}}}
  }
}
```

2) Run JSON — logs/test_run_*.json and logs/cluster_run_*.json
There are two primary run logs: a single‑agent test harness output and multi‑agent cluster outputs.

Single agent — test_run_*.json (schema)
```
{
  "agent_id": <string>,
  "start_ts": <float>,
  "end_ts": <float>,
  "elapsed_sec": <float>,
  "counts": {"chat": <int>, "fork": <int>, "status": <int>, "errors": <int>},
  "events": [
    {"t": <float>, "type": "chat", "prompt": <string>, "reply": <string>},
    {"t": <float>, "type": "status", "tail_mem": <int>, "tail_ev": <int>},
    {"t": <float>, "type": "fork", "child_id": <string>},
    {"t": <float>, "type": "error", "error": <string>}
  ],
  "logs": {"txt": <path>, "json": <path>, "log": <path>}
}
```

Cluster — cluster_run_*.json (schema)
```
{
  "agents": [<agent_id>, ...],
  "model": <string>,
  "use_ollama": <bool>,
  "ticks": <int>,
  "elapsed_sec": <float>,
  "counts": {
    <agent_id>: {"chat": <int>, "errors": <int>},
    ...
  },
  "events": [ Event, ... ]
}

Event :=
  {"t": <float>, "type": "handoff", "from": <agent>, "to": <agent>, "prompt": <string>, "reply": <string>, "tick": <int>} |
  {"t": <float>, "type": "broadcast", "from": <agent>, "to": <agent>, "prompt": <string>, "reply": <string>, "tick": <int>} |
  {"t": <float>, "type": "moe", "expert": <agent>, "prompt": <string>, "reply": <string>, "tick": <int>, "router_scores": {<agent>: <float>, ...}} |
  {"t": <float>, "type": "aggregate", "summarizer": <agent>, "prompt": <string>, "reply": <string>, "tick": <int>} |
  {"t": <float>, "type": "input_goal", "text": <string> } |
  {"t": <float>, "type": "error", "agent": <agent>, "error": <string> }
```

Notes
- Time values are UNIX epoch floats (seconds).
- String fields use UTF‑8 and may include newlines.
- Event shapes are intentionally simple for easy ingestion into log analyzers.

Example (cluster excerpt)
```
{
  "agents": ["A","B","C"],
  "model": "gemma3:4b",
  "ticks": 12,
  "counts": {"A": {"chat": 4}, "B": {"chat": 5}, "C": {"chat": 3}},
  "events": [
    {"t": 1730001000.1, "type": "moe", "expert": "B", "router_scores": {"A": 0.3, "B": 0.9, "C": 0.2}, "prompt": "...", "reply": "...", "tick": 7},
    {"t": 1730001001.2, "type": "aggregate", "summarizer": "A", "reply": "Baton ...", "prompt": "...", "tick": 7}
  ]
}
```

3) Related files (for reference)
- state/<agent_id>/manifest.json — canonical persona snapshot used by the agent.
- state/<agent_id>/memory.jsonl — append‑only conversation and system messages.
- state/<agent_id>/events.jsonl — operational events (see examples above).
- state/index.json — global cluster index with parent mapping and counters (lines per agent).

This documentation reflects the current structures used by qjson-agents. Fields may evolve conservatively; parsers should be tolerant of additional keys.
