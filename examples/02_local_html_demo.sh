#!/usr/bin/env bash
set -euo pipefail

# Example: Use find + open interactively

AGENT_ID=${AGENT_ID:-WebDemo}

echo "Launch chat, then type:\n  /find \"your topic\"\n  /open 1\n  Summarize the page."
qjson-agents chat --id "$AGENT_ID"
