#!/usr/bin/env bash
# Publish the current data for the hosted app: pack it, then replace the `deploy-data`
# branch with a single commit holding the archive. Redeploy on Render afterwards
# (Manual Deploy, or its deploy hook) so the image picks it up.
#   bash scripts/publish_data.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY=backend/.venv/Scripts/python
[ -x "$PY" ] || PY=backend/.venv/bin/python
"$PY" scripts/pack_data.py

work=$(mktemp -d)
trap 'git worktree remove --force "$work" >/dev/null 2>&1 || true; git branch -D deploy-data-tmp >/dev/null 2>&1 || true' EXIT
git worktree add -q --orphan -b deploy-data-tmp "$work"
cp deploy/pitwall-data.tar.gz "$work/"
git fetch -q origin deploy-data 2>/dev/null && git show origin/deploy-data:README.md > "$work/README.md" || true
git -C "$work" add -A
git -C "$work" commit -q -m "Data snapshot $(date +%Y-%m-%d)"
git -C "$work" push -q -f origin deploy-data-tmp:deploy-data
echo "Published. Now redeploy the Render service."
