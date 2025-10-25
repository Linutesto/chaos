#!/usr/bin/env bash
set -euo pipefail

# Healthcare Demo: SOP Navigator (local search + outline injection)

AGENT_ID=${AGENT_ID:-HealthcareDemo}
DOCS_DIR=${DOCS_DIR:-./demo/healthcare_docs}

echo "[demo] Using agent: $AGENT_ID"

# Set defaults: local mode, show context summary, default /open mode text
qjson-agents exec "/engine mode=local" --id "$AGENT_ID" || true
export QJSON_SHOW_CONTEXT=1
export QJSON_WEBOPEN_DEFAULT=text

# Import docs (Confluence export or local folder with HTML/MD/TXT)
if [ -d "$DOCS_DIR" ]; then
  qjson-agents exec "/confluence_import $DOCS_DIR" --id "$AGENT_ID"
else
  echo "[demo] Docs directory not found: $DOCS_DIR (skipping import)"
fi

# Search and open
qjson-agents exec "/find anesthesia SOP mode=local" --id "$AGENT_ID"
qjson-agents exec "/open 1 text" --id "$AGENT_ID"

echo "[demo] Done. Try 'qjson-agents chat --id $AGENT_ID' and ask for a summary."

