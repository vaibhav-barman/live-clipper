#!/usr/bin/env python3
"""sfx_catalog.py — measure every SFX file so cues are scheduled by PEAK, not by file start.

    python3 sfx_catalog.py sfx/ > sfx/catalog.json

Per file: peak_s (argmax |x| offset), peak_dbfs (per-channel max, NOT a mono sum — summing
channels reads in-phase transients up to +6 dB hot), onset_s (first 10 ms block within 30 dB of
the peak), dur_s. Needs ffmpeg + numpy.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aif", ".aiff"}
SR = 48000


def channels(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                          "stream=channels", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.strip()
    return int(out or 1)


def decode(path):
    """Decode at the file's OWN channel count — a forced up/down-mix changes the level."""
    ch = channels(path)
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ar", str(SR), "-"],
        capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    return x.reshape(-1, ch) if x.size else np.zeros((0, ch), np.float32)


def measure(path):
    x = decode(path)
    if not len(x):
        return None
    mag = np.abs(x).max(axis=1)                 # per-sample max over channels, never the sum
    i = int(mag.argmax())
    peak = float(mag[i])
    blk = SR // 100
    n = len(mag) // blk
    rms = np.sqrt((mag[: n * blk].reshape(n, blk) ** 2).mean(axis=1)) if n else np.array([peak])
    above = np.nonzero(rms >= peak * 10 ** (-30 / 20))[0]
    onset = float(above[0] * blk / SR) if len(above) else 0.0
    return {
        "file": str(path),
        "peak_s": round(i / SR, 4),
        "peak_dbfs": round(20 * np.log10(max(peak, 1e-9)), 2),
        "onset_s": round(onset, 4),
        "dur_s": round(len(x) / SR, 3),
    }


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = Path(sys.argv[1])
    out = []
    for p in sorted(root.rglob("*")):
        if p.suffix.lower() in EXT:
            try:
                m = measure(p)
            except subprocess.CalledProcessError:
                print(f"skip (decode failed): {p}", file=sys.stderr)
                continue
            if m:
                out.append(m)
    json.dump(out, sys.stdout, indent=1)
    print(f"{len(out)} files measured", file=sys.stderr)


if __name__ == "__main__":
    main()
