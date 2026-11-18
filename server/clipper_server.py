#!/usr/bin/env python3
"""live-clipper MCP server ("clipper"). Deterministic machinery for the clip factory: the SQLite
ledger, ingest, signals, cut assembly, facecam detection, captions, render, review, publishing.
Agents decide; these tools do the work. Long jobs return a task_id — poll task_status."""
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastmcp import FastMCP  # noqa: E402

from clipper import analysis, db, media, paths, production, publish, tasks  # noqa: E402

mcp = FastMCP(
    "clipper",
    instructions=(
        "Clip-factory machinery. Read state from the ledger (get_job, get_clip, list_clips) — never "
        "trust chat summaries. Long tools return task_id: poll task_status(task_id, wait_s=50) until "
        "status is done/failed. publish_clip only works on clips a human approved via /publish."),
)
db.init()


def _job(job_id):
    j = db.one("SELECT * FROM jobs WHERE id=?", job_id)
    if not j:
        raise ValueError(f"no job {job_id}")
    return j


def _clip(clip_id):
    c = db.one("SELECT * FROM clips WHERE id=?", clip_id)
    if not c:
        raise ValueError(f"no clip {clip_id}")
    return c


# ------------------------------------------------------------------ general

@mcp.tool
def plugin_info() -> dict:
    """Absolute paths of the plugin, its skill scripts and the data folder, plus which tools are
    installed. Call this before running any skill script with Bash."""
    return {"plugin_root": str(paths.PLUGIN_ROOT), "data_home": str(paths.HOME),
            "scripts": {k: str(v) for k, v in paths.SCRIPTS.items()},
            "python": sys.executable, "sfx_dir": str(paths.SFX_DIR), "tools": media.tool_status()}


@mcp.tool
def task_status(task_id: str, wait_s: int = 0) -> dict:
    """Status of a background task. wait_s (≤55) blocks until it finishes or the wait ends."""
    return tasks.status(task_id, wait_s)


@mcp.tool
def stop_task(task_id: str) -> dict:
    """Stop a running background task (e.g. live recording)."""
    return tasks.stop(task_id)


# ------------------------------------------------------------------ jobs / ledger

@mcp.tool
def create_job(source: str, mode: str = "vod", max_clips: int = 5, min_score: float = 7.0,
               streamer: str = "", platform: str = "", keywords: Optional[list[str]] = None) -> dict:
    """Start a job. source = VOD/stream URL or a local video path. mode 'vod' or 'live'.
    max_clips is a CAP, not a quota. streamer/platform feed the credit strip."""
    if mode not in ("vod", "live"):
        raise ValueError("mode must be vod or live")
    jid = time.strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6]
    d = paths.job_dir(jid)
    db.exec_("INSERT INTO jobs(id, source, mode, status, max_clips, min_score, keywords, streamer, "
             "platform, dir, meta, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", jid, source, mode,
             "created", max_clips, min_score, json.dumps(keywords or []), streamer, platform,
             str(d), "{}", time.time())
    return {"job_id": jid, "dir": str(d)}


@mcp.tool
def get_job(job_id: str) -> dict:
    """Job, chunk progress, candidate counts and every clip with its status."""
    j = _job(job_id)
    j["chunks"] = {r["status"]: r["n"] for r in db.many(
        "SELECT status, COUNT(*) n FROM chunks WHERE job_id=? GROUP BY status", job_id)}
    j["candidates"] = {r["status"]: r["n"] for r in db.many(
        "SELECT status, COUNT(*) n FROM candidates WHERE job_id=? GROUP BY status", job_id)}
    j["clips"] = db.many("SELECT id, status, score, start, end, layout, review_verdict, attempts "
                         "FROM clips WHERE job_id=? ORDER BY id", job_id)
    j["recorded_until_s"] = (db.one("SELECT MAX(end) m FROM chunks WHERE job_id=?", job_id) or {}).get("m")
    return j


@mcp.tool
def list_jobs(limit: int = 10) -> list:
    """Most recent jobs."""
    return db.many("SELECT id, source, mode, status, max_clips, created FROM jobs "
                   "ORDER BY created DESC LIMIT ?", limit)


@mcp.tool
def get_clip(clip_id: str) -> dict:
    """Everything known about a clip: status, window, paths, geometry, review, post copy."""
    return _clip(clip_id)


@mcp.tool
def list_clips(job_id: Optional[str] = None, status: Optional[str] = None) -> list:
    """Clips, optionally filtered by job and/or status."""
    q, a = "SELECT id, job_id, status, score, start, end, layout, review_verdict, title FROM clips WHERE 1=1", []
    if job_id:
        q += " AND job_id=?"
        a.append(job_id)
    if status:
        q += " AND status=?"
        a.append(status)
    return db.many(q + " ORDER BY id", *a)


UPDATABLE = {"status", "layout", "title", "caption", "hashtags", "reason", "attempts"}


