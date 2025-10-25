Roadmap

Near-term (P0/P1)
- CI: expand validation matrix (Python 3.10–3.12), add smoke run.
- Ingest connectors: harden Confluence/SharePoint import (edge cases, encoding).
- Retrieval: configurable IVF defaults, better recent-vs-relevant balancing.
- UX: richer `/find` snippets and `/open` preview with section titles.

Mid-term (P2)
- Embeddings: pluggable backends (transformers opt-in, batching + caching).
- Dedup & canonicalization: stronger URL/file canonical forms and SHA1 scopes.
- Cluster orchestration: fairness metrics, ring/mesh/MoE knobs in CLI.
- Schema tooling: stricter schemas for run logs + helpful error messages.

Exploratory
- Persona logic packs: reusable utilities for common agent policies.
- Local web UI: minimal panel for browse/search/inject/inspect.
- Importers: Jira/export JSON, Notion markdown, generic file tree.

How to contribute
- See docs/Developer_Guide.md for coding/testing guidelines.
- Keep changes focused and add/extend tests when touching core logic.

