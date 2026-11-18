#!/usr/bin/env bash
# Kept for old instructions: the real launcher is scripts/run_server.py (used by .mcp.json).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${CLIPPER_PYTHON:-python3}" "$ROOT/scripts/run_server.py"
