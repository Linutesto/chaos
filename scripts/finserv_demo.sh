#!/usr/bin/env bash
set -euo pipefail

# Financial Services Demo: Policy & Compliance Assistant (local search)

AGENT_ID=${AGENT_ID:-FinServDemo}
DOCS_DIR=${DOCS_DIR:-./demo/finserv_docs}

echo "[demo] Using agent: $AGENT_ID"

qjson-agents exec "/engine mode=local" --id "$AGENT_ID" || true
export QJSON_SHOW_CONTEXT=1
export QJSON_WEBOPEN_DEFAULT=text

if [ -d "$DOCS_DIR" ]; then
  qjson-agents exec "/sharepoint_import $DOCS_DIR" --id "$AGENT_ID"
else
  echo "[demo] Docs directory not found: $DOCS_DIR (skipping import)"
fi

qjson-agents exec "/find policy exception mode=local" --id "$AGENT_ID"
qjson-agents exec "/open 1 text" --id "$AGENT_ID"

echo "[demo] Done. Try 'qjson-agents chat --id $AGENT_ID' and ask: What sections mention control X?"

