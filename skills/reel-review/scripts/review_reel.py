#!/usr/bin/env python3
"""review_reel.py — the deterministic half of the review gate for a finished 9:16 clip.

A script measures what is measurable; the vision reviewer (a different model) judges the rest
from the contact sheets this script builds. Every check whose input is missing reports SKIP —
a skipped check is never a pass.

Usage (only the video is required):
    python3 review_reel.py out/clip.mp4 --out review/ \
        --cut cut.json                 # pieces with "dur" (s) -> expected frame count + sections
        --captions captions.json       # [{"text","from","to"}] frames (to = exclusive), or
                                       # [{"text","start","end"}] seconds
        --voice cut_voice16k.wav       # voice stem of the CUT timeline (Demucs) -> dead-air
                                       # audit + repeat scan. Without it, dead-air runs on the
                                       # render's mix as a WARN and the repeat scan SKIPs.
        --overlay overlay.mov          # graphics-only render WITH alpha (ProRes 4444 / PNG seq)
        --face-band 1180:1820          # y-range (output px) where the face lives -> face guard
        --region game:1080:726:0:0     # name:w:h:x:y, repeatable -> per-region motion
        --sections sections.txt        # "start end label" per line (output seconds)

Exit code 1 if any check FAILs, else 0. Writes report.json, report.md, sheet_mid.jpg,
sheet_post.jpg into --out.

Needs: ffmpeg + ffprobe on PATH, numpy.
"""
import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np

ARTICLES = {"a", "an", "the"}
PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"


# ---------------------------------------------------------------- helpers

def run(cmd, binary=False):
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {p.stderr.decode(errors='replace')[-800:]}")
    return p if binary else p.stdout.decode(errors="replace") + p.stderr.decode(errors="replace")


def ffprobe(path, count=False):
    cmd = ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json"]
    if count:
        cmd[1:1] = ["-count_frames"]
    return json.loads(subprocess.run(cmd + [str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                                     check=True).stdout)


def frac(s):
    try:
        return float(Fraction(s))
    except (ValueError, ZeroDivisionError):
        return 0.0


def result(name, status, summary, **data):
    return {"check": name, "status": status, "summary": summary, **data}


def decode_audio(path, sr=16000):
    raw = run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr),
               "-f", "f32le", "-"], binary=True).stdout
    return np.frombuffer(raw, dtype=np.float32), sr


def rms_db(x, sr, hop_s=0.01):
    hop = int(sr * hop_s)
    n = len(x) // hop
    if n == 0:
        return np.array([-120.0])
    r = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
    return 20 * np.log10(np.maximum(r, 1e-6))


def frames_iter(path, w, h, pix="gray", fps=None):
    """Yield frames as numpy arrays without holding the whole clip in memory."""
    ch = {"gray": 1, "rgba": 4}[pix]
    vf = f"scale={w}:{h}:flags=area"
    if fps:
        vf = f"fps={fps}," + vf
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(path), "-vf", vf, "-f", "rawvideo",
                          "-pix_fmt", pix, "-"], stdout=subprocess.PIPE)
    size = w * h * ch
    while True:
        buf = p.stdout.read(size)
        if len(buf) < size:
            break
        a = np.frombuffer(buf, dtype=np.uint8)
        yield a.reshape(h, w) if ch == 1 else a.reshape(h, w, ch)
    p.wait()


# ---------------------------------------------------------------- checks

