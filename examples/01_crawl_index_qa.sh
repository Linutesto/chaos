#!/usr/bin/env bash
set -euo pipefail

# Example: Crawl, index, and ask a question

AGENT_ID=${AGENT_ID:-WebDemo}

# 1) Install (one-time)
# python -m venv .venv && source .venv/bin/activate && pip install -e .

# 2) Initialize an agent (one-time)
qjson-agents init --manifest manifests/lila.json --model llama3.1 || true

# 3) Crawl & index non-interactively
qjson-agents crawl --seeds https://example.com --depth 1 --pages 5 --id "$AGENT_ID"

# 4) Enable retrieval and ask a question
QJSON_RETRIEVAL=1 QJSON_RETRIEVAL_TOPK=6 qjson-agents chat --id "$AGENT_ID" -c "Extract a dated timeline from the most recent crawl."

