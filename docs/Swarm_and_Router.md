Swarm, Router, and Fairness

Topologies
- ring: Pass a baton deterministically agent→agent.
- mesh: Broadcast baton to all; aggregate last reply.
- moe (mixture of experts): Score agents as experts each tick; top‑K reply; summarizer aggregates.

Router scoring (moe)
- Tokenization: lower‑cased alphanumerics; build unigrams and bigrams for baton and agent documents (roles + goals).
- TF‑IDF overlap: sum tf[token] * idf[token] over tokens shared between baton and agent doc.
- Cooldown penalty: avoid selecting the same agent repeatedly; hard cooldown and mild recency penalty.
- Persistent weights: router_weights.json nudges under‑used agents upward across runs.

Scoring formula (illustrative)
```
score(agent) = Σ_{t∈baton∩agent} tf_agent[t] * idf[t]
               - I(selected_recently) * cooldown_penalty
               + router_bias[agent]
               - I(agent == previous) * same_prev_penalty
               - recency_penalty / Δt_since_selected
```

Aggregation
- Experts reply; summarizer agent compresses to a baton (optionally with constraints from swarm config: sentence/char caps).
- All prompts/replies and router scores are logged.

Fairness metrics (analyze)
- Non‑empty ratio, total tokens, tokens/sec, per‑agent TPS
- MoE distribution across experts (current vs baseline)
- Imbalance stats (std, coefficient of variation, max‑min)

Outputs
- JSON run file (counts, events with prompts/replies router scores)
- TXT human log with transcript
- LOG debug trace

Run JSON (snippets)
```
{
  "agents": ["A","B","C"],
  "model": "gemma3:4b",
  "ticks": 12,
  "counts": {"A": {"chat": 4}, "B": {"chat": 5}, "C": {"chat": 3}},
  "events": [
    {"t": 1730001000.1, "type": "moe", "expert": "B", "router_scores": {"A": 0.3, "B": 0.9, "C": 0.2}},
    {"t": 1730001001.2, "type": "aggregate", "summarizer": "A", "reply": "Baton ..."}
  ]
}
```