def check_specs(info, a):
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    au = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    if v is None:
        return result("specs", FAIL, "no video stream"), None, None
    problems = []
    if (v["width"], v["height"]) != (a.width, a.height):
        problems.append(f"size {v['width']}x{v['height']} != {a.width}x{a.height}")
    fps = frac(v.get("r_frame_rate", "0"))
    if abs(fps - a.fps) > 0.01:
        problems.append(f"fps {fps:.3f} != {a.fps}")
    if v.get("codec_name") != "h264":
        problems.append(f"video codec {v.get('codec_name')} (want h264)")
    if v.get("pix_fmt") != "yuv420p":
        problems.append(f"pix_fmt {v.get('pix_fmt')} (want yuv420p)")
    if au is None:
        problems.append("no audio stream")
    else:
        if au.get("codec_name") != "aac":
            problems.append(f"audio codec {au.get('codec_name')} (want aac)")
        if int(au.get("sample_rate", 0)) != 48000:
            problems.append(f"sample rate {au.get('sample_rate')} (want 48000)")
        if int(au.get("channels", 0)) != 2:
            problems.append(f"{au.get('channels')} audio channels (want 2)")
    dur = float(info["format"].get("duration", 0))
    if not (a.min_dur <= dur <= a.max_dur):
        problems.append(f"duration {dur:.2f}s outside {a.min_dur}-{a.max_dur}s")
    st = FAIL if problems else PASS
    return result("specs", st, "; ".join(problems) or f"{v['width']}x{v['height']} {fps:g}fps "
                  f"h264/aac48k, {dur:.2f}s", duration=dur), v, dur


def check_cfr(v):
    r, avg = frac(v.get("r_frame_rate", "0")), frac(v.get("avg_frame_rate", "0"))
    if r == 0 or avg == 0:
        return result("cfr", WARN, "frame rate fields missing; cannot confirm CFR")
    if abs(r - avg) > 0.01:
        return result("cfr", FAIL, f"VFR: declared {r:.3f} vs average {avg:.3f} fps")
    return result("cfr", PASS, f"CFR {r:g} fps")


def check_frames(v, dur, a):
    n = int(v.get("nb_read_frames") or v.get("nb_frames") or 0)
    if a.cut:
        cut = json.load(open(a.cut, encoding="utf-8"))
        total = cut.get("total") or sum(p["dur"] for p in cut["pieces"])
        expect = round(total * a.fps)
        src = "cut.json"
    else:
        expect, src = round(dur * a.fps), "container duration"
    diff = n - expect
    tol = 1 if a.cut else 2
    st = PASS if abs(diff) <= tol else FAIL
    return result("frames", st, f"{n} frames vs {expect} expected from {src} ({diff:+d})",
                  frames=n, expected=expect)


def check_loudness(a):
    out = run(["ffmpeg", "-nostats", "-i", str(a.video), "-vn", "-af", "ebur128=peak=true",
               "-f", "null", "-"])
    summary = out[out.rfind("Summary:"):] if "Summary:" in out else ""
    mi = re.search(r"I:\s+(-?[\d.]+|-inf)\s+LUFS", summary)
    mp = re.search(r"Peak:\s+(-?[\d.]+|-inf)\s+dBFS", summary)
    if not mi or not mp:
        return result("loudness", FAIL, "could not parse loudness/true peak — a missing number "
                      "is not a pass; verify by hand")
    lufs, tp = float(mi.group(1)), float(mp.group(1))
    probs = []
    if abs(lufs - a.lufs) > a.lufs_tol:
        probs.append(f"integrated {lufs:.1f} LUFS (target {a.lufs}±{a.lufs_tol})")
    if tp > a.max_tp:
        probs.append(f"true peak {tp:.1f} dBTP > {a.max_tp}")
    return result("loudness", FAIL if probs else PASS,
                  "; ".join(probs) or f"{lufs:.1f} LUFS, {tp:.1f} dBTP (measured on encoded file)",
                  lufs=lufs, true_peak=tp)


