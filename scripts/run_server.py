"""Starts the clipper MCP server from the venv that scripts/setup.py created. macOS, Linux, Windows.

.mcp.json runs this with ${CLIPPER_PYTHON:-python3}: any Python 3 works, it hands off to the venv.
Stdlib only — it must run before the venv exists, just to print the setup hint.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = Path(os.environ.get("CLIPPER_HOME", Path.home() / ".live-clipper")).expanduser()
WINDOWS = os.name == "nt"
PY = HOME / "venv" / ("Scripts/python.exe" if WINDOWS else "bin/python")
SERVER = ROOT / "server" / "clipper_server.py"

if not PY.exists():
    sys.stderr.write(f"live-clipper is not set up yet. Run: python3 \"{ROOT / 'scripts' / 'setup.py'}\""
                     "  (Windows: py -3.12 ...)  or /live-clipper:clip-setup\n")
    sys.exit(1)

if Path(sys.executable).resolve() == PY.resolve():
    sys.path.insert(0, str(SERVER.parent))
    sys.argv = [str(SERVER)]
    import runpy
    runpy.run_path(str(SERVER), run_name="__main__")
elif WINDOWS:
    # execv on Windows spawns and returns, which breaks the MCP stdio pipe; run as a child instead.
    sys.exit(subprocess.call([str(PY), str(SERVER)]))
else:
    os.execv(str(PY), [str(PY), str(SERVER)])
