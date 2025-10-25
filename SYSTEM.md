SYSTEM: Architecture and Runtime Overview

Start with docs/Architecture.md for a complete walkthrough of layers and flows.

Key pointers
- Agents: qjson_agents/agent.py
- CLI: qjson_agents/cli.py
- Personas & logic: qjson_agents/qjson_types.py, qjson_agents/yson.py, qjson_agents/logic/*
- State & memory: qjson_agents/memory.py, qjson_agents/fmm_store.py
- Orchestration: cluster‑test, analyze, menu

State model
- See docs/Memory_and_Fractal.md for JSONL, fmm.json, and index.json details.

Safety and performance
- See docs/Security_Performance.md for SAFE_MODE, logic gates, batching, and caps.
