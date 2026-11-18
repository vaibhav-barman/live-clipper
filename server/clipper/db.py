"""The SQLite ledger — the factory floor. Every agent reads its inputs here and writes results back."""
import json
import sqlite3
import time
from contextlib import contextmanager

from . import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
  id TEXT PRIMARY KEY, source TEXT, mode TEXT, status TEXT, max_clips INTEGER, min_score REAL,
  keywords TEXT, streamer TEXT, platform TEXT, dir TEXT, meta TEXT, created REAL);
CREATE TABLE IF NOT EXISTS chunks(
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, idx INTEGER, start REAL, end REAL,
  path TEXT, status TEXT, words_path TEXT, UNIQUE(job_id, idx));
CREATE TABLE IF NOT EXISTS candidates(
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, t_peak REAL, start REAL, end REAL,
  features TEXT, signal_score REAL, status TEXT, score REAL, reason TEXT);
CREATE TABLE IF NOT EXISTS clips(
  id TEXT PRIMARY KEY, job_id TEXT, candidate_id INTEGER, status TEXT, score REAL, reason TEXT,
  start REAL, end REAL, tease INTEGER, layout TEXT, dir TEXT, data TEXT, title TEXT,
  caption TEXT, hashtags TEXT, review_verdict TEXT, review_report TEXT, attempts INTEGER DEFAULT 0,
  approved_at REAL, approved_by TEXT, created REAL, updated REAL);
CREATE TABLE IF NOT EXISTS tasks(
  id TEXT PRIMARY KEY, kind TEXT, job_id TEXT, clip_id TEXT, args TEXT, status TEXT,
  pid INTEGER, log TEXT, result TEXT, started REAL, finished REAL);
CREATE TABLE IF NOT EXISTS posts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, clip_id TEXT, platform TEXT, account TEXT,
  remote_id TEXT, url TEXT, status TEXT, posted_at REAL, stats TEXT, stats_at REAL);
CREATE TABLE IF NOT EXISTS rubric(part TEXT PRIMARY KEY, weight REAL);
"""

RUBRIC_DEFAULT = {"hook": 1.0, "payoff": 1.0, "self_contained": 1.0, "reaction": 1.0,
                  "shareability": 1.0}

CLIP_STATUSES = ["scored", "preparing", "prepared", "cut", "audited", "geometry", "rendered",
                 "reviewed", "ready_for_approval", "approved", "published", "rejected",
                 "needs_human", "failed"]


@contextmanager
def conn():
    paths.ensure()
    c = sqlite3.connect(paths.DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)
        for k, v in RUBRIC_DEFAULT.items():
            c.execute("INSERT OR IGNORE INTO rubric(part, weight) VALUES (?, ?)", (k, v))


def row(r):
    if r is None:
        return None
    d = dict(r)
    for k in ("keywords", "meta", "features", "data", "args", "result", "stats"):
        if k in d and isinstance(d[k], str):
            try:
                d[k] = json.loads(d[k])
            except json.JSONDecodeError:
                pass
    return d


def one(sql, *a):
    with conn() as c:
        return row(c.execute(sql, a).fetchone())


def many(sql, *a):
    with conn() as c:
        return [row(r) for r in c.execute(sql, a).fetchall()]


def exec_(sql, *a):
    with conn() as c:
        cur = c.execute(sql, a)
        return cur.lastrowid


def clip_data(clip_id):
    r = one("SELECT data FROM clips WHERE id=?", clip_id)
    return (r or {}).get("data") or {}


def merge_clip_data(clip_id, **kv):
    d = clip_data(clip_id)
    d.update({k: v for k, v in kv.items()})
    exec_("UPDATE clips SET data=?, updated=? WHERE id=?", json.dumps(d), time.time(), clip_id)
    return d


def set_clip(clip_id, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    exec_(f"UPDATE clips SET {cols}, updated=? WHERE id=?", *fields.values(), time.time(), clip_id)
