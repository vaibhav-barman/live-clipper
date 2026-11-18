#!/usr/bin/env bash
# Starts the clipper MCP server from the venv that scripts/setup.sh created.
HOME_DIR="${CLIPPER_HOME:-$HOME/.live-clipper}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$HOME_DIR/venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "live-clipper is not set up yet. Run: bash \"$ROOT/scripts/setup.sh\"  (or /live-clipper:clip-setup)" >&2
  exit 1
fi
exec "$PY" "$ROOT/server/clipper_server.py"
