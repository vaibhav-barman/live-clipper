"""The page side of the factory — inspired by Parker's (@DotComParker) faceless clipping-page
playbook: page identity, creator permissions and takedowns, per-platform copy rules, spoiler and
value-add checks, post kits for manual/Buffer uploads, the 12/24/72 h scoreboard and learning.md."""
import csv
import json
import re
import shutil
import sys
import time
from pathlib import Path

from . import db, media, paths

PAGE_FILE = paths.HOME / "page.json"
LEARNING = paths.HOME / "learning.md"
SCOREBOARD = paths.HOME / "scoreboard.csv"

# macOS keeps videos in ~/Movies; Windows and most Linux desktops use ~/Videos.
DEFAULT_OUTPUT = "~/Movies/live-clipper" if sys.platform == "darwin" else "~/Videos/live-clipper"

PAGE_DEFAULT = {
    "name": "", "handle": "", "niche": "", "platforms": ["youtube", "instagram"],
    "timezone": "Asia/Kolkata", "awake_hours": "09:00-23:00",
    "voice": "hype but clean; short punchy headlines; sentence case; one emoji max",
    "posts_per_day": {"youtube": 2, "instagram": 2, "tiktok": 2, "x": 4},
    "approval_rules": "every post needs approval in /publish",
    "not_affiliated_with": "",
    "credit_format": "🎥 @{creator}",
    "avoid_creators": [],
    "output_dir": DEFAULT_OUTPUT,
}

PLATFORM_RULES = {
    # hashtags: (min, max); title/caption limits; extra rules are in the page-playbook skill
    "youtube":   {"hashtags": (1, 5), "title_max": 100, "text_max": 4900, "max_len_s": 180},
    "instagram": {"hashtags": (3, 5), "text_max": 2200, "max_len_s": 180},
    "tiktok":    {"hashtags": (1, 5), "text_max": 2200, "max_len_s": 180},
    "x":         {"hashtags": (0, 0), "text_max": 280, "max_len_s": 140},
    "threads":   {"hashtags": (0, 1), "text_max": 500, "max_len_s": 300},
}

EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]")
BANNED_WORDS = ["official", "leak", "leaked", "play early", "free copy", "giveaway", "datamine"]


# ------------------------------------------------------------------ page profile

def get_page():
    page = dict(PAGE_DEFAULT)
    if PAGE_FILE.exists():
        page.update(json.load(open(PAGE_FILE, encoding="utf-8")))
    page["configured"] = PAGE_FILE.exists() and bool(page.get("name"))
    return page


def set_page(fields):
    page = get_page()
    page.pop("configured", None)
    unknown = set(fields) - set(PAGE_DEFAULT)
    if unknown:
        raise ValueError(f"unknown page fields: {sorted(unknown)}")
    page.update(fields)
    paths.ensure()
    PAGE_FILE.write_text(json.dumps(page, indent=1, ensure_ascii=False), encoding="utf-8")
    return get_page()


# ------------------------------------------------------------------ creators & permission

PERMISSIONS = ("unknown", "asked", "granted", "denied", "blocked")


def upsert_creator(handle, platform="", permission="unknown", notes=""):
    handle = handle.lstrip("@").lower()
    if permission not in PERMISSIONS:
        raise ValueError(f"permission must be one of {PERMISSIONS}")
    old = db.one("SELECT * FROM creators WHERE handle=?", handle)
    if old and old["permission"] == "blocked" and permission != "blocked":
        notes = (notes + " " if notes else "") + "(unblocked by user)"
    db.exec_("INSERT INTO creators(handle, platform, permission, notes, updated) VALUES (?,?,?,?,?) "
             "ON CONFLICT(handle) DO UPDATE SET platform=excluded.platform, "
             "permission=excluded.permission, notes=excluded.notes, updated=excluded.updated",
             handle, platform, permission, notes, time.time())
    return db.one("SELECT * FROM creators WHERE handle=?", handle)


def creator_permission(handle):
    if not handle:
        return "unknown"
    r = db.one("SELECT permission FROM creators WHERE handle=?", handle.lstrip("@").lower())
    return r["permission"] if r else "unknown"


def assert_creator_ok(handle):
    p = creator_permission(handle)
    if p in ("denied", "blocked"):
        raise RuntimeError(f"creator @{handle} is '{p}' — don't clip or post their content")
    return p


# ------------------------------------------------------------------ takedowns

