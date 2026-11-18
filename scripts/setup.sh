#!/usr/bin/env bash
# Kept for old instructions: the real setup is scripts/setup.py (macOS, Linux, Windows).
#   bash scripts/setup.sh [--lite]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$(command -v python3.12 || command -v python3.11 || command -v python3.10 || command -v python3 || command -v python)"
exec "$PY" "$ROOT/scripts/setup.py" "$@"
