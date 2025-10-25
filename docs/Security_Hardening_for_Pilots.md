Security Hardening for Pilots (Short Guide)

Scope
This guide lists practical steps to harden qjson‑agents deployments for pilot phases in regulated or security‑conscious environments.

1) Environment isolation
- Use a dedicated virtualenv or container; pin Python version (3.10+).
- Restrict filesystem access of the runtime user to the intended workspace.
- Set `QJSON_AGENTS_HOME` to a dedicated state directory with proper permissions.

2) Network posture
- Default to local mode (`/engine mode=local`) when web access is not needed.
- If online search is required, prefer allow‑listed domains; set `QJSON_CRAWL_RATE` conservatively.
- Keep web fetch caps modest: `QJSON_WEBOPEN_TIMEOUT≈6–10s`, `QJSON_WEBOPEN_MAX_BYTES≤200KB`, `QJSON_WEBOPEN_CAP≈12k`.

3) Logic and execution safety
- Do not enable `--allow-yson-exec` unless logic code is reviewed and approved.
- Enable persona logic hooks (`--allow-logic`) only for vetted entrypoints; prefer assist mode over replace.
- Keep `QJSON_TINY_SYSTEM=1` to reduce prompt bloat and accidental leakage.

4) Retrieval and data minimization
- Start with retrieval off; enable gradually with small `QJSON_RETRIEVAL_TOPK` (3–6), `QJSON_RETRIEVAL_MINSCORE≥0.25`.
- Set `QJSON_RETRIEVAL_INGEST=1` and `QJSON_RETRIEVAL_INGEST_CAP≈2000` to limit what gets embedded initially.
- Use IVF/FMM for speed, but ensure state backups include fmm.json (index metadata).

5) Auditing & validation
- Turn on context summary (menu → Agent Management → toggle context summary) to see when web/retrieval content is used.
- Validate state and runs with the provided schemas (docs/schemas). Integrate `qjson-agents validate` into CI.
- Keep `logs/*.{json,txt,log}` under version control for pilot analysis where appropriate.

6) Models and PI/PHI
- Choose small local models for iteration; document where prompts/replies are stored.
- If prompts may contain PI/PHI, do not route to cloud models. Use Ollama locally.

7) Operational hygiene
- Backup `state/` and retrieval DB (`state/retrieval.sqlite3` or `~/.qjson/memory.sqlite3`).
- Rotate pilot personas and logs; do not reuse pilot state in production.
- Document operators, change windows, and rollback plans.

Appendix: Quick commands
```
# Local-only mode
qjson-agents exec "/engine mode=local"

# Validate fmm.json and run logs
qjson-agents validate --file state/<AGENT>/fmm.json --schema fmm
qjson-agents validate --dir logs --glob "*.json" --schema auto
```
