"""Where everything lives. The plugin folder is read-only code; all data goes under CLIPPER_HOME."""
import os
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SKILLS = PLUGIN_ROOT / "skills"
HOME = Path(os.environ.get("CLIPPER_HOME", Path.home() / ".live-clipper")).expanduser()
DB_PATH = HOME / "ledger.sqlite"
JOBS = HOME / "jobs"
CREDS = HOME / "credentials"
LOGS = HOME / "logs"
SFX_DIR = Path(os.environ.get("CLIPPER_SFX_DIR", HOME / "sfx")).expanduser()
ACCOUNTS = HOME / "accounts.json"

SCRIPTS = {
    "build_wx2": SKILLS / "shortform-cutaway/scripts/build_wx2.py",
    "edge_sweep": SKILLS / "shortform-cutaway/scripts/edge_sweep.py",
    "envtools": SKILLS / "shortform-cutaway/scripts/envtools.py",
    "probe": SKILLS / "shortform-cutaway/scripts/probe.py",
    "isowords": SKILLS / "shortform-cutaway/scripts/isowords.py",
    "listen_back": SKILLS / "shortform-cutaway/scripts/listen_back.py",
    "whisperx_align": SKILLS / "shortform-cutaway/scripts/whisperx_align.py",
    "motion_score": SKILLS / "shortform-cutaway/scripts/motion_score.py",
    "measure_take": SKILLS / "take-geometry/scripts/measure_take.py",
    "review_reel": SKILLS / "reel-review/scripts/review_reel.py",
    "sfx_catalog": SKILLS / "sfx-design/scripts/sfx_catalog.py",
    "reverb_throw": SKILLS / "shortform-finish/scripts/reverb_throw.sh",
}


def ensure():
    for d in (HOME, JOBS, CREDS, LOGS):
        d.mkdir(parents=True, exist_ok=True)


def job_dir(job_id):
    d = JOBS / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def clip_dir(job_id, clip_id):
    d = JOBS / job_id / "clips" / clip_id
    d.mkdir(parents=True, exist_ok=True)
    return d
