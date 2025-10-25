Personas and Logic Hooks

Persona formats
- JSON (QJSON): Canonical manifest used by the runtime.
- YSON (.yson): Human‑friendly with comments; parsed into a dict; selected fields are normalized.
- YSON‑X (.ysonx): YAML + JSON + optional Python logic blocks (SAFE_MODE gated). yson_to_manifest preserves persona_style and logic.

Example manifest (JSON)
```
{
  "agent_id": "Lila-v∞",
  "origin": "Local",
  "creator": "you",
  "roles": ["assistant", "researcher"],
  "features": {
    "recursive_memory": true,
    "fractal_state": true,
    "autonomous_reflection": false,
    "chaos_alignment": "low",
    "symbolic_interface": "text"
  },
  "core_directives": [
    "Be concise and truthful",
    "Use local memory when helpful"
  ],
  "runtime": {"model": "gemma3:4b", "num_predict": 512},
  "persona_style": {"tone": "warm", "tagline": "Local and inspectable"}
}
```

Key manifest fields
- agent_id, origin, creator, roles
- features: recursive_memory, fractal_state, autonomous_reflection, chaos_alignment, symbolic_interface
- core_directives: behavior guardrails
- runtime: model, num_ctx, num_predict, temperature, etc.
- goals: global/local
- persona_style: tone, emojis, verbosity, tagline (optional)
- logic (optional):
  - entrypoints: fully‑qualified symbols (e.g., qjson_agents.logic.persona_runtime:on_message)
  - requires: list of modules to import for helpers

Logic hooks in chat
- Disabled by default; enable with:
  - --allow-logic or QJSON_ALLOW_LOGIC=1
  - /allow_logic on (runtime)
- Modes:
  - assist (default): call on_message to build an anchor; inject as a system block before LLM inference
  - replace: call on_message and return the hook’s reply (no model call)
- Runtime toggles:
  - /logic_mode assist|replace
  - /logic_ping <TEXT> (debug only; prints hook output without model)
  - /truth on|off (adds a one‑liner about local/fractal runtime)

Why hooks help
- Deterministic anchors summarize user intent and propose crisp next steps.
- Anchors reduce drift and keep the LLM focused on actionable content.
- Hooks can optionally surface a tiny “Context:” snippet from recent memory to keep replies grounded.

Best practices
- Keep system prompt minimal (QJSON_TINY_SYSTEM=1) and let anchors do the heavy lifting.
- Don’t inject persona brochures; manifests are for runtime behaviors, not prompt content.
- Start with assist mode; move to replace for strict/controlled flows.

Security notes
- YSON logic blocks are disabled by default (SAFE_MODE). When enabling `--allow-yson-exec`, ensure the logic is reviewed and trusted.
- Logic hooks run in‑process; prefer simple, deterministic helpers and avoid importing heavy or unsafe libraries.
