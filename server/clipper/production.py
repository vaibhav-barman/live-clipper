"""Graph 2 · Production — window prep, cut assembly, facecam detection, captions."""
import json
from pathlib import Path

import numpy as np

from . import db, ingest, media, paths

FPS = media.FPS
PAD = 5.0
ARTICLES = {"a", "an", "the"}
FUNC = ARTICLES | {"to", "of", "and", "or", "but", "in", "on", "at", "for", "with", "my", "your",
                   "is", "it's", "i", "you", "we", "that", "this"}


def prepare_clip(clip_id):
    """Window ±5 s → window.mp4, mix.wav (48k stereo), voice16k.wav (Demucs), words.json
    (WhisperX on the voice, WINDOW times). Everything the cutter needs."""
    c = db.one("SELECT * FROM clips WHERE id=?", clip_id)
    d = Path(c["dir"])
    ws = max(0.0, c["start"] - PAD)
    we = c["end"] + PAD
    db.set_clip(clip_id, status="preparing")
    win = d / "window.mp4"
    ingest.window_source(c["job_id"], ws, we, str(win))
    mix = media.extract_wav(str(win), str(d / "mix.wav"), sr=48000, ch=2)
    voice, is_voice = media.separate_voice(mix, d / "sep")
    Path(voice).replace(d / "voice16k.wav")
    words = media.transcribe(str(d / "voice16k.wav"), str(d / "words.json"), accurate=True)
    db.merge_clip_data(clip_id, window_start=ws, window_end=we, voice_is_stem=is_voice,
                       window=str(win), mix=str(d / "mix.wav"), voice=str(d / "voice16k.wav"),
                       words=str(d / "words.json"),
                       hook_offset=round(c["start"] - ws, 3))
    db.set_clip(clip_id, status="prepared")
    return {"clip_dir": str(d), "window_s": round(we - ws, 2), "words": len(words),
            "voice_is_stem": is_voice,
            "note": None if is_voice else "Demucs unavailable: envelope tools are reading the MIX"}


def assemble_cut(clip_id):
    """cut.json (window times) → cut.mp4 (video, CFR, frame-exact), cut_mix.wav and
    cut_voice16k.wav sliced by SAMPLE index with the flagged micro-fades, sections.txt."""
    c = db.one("SELECT * FROM clips WHERE id=?", clip_id)
    d = Path(c["dir"])
    cut = json.load(open(d / "cut.json"))
    pieces = cut["pieces"]
    if not pieces:
        raise RuntimeError("cut.json has no pieces")
    # frame-exact piece bounds
    spans = []
    for p in pieces:
        f0 = round(p["a"] * FPS)
        nf = max(1, round(p["dur"] * FPS))
        spans.append((f0, nf, p))
    total_frames = sum(nf for _, nf, _ in spans)
    # video
    parts = []
    for i, (f0, nf, _) in enumerate(spans):
        parts.append(f"[0:v]trim=start_frame={f0}:end_frame={f0 + nf},setpts=PTS-STARTPTS[v{i}]")
    graph = ";".join(parts) + ";" + "".join(f"[v{i}]" for i in range(len(spans))) + \
        f"concat=n={len(spans)}:v=1:a=0,fps={FPS},format=yuv420p[v]"
    media.run(["ffmpeg", "-v", "error", "-y", "-i", d / "window.mp4", "-filter_complex", graph,
               "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
               "-r", str(FPS), d / "cut.mp4"])
    # audio, sample-exact
    for src, dst in ((d / "mix.wav", d / "cut_mix.wav"), (d / "voice16k.wav", d / "cut_voice16k.wav")):
        x, sr = media.read_wav(src)
        out = []
        for f0, nf, p in spans:
            a = round(f0 / FPS * sr)
            n = round(nf / FPS * sr)
            seg = x[a:a + n].copy()
            if len(seg) < n:
                seg = np.vstack([seg, np.zeros((n - len(seg), x.shape[1]), np.float32)])
            if p.get("fade_in", True):
                k = min(len(seg), int(0.015 * sr))
                seg[:k] *= np.linspace(0, 1, k)[:, None]
            if p.get("fade_out", True):
                k = min(len(seg), int(0.025 * sr))
                seg[len(seg) - k:] *= np.linspace(1, 0, k)[:, None]
            out.append(seg)
        media.write_wav(dst, np.vstack(out), sr)
    # sections in OUTPUT seconds
    t, lines = 0, []
    for f0, nf, p in spans:
        lines.append(f"{t / FPS:.3f} {(t + nf) / FPS:.3f} {p.get('beat') or p.get('id', '')}")
        t += nf
    (d / "sections.txt").write_text("\n".join(lines) + "\n")
    db.merge_clip_data(clip_id, cut=str(d / "cut.mp4"), cut_mix=str(d / "cut_mix.wav"),
                       cut_voice=str(d / "cut_voice16k.wav"), sections=str(d / "sections.txt"),
                       total_frames=total_frames)
    db.set_clip(clip_id, status="cut")
    return {"cut": str(d / "cut.mp4"), "pieces": len(spans), "frames": total_frames,
            "duration_s": round(total_frames / FPS, 3)}