@mcp.tool
def update_clip(clip_id: str, fields: dict) -> dict:
    """Set clip fields: status, layout, title, caption, hashtags, reason, attempts, and a 'data'
    dict merged into the clip's data (e.g. notes, findings). 'approved' cannot be set here."""
    _clip(clip_id)
    f = dict(fields)
    data = f.pop("data", None)
    bad = set(f) - UPDATABLE
    if bad:
        raise ValueError(f"not updatable: {sorted(bad)}")
    if f.get("status") in ("approved", "published"):
        raise ValueError("approval happens only through approve_clip after a human says yes")
    if f.get("status") and f["status"] not in db.CLIP_STATUSES:
        raise ValueError(f"status must be one of {db.CLIP_STATUSES}")
    if f:
        db.set_clip(clip_id, **f)
    if data:
        db.merge_clip_data(clip_id, **data)
    return _clip(clip_id)


# ------------------------------------------------------------------ Graph 1 · Ingest

@mcp.tool
def ingest_vod(job_id: str) -> dict:
    """Download (yt-dlp) or take the local file, normalise to CFR 30 / H.264 / AAC 48k, split into
    60 s chunks, grab chat replay when the site offers it. Background → task_id."""
    _job(job_id)
    return {"task_id": tasks.start("ingest_vod", {"job_id": job_id}, job_id=job_id)}


@mcp.tool
def start_live(job_id: str) -> dict:
    """Record the live stream (streamlink → ffmpeg) into 60 s CFR chunks until stop_live.
    Background → task_id. Chunks appear in get_job/list_chunks as they finish."""
    j = _job(job_id)
    if j["mode"] != "live":
        raise ValueError("job is not a live job")
    tid = tasks.start("live_ingest", {"job_id": job_id}, job_id=job_id)
    meta = j.get("meta") or {}
    meta["live_task"] = tid
    db.exec_("UPDATE jobs SET meta=? WHERE id=?", json.dumps(meta), job_id)
    return {"task_id": tid}


@mcp.tool
def stop_live(job_id: str) -> dict:
    """Stop recording a live job."""
    tid = (_job(job_id).get("meta") or {}).get("live_task")
    if not tid:
        raise ValueError("no live recording for this job")
    return tasks.stop(tid)


@mcp.tool
def list_chunks(job_id: str, status: Optional[str] = None) -> list:
    """Chunks with their status (new → transcribed → analyzed)."""
    q = "SELECT id, idx, start, end, status FROM chunks WHERE job_id=?"
    return db.many(q + (" AND status=?" if status else "") + " ORDER BY idx",
                   *([job_id, status] if status else [job_id]))


@mcp.tool
def transcribe_chunks(job_id: str, chunk_ids: Optional[list[int]] = None) -> dict:
    """Fast transcription (for scouting) of new chunks, stream-time words. Background → task_id."""
    return {"task_id": tasks.start("transcribe_chunks", {"job_id": job_id, "chunk_ids": chunk_ids},
                                   job_id=job_id)}


@mcp.tool
def analyze_signals(job_id: str) -> dict:
    """Loudness spikes, scene cuts, chat bursts and hype keywords on transcribed chunks →
    candidate moments. Background → task_id."""
    return {"task_id": tasks.start("analyze_signals", {"job_id": job_id}, job_id=job_id)}


@mcp.tool
def get_candidates(job_id: str, limit: int = 15, live_margin_s: float = 0) -> list:
    """New candidates (strongest signal first) with ±30 s of transcript and signal features.
    Live: pass live_margin_s=45 so only fully-recorded moments come back."""
    ready = None
    if live_margin_s:
        m = (db.one("SELECT MAX(end) m FROM chunks WHERE job_id=?", job_id) or {}).get("m") or 0
        ready = m - live_margin_s
    return analysis.candidates_for_scout(job_id, limit, ready)


@mcp.tool
def get_rubric() -> dict:
    """Current weights for the five hook-rubric parts (tuned by the feedback-analyst)."""
    return {r["part"]: r["weight"] for r in db.many("SELECT * FROM rubric")}


@mcp.tool
def save_scores(job_id: str, scores: list[dict]) -> dict:
    """Hook-scout results: [{candidate_id, parts:{hook,payoff,self_contained,reaction,shareability}
    (0–2 each) or score (0–10), reason, start, end, tease}]. Enforces reason required, min_score,
    no overlaps, window length and the clip cap; accepted ones become clips."""
    return analysis.save_scores(job_id, scores)


# ------------------------------------------------------------------ Graph 2 · Production

@mcp.tool
def prepare_clip(clip_id: str) -> dict:
    """Window ±5 s → window.mp4, mix.wav, voice16k.wav (Demucs), words.json (WhisperX, window
    seconds) in the clip folder. Background → task_id."""
    _clip(clip_id)
    return {"task_id": tasks.start("prepare_clip", {"clip_id": clip_id}, clip_id=clip_id)}


@mcp.tool
def assemble_cut(clip_id: str) -> dict:
    """Build cut.mp4 + cut_mix.wav + cut_voice16k.wav + sections.txt from the clip's cut.json
    (pieces in WINDOW seconds, from build_wx2.py). Frame-exact video, sample-exact audio with the
    flagged micro-fades. Background → task_id."""
    c = _clip(clip_id)
    if not (Path(c["dir"]) / "cut.json").exists():
        raise ValueError("write cut.json first (shortform-cutaway skill)")
    return {"task_id": tasks.start("assemble_cut", {"clip_id": clip_id}, clip_id=clip_id)}


