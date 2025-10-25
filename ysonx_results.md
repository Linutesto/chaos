# Fairness Delta Report: Genesis (5 agents) vs FractalSwarmMoE

## Summary
- FractalSwarmMoE: tps=31.6, events=24
- Genesis (5 agents): tps=54.22, events=20

## MoE Distributions
### FractalSwarmMoE
```
{
  "SynapseRogue": 0.278,
  "EchoPhage": 0.222,
  "NeonOracle": 0.278,
  "FRACT4L": 0.222,
  "ChaosMuse": 0.0
}
```
### Genesis (5 agents)
```
{
  "agent_FractaLux": 0.267,
  "agent_NyxEcho": 0.2,
  "agent_NekoInferno": 0.267,
  "agent_ObserverX": 0.267,
  "agent_EchoMuse": 0.0
}
```

## Observations
- Debate priming and cooldown promote more equitable expert usage; distributions may differ by content and timing.
- Router scores per tick are available in JSON (router_scores) for deeper fairness diagnostics.
- Summarizer model and baton compression targets can shape baton succinctness, affecting routing vocabulary.