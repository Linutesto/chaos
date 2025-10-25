#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   scripts/push_to_github.sh <remote_url> [branch]
# Example:
#   scripts/push_to_github.sh git@github.com:youruser/qjson_agents.git main

REMOTE_URL=${1:-}
BRANCH=${2:-main}

if [ -z "$REMOTE_URL" ]; then
  echo "Usage: $0 <remote_url> [branch]" >&2
  exit 2
fi

# Ensure .gitignore exists to avoid pushing state/logs/venv
if [ ! -f .gitignore ]; then
  cat > .gitignore <<'IGN'
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.venv/
venv/
build/
dist/
*.egg-info/
state/
logs/
out/
tmp/
tmp_*/
.DS_Store
.idea/
.vscode/
qjson_agents/venv/
IGN
fi

if [ ! -d .git ]; then
  git init
fi

git checkout -B "$BRANCH"
git add .
git commit -m "Initial commit: code and docs only" || true

if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE_URL"
else
  git remote add origin "$REMOTE_URL"
fi

git push -u origin "$BRANCH"