def takedown(clip_id=None, creator=None, reason=""):
    """Same-day takedown: cancel scheduled posts, mark clips taken_down, block the creator, log it.
    Returns the live URLs the user must delete by hand (APIs here don't delete posts)."""
    if not clip_id and not creator:
        raise ValueError("give a clip_id or a creator")
    clips = []
    if clip_id:
        clips = [db.one("SELECT * FROM clips WHERE id=?", clip_id)]
        if not clips[0]:
            raise ValueError(f"no clip {clip_id}")
        job = db.one("SELECT streamer FROM jobs WHERE id=?", clips[0]["job_id"])
        creator = creator or (job or {}).get("streamer")
    if creator:
        h = creator.lstrip("@").lower()
        clips += db.many("SELECT c.* FROM clips c JOIN jobs j ON j.id=c.job_id "
                         "WHERE lower(replace(j.streamer,'@',''))=?", h)
        upsert_creator(h, permission="blocked", notes=f"takedown: {reason}")
    ids = sorted({c["id"] for c in clips if c})
    urls = []
    for cid in ids:
        for p in db.many("SELECT * FROM posts WHERE clip_id=?", cid):
            if p["status"] == "scheduled":
                db.exec_("UPDATE posts SET status='cancelled' WHERE id=?", p["id"])
            elif p["status"] == "published":
                db.exec_("UPDATE posts SET status='takedown_pending' WHERE id=?", p["id"])
                urls.append({"clip_id": cid, "platform": p["platform"], "account": p["account"],
                             "url": p["url"]})
        db.set_clip(cid, status="taken_down")
    db.exec_("INSERT INTO takedowns(clip_id, creator, reason, urls, created) VALUES (?,?,?,?,?)",
             clip_id, creator, reason, json.dumps(urls), time.time())
    return {"clips": ids, "creator_blocked": creator, "delete_these_now": urls,
            "note": "Delete each URL in the platform app today, then call confirm_takedown."}


def confirm_takedown(clip_id):
    db.exec_("UPDATE posts SET status='removed' WHERE clip_id=? AND status='takedown_pending'", clip_id)
    db.exec_("UPDATE takedowns SET resolved=? WHERE clip_id=? AND resolved IS NULL", time.time(), clip_id)
    return {"clip_id": clip_id, "status": "removed"}


# ------------------------------------------------------------------ copy rules

def _hashtags(text):
    return re.findall(r"(?<!\w)#\w+", text or "")


def _used_recently(clip_id, plat, first_line, days=7):
    rows = db.many("SELECT c.id, c.data FROM posts p JOIN clips c ON c.id=p.clip_id "
                   "WHERE p.status='published' AND p.posted_at>=? AND c.id<>?",
                   time.time() - days * 86400, clip_id)
    for r in rows:
        e = ((r.get("data") or {}).get("copy") or {}).get(plat) or {}
        t = "\n".join(str(v) for v in e.values()).strip().splitlines()
        if t and t[0].strip().lower() == first_line:
            return True
    return False


def check_copy(clip_id):
    """Per-platform copy checks from the page playbook. Returns problems per platform (empty = ok)."""
    c = db.one("SELECT * FROM clips WHERE id=?", clip_id)
    job = db.one("SELECT * FROM jobs WHERE id=?", c["job_id"])
    data = c.get("data") or {}
    copy = data.get("copy") or {}
    page = get_page()
    creator = (job.get("streamer") or "").lstrip("@")
    dur = (data.get("total_frames") or 0) / media.FPS
    out = {}
    targets = copy.keys() or page["platforms"]
    for plat in targets:
        rules = PLATFORM_RULES.get(plat)
        probs = []
        entry = copy.get(plat)
        if not rules:
            out[plat] = ["unknown platform"]
            continue
        if not entry:
            out[plat] = ["no copy written for this platform"]
            continue
        text = "\n".join(str(v) for v in entry.values())
        tags = _hashtags(text)
        lo, hi = rules["hashtags"]
        if not lo <= len(tags) <= hi:
            probs.append(f"{len(tags)} hashtags (want {lo}–{hi})")
        if len(EMOJI.findall(text.replace("🎥", ""))) > 1:
            probs.append("more than one emoji (credit camera excluded)")
        if creator and creator.lower() not in text.lower():
            probs.append(f"no credit line for @{creator}")
        low = text.lower()
        for w in BANNED_WORDS:
            if re.search(rf"\b{re.escape(w)}\b", low) and not ("not affiliated" in low and w == "official"):
                probs.append(f"contains '{w}'")
        first = (body_line := (text.strip().splitlines() or [""])[0].strip().lower())
        if first and _used_recently(clip_id, plat, first):
            probs.append("same opening line as a post in the last 7 days")
        if data.get("spoiler") and "spoiler" not in low:
            probs.append("clip is flagged spoiler: label it SPOILER in the caption")
        if plat == "youtube" and len(entry.get("title", "")) > rules["title_max"]:
            probs.append("title over 100 chars")
        body = entry.get("text") or entry.get("caption") or entry.get("description") or ""
        if len(body) > rules["text_max"]:
            probs.append(f"text over {rules['text_max']} chars")
        if dur and dur > rules["max_len_s"]:
            probs.append(f"clip is {dur:.0f}s, platform limit {rules['max_len_s']}s")
        out[plat] = probs
    ok = all(not v for v in out.values())
    db.merge_clip_data(clip_id, copy_check={"ok": ok, "problems": out, "at": time.time()})
    return {"ok": ok, "problems": out}