def check_motion(a, n_expected):
    """One decode pass: frozen frames, black frames, per-region motion."""
    k = 4                                    # analyse at 1/4 resolution
    w, h = a.width // k, a.height // k
    regions = []
    for spec in a.region:
        name, rw, rh, rx, ry = spec.split(":")
        regions.append((name, int(rx) // k, int(ry) // k, int(rw) // k, int(rh) // k))
    diffs, lumas, reg_d = [], [], {r[0]: [] for r in regions}
    prev = None
    for f in frames_iter(a.video, w, h):
        f = f.astype(np.int16)
        lumas.append(float(f.mean()))
        if prev is not None:
            d = np.abs(f - prev)
            diffs.append(float(d.mean()))
            for name, x, y, rw, rh in regions:
                reg_d[name].append(float(d[y:y + rh, x:x + rw].mean()))
        prev = f
    out = []
    if not diffs:
        return [result("frozen", FAIL, "could not decode frames")]
    diffs = np.array(diffs)
    frozen = diffs < a.frozen_thresh
    longest = cur = 0
    for z in frozen:
        cur = cur + 1 if z else 0
        longest = max(longest, cur)
    pct = 100 * frozen.mean()
    st = FAIL if (pct > a.frozen_max_pct or longest > a.frozen_run_max) else PASS
    out.append(result("frozen", st, f"{pct:.2f}% frozen, longest run {longest} frames "
                      f"(limits {a.frozen_max_pct}% / {a.frozen_run_max}f)",
                      frozen_pct=round(pct, 3), longest_run=longest))
    lum = np.array(lumas)
    black = lum < a.black_luma
    runs, cur, start = [], 0, 0
    for i, b in enumerate(black):
        if b and cur == 0:
            start = i
        cur = cur + 1 if b else 0
        if cur == a.black_run:
            runs.append(round(start / a.fps, 2))
    out.append(result("black", FAIL if runs else PASS,
                      f"black stretches (≥{a.black_run}f) start at {runs} s" if runs
                      else "no black stretches", starts_s=runs))
    for name, *_ in regions:
        d = np.array(reg_d[name])
        moving = 100 * (d >= a.motion_thresh).mean()
        st = WARN if moving < 30 else PASS
        out.append(result(f"motion:{name}", st,
                          f"{moving:.0f}% of frames move in region '{name}'"
                          + (" — below 30%: look at it, not automatically a bug" if st == WARN
                             else ""), moving_pct=round(moving, 1)))
    return out


def load_captions(path, fps):
    raw = json.load(open(path, encoding="utf-8"))
    caps = []
    for c in raw:
        if "from" in c:
            s, e = c["from"] / fps, c["to"] / fps
        else:
            s, e = float(c["start"]), float(c["end"])
        caps.append({"text": c["text"].strip(), "s": s, "e": e})
    return sorted(caps, key=lambda c: c["s"])


def check_captions(a, voice_env, env_is_voice):
    caps = load_captions(a.captions, a.fps)
    fr = 1 / a.fps
    issues = []
    for i, c in enumerate(caps):
        words = c["text"].split()
        tag = f"#{i} '{c['text']}' @{c['s']:.2f}s"
        if len(words) > 3:
            issues.append(f"{tag}: {len(words)} words (max 3)")
        if c["e"] - c["s"] < 0.30 - 1e-6:
            issues.append(f"{tag}: {c['e'] - c['s']:.2f}s on screen (min 0.30)")
        if words and words[0].lower().strip(",.!?'\"") in ARTICLES:
            issues.append(f"{tag}: opens on an article")
        if i:
            gap = c["s"] - caps[i - 1]["e"]
            if gap < -fr / 2:
                issues.append(f"{tag}: overlaps the previous run by {-gap:.2f}s")
            elif fr / 2 < gap <= 2.5 * fr:
                issues.append(f"{tag}: {round(gap * a.fps)}-frame hole before it "
                              "('to' must equal the next 'from')")
    out = [result("captions", FAIL if issues else PASS,
                  f"{len(issues)} rule violations in {len(caps)} runs" if issues
                  else f"{len(caps)} runs, all rules hold", issues=issues)]
    # dead-air audit
    env = voice_env
    floor, speech = noise_floor(env), float(np.percentile(env[env > -90], 90)) if (env > -90).any() else 0.0
    thr = floor + 0.45 * (speech - floor)
    dead = []
    for c in caps:
        seg = env[int(c["s"] * 100):max(int(c["e"] * 100), int(c["s"] * 100) + 1)]
        if len(seg) and (seg < thr).mean() > 0.75:
            dead.append(f"'{c['text']}' @{c['s']:.2f}s ({100 * (seg < thr).mean():.0f}% below threshold)")
    if dead:
        st = FAIL if env_is_voice else WARN
        summ = f"{len(dead)} runs sit over dead air" + ("" if env_is_voice else
                                                         " (measured on the mix — pass --voice)")
    else:
        st, summ = PASS, "every run sits over speech"
    out.append(result("caption dead air", st, summ, runs=dead))
    return out


# ---- repeat scan: spectral self-similarity of adjacent voice bursts

def mel_fb(sr, n_fft, n_mels=40):
    def hz2mel(f): return 2595 * np.log10(1 + f / 700)
    def mel2hz(m): return 700 * (10 ** (m / 2595) - 1)
    pts = mel2hz(np.linspace(hz2mel(60), hz2mel(sr / 2 - 200), n_mels + 2))
    bins = np.floor((n_fft + 1) * pts / sr).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1))
    for m in range(1, n_mels + 1):
        l, c, r = bins[m - 1], bins[m], bins[m + 1]
        for k in range(l, c):
            fb[m - 1, k] = (k - l) / max(c - l, 1)
        for k in range(c, r):
            fb[m - 1, k] = (r - k) / max(r - c, 1)
    return fb


