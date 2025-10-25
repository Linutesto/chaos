Schemas — Validating QJSON Agent Files

This folder contains JSON Schemas (Draft 2020‑12) for key data files:

- fmm.schema.json — fractal memory store (state/<id>/fmm.json)
- test_run.schema.json — single‑agent test harness JSON (logs/test_run_*.json)
- cluster_run.schema.json — cluster run JSON (logs/cluster_run_*.json)

Validate with Python (jsonschema)
```
pip install jsonschema
python - << 'PY'
import json
from jsonschema import validate

with open('docs/schemas/fmm.schema.json') as f: fmm_schema = json.load(f)
with open('state/YourAgent/fmm.json') as f: fmm = json.load(f)
validate(instance=fmm, schema=fmm_schema)
print('fmm.json OK')
PY
```

Validate with ajv-cli (Node)
```
npm i -g ajv-cli
ajv validate -s docs/schemas/cluster_run.schema.json -d logs/cluster_run_*.json
```

Notes
- Schemas are intentionally permissive (`additionalProperties: true`) in many places to avoid breakage as fields evolve.
- Event unions use `oneOf` with minimal required fields; your tools may include extra keys.