# ------------------------------------------------------------------ cover + post kit

def set_cover(clip_id, t):
    c = db.one("SELECT * FROM clips WHERE id=?", clip_id)
    d = Path(c["dir"])
    final = (c.get("data") or {}).get("final")
    if not final:
        raise ValueError("render the clip first")
    media.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{float(t):.3f}", "-i", final, "-frames:v", "1",
               "-q:v", "2", d / "cover.jpg"])
    db.merge_clip_data(clip_id, cover=str(d / "cover.jpg"), cover_t=float(t))
    return {"cover": str(d / "cover.jpg")}


def export_post_kit(clip_id):
    """A folder ready for manual or Buffer upload: video, cover, one text file per platform."""
    c = db.one("SELECT * FROM clips WHERE id=?", clip_id)
    if c["status"] not in ("approved", "scheduled", "published"):
        raise RuntimeError("post kits are only made for clips a human approved in /publish")
    data = c.get("data") or {}
    kit = Path(c["dir"]) / "post_kit"
    kit.mkdir(exist_ok=True)
    shutil.copy(data["final"], kit / f"{clip_id}.mp4")
    if data.get("cover"):
        shutil.copy(data["cover"], kit / "cover.jpg")
    for plat, entry in (data.get("copy") or {}).items():
        (kit / f"{plat}.txt").write_text("\n\n".join(f"{v}" for v in entry.values()), encoding="utf-8")
    (kit / "README.txt").write_text(
        "Upload the MP4 itself, never a link to someone else's post. Buffer/automations need a "
        "direct, public, permanent HTTPS URL to the MP4 — not a share page or an expiring link.\n")
    return {"kit": str(kit), "files": sorted(p.name for p in kit.iterdir())}


# ------------------------------------------------------------------ scoreboard + learning

COLS = ["post_id", "date", "time", "platform", "pillar", "format", "hook", "length_sec", "credit",
        "views_12h", "views_24h", "views_72h", "likes", "reposts_or_shares", "replies_or_comments",
        "saves_or_bookmarks", "followers_at_read", "test_name", "notes"]