def logmel(x, sr, fb, n_fft=400, hop=160):
    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    n = 1 + (len(x) - n_fft) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(n)[:, None]
    spec = np.abs(np.fft.rfft(x[idx] * np.hanning(n_fft), axis=1)) ** 2
    m = np.log(spec @ fb.T + 1e-8)
    m -= m.mean(axis=0)                      # per-burst mean normalisation
    return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-8)


def dtw_similarity(A, B):
    """Mean cosine similarity along the best DTW path (A fully, B open-ended)."""
    S = A @ B.T
    C = 1 - S
    n, m = C.shape
    D = np.full((n + 1, m + 1), np.inf)
    L = np.zeros((n + 1, m + 1))
    D[0, 0] = 0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            opts = (D[i - 1, j - 1], D[i - 1, j], D[i, j - 1])
            k = int(np.argmin(opts))
            pi, pj = [(i - 1, j - 1), (i - 1, j), (i, j - 1)][k]
            D[i, j] = C[i - 1, j - 1] + opts[k]
            L[i, j] = L[pi, pj] + 1
    j = int(np.argmin(D[n, 1:] / np.maximum(L[n, 1:], 1))) + 1   # open end in B
    return 1 - D[n, j] / L[n, j]


def noise_floor(env_db):
    """10th percentile of the envelope, ignoring digital silence (padding reads -120 dB)."""
    live = env_db[env_db > -90]
    return float(np.percentile(live if len(live) else env_db, 10))


def bursts(env_db, hop=0.01, join=0.08, min_len=0.22):
    floor = noise_floor(env_db)
    on = env_db > floor + 14
    segs, start = [], None
    for i, v in enumerate(np.append(on, False)):
        if v and start is None:
            start = i
        elif not v and start is not None:
            segs.append([start * hop, i * hop])
            start = None
    merged = []
    for s in segs:
        if merged and s[0] - merged[-1][1] < join:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    return [s for s in merged if s[1] - s[0] >= min_len]


def check_repeats(voice, sr, env_db, thresh):
    fb = mel_fb(sr, 400)
    bs = bursts(env_db)
    hits, scores = [], []
    for (s1, e1), (s2, e2) in zip(bs, bs[1:]):
        if s2 - e1 > 1.5:                    # not adjacent enough to be a restart
            continue
        la = min(e1 - s1, 3.0)
        A = logmel(voice[int(s1 * sr):int((s1 + la) * sr)], sr, fb)
        B = logmel(voice[int(s2 * sr):int(min(e2, s2 + la * 1.4) * sr)], sr, fb)
        if len(A) < 10 or len(B) < 10:
            continue
        sim = float(dtw_similarity(A, B))
        scores.append(sim)
        if sim >= thresh:
            hits.append(f"{s1:.2f}-{e1:.2f}s ≈ head of {s2:.2f}s (score {sim:.2f})")
    st = FAIL if hits else PASS
    return result("repeat scan", st,
                  f"{len(hits)} likely false-start/redo pairs (≥{thresh})" if hits else
                  f"{len(bs)} bursts, {len(scores)} adjacent pairs, none ≥ {thresh}"
                  + (f" (max {max(scores):.2f})" if scores else ""), pairs=hits)


