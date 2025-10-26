Plugin Tests — Running and Validating Plugins

Overview
This repo includes built‑in plugins and a test suite that exercises them both via the CLI and via direct plugin calls where stateful behavior is required (e.g., SQLite connection persistence).

What’s covered
- Filesystem: list/read/write (writes gated, rooted paths)
- Python exec: gated by QJSON_ALLOW_EXEC
- Git (read‑only): status/log/diff
- Generic API: gating behavior (no network by default)
- SQLite DB: open/query/tables with in‑process plugin instance
- Advanced plugins: Swarm‑Forge, Cognitive‑Prism, Meme‑Weaver, Holistic‑Scribe, Continuum

Run smoke tests (no pytest required)
```bash
python tools/smoke_test_plugins.py                 # basic plugins
python tools/smoke_test_advanced_plugins.py        # advanced plugins, venv auto‑created
```

Run with pytest (optional)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e . pytest
pytest -q tests/test_new_plugins.py tests/test_advanced_plugins.py
```

Environment gates (safety)
- Filesystem writes: `QJSON_FS_WRITE=1` and restrict to roots via `QJSON_FS_ROOTS` (os.pathsep‑separated)
- Code execution: `QJSON_ALLOW_EXEC=1` (timeout via `QJSON_EXEC_TIMEOUT`)
- Generic API: `QJSON_ALLOW_NET=1` (response previews capped)
- Git root: `QJSON_GIT_ROOT` (defaults to CWD)
- SQLite: in CLI `exec`, `/sql_open` does not persist across processes; tests exercise an in‑process plugin instance instead

Notes
- The exec‑based tests intentionally keep commands small and stateless where possible.
- For network‑restricted environments, the API tests validate gating rather than external calls.

