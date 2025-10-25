# YSON‑X State and Telemetry

This document explains where to find key state artifacts and how to query them when running YSON‑X swarms.

## Files and Folders
- logs/cluster_run_<ts>.json
  - Structured run log with events. Notable event types:
    - `input_goal`: starting global goal text
    - `moe`: expert calls; includes `router_scores` (agent→score) for that tick
    - `aggregate`: summarizer baton creation
- logs/cluster_run_<ts>.txt
  - Human‑readable transcript with priming text, prompts, replies, and baton summaries
- logs/yson_swarm/<ts>/*.json
  - Temporary synthesized manifests for each agent (from YSON/YSON‑X swarm)
- state/<agent_id>/fmm.json
  - Persistent fractal memory store for each agent
  - Where goals and batons are persisted:
    - `['goals','runs',<run_ts>]` → {global_goal, agent_goal, model, topology}
    - `['moe','baton']` → baton lineage (appended)
- state/router_weights.json
  - Persistent router bias weights (agent→float). Updated each run to boost under‑used experts.

## Goals and Priming
- Global goal can be set via swarm YSON (`goals.global`) or CLI (`--goal-prompt`/`--goal-file`).
- Per‑agent subgoals via swarm YSON (`goals.agents`) or CLI (`--agent-goal`). Runtime pads/truncates to match agent count.
- Priming per tick:
  - Built‑in templates: set `priming_template: debate|critique|qa` in swarm YSON
  - Custom: define `logic.make_priming(tick, baton, peers)` in YSON‑X swarm

## Summarizer and Baton Compression
- Aggregation model can differ from experts via `runtime.summarizer_model`.
- Baton compression targets:
  - `runtime.baton_sentences`: maximum sentences in baton
  - `runtime.baton_chars`: maximum character length of baton

## Fairness and Telemetry
- Per MoE event, `router_scores` shows the score each agent received before selection.
- Compare fairness across runs with analyzer:
  - `qjson-agents analyze --path logs/cluster_run_NEW.json --compare logs/cluster_run_BASE.json`

## Troubleshooting
- Use `yson-validate --strict` to detect structural issues in swarm YSON.
- If no agents detected in `.ysonx`, ensure `swarm_architecture` and `agents: [...]` are present (fallback parser can only parse simple lists).
- Install `PyYAML` to improve non‑JSON parsing when needed (optional).

