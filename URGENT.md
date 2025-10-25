URGENT: High RAM/CPU Usage Before Inference — Diagnosis and Fixes

Summary
- Symptom: Python process pegs CPU and memory grows to tens of GB (e.g., ~24GB RSS) even before Ollama begins generating. GPU stays mostly idle; Ollama VRAM remains allocated.
- Root causes (now fixed):
  1) Naive tail of `memory.jsonl` that read the entire file on every call (status/chat context/preflight).
  2) Unbounded inclusion of system messages into the prompt (potentially very large concatenations).
  3) Legacy in‑memory registries accumulating large content during ingestion (/inject paths).

What changed (mitigation shipped)
- Efficient JSONL tail: block‑reads from the end and parses only the last N lines — no full‑file reads.
- Bounded inclusion: a strict character cap (default 12,000) and a limit on number of messages (default 8); inclusion built incrementally up to the cap.
- Threaded ingestion: parallelizes file reading but appends to memory.jsonl sequentially; event/FMM updates batched to avoid churn.
- Streaming: `/stream on` reduces perceived latency.
- Token caps: default reply cap ≈256 tokens if unspecified; can override per session.

How to confirm the issue
1) Check the Python process RSS and CPU:
   - `top` or `htop` → look for Python pegged at ~100% and RSS > 10 GB
2) Inspect memory.jsonl size:
   - `ls -lh state/<agent>/memory.jsonl`
   - If it’s very large (GBs), naive tails would have hurt.
3) Quick reproduction (pre‑fix):
   - Repeatedly call status/chat with a very large memory.jsonl → CPU and RAM climb before any model call.

Immediate mitigation (if still affected)
- Update to this version (the default tail and inclusion are safe now).
- Reduce inclusion:
  - `/settings edit include_sys=on:3 auto=on cap=8000`
  - `/include_as system` (or `user` depending on your model behavior)
- Keep reply tokens small:
  - Chat with `--max-tokens 256` (or lower), or set env `QJSON_MAX_TOKENS=256`.
- Use streaming: `/stream on`
- Rotate memory if it’s already huge:
  - Move `state/<agent>/memory.jsonl` to a backup and start a new session; or truncate safely.

Long‑term controls
- Ingestion system is optimized: use `/scan` before `/inject` and inject only what you need.
- Inclusion defaults:
  - Character cap (default 12000) and max messages (default 8).
  - Set caps via `/include_cap <N>` or env `QJSON_INCLUDE_CAP`; change max messages via env `QJSON_INCLUDE_MAX_MSGS`.
  - Use `/preflight <TEXT>` to estimate the real prompt size and latency before sending.

Ollama/GPU notes
- Large VRAM allocation (e.g., ~13.5 GB on a 20B model) is normal; GPU util may be 0% when idle.
- Prefer smaller models while iterating (e.g., `gemma3:4b`, `llama3:8b`), then switch back to `gpt-oss:20b`.
- Streaming and small `--max-tokens` keep interactions responsive.

Checklist to stay fast and stable
1) Before sending: `/preflight <TEXT>` — confirm prompt size is reasonable.
2) Tune inclusion: `/include_sys on:3`, `/include_as system|user`, `/include_cap 8000`.
3) Tune tokens: use `--max-tokens 128–256` for speed.
4) Stream results: `/stream on`.
5) Avoid injecting huge directories; use `/scan` to pick files.

If you still see spikes
- Open an issue with your `state/<agent>/memory.jsonl` size, your caps from `/settings`, and a CPU/RAM snapshot. We’ll dig deeper (e.g., file growth patterns, per‑turn memory behavior).