def check_overlay(a):
    k = 2
    w, h = a.width // k, a.height // k
    fb_top = fb_bot = None
    if a.face_band:
        fb_top, fb_bot = (int(v) // k for v in a.face_band.split(":"))
    sx0, sx1, sy0, sy1 = 35 // k, (a.width - 100) // k, 220 // k, 1470 // k
    face_hits, safe_hits = [], []
    sample_fps = 10
    for i, f in enumerate(frames_iter(a.overlay, w, h, pix="rgba", fps=sample_fps)):
        t = i / sample_fps
        opaque = f[:, :, 3] > 200
        if opaque.mean() > 0.85:             # deliberate full-frame graphic
            continue
        if fb_top is not None:
            n = int(opaque[fb_top:fb_bot].sum())
            if n > 25:
                face_hits.append(f"{t:.1f}s ({n * k * k} px)")
        outside = opaque.copy()
        outside[sy0:sy1, sx0:sx1] = False
        n = int(outside.sum())
        if n > 50:
            safe_hits.append(f"{t:.1f}s ({n * k * k} px)")
    out = []
    if a.face_band:
        out.append(result("face guard", FAIL if face_hits else PASS,
                          f"opaque graphics inside face band at {len(face_hits)} sampled frames"
                          if face_hits else "no graphics inside the face band",
                          hits=face_hits[:40]))
    else:
        out.append(result("face guard", SKIP, "no --face-band given"))
    out.append(result("safe area", WARN if safe_hits else PASS,
                      f"overlay ink outside the text-safe area at {len(safe_hits)} sampled frames "
                      "(fine for imagery, not for text — vision pass decides)" if safe_hits
                      else "all overlay ink inside y220–1470, x35–980", hits=safe_hits[:40]))
    return out


# ---------------------------------------------------------------- sections + sheets

def sections(a, dur):
    if a.sections:
        out = []
        for line in open(a.sections, encoding="utf-8"):
            line = line.split("#")[0].strip()
            if line:
                s, e, *lab = line.split()
                out.append((float(s), float(e), " ".join(lab)))
        return out
    if a.cut:
        t, out = 0.0, []
        for p in json.load(open(a.cut, encoding="utf-8"))["pieces"]:
            out.append((t, t + p["dur"], str(p.get("beat") or p.get("id", ""))))
            t += p["dur"]
        return out
    step = 3.0
    return [(s, min(s + step, dur), f"auto{i}") for i, s in enumerate(np.arange(0, dur, step))]


def contact_sheets(a, secs, dur, outdir):
    tmp = outdir / "_frames"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    index = {"mid": [], "post": []}
    for kind in ("mid", "post"):
        for i, (s, e, lab) in enumerate(secs):
            t = (s + e) / 2 if kind == "mid" else s + 0.35
            t = min(max(t, 0), max(dur - 0.05, 0))
            dst = tmp / f"{kind}_{i:04d}.jpg"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(a.video),
                            "-frames:v", "1", "-vf", "scale=270:480", "-q:v", "3", str(dst)],
                           check=False)
            if dst.exists():
                index[kind].append({"tile": len(index[kind]), "section": lab, "t": round(t, 2)})
        n = len(index[kind])
        if n:
            cols = min(6, n)
            rows = math.ceil(n / cols)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "1", "-i",
                            str(tmp / f"{kind}_%04d.jpg"), "-vf",
                            f"tile={cols}x{rows}:padding=6:color=white", "-frames:v", "1",
                            str(outdir / f"sheet_{kind}.jpg")], check=False)
    shutil.rmtree(tmp)
    return index


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--cut"); ap.add_argument("--captions"); ap.add_argument("--voice")
    ap.add_argument("--overlay"); ap.add_argument("--face-band"); ap.add_argument("--sections")
    ap.add_argument("--region", action="append", default=[])
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--width", type=int, default=1080); ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--min-dur", type=float, default=5.0); ap.add_argument("--max-dur", type=float, default=60.0)
    ap.add_argument("--lufs", type=float, default=-14.0); ap.add_argument("--lufs-tol", type=float, default=1.0)
    ap.add_argument("--max-tp", type=float, default=-1.0)
    ap.add_argument("--frozen-thresh", type=float, default=0.1, help="mean |Δluma| below this = frozen")
    ap.add_argument("--frozen-max-pct", type=float, default=0.5)
    ap.add_argument("--frozen-run-max", type=int, default=15, help="longest allowed frozen run, frames")
    ap.add_argument("--black-luma", type=float, default=18.0)
    ap.add_argument("--black-run", type=int, default=3)
    ap.add_argument("--motion-thresh", type=float, default=1.0, help="region |Δluma| that counts as moving")
    ap.add_argument("--repeat-thresh", type=float, default=0.78)
    a = ap.parse_args()

    outdir = a.out or a.video.with_suffix("").parent / (a.video.stem + "_review")
    outdir.mkdir(parents=True, exist_ok=True)
    results = []

    info = ffprobe(a.video, count=True)
    spec, v, dur = check_specs(info, a)
    results.append(spec)
    if v is None:
        dur = float(info["format"].get("duration", 0))
    else:
        results.append(check_cfr(v))
        results.append(check_frames(v, dur, a))
        results += check_motion(a, None)
    results.append(check_loudness(a))

    voice = env = None
    if a.voice:
        voice, sr = decode_audio(a.voice)
        env = rms_db(voice, sr)
    if a.captions:
        if env is not None:
            results += check_captions(a, env, True)
        else:
            mix, msr = decode_audio(a.video)
            results += check_captions(a, rms_db(mix, msr), False)
    else:
        results.append(result("captions", SKIP, "no --captions given"))
    if voice is not None:
        results.append(check_repeats(voice, sr, env, a.repeat_thresh))
    else:
        results.append(result("repeat scan", SKIP, "needs --voice (meaningless on a mix with game audio)"))
    if a.overlay:
        results += check_overlay(a)
    else:
        results.append(result("face guard", SKIP, "no --overlay given"))

    secs = sections(a, dur)
    index = contact_sheets(a, secs, dur, outdir)

    worst = FAIL if any(r["status"] == FAIL for r in results) else (
        WARN if any(r["status"] == WARN for r in results) else PASS)
    report = {"video": str(a.video), "verdict": worst, "checks": results, "sheets": index}
    (outdir / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")

    skipped = [r["check"] for r in results if r["status"] == SKIP]
    md = [f"# Review: {a.video.name}", "", f"**Verdict: {worst}**"
          + (f" — skipped (not passed): {', '.join(skipped)}" if skipped else ""), "",
          "| check | status | summary |", "| --- | --- | --- |"]
    md += [f"| {r['check']} | {r['status']} | {r['summary']} |" for r in results]
    for r in results:
        for key in ("issues", "runs", "pairs", "hits"):
            if isinstance(r.get(key), list) and r[key]:
                md += ["", f"### {r['check']} — {key}", ""] + [f"- {x}" for x in r[key]]
    for kind, label in (("mid", "mid-beat"), ("post", "+0.35 s after each boundary")):
        md += ["", f"### sheet_{kind}.jpg ({label})", "", "| tile | section | t (s) |", "| --- | --- | --- |"]
        md += [f"| {x['tile']} | {x['section']} | {x['t']} |" for x in index[kind]]
    (outdir / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    for r in results:
        print(f"[{r['status']:4}] {r['check']}: {r['summary']}")
    skips = sum(r["status"] == SKIP for r in results)
    print(f"\nverdict: {worst}" + (f" ({skips} checks SKIPPED — not passed)" if skips else "")
          + f"  ->  {outdir / 'report.md'}")
    sys.exit(1 if worst == FAIL else 0)


if __name__ == "__main__":
    main()
