# YSON Full Format (QJSON-YSON)

YSON is a hybrid, AI‑first format that blends YAML/JSON structure with optional embedded Python logic and QJSON persona semantics. It’s designed for agent manifests and swarm orchestration files.

## Goals
- Human‑readable metadata headers for quick scanning
- Flexible body: JSON or YAML syntax (or a mix)
- Optional embedded Python logic blocks (introspection hooks)
- Interop with QJSON manifests and the cluster runtime

## File Structure

1) Meta headers (lines starting with `#@`)
- `#@format:` Human readable format id (e.g., `QJSON-YSON v1.0`)
- `#@type:` File type hint (e.g., `agent_manifest`, `swarm`)
- `#@version:` Version string
- `#@id:` Optional id hint
- `#@tags:` Optional tag list (Python list literal)

2) Body (YAML/JSON)
- May use JSON braces `{}` with unquoted keys (YAML style)
- Comments allowed via `#`
- Parsed as: JSON → YAML → JSON5‑like best‑effort preprocessor

3) Optional logic block
- A top‑level `logic:` section followed by Python functions
- Lines starting with `#@` inside logic are stripped
- Executed in an isolated namespace

## Supported YSON Profiles

### Persona YSON (agent_manifest)
Minimal example:

```
#@format: QJSON-YSON v1.0
#@type: agent_manifest
#@id: FractaLux
#@tags: [oracle, memory, summarizer]

identity:
  name: FractaLux
  creator: Yan Desbiens
  origin: Persona Library

logic:
  #@exec:py
  def introspect(memory):
      return {"ok": True, "n": len(memory)}
```

Loading via CLI:
- Use directly in chat/cluster with `--manifest personas/FractaLux.yson`
  - The loader maps id/tags → a QJSON manifest with defaults

### Swarm YSON
Describes a cluster of agents, their selection strategy, and swarm features.

Key: `swarm_architecture` with an `agents` array of agent names. Example: `yson/FractalSwarmMoE.yson`.

Run via CLI:
- `qjson-agents yson-run-swarm --yson yson/FractalSwarmMoE.yson --duration 60 --use-ollama --model gemma3:4b --topology moe --moe-topk 2`

## CLI
- `yson-validate --path file.yson [--json]` Inspect meta + top‑level keys
- `yson-validate --path file.yson --strict` Perform strict structural checks (basic schema)
- `yson-run-swarm --yson file.yson [...cluster flags...]` Convert YSON → synthesized manifests and run cluster
- `ysonx-convert --input <file|dir> [--output-dir <dir>]` Convert .json/.yson → .ysonx

### Goal Prompting
- Global goal: `--goal-prompt` or `--goal-file` (used to seed the first baton and logged as `input_goal`)
- Per‑agent subgoals: repeat `--agent-goal` (or `--agent-goal-file`) in cluster order; combined with the global goal to form each agent’s effective goal
- All goals are persisted to `state/<agent_id>/fmm.json` under `['goals','runs',<run_ts>]` for later querying

## Loader Semantics

`load_yson(path)` → `{ meta, body, logic, raw }`
- Parses `#@` meta
- Attempts JSON → YAML (if `PyYAML` is available) → JSON5‑like transform
- Extracts a Python `logic:` block if present

`yson_to_manifest(path)` → QJSON manifest
- Heuristics: id/name → `agent_id`; `#@tags` → roles; creator/origin derived from body or meta
- Default features: recursive_memory, fractal_state, autonomous_reflection, chaos_alignment=balanced

`yson_to_swarm(path)` → `{ meta, config, agents, logic, goals }`
- Extracts `swarm_architecture.agents` and the `goals` block (`global`, `template`, `agents[]`)
- Returns `logic` dict to allow custom `make_priming` if present

`synthesize_manifest_from_yson_name(name)` → QJSON manifest
- Roles inferred from name tokens, e.g., `Echo` → archivist; `Chaos`/`Rogue` → chaos amplifier; `Oracle` → summarizer

## Interop with QJSON
- Persona YSON files are normalized into QJSON manifests and used by all existing commands
- Swarm YSON files generate ephemeral QJSON manifests and feed into the cluster runtime

## Safety
- Embedded `logic:` is executed; limit its use to trusted files
- YSON swarm files express behavior intent but do not bypass runtime safety checks

## Examples

Persona (FractaLux): `personas/FractaLux.yson`
Swarm (FractalSwarmMoE): `yson/FractalSwarmMoE.yson`

## YSON‑X Extras
- `.ysonx` files may carry `logic.make_priming` to shape inter‑agent discourse.
- Built‑in priming templates: set `priming_template: debate|critique|qa` in the swarm.
- Strict mode warns if `goals.agents` length doesn’t match the agent list; at runtime, the system pads or truncates the list.

## Troubleshooting
- If a YSON body fails to parse:
  - Ensure keys are followed by `:` and strings are quoted if they include punctuation
  - Install `PyYAML` to improve non‑JSON parsing (`pip install pyyaml`) — optional
- Use `yson-validate` to verify meta and top‑level keys
