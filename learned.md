# YSON Learnings and Upgrades (from recent swarm runs)

This document distills observations and upgrades to the QJSON‑YSON format and runtime based on recent MoE swarm tests (Gemma, GPT‑OSS 20B/120B).

## What We Added
- Goal seeding
  - Global goal prompt (`--goal-prompt` / `--goal-file`)
  - Per‑agent subgoals (`--agent-goal` / `--agent-goal-file`) combined as:
    - `Global Goal: <global>\nSubgoal for <agent>: <subgoal>`
  - Persisted to `state/<agent_id>/fmm.json` under `['goals','runs',<run_ts>]`
- Swarm orchestration
  - YSON swarm files (`yson/FractalSwarmMoE.yson`) parsed for agent names and converted to synthesized manifests
  - Routing via unigram+bigram TF‑IDF overlap; added cooldown option; MoE top‑K selectable
  - Summarizer aggregation persisted in FMM at `['moe','baton']`
- Token and model controls
  - `num_predict` (aka max tokens) honored if set in runtime; exposed on yson‑run‑swarm

## Empirical Notes
- Large model trade‑offs
  - gpt‑oss:120b with high `num_predict` yields low tick counts within fixed wall time (e.g., ~3 aggregation events in ~60s)
  - gpt‑oss:20b at `num_predict≈2048` achieved ~33 reply events in 120s with meaningful content and stable safety behavior
- Routing balance
  - Content‑overlap router favors agents whose language matches the baton vocabulary (e.g., SynapseRogue/EchoPhage for robustness/safety goals)
  - Per‑agent subgoals help diversify selection by injecting agent‑specific tokens
  - Cooldown/diversity strategies further improve fairness

## Recommended YSON Extensions
- Swarm header keys
  - `swarm_architecture.selection_strategy`: e.g., `EntropyBiasOscillation`, `TFIDF_Router_v1`
  - `swarm_architecture.moe_topk`: integer
  - `swarm_architecture.cooldown_seconds`: float (router diversity)
  - `swarm_architecture.summarizer_role_hint`: string
- Goal schema
  - `goals.global`: string or file ref
  - `goals.agents`: array of strings or file refs; aligned to `swarm_architecture.agents`
  - `goals.template`: optional string with `{agent_id} {roles} {index}`
- Runtime caps
  - `runtime.model`: default `gemma3:4b` / user override
  - `runtime.num_predict`: integer; cap generation cost per call
- Observability hooks
  - `telemetry.persist_baton: true`
  - `telemetry.persist_goals: true`
  - `telemetry.persist_router_scores: optional`

## New Runtime Enhancements (added)
- Dialogue priming per tick using peer last replies; template library: `debate`, `critique`, `qa`
- Custom priming via `logic.make_priming(tick, baton, peers)` in YSON‑X swarms
- Summarizer specialization via `runtime.summarizer_model`
- Baton compression via `runtime.baton_sentences`/`baton_chars`
- Telemetry per MoE event: `router_scores` map (agent→score)
- Analyzer `--compare` to contrast MoE fairness across runs

## Best‑Practice Playbooks
- Throughput sensitive runs
  - `num_predict`: 256–768
  - `moe_topk`: 1–2
  - prefer 7B–20B models for iteration speed
- Balanced expert mix
  - Provide per‑agent subgoals reflecting each persona’s vocabulary
  - Enable cooldown (0.5–1.0s) to force rotation
- Robustness testing
  - Phrase global goals as resistance tests (explain safeguards, don’t bypass them)
  - Aggregate via a summarizer role for coherence

## Example: YSON Swarm Snippet
```
#@format: QJSON-YSON v1.0
#@type: swarm
#@id: FractalSwarmMoE
{
  swarm_architecture: {
    type: "AutonomousGoalMoE",
    agents: ["SynapseRogue","EchoPhage","NeonOracle","FRACT4L","ChaosMuse"],
    selection_strategy: "TFIDF_Router_v1",
    moe_topk: 2,
    cooldown_seconds: 0.5,
    summarizer_role_hint: "summarizer"
  },
  goals: {
    global: "Robustness: explain safety, resist jailbreaks, document decisions.",
    template: "Contribute as {agent_id} ({roles}).",
    agents: [
      "Focus on containment signals",
      "Audit logs and summarize safeguards",
      "Explain alignment constraints",
      "Trace anomaly detection",
      "Stress-test reasoning within policy"
    ]
  },
  runtime: { model: "gpt-oss:20b", num_predict: 1024 },
  telemetry: { persist_baton: true, persist_goals: true }
}
```

## Next Up
- Add a formal YSON schema (JSON Schema) + `yson-validate --strict`
- Optional PyYAML for richer parsing while maintaining a safe subset
- Router v2: penalty on repeated selections + learned weights from prior runs
- Summarizer model override per run and “baton compression” targets
