"""ffmpeg / audio / speech helpers shared by every stage."""
import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

from . import paths

FPS = 30


def log(*a):
    # stderr only: the MCP server speaks JSON-RPC on stdout, a stray print would corrupt it
    print(*a, file=sys.stderr, flush=True)


def run(cmd, check=True, cwd=None):
    log("$", " ".join(str(c) for c in cmd)[:600])
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, cwd=cwd)
    if check and p.returncode != 0:
        raise RuntimeError(f"{Path(str(cmd[0])).name} failed ({p.returncode}): {p.stderr[-1500:]}")
    return p


def probe(path):
    out = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path]).stdout
    return json.loads(out)


def duration(path):
    return float(probe(path)["format"].get("duration") or 0)


def video_size(path):
    v = next(s for s in probe(path)["streams"] if s["codec_type"] == "video")
    return int(v["width"]), int(v["height"])


def normalize(src, dst, start=None, end=None, max_h=1080):
    """Re-encode to the house intermediate: H.264, CFR 30 fps, yuv420p, AAC 48 kHz stereo.
    Never cut a VFR stream recording directly — every later frame count depends on CFR."""
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if start is not None:
        cmd += ["-ss", f"{max(0, start):.3f}"]
    cmd += ["-i", src]
    if end is not None:
        cmd += ["-t", f"{end - max(0, start or 0):.3f}"]
    cmd += ["-vf", f"scale=-2:'min({max_h},ih)':flags=lanczos,fps={FPS},format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
            "-ar", "48000", "-ac", "2", "-movflags", "+faststart", dst]
    run(cmd)
    return dst


def extract_wav(src, dst, sr=16000, ch=1, start=None, dur=None):
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", src]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-vn", "-ac", str(ch), "-ar", str(sr), "-c:a", "pcm_s16le", dst]
    run(cmd)
    return dst


def read_wav(path):
    with wave.open(str(path)) as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768
    return x.reshape(-1, ch), sr


def write_wav(path, x, sr):
    x = np.clip(x, -1, 1)
    if x.ndim == 1:
        x = x[:, None]
    with wave.open(str(path), "wb") as w:
        w.setnchannels(x.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def rms_db(x, sr, hop_s=0.01):
    if x.ndim == 2:
        x = x.mean(axis=1)
    hop = max(1, int(sr * hop_s))
    n = len(x) // hop
    if n == 0:
        return np.array([-120.0])
    r = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
    return 20 * np.log10(np.maximum(r, 1e-6))


def loudness(path):
    p = run(["ffmpeg", "-nostats", "-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"],
            check=False)
    s = p.stderr[p.stderr.rfind("Summary:"):]
    import re
    i = re.search(r"I:\s+(-?[\d.]+)\s+LUFS", s)
    tp = re.search(r"Peak:\s+(-?[\d.]+)\s+dBFS", s)
    return (float(i.group(1)) if i else None, float(tp.group(1)) if tp else None)


# ------------------------------------------------------------------ speech

def have(module):
    try:
        __import__(module)
        return True
    except Exception:
        return False


def separate_voice(mix_wav, out_dir):
    """Demucs two-stem split → vocals. Returns (path, is_voice). Falls back to the mix."""
    out_dir = Path(out_dir)
    if have("demucs"):
        try:
            run([sys.executable, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs",
                 "-o", out_dir, mix_wav])
            voc = next(out_dir.rglob("vocals.wav"))
            dst = out_dir / "voice16k.wav"
            run(["ffmpeg", "-v", "error", "-y", "-i", voc, "-ac", "1", "-ar", "16000", dst])
            return str(dst), True
        except Exception as e:                         # noqa: BLE001
            log("demucs failed, falling back to the mix:", e)
    dst = out_dir / "voice16k.wav"
    out_dir.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-v", "error", "-y", "-i", mix_wav, "-ac", "1", "-ar", "16000", dst])
    return str(dst), False


def transcribe(wav, out_json, accurate=True, offset=0.0, model="small"):
    """Words as [{s, e, w}]. accurate → WhisperX forced alignment (the cut needs it);
    otherwise faster-whisper word timestamps (good enough for scouting)."""
    words = None
    if accurate and have("whisperx"):
        tmp = Path(out_json).with_suffix(".wx.json")
        run([sys.executable, paths.SCRIPTS["whisperx_align"], wav, tmp])
        words = json.load(open(tmp))
    elif have("faster_whisper"):
        from faster_whisper import WhisperModel
        m = WhisperModel(model if not accurate else "medium", device="cpu", compute_type="int8")
        segs, _ = m.transcribe(str(wav), word_timestamps=True, vad_filter=False)
        words = [{"s": round(w.start, 3), "e": round(w.end, 3), "w": w.word.strip()}
                 for s in segs for w in (s.words or [])]
    else:
        raise RuntimeError("no speech engine: install whisperx (or faster-whisper) — run /clip-setup")
    for w in words:
        w["s"] = round(w["s"] + offset, 3)
        w["e"] = round(w["e"] + offset, 3)
    json.dump(words, open(out_json, "w"), ensure_ascii=False)
    return words


def tool_status():
    def which(b):
        return shutil.which(b) is not None
    return {
        "ffmpeg": which("ffmpeg"), "ffprobe": which("ffprobe"),
        "yt_dlp": have("yt_dlp") or which("yt-dlp"),
        "streamlink": have("streamlink") or which("streamlink"),
        "whisperx": have("whisperx"), "faster_whisper": have("faster_whisper"),
        "demucs": have("demucs"), "opencv": have("cv2"),
        "google_api": have("googleapiclient"), "boto3": have("boto3"),
        "python": sys.version.split()[0],
    }
