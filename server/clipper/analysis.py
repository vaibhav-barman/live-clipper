"""Graph 1 (rest) — fast transcription for scouting, signal analysis, candidates, scoring."""
import json
import re
from pathlib import Path

import numpy as np

from . import db, ingest, media, paths

HYPE = ["no way", "oh my god", "oh my gosh", "let's go", "lets go", "what", "bro", "yo", "wait",
        "holy", "clip it", "clip that", "insane", "crazy", "are you serious", "i'm done", "noo",
        "yes", "omg", "wtf", "dude", "hell no", "run", "help"]


def transcribe_chunks(job_id, chunk_ids=None):
    """Fast pass (faster-whisper) over new chunks → words with STREAM times. For scouting only;
    the clip stage re-transcribes its window accurately on the voice stem."""
    q = "SELECT * FROM chunks WHERE job_id=? AND status='new' ORDER BY idx"
    chunks = db.many(q, job_id)
    if chunk_ids:
        chunks = [c for c in chunks if c["id"] in set(chunk_ids)]
    wd = paths.job_dir(job_id) / "words"
    wd.mkdir(exist_ok=True)
    done = 0
    for c in chunks:
        f, off = ingest.chunk_media(c)
        wav = wd / f"chunk_{c['idx']:05d}.wav"
        media.extract_wav(f, str(wav), start=off, dur=c["end"] - c["start"])
        out = wd / f"chunk_{c['idx']:05d}.json"
        media.transcribe(str(wav), str(out), accurate=False, offset=c["start"])
        wav.unlink(missing_ok=True)
        db.exec_("UPDATE chunks SET status='transcribed', words_path=? WHERE id=?", str(out), c["id"])
        done += 1
        media.log(f"chunk {c['idx']} transcribed")
    return {"transcribed": done}


