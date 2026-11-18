"""Graph 1 · Ingest — VOD download / live recording into 60 s chunks, plus chat when available."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import db, media, paths

CHUNK_S = 60


def _ytdlp():
    return [sys.executable, "-m", "yt_dlp"] if media.have("yt_dlp") else ["yt-dlp"]


def _streamlink():
    return [sys.executable, "-m", "streamlink"] if media.have("streamlink") else ["streamlink"]


def ingest_vod(job_id):
    job = db.one("SELECT * FROM jobs WHERE id=?", job_id)
    d = paths.job_dir(job_id)
    src = job["source"]
    raw = None
    if Path(src).expanduser().exists():
        raw = str(Path(src).expanduser())
        media.log("local source:", raw)
    else:
        media.log("downloading", src)
        media.run(_ytdlp() + ["-f", "bv*[height<=1080]+ba/b[height<=1080]/b", "--merge-output-format",
                              "mp4", "-o", str(d / "raw.%(ext)s"), src])
        raw = str(next(p for p in d.glob("raw.*") if p.suffix in (".mp4", ".mkv", ".webm")))
        # chat replay (YouTube) — optional, never fatal
        media.run(_ytdlp() + ["--skip-download", "--write-subs", "--sub-langs", "live_chat",
                              "-o", str(d / "chat"), src], check=False)
        _parse_live_chat(d)
    media.log("normalising to CFR 30 / H.264 / AAC 48k")
    media.normalize(raw, str(d / "source.mp4"))
    dur = media.duration(str(d / "source.mp4"))
    n = 0
    with db.conn() as c:
        t = 0.0
        while t < dur - 0.5:
            c.execute("INSERT OR IGNORE INTO chunks(job_id, idx, start, end, path, status) "
                      "VALUES (?,?,?,?,?,?)", (job_id, n, t, min(t + CHUNK_S, dur),
                                               str(d / "source.mp4"), "new"))
            t += CHUNK_S
            n += 1
    db.exec_("UPDATE jobs SET status='ingested' WHERE id=?", job_id)
    return {"source": str(d / "source.mp4"), "duration_s": round(dur, 2), "chunks": n,
            "chat": (d / "chat.json").exists()}


def _parse_live_chat(d):
    f = next(iter(d.glob("chat*.live_chat.json")), None)
    if not f:
        return
    msgs = []
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            o = json.loads(line)
            act = o["replayChatItemAction"]
            ms = int(act.get("videoOffsetTimeMsec", 0))
            for a in act["actions"]:
                item = a.get("addChatItemAction", {}).get("item", {})
                r = item.get("liveChatTextMessageRenderer")
                if r:
                    text = "".join(x.get("text", "") for x in r.get("message", {}).get("runs", []))
                    msgs.append({"t": ms / 1000, "text": text})
        except (KeyError, json.JSONDecodeError, ValueError):
            continue
    json.dump(msgs, open(d / "chat.json", "w", encoding="utf-8"))
    media.log(f"chat: {len(msgs)} messages")


def live_ingest(job_id):
    """Record a live stream into CFR 60 s chunks until stopped. Registers each finished chunk."""
    job = db.one("SELECT * FROM jobs WHERE id=?", job_id)
    d = paths.job_dir(job_id)
    cd = d / "chunks"
    cd.mkdir(exist_ok=True)
    sl = subprocess.Popen(_streamlink() + ["--stdout", job["source"], "best"], stdout=subprocess.PIPE)
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-i", "pipe:0", "-vf",
                           "scale=-2:'min(1080,ih)',fps=30,format=yuv420p", "-c:v", "libx264",
                           "-preset", "veryfast", "-crf", "20", "-force_key_frames",
                           f"expr:gte(t,n_forced*{CHUNK_S})", "-c:a", "aac", "-ar", "48000",
                           "-ac", "2", "-f", "segment", "-segment_time", str(CHUNK_S),
                           "-reset_timestamps", "1", str(cd / "chunk_%05d.mp4")], stdin=sl.stdout)
    db.exec_("UPDATE jobs SET status='live' WHERE id=?", job_id)
    t0 = time.time()
    try:
        while ff.poll() is None:
            _register_live_chunks(job_id, cd, final=False)
            time.sleep(5)
    finally:
        for p in (sl, ff):
            if p.poll() is None:
                p.terminate()
        _register_live_chunks(job_id, cd, final=True)
        db.exec_("UPDATE jobs SET status='live_ended' WHERE id=?", job_id)
    return {"recorded_s": round(time.time() - t0)}


def _register_live_chunks(job_id, cd, final):
    files = sorted(cd.glob("chunk_*.mp4"))
    if not final:
        files = files[:-1]                    # the newest segment is still being written
    with db.conn() as c:
        for f in files:
            idx = int(f.stem.split("_")[1])
            if c.execute("SELECT 1 FROM chunks WHERE job_id=? AND idx=?", (job_id, idx)).fetchone():
                continue
            try:
                dur = media.duration(str(f))
            except Exception:                  # noqa: BLE001
                continue
            c.execute("INSERT INTO chunks(job_id, idx, start, end, path, status) VALUES (?,?,?,?,?,?)",
                      (job_id, idx, idx * CHUNK_S, idx * CHUNK_S + dur, str(f), "new"))


def chunk_media(chunk):
    """(file, offset_in_file) for a chunk: VOD chunks are ranges of source.mp4, live chunks are files."""
    if chunk["path"].endswith("source.mp4"):
        return chunk["path"], chunk["start"]
    return chunk["path"], 0.0


def window_source(job_id, start, end, dst):
    """Cut [start, end] (stream seconds) out of the job's media into a normalised file."""
    job_d = paths.job_dir(job_id)
    src = job_d / "source.mp4"
    if src.exists():
        return media.normalize(str(src), dst, start=start, end=end)
    chunks = db.many("SELECT * FROM chunks WHERE job_id=? AND end>? AND start<? ORDER BY idx",
                     job_id, start, end)
    if not chunks:
        raise RuntimeError("no recorded media covers that window yet")
    lst = Path(dst).with_suffix(".txt")
    lst.write_text("".join(f"file '{c['path']}'\n" for c in chunks), encoding="utf-8")
    joined = Path(dst).with_suffix(".joined.mp4")
    media.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
               joined])
    off = chunks[0]["start"]
    media.normalize(str(joined), dst, start=start - off, end=end - off)
    joined.unlink(missing_ok=True)
    lst.unlink(missing_ok=True)
    return dst
