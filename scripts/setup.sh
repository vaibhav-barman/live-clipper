#!/usr/bin/env bash
# One-time setup: venv + dependencies in ~/.live-clipper (override with CLIPPER_HOME).
#   bash scripts/setup.sh           full install (includes WhisperX + Demucs, ~3-4 GB with torch)
#   bash scripts/setup.sh --lite    no speech models (you can scout, but cut/captions need --full later)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOME_DIR="${CLIPPER_HOME:-$HOME/.live-clipper}"
MODE="${1:-full}"

PY=""
for c in python3.12 python3.11 python3.10; do
  if command -v "$c" >/dev/null 2>&1; then PY="$(command -v "$c")"; break; fi
done
if [ -z "$PY" ]; then
  echo "Need Python 3.10-3.12 (WhisperX does not support 3.13 yet)."
  echo "macOS: brew install python@3.12    Ubuntu: sudo apt install python3.12-venv"
  exit 1
fi
for b in ffmpeg ffprobe; do
  command -v "$b" >/dev/null 2>&1 || { echo "Need $b.  macOS: brew install ffmpeg   Ubuntu: sudo apt install ffmpeg"; exit 1; }
done

mkdir -p "$HOME_DIR"/{credentials,sfx,logs,jobs}
chmod 700 "$HOME_DIR/credentials"
echo "-> venv at $HOME_DIR/venv using $PY"
"$PY" -m venv "$HOME_DIR/venv"
PIP="$HOME_DIR/venv/bin/pip"
"$PIP" install -q -U pip wheel
"$PIP" install -q -r "$ROOT/server/requirements.txt"
if [ "$MODE" != "--lite" ]; then
  echo "-> installing WhisperX + Demucs (large download: torch)"
  "$PIP" install -q -r "$ROOT/server/requirements-speech.txt"
fi
if [ ! -f "$HOME_DIR/accounts.json" ]; then
  cp "$ROOT/templates/accounts.example.json" "$HOME_DIR/accounts.json"
  echo "-> wrote $HOME_DIR/accounts.json (edit it before publishing)"
fi
echo "-> checking"
"$HOME_DIR/venv/bin/python" - <<PY
import sys; sys.path.insert(0, "$ROOT/server")
from clipper import media, db
db.init()
for k, v in media.tool_status().items(): print(f"   {k:15} {v}")
PY
echo
echo "Done. Restart Claude Code so the clipper MCP server starts, then run /live-clipper:clip-vod <url>."
echo "Optional: put licensed SFX in $HOME_DIR/sfx and run:"
echo "  $HOME_DIR/venv/bin/python $ROOT/skills/sfx-design/scripts/sfx_catalog.py $HOME_DIR/sfx > $HOME_DIR/sfx/catalog.json"
