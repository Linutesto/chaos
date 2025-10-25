Enterprise Readiness Checklist (One‑Pager)

Core
- Local‑first runtime; no external DB required (SQLite + fractal store)
- Deterministic, append‑only logs (memory.jsonl, events.jsonl) and run artifacts
- SAFE defaults; explicit gates for YSON logic execution and persona logic hooks
- Reproducible runs; JSON Schemas for validation (docs/schemas)

Identity & Access
- [ ] SSO/OIDC/SAML (roadmap)
- [ ] Role‑based controls on commands (roadmap)
- [ ] Per‑agent state permissions (roadmap)

Audit & Compliance
- [x] Structured event logs (JSON + TXT human logs)
- [x] Validatable state and run outputs (schemas)
- [ ] Centralized log sink export (SIEM) (roadmap)
- [ ] Signed manifests / allow‑listed logic entrypoints (roadmap)

Security
- [x] SAFE_MODE off by default for YSON logic
- [x] Web caps: timeout, max bytes, injected char cap; no script execution
- [x] Retrieval caps and hybrid/offline modes
- [ ] Policy framework for connectors and allowed domains (roadmap)

Ops & Packaging
- [x] Pure Python; minimal deps; runs in venv/conda
- [x] One‑file state per agent + SQLite DB for retrieval
- [ ] Air‑gapped packaging & signed updates (roadmap)

Observability
- [x] Preflight estimator (/preflight)
- [x] Context visibility toggle ([context] … line)
- [ ] Built‑in dashboards for memory/fmm/run analysis (roadmap)

Supportability
- [x] CLI + TUI (menu) for operations
- [ ] LTS branches and SLAs (roadmap)
- [ ] Connector marketplace and version pinning (roadmap)

Go/No‑Go for Pilot
- [ ] Customer confirms local‑first requirement and data boundaries
- [ ] Selected models available via Ollama
- [ ] Pilot personas and success metrics defined (accuracy, latency, time saved)