# ------------------------------------------------------------------ facecam

def detect_facecam(clip_id, samples=24):
    """Find the facecam rectangle in a composited stream frame. Returns the rect in source px,
    the median face box inside it, and a verification image the agent MUST look at."""
    import cv2
    c = db.one("SELECT * FROM clips WHERE id=?", clip_id)
    d = Path(c["dir"])
    src = str(d / "cut.mp4") if (d / "cut.mp4").exists() else str(d / "window.mp4")
    W, H = media.video_size(src)
    dur = media.duration(src)
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if casc.empty():
        return {"facecam": None, "face": None, "full_frame_face": None, "confidence": 0.0,
                "error": "OpenCV has no Haar cascade (OpenCV 5 dropped it). Run /clip-setup "
                         "(pins opencv-python-headless<5) or set geometry by hand with set_geometry."}
    frames, faces = [], []
    for t in np.linspace(0.5, max(dur - 0.5, 0.6), samples):
        p = __import__("subprocess").run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", src,
                                          "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                                         capture_output=True)
        if len(p.stdout) != W * H:
            continue
        g = np.frombuffer(p.stdout, np.uint8).reshape(H, W)
        frames.append(g)
        for (x, y, w, h) in casc.detectMultiScale(g, 1.1, 6, minSize=(max(24, W // 40),) * 2):
            faces.append((x, y, w, h))
    result = {"facecam": None, "face": None, "full_frame_face": None, "confidence": 0.0}
    if not frames:
        return result
    stack = np.stack(frames).astype(np.float32)
    if faces:
        fa = np.array(faces, dtype=float)
        cx, cy = fa[:, 0] + fa[:, 2] / 2, fa[:, 1] + fa[:, 3] / 2
        mx, my = np.median(cx), np.median(cy)
        keep = (np.abs(cx - mx) < W * 0.08) & (np.abs(cy - my) < H * 0.08)
        stable = keep.mean()
        med = np.median(fa[keep], axis=0) if keep.any() else np.median(fa, axis=0)
        face = [int(v) for v in med]
        result["face"] = face
        big = face[3] > H * 0.22                     # face fills the frame → IRL / full-frame
        if big:
            result["full_frame_face"] = face
            result["confidence"] = round(float(stable), 2)
        else:
            rect = _cam_rect(stack, face, W, H)
            result["facecam"] = rect
            result["confidence"] = round(float(stable) * (0.9 if rect else 0.4), 2)
    # verification image
    vis = cv2.cvtColor(frames[len(frames) // 2], cv2.COLOR_GRAY2BGR)
    if result["facecam"]:
        x, y, w, h = result["facecam"]
        cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 255), 4)
    if result["face"]:
        x, y, w, h = result["face"]
        cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 0, 255), 3)
    cv2.imwrite(str(d / "facecam_check.jpg"), cv2.resize(vis, (W // 2, H // 2)))
    result["check_image"] = str(d / "facecam_check.jpg")
    result["source_size"] = [W, H]
    db.merge_clip_data(clip_id, facecam=result["facecam"], face=result["face"],
                       full_frame_face=result["full_frame_face"], source_size=[W, H])
    return result


def _cam_rect(stack, face, W, H):
    """Grow a box out from the face until temporal variance / a straight edge says the camera ends."""
    std = stack.std(axis=0)
    mean = stack.mean(axis=0)
    x, y, w, h = face
    cx, cy = x + w // 2, y + h // 2
    gx = np.abs(np.diff(mean, axis=1))
    gy = np.abs(np.diff(mean, axis=0))
    act = std > max(4.0, np.percentile(std, 40))

    def edge(line_grad, line_act, start, step, limit):
        pos = start
        best, best_v = None, 0
        while 0 < pos < limit - 1:
            v = line_grad(pos)
            if v > best_v and v > 18:
                best, best_v = pos, v
            if not line_act(pos) and best is not None:
                break
            pos += step
            if abs(pos - start) > limit * 0.6:
                break
        return best

    y0, y1 = max(0, y - h), min(H - 1, y + 2 * h)
    x0, x1 = max(0, x - w), min(W - 1, x + 2 * w)
    left = edge(lambda p: gx[y0:y1, p - 1].mean() if p > 0 else 0,
                lambda p: act[y0:y1, p].mean() > 0.3, x, -1, W)
    right = edge(lambda p: gx[y0:y1, p].mean(), lambda p: act[y0:y1, p].mean() > 0.3, x + w, 1, W)
    top = edge(lambda p: gy[p - 1, x0:x1].mean() if p > 0 else 0,
               lambda p: act[p, x0:x1].mean() > 0.3, y, -1, H)
    bottom = edge(lambda p: gy[p, x0:x1].mean(), lambda p: act[p, x0:x1].mean() > 0.3, y + h, 1, H)
    left = 0 if left is None else left
    top = 0 if top is None else top
    right = W if right is None else right + 1
    bottom = H if bottom is None else bottom + 1
    rw, rh = right - left, bottom - top
    if rw < w * 1.3 or rh < h * 1.3 or rw * rh > 0.5 * W * H:
        # fall back to a 16:9 box around the face (face ≈ 1/3 of cam height)
        rh = min(H, int(h * 3.2))
        rw = min(W, int(rh * 16 / 9))
        left = int(np.clip(cx - rw / 2, 0, W - rw))
        top = int(np.clip(cy - rh * 0.45, 0, H - rh))
    return [int(left), int(top), int(rw), int(rh)]


# ------------------------------------------------------------------ captions

def _map_word(w, spans):
    """window seconds → output seconds through the cut (None if the word was cut)."""
    t_out = 0.0
    for a, dur in spans:
        if a - 0.02 <= w["s"] < a + dur:
            s = t_out + (w["s"] - a)
            e = t_out + min(w["e"], a + dur) - a
            return max(0.0, s), max(s + 0.05, e)
        t_out += dur
    return None


def make_captions(clip_id, max_words=3):
    """Source word times → output frames through cut.json, grouped by caption-align's rules.
    Writes captions.json ([{text, from, to}], frames, `to` exclusive)."""
    c = db.one("SELECT * FROM clips WHERE id=?", clip_id)
    d = Path(c["dir"])
    cut = json.load(open(d / "cut.json"))
    words = json.load(open(d / "words.json"))
    spans = [(p["a"], round(p["dur"] * FPS) / FPS) for p in cut["pieces"]]
    total = sum(s[1] for s in spans)
    mapped = []
    for w in sorted(words, key=lambda w: w["s"]):
        m = _map_word(w, spans)
        if m and w["w"].strip():
            mapped.append({"w": w["w"].strip(), "s": m[0], "e": m[1]})
    runs, cur = [], []

    def flush():
        if cur:
            runs.append(list(cur))
            cur.clear()

    def bare(w):
        return w["w"].lower().strip(",.!?\"'")

    for i, w in enumerate(mapped):
        if cur and (w["s"] - cur[-1]["e"] > 0.45):
            flush()
        cur.append(w)
        end_punct = w["w"][-1:] in ".!?,"
        if len(cur) >= max_words or end_punct:
            nxt = mapped[i + 1] if i + 1 < len(mapped) else None
            carry_last = (not end_punct and nxt is not None and len(cur) >= 3 and
                          (bare(cur[-1]) in FUNC or bare(nxt) in ARTICLES))
            if carry_last:
                # keep the last word for the next run, so no run ENDS on a function word and the
                # next run doesn't OPEN on an article ("so the big" not "go okay so" | "the big")
                carry = cur.pop()
                flush()
                cur.append(carry)
            else:
                flush()
    flush()
    # never open on an article: move a leading article back onto the previous run if it fits
    for i in range(1, len(runs)):
        if runs[i] and runs[i][0]["w"].lower().strip(",.!?") in ARTICLES and len(runs[i]) > 1:
            if len(runs[i - 1]) < max_words:
                runs[i - 1].append(runs[i].pop(0))
    runs = [r for r in runs if r]
    caps = []
    for r in runs:
        caps.append({"text": " ".join(w["w"] for w in r), "s": r[0]["s"], "e": r[-1]["e"]})
    # ≥0.30 s: merge short runs forward when the cap allows, else extend
    merged = []
    for cap in caps:
        if merged and cap["e"] - cap["s"] < 0.30 and \
                len(merged[-1]["text"].split()) + len(cap["text"].split()) <= max_words and \
                cap["s"] - merged[-1]["e"] < 0.2:
            merged[-1]["text"] += " " + cap["text"]
            merged[-1]["e"] = cap["e"]
        else:
            merged.append(cap)
    out = []
    for i, cap in enumerate(merged):
        f0 = round(cap["s"] * FPS)
        f1 = max(round(cap["e"] * FPS) + 3, f0 + 9)          # ≥0.30 s
        if i + 1 < len(merged):
            nxt = round(merged[i + 1]["s"] * FPS)
            if nxt - f1 <= 3:                                 # close the gap: `to` = next `from`
                f1 = nxt
            f1 = min(f1, nxt)
        f1 = min(f1, round(total * FPS))
        if f1 > f0:
            out.append({"text": cap["text"], "from": f0, "to": f1})
    json.dump(out, open(d / "captions.json", "w"), indent=1, ensure_ascii=False)
    db.merge_clip_data(clip_id, captions=str(d / "captions.json"))
    return {"captions": str(d / "captions.json"), "runs": len(out)}