def export_scoreboard():
    rows = db.many("SELECT p.*, c.data cdata, c.layout, j.streamer, j.id job FROM posts p "
                   "JOIN clips c ON c.id=p.clip_id JOIN jobs j ON j.id=c.job_id "
                   "WHERE p.status IN ('published','takedown_pending','removed') ORDER BY p.posted_at")
    page = get_page()
    with open(SCOREBOARD, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            cd = json.loads(r["cdata"]) if isinstance(r["cdata"], str) else (r["cdata"] or {})
            st = r.get("stats") or {}
            reads = st.get("reads", {}) if isinstance(st, dict) else {}
            latest = st.get("latest", {}) if isinstance(st, dict) else {}
            t = time.localtime(r["posted_at"] or 0)

            def g(bucket, k):
                v = (reads.get(bucket) or {}).get(k)
                return "" if v is None else v      # never guess a number
            w.writerow({
                "post_id": r["remote_id"], "date": time.strftime("%Y-%m-%d", t),
                "time": time.strftime("%H:%M", t), "platform": r["platform"],
                "pillar": cd.get("pillar", "gameplay clip"), "format": r.get("layout") or "",
                "hook": cd.get("top_stamp", ""), "length_sec": round((cd.get("total_frames") or 0) / media.FPS, 1),
                "credit": r.get("streamer") or "", "views_12h": g("12h", "views"),
                "views_24h": g("24h", "views"), "views_72h": g("72h", "views"),
                "likes": latest.get("likes", ""), "reposts_or_shares": latest.get("shares", ""),
                "replies_or_comments": latest.get("comments", ""), "saves_or_bookmarks": latest.get("saves", ""),
                "followers_at_read": "", "test_name": cd.get("test_name", ""), "notes": cd.get("notes", ""),
            })
    return {"scoreboard": str(SCOREBOARD), "rows": len(rows), "page": page.get("handle")}


SECTIONS = ("Wins", "Losses", "Current Rules", "Weekly reviews")


def get_learning():
    if not LEARNING.exists():
        return {"text": "", "note": "no lessons yet"}
    return {"text": LEARNING.read_text(encoding="utf-8")}


def add_learning(section, text):
    if section not in SECTIONS:
        raise ValueError(f"section must be one of {SECTIONS}")
    paths.ensure()
    if not LEARNING.exists():
        LEARNING.write_text("# learning.md\n\n" + "".join(f"## {s}\n\n" for s in SECTIONS), encoding="utf-8")
    doc = LEARNING.read_text(encoding="utf-8")
    line = f"- {time.strftime('%Y-%m-%d')}: {text.strip()}\n"
    marker = f"## {section}\n\n"
    i = doc.index(marker) + len(marker)
    doc = doc[:i] + line + doc[i:]
    LEARNING.write_text(doc, encoding="utf-8")
    return {"section": section, "added": line.strip()}


def daily_summary(hours=24):
    since = time.time() - hours * 3600
    posted = db.many("SELECT p.clip_id, p.platform, p.account, p.url, p.stats, p.posted_at, c.data "
                     "FROM posts p JOIN clips c ON c.id=p.clip_id WHERE p.posted_at>=? "
                     "AND p.status='published' ORDER BY p.posted_at", since)

    def views(p):
        st = p.get("stats") or {}
        return ((st.get("latest") or {}).get("views")) if isinstance(st, dict) else None
    top = max((p for p in posted if views(p) is not None), key=views, default=None)
    return {
        "posted": [{"clip_id": p["clip_id"], "platform": p["platform"], "url": p["url"],
                    "views": views(p), "test_name": (p.get("data") or {}).get("test_name")} for p in posted],
        "top_post": {"clip_id": top["clip_id"], "platform": top["platform"], "views": views(top)} if top else None,
        "waiting_for_approval": [r["id"] for r in db.many("SELECT id FROM clips WHERE status='ready_for_approval'")],
        "scheduled": db.many("SELECT clip_id, platform, account, scheduled_at FROM posts WHERE status='scheduled' "
                             "ORDER BY scheduled_at"),
        "needs_human": [r["id"] for r in db.many("SELECT id FROM clips WHERE status='needs_human'")],
        "failed_posts": db.many("SELECT clip_id, platform, account, error FROM posts WHERE status='failed'"),
        "open_takedowns": db.many("SELECT clip_id, creator, urls FROM takedowns WHERE resolved IS NULL"),
    }


# ------------------------------------------------------------------ delivery to the user's folder

def _safe(x):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", x or "").strip("-")[:60] or "clip"


def output_root(output_dir=None):
    """The 'live-clipper' folder clips are delivered into. A custom --out gets a live-clipper
    sub-folder unless it already is one, so every run lands in the same tidy tree."""
    out = Path(output_dir or get_page()["output_dir"]).expanduser()
    return out if out.name.lower() == "live-clipper" else out / "live-clipper"


def deliver_clip(clip_id, output_dir=None):
    """Copy a reviewed clip into the user's folder:
    <out>/live-clipper/<creator>/<date>_<nn>_<title>.mp4 plus the cover and a .txt with the
    per-platform copy and the review verdict. Never posts anything."""
    c = db.one("SELECT * FROM clips WHERE id=?", clip_id)
    job = db.one("SELECT * FROM jobs WHERE id=?", c["job_id"])
    data = c.get("data") or {}
    if not data.get("final"):
        raise ValueError("clip has no final render")
    creator = _safe((job.get("streamer") or "").lstrip("@")) if job.get("streamer") else "unknown-creator"
    folder = output_root(output_dir) / creator
    folder.mkdir(parents=True, exist_ok=True)
    n = clip_id.rsplit("-c", 1)[-1]
    date = time.strftime("%Y-%m-%d", time.localtime(job["created"]))
    base = f"{date}_{n}_{_safe(c.get('title') or data.get('top_stamp') or clip_id)}"
    name, k = base, 2
    while (folder / f"{name}.mp4").exists() and data.get("delivered_to") != str(folder / f"{name}.mp4"):
        name, k = f"{base}-{k}", k + 1           # two jobs, same creator, same day: never overwrite
    shutil.copy(data["final"], folder / f"{name}.mp4")
    if data.get("cover"):
        shutil.copy(data["cover"], folder / f"{name}_cover.jpg")
    lines = [f"clip: {clip_id}", f"score: {c.get('score')}  layout: {c.get('layout')}  review: {c.get('review_verdict')}",
             f"source: {job['source']}  credit: @{(job.get('streamer') or '').lstrip('@')}", ""]
    for plat, entry in (data.get("copy") or {}).items():
        lines += [f"== {plat} ==", *[str(v) for v in entry.values()], ""]
    (folder / f"{name}.txt").write_text("\n".join(lines), encoding="utf-8")
    db.merge_clip_data(clip_id, delivered_to=str(folder / f"{name}.mp4"))
    return {"file": str(folder / f"{name}.mp4"), "folder": str(folder)}
