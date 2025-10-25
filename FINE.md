FINE: File Ingestion, Normalization, and Estimation

This note summarizes new ingestion features and preflight estimation.

Ingestion (chat commands)
- /scan <path>: recursively list allowed files (.json, .yson, .ysonx, .txt, .md, .py)
- /inject <path>: recursively ingest .json/.yson/.ysonx/.txt/.md as system messages
- /inject_py <path>: recursively ingest .py as system messages (source=inject_py)
- /inject_mem <path>: ingest exact files verbatim as system messages

Normalization
- Paths are normalized (expanding ~ and env vars, removing quotes, collapsing whitespace around slashes)
- Logs events and persists to FMM

Inclusion
- /include_sys [on|off|N|auto] and /include_as [system|user]
- /include_cap N to cap included content (default 12000 chars)
- /show_sys [N] preview which system entries will be included

Preflight estimation
- /preflight <TEXT> estimates:
  - prompt_chars, prompt_tokens (~chars/4), pred_tokens (num_predict)
  - gen_tps/enc_tps heuristic from model name
  - latency ≈ prompt_tokens/enc_tps + pred_tokens/gen_tps + 0.5s

Streaming
- /stream [on|off] toggles streaming partial output; falls back to non-streaming

