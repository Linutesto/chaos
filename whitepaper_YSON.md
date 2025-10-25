# QJSON–YSON Whitepaper: A Hybrid Format for Agentic Swarms

Author: Project Team (compiled by the QJSON Agents runtime)
Date: 2025-10-19

## Abstract
YSON blends human-friendly YAML/JSON with optional embedded Python logic and QJSON persona semantics. It supports single‑agent manifests and multi‑agent swarm orchestration. We report a set of design principles, runtime affordances, and empirical findings from mixture‑of‑experts (MoE) swarms using local models via Ollama.

## 1. Format Philosophy
- Human‑legible meta headers (lines starting with `#@`) for quick understanding
- Flexible body: JSON, YAML, or lenient JSON5‑like parsing without external deps
- Optional logic: `logic:` block executed in an isolated namespace for introspection hooks
- Interop: persona YSON → normalized QJSON manifest; swarm YSON → synthesized agent manifests

## 2. Personas and Swarms
- Persona YSON encodes identity (id, roles/tags, creator/origin) and optional logic hooks.
- Swarm YSON encodes `swarm_architecture` (agents, strategy, moe_topk, cooldown) and `goals`:
  - `goals.global`: a global baton seed
  - `goals.template`: per‑agent template
  - `goals.agents`: an ordered list mapping to `swarm_architecture.agents`

## 3. Runtime Architecture (Repo Overview)
- qjson_agents/agent.py: QJSON Agent core; system prompt assembly; chat and logging
- memory.py: state folder management; JSONL tailers; router weight persistence
- yson.py: YSON loader; manifest+swarm projection; strict validator
- cli.py: CLI subcommands (chat/test/cluster/analyze/personas/swap/evolve/introspect/yson‑validate/yson‑run‑swarm)
- fmm_store.py: persistent fractal memory store per agent
- ollama_client.py: minimal HTTP client for local inference

## 4. MoE Router and Aggregation
- Router v1: unigram+bigram TF‑IDF overlap between baton and per‑agent (roles+goals)
  - Penalties: recent selection; same as previous expert
  - Diversity: cooldown (seconds)
  - Persistent bias: router weights stored globally; under‑used agents get weight boosts for future runs
- Aggregation: Summarizer agent compresses expert replies into a baton (optionally with its own model); baton persisted to FMM.

## 5. Goals and Persistence
- Global and per‑agent goals are injected into prompts and logged as `input_goal` in run JSON
- Goals are persisted to `state/<agent_id>/fmm.json` under `['goals','runs',<run_ts>]`.

## 6. Empirical Findings
- Large models (e.g., gpt‑oss:120b) with high token budgets reduce tick counts; lighter models (e.g., 20B) offer better step coverage
- Per‑agent subgoals + cooldown produce more balanced expert selection
- Summarizer role strongly influences baton tone and vocabulary; using a different summarizer can shift routing distribution

## 7. Validation and Safety
- `yson-validate --strict` performs basic structural checks (agents array, optional runtime/goals typing)
- Robustness goals (resist jailbreak, explain safeguards) are recommended for testing safety behaviors; the runtime does not assist in bypassing controls

## 8. Next‑Gen Extensions
- Formal JSON Schema for persona and swarm YSON; `yson-validate --strict` to adopt it when available
- Router v2: learned weights + fairness constraints; richer tokenization and decay schedules
- Summarizer specialization: model and compression targets; baton length/entropy budgets
- Telemetry: router score dumps per tick; richer post‑hoc analyses and dashboards

## 9. Conclusion
YSON provides a practical bridge between readable specifications and executable agentic behavior. Coupled with a simple, local‑first runtime, it enables transparent experimentation with multi‑agent swarms, routing/aggregation strategies, and safe goal prompting.

