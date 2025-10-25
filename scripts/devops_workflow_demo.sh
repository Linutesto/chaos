#!/usr/bin/env bash
set -euo pipefail

# DevOps workflow demo: git → fs → exec → (optional) api

DEMO_DIR=${DEMO_DIR:-"./tmp/devops_repo_$(date +%s)"}
AGENT_ID=${AGENT_ID:-DevOpsAgent}

echo "[demo] creating demo repo at $DEMO_DIR"
mkdir -p "$DEMO_DIR"
git init "$DEMO_DIR" >/dev/null
(
  cd "$DEMO_DIR"
  git config user.email "demo@example.com"
  git config user.name "DevOps Demo"
  echo 'print("hello from test")' > test.py
  git add test.py
  git commit -m "add test.py" >/dev/null
  echo -e '#!/usr/bin/env python3
print("result: 2+2=", 2+2)' > new_test.py
  chmod +x new_test.py
)

export QJSON_GIT_ROOT="$(realpath "$DEMO_DIR")"
export QJSON_FS_ROOTS="$QJSON_GIT_ROOT"

echo "[demo] git diff for new_test.py"
python -m qjson_agents.cli exec "/git_diff new_test.py" --id "$AGENT_ID"

echo "[demo] reading new_test.py"
python -m qjson_agents.cli exec "/fs_read $DEMO_DIR/new_test.py max_bytes=1024" --id "$AGENT_ID"

echo "[demo] executing new_test.py via /py (QJSON_ALLOW_EXEC=1)"
QJSON_ALLOW_EXEC=1 python -m qjson_agents.cli exec "/py @$DEMO_DIR/new_test.py" --id "$AGENT_ID"

if [ "${QJSON_ALLOW_NET:-0}" = "1" ]; then
  echo "[demo] posting results via /api_post (mock URL)"
  QJSON_ALLOW_NET=1 python -m qjson_agents.cli exec "/api_post https://httpbin.org/post body='{"msg":"devops demo complete"}' ct=application/json timeout=6" --id "$AGENT_ID" || true
else
  echo "[demo] skipping /api_post (set QJSON_ALLOW_NET=1 to enable)"
fi

echo "[demo] done"