@mcp.tool
def detect_facecam(clip_id: str) -> dict:
    """Find the facecam rectangle (or a full-frame face) in the clip. Returns rects in source px
    and check_image — READ that image and confirm the yellow box is the camera before trusting it."""
    _clip(clip_id)
    return production.detect_facecam(clip_id)


@mcp.tool
def set_geometry(clip_id: str, facecam: Optional[list[int]] = None, face: Optional[list[int]] = None,
                 full_frame_face: Optional[list[int]] = None, game_center: Optional[list[int]] = None) -> dict:
    """Override/confirm geometry in source px: facecam [x,y,w,h], face [x,y,w,h] (median face box),
    full_frame_face for IRL shots, game_center [x,y] for the gameplay crop."""
    kv = {k: v for k, v in dict(facecam=facecam, face=face, full_frame_face=full_frame_face,
                                game_center=game_center).items() if v is not None}
    return db.merge_clip_data(clip_id, **kv)


@mcp.tool
def make_captions(clip_id: str, max_words: int = 3) -> dict:
    """Draft captions.json from the window's words mapped through cut.json (frames, `to` exclusive),
    grouped by caption-align's rules. The captioner then checks and edits the file."""
    _clip(clip_id)
    return production.make_captions(clip_id, max_words)


@mcp.tool
def render_clip(clip_id: str, layout: str = "auto", top_stamp: str = "", credit: Optional[str] = None,
                punch: bool = True, hook_zoom: bool = True, sfx: bool = True,
                caption_y: Optional[int] = None) -> dict:
    """Final 1080×1920 render: layout (auto|split|full|gameplay) per piece with static 1.00/1.12
    punch alternation, hook zoom-out on the opening only, captions + top stamp + credit strip
    burned in and exported alone with alpha (overlay.mov), peak-aligned SFX if a catalogue exists,
    two-pass loudnorm to −14 LUFS. Background → task_id."""
    c = _clip(clip_id)
    data = c.get("data") or {}
    opts = dict(layout=layout, top_stamp=top_stamp, credit=credit, punch=punch, hook_zoom=hook_zoom,
                sfx=sfx, caption_y=caption_y, game_center=data.get("game_center"))
    return {"task_id": tasks.start("render_clip", {"clip_id": clip_id, "options": opts}, clip_id=clip_id)}


@mcp.tool
def review_clip(clip_id: str) -> dict:
    """Run review_reel.py with every input the clip has. Returns verdict, FAIL/WARN/SKIP lists,
    report path and the two contact sheets for the vision reviewer. Background → task_id."""
    _clip(clip_id)
    return {"task_id": tasks.start("review_clip", {"clip_id": clip_id}, clip_id=clip_id)}


# ------------------------------------------------------------------ Graph 3 · Distribution

@mcp.tool
def list_accounts() -> list:
    """Configured posting accounts (names and platforms only)."""
    return [{"name": a["name"], "platform": a["platform"]} for a in publish.accounts()]


@mcp.tool
def approve_clip(clip_id: str, approved_by: str) -> dict:
    """Mark a clip approved. ONLY call this from /publish after the human explicitly said yes to
    this clip in this session. Approval expires after 24 h."""
    return publish.approve(clip_id, approved_by)


@mcp.tool
def publish_clip(clip_id: str, platform: str, account: str) -> dict:
    """Upload an APPROVED clip to youtube or instagram on the named account. Refuses unapproved or
    stale approvals and double posts. Background → task_id."""
    c = _clip(clip_id)
    publish._check_gate(c)
    return {"task_id": tasks.start("publish", {"clip_id": clip_id, "platform": platform,
                                               "account": account}, clip_id=clip_id)}


# ------------------------------------------------------------------ Graph 4 · Feedback

@mcp.tool
def fetch_stats(job_id: Optional[str] = None) -> list:
    """Pull views/likes/etc. for published clips and store them."""
    return publish.fetch_stats(job_id)


@mcp.tool
def feedback_table(limit: int = 50) -> list:
    """Published clips with their rubric score, reason and latest stats — the feedback-analyst's input."""
    return db.many("SELECT c.id, c.score, c.reason, c.layout, p.platform, p.stats, p.posted_at "
                   "FROM clips c JOIN posts p ON p.clip_id=c.id ORDER BY p.posted_at DESC LIMIT ?", limit)


@mcp.tool
def set_rubric(weights: dict) -> dict:
    """Update hook-rubric weights (each 0.5–2.0). Only the feedback-analyst calls this."""
    for k, v in weights.items():
        if k not in db.RUBRIC_DEFAULT:
            raise ValueError(f"unknown part {k}")
        db.exec_("UPDATE rubric SET weight=? WHERE part=?", float(min(2.0, max(0.5, v))), k)
    return {r["part"]: r["weight"] for r in db.many("SELECT * FROM rubric")}


if __name__ == "__main__":
    mcp.run()
