#!/usr/bin/env python3
"""reverb_throw.py — DRY audio that blooms into a wet Freeverb tail right as it cuts.
The signature audio move: the body stays clean; only the LAST moment gets thrown into reverb and
drags out into silence. Stack it with a riser / SFX at a cut point for depth.

Deps: sox + ffmpeg on PATH (ffmpeg's afir convolution is BROKEN in some builds, outputs silence).
  macOS: brew install sox    Ubuntu: sudo apt install sox    Windows: winget install ChrisBagwell.SoX
Usage: reverb_throw.py IN.wav OUT.wav [THROW_SEC=0.7] [REVERB=78] [TAIL_PAD=4] [WET=1.0]
  IN        = an already-trimmed audio clip (the cut you want to end on)
  THROW_SEC = how much of the ENDING gets sent to reverb (0.7 = just the last beat/chord)
  REVERB    = sox reverberance 0-100 (tail length/lushness; 78 = ~2-3s hall)
  TAIL_PAD  = seconds of silence appended so the tail has room to ring
  WET       = wet-tail mix level vs the dry body (1.0 default)
Output is normalized to -3 dB (tasteful, not slamming). Cross-platform port of reverb_throw.sh.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def run(cmd):
    return subprocess.run([str(c) for c in cmd], check=True, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    import shutil
    missing = [b for b in ("sox", "ffmpeg", "ffprobe") if not shutil.which(b)]
    if missing:
        sys.exit(f"reverb_throw needs {', '.join(missing)} on PATH — see the install lines at the top of this file.")
    src, out = argv[0], argv[1]
    throw, rev, pad, wet = (argv[2:] + ["0.7", "78", "4", "1.0"][len(argv) - 2:])[:4]
    throw, pad, wet = float(throw), float(pad), float(wet)
    dur = float(run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0",
                     src]).stdout.strip())
    start = dur - throw
    delay_ms = round(start * 1000)
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        ff = ["ffmpeg", "-y", "-loglevel", "error"]
        # 1. isolate the ending, pad so the reverb can ring out
        run(ff + ["-ss", f"{start}", "-t", f"{throw}", "-i", src, t / "tailsrc.wav"])
        run(ff + ["-i", t / "tailsrc.wav", "-af", f"apad=pad_dur={pad}", t / "tailpad.wav"])
        # 2. WET-ONLY Freeverb on just that ending
        run(["sox", t / "tailpad.wav", t / "wet.wav", "reverb", "-w", rev, "45", "100", "100", "20", "1"])
        # 3. dry full clip, padded to match
        run(ff + ["-i", src, "-af", f"apad=pad_dur={pad}", t / "dry.wav"])
        # 4. bloom the wet tail in at the cut, mixed UNDER the clean dry body
        run(ff + ["-i", t / "dry.wav", "-i", t / "wet.wav", "-filter_complex",
                  f"[1:a]adelay={delay_ms}|{delay_ms}[wd];[0:a][wd]amix=inputs=2:weights=1 {wet}:normalize=0[mix]",
                  "-map", "[mix]", t / "raw.wav"])
        # 5. normalize to -3 dB
        det = subprocess.run(["ffmpeg", "-i", str(t / "raw.wav"), "-af", "volumedetect", "-f", "null", "-"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
        peak = float(re.search(r"max_volume:\s*(-?[0-9.]+) dB", det).group(1))
        run(ff + ["-i", t / "raw.wav", "-af", f"volume={-3.0 - peak:.2f}dB", out])
    print(f"wrote {out} (throw={throw}s reverb={rev} pad={pad}s wet={wet})")


if __name__ == "__main__":
    main(sys.argv[1:])
