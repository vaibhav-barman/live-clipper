"""One-time setup: venv + dependencies in ~/.live-clipper (override with CLIPPER_HOME).
Works on macOS, Linux and Windows. Run it with any Python 3; it finds a 3.10-3.12 for the venv.

    python3 scripts/setup.py           full install (WhisperX + Demucs, ~3-4 GB with torch)
    python3 scripts/setup.py --lite    no speech models (you can scout, but cut/captions need full)
    Windows:  py scripts\\setup.py     (same flags)
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = Path(os.environ.get("CLIPPER_HOME", Path.home() / ".live-clipper")).expanduser()
WINDOWS = os.name == "nt"
LITE = "--lite" in sys.argv[1:]
VENV_PY = HOME / "venv" / ("Scripts/python.exe" if WINDOWS else "bin/python")
OK_VERSIONS = ("3.12", "3.11", "3.10")        # WhisperX does not support 3.13 yet

INSTALL_HINTS = {
    "python": {"darwin": "brew install python@3.12", "linux": "sudo apt install python3.12-venv",
               "win32": "winget install Python.Python.3.12"},
    "ffmpeg": {"darwin": "brew install ffmpeg", "linux": "sudo apt install ffmpeg",
               "win32": "winget install Gyan.FFmpeg   (then open a new terminal)"},
}


def hint(tool):
    plat = "win32" if WINDOWS else ("darwin" if sys.platform == "darwin" else "linux")
    return INSTALL_HINTS[tool][plat]


def version_of(cmd):
    try:
        out = subprocess.run(cmd + ["-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                             capture_output=True, text=True, timeout=20)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def find_python():
    if "%d.%d" % sys.version_info[:2] in OK_VERSIONS:
        return [sys.executable]
    candidates = ([["py", f"-{v}"] for v in OK_VERSIONS] if WINDOWS else []) + \
                 [[f"python{v}"] for v in OK_VERSIONS] + [["python3"], ["python"]]
    for c in candidates:
        if (WINDOWS or shutil.which(c[0])) and version_of(c) in OK_VERSIONS:
            return c
    return None


def main():
    py = find_python()
    if not py:
        sys.exit(f"Need Python 3.10-3.12 (WhisperX does not support 3.13 yet).  {hint('python')}")
    for b in ("ffmpeg", "ffprobe"):
        if not shutil.which(b):
            sys.exit(f"Need {b}.  {hint('ffmpeg')}")

    for sub in ("credentials", "sfx", "logs", "jobs"):
        (HOME / sub).mkdir(parents=True, exist_ok=True)
    if not WINDOWS:
        os.chmod(HOME / "credentials", 0o700)

    print(f"-> venv at {HOME / 'venv'} using {' '.join(py)}")
    subprocess.run(py + ["-m", "venv", str(HOME / "venv")], check=True)
    pip = [str(VENV_PY), "-m", "pip", "install", "-q"]
    subprocess.run(pip + ["-U", "pip", "wheel"], check=True)
    subprocess.run(pip + ["-r", str(ROOT / "server" / "requirements.txt")], check=True)
    if not LITE:
        print("-> installing WhisperX + Demucs (large download: torch)")
        subprocess.run(pip + ["-r", str(ROOT / "server" / "requirements-speech.txt")], check=True)

    accounts = HOME / "accounts.json"
    if not accounts.exists():
        shutil.copy(ROOT / "templates" / "accounts.example.json", accounts)
        print(f"-> wrote {accounts} (edit it before publishing)")

    if WINDOWS:
        # .mcp.json launches ${CLIPPER_PYTHON:-python3}; on Windows "python3" is often the Store
        # stub, so point it at the venv for good. New terminals / Claude Code pick it up.
        subprocess.run(["setx", "CLIPPER_PYTHON", str(VENV_PY)], capture_output=True)
        print(f"-> set CLIPPER_PYTHON={VENV_PY} (user environment)")

    print("-> checking")
    check = ("import sys; sys.path.insert(0, %r)\n"
             "from clipper import media, db\n"
             "db.init()\n"
             "for k, v in media.tool_status().items(): print(f'   {k:15} {v}')\n") % str(ROOT / "server")
    subprocess.run([str(VENV_PY), "-c", check], check=True)

    print("\nDone. Restart Claude Code (fully quit it on Windows so it sees CLIPPER_PYTHON), "
          "then run /live-clipper:clip-vod <url>.")
    print(f"Optional: put licensed SFX in {HOME / 'sfx'} and run:")
    print(f"  \"{VENV_PY}\" \"{ROOT / 'skills/sfx-design/scripts/sfx_catalog.py'}\" \"{HOME / 'sfx'}\""
          f" > \"{HOME / 'sfx' / 'catalog.json'}\"")


if __name__ == "__main__":
    main()