def job_words(job_id, start=None, end=None):
    words = []
    for c in db.many("SELECT words_path FROM chunks WHERE job_id=? AND words_path IS NOT NULL "
                     "ORDER BY idx", job_id):
        try:
            words += json.load(open(c["words_path"], encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    if start is not None:
        words = [w for w in words if start <= w["s"] < end]
    return words


def _chat(job_id):
    f = paths.job_dir(job_id) / "chat.json"
    if f.exists():
        return json.load(open(f, encoding="utf-8"))
    return []


def analyze_signals(job_id):
    """Loudness spikes + scene cuts + chat bursts + hype keywords → candidate peaks."""
    job = db.one("SELECT * FROM jobs WHERE id=?", job_id)
    chunks = db.many("SELECT * FROM chunks WHERE job_id=? AND status='transcribed' ORDER BY idx", job_id)
    if not chunks:
        return {"candidates_added": 0, "note": "no transcribed chunks"}
    keywords = [k.lower() for k in (job.get("keywords") or [])] + HYPE
    events = []                                   # (t, kind, strength)
    for c in chunks:
        f, off = ingest.chunk_media(c)
        dur = c["end"] - c["start"]
        tmp = paths.job_dir(job_id) / f"_sig_{c['idx']}.wav"
        media.extract_wav(f, str(tmp), sr=8000, start=off, dur=dur)
        x, sr = media.read_wav(tmp)
        tmp.unlink(missing_ok=True)
        env = media.rms_db(x, sr, hop_s=0.5)
        base = np.median(env[env > -80]) if (env > -80).any() else -60
        for i, v in enumerate(env):
            if v - base > 6:
                events.append((c["start"] + i * 0.5, "loud", float(v - base)))
        # scene cuts at low res
        p = media.run(["ffmpeg", "-v", "info", "-ss", f"{off:.2f}", "-t", f"{dur:.2f}", "-i", f,
                       "-vf", "fps=4,scale=320:-2,select='gt(scene,0.35)',showinfo", "-an",
                       "-f", "null", "-"], check=False)
        for m in re.finditer(r"pts_time:([\d.]+)", p.stderr):
            events.append((c["start"] + float(m.group(1)), "scene", 1.0))
        db.exec_("UPDATE chunks SET status='analyzed' WHERE id=?", c["id"])
    # keywords on the fast transcript
    t0, t1 = chunks[0]["start"], chunks[-1]["end"]
    words = job_words(job_id, t0, t1)
    text_ts = [(w["s"], w["w"].lower().strip(" ,.!?")) for w in words]
    for i, (t, w) in enumerate(text_ts):
        bigram = w + " " + (text_ts[i + 1][1] if i + 1 < len(text_ts) else "")
        if w in keywords or bigram in keywords:
            events.append((t, "keyword", 1.0))
    # chat bursts
    chat = [m for m in _chat(job_id) if t0 <= m["t"] < t1]
    if chat:
        bins = np.zeros(int((t1 - t0) // 5) + 1)
        for m in chat:
            bins[int((m["t"] - t0) // 5)] += 1
        med = max(np.median(bins), 0.5)
        for i, b in enumerate(bins):
            if b / med >= 2.5:
                events.append((t0 + i * 5 + 2.5, "chat", float(b / med)))
    added = _cluster(job_id, events)
    return {"events": len(events), "candidates_added": added}


def _cluster(job_id, events, gap=20.0):
    if not events:
        return 0
    events.sort()
    clusters, cur = [], [events[0]]
    for e in events[1:]:
        if e[0] - cur[-1][0] <= gap:
            cur.append(e)
        else:
            clusters.append(cur)
            cur = [e]
    clusters.append(cur)
    existing = db.many("SELECT t_peak FROM candidates WHERE job_id=?", job_id)
    added = 0
    for cl in clusters:
        kinds = {}
        for t, k, s in cl:
            kinds.setdefault(k, []).append(s)
        loud = [e for e in cl if e[1] == "loud"]
        peak = max(loud, key=lambda e: e[2])[0] if loud else cl[len(cl) // 2][0]
        if any(abs(peak - e["t_peak"]) < 15 for e in existing):
            continue
        feats = {k: {"count": len(v), "max": round(max(v), 2)} for k, v in kinds.items()}
        score = (min(1, len(kinds.get("loud", [])) / 6) * 0.35
                 + min(1, len(kinds.get("keyword", [])) / 3) * 0.25
                 + min(1, max(kinds.get("chat", [0])) / 5) * 0.3
                 + min(1, len(kinds.get("scene", [])) / 4) * 0.1)
        db.exec_("INSERT INTO candidates(job_id, t_peak, start, end, features, signal_score, status) "
                 "VALUES (?,?,?,?,?,?,?)", job_id, peak, max(0, peak - 30), peak + 30,
                 json.dumps(feats), round(score, 3), "new")
        added += 1
    return added


def candidates_for_scout(job_id, limit=15, ready_before=None):
    """New candidates with ±30 s transcript, strongest signal first. In live mode only candidates
    whose context window is fully recorded (`ready_before`) are returned."""
    rows = db.many("SELECT * FROM candidates WHERE job_id=? AND status='new' "
                   "ORDER BY signal_score DESC", job_id)
    out = []
    for r in rows:
        if ready_before is not None and r["end"] > ready_before:
            continue
        words = job_words(job_id, r["start"], r["end"])
        r["transcript"] = " ".join(f"[{w['s']:.1f}]{w['w']}" if i % 12 == 0 else w["w"]
                                   for i, w in enumerate(words))
        out.append(r)
        if len(out) >= limit:
            break
    return out


def save_scores(job_id, scores):
    """scores: [{candidate_id, score, reason, start, end, tease}] → clips for the best,
    honouring min_score, no overlaps, and the job's max_clips cap."""
    job = db.one("SELECT * FROM jobs WHERE id=?", job_id)
    weights = {r["part"]: r["weight"] for r in db.many("SELECT * FROM rubric")}
    existing = db.many("SELECT * FROM clips WHERE job_id=? AND status NOT IN ('rejected','failed')",
                       job_id)
    accepted, rejected = [], []
    def weighted(s):
        parts = s.get("parts")
        if parts:                                      # weighted 0–10 from the five parts
            tot = sum(weights.get(k, 1) * float(v) for k, v in parts.items())
            mx = sum(weights.get(k, 1) * 2 for k in parts)
            if mx:
                return round(10 * tot / mx, 2)
        return float(s.get("score", 0))

    for s in sorted(scores, key=lambda s: -weighted(s)):
        cid = int(s["candidate_id"])
        score = weighted(s)
        st, en = float(s["start"]), float(s["end"])
        reason = s.get("reason", "")
        why = None
        if not reason:
            why = "no reason given"
        elif score < job["min_score"]:
            why = f"score {score} < {job['min_score']}"
        elif not (8 <= en - st <= 75):
            why = f"window {en - st:.1f}s outside 8–75 s"
        elif any(st < c["end"] and en > c["start"] for c in existing + accepted):
            why = "overlaps a kept clip"
        elif len(existing) + len(accepted) >= job["max_clips"]:
            why = "clip cap reached"
        if why:
            db.exec_("UPDATE candidates SET status='rejected', score=?, reason=? WHERE id=?",
                     score, f"{reason} [{why}]", cid)
            rejected.append({"candidate_id": cid, "why": why})
            continue
        n = len(existing) + len(accepted) + 1
        clip_id = f"{job_id}-c{n:02d}"
        while db.one("SELECT id FROM clips WHERE id=?", clip_id):
            n += 1
            clip_id = f"{job_id}-c{n:02d}"
        d = paths.clip_dir(job_id, clip_id)
        import time
        db.exec_("INSERT INTO clips(id, job_id, candidate_id, status, score, reason, start, end, "
                 "tease, dir, data, created, updated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 clip_id, job_id, cid, "scored", score, reason, st, en, int(bool(s.get("tease"))),
                 str(d), json.dumps({"spoiler": bool(s.get("spoiler")),
                                     "pillar": s.get("pillar", "gameplay clip"),
                                     "parts": s.get("parts")}), time.time(), time.time())
        db.exec_("UPDATE candidates SET status='accepted', score=?, reason=? WHERE id=?",
                 score, reason, cid)
        accepted.append({"id": clip_id, "start": st, "end": en, "score": score})
    return {"accepted": accepted, "rejected": rejected}
