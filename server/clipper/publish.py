"""Graph 3 · Distribution and Graph 4 · Feedback — accounts, the approval gate, YouTube Shorts and
Instagram Reels upload, stats.

Credentials (never in the plugin folder):
  ~/.live-clipper/accounts.json
    [{"name": "main-yt", "platform": "youtube"},
     {"name": "main-ig", "platform": "instagram", "ig_user_id": "1784...", "token_env": "IG_TOKEN_MAIN"}]
  ~/.live-clipper/credentials/youtube_client_secret.json   (OAuth desktop client from Google Cloud)
  ~/.live-clipper/credentials/youtube_<name>_token.json    (made by scripts/auth_youtube.py <name>)
  Instagram: a long-lived token in the env var named by token_env; the video must be at a public
  URL, so it is uploaded to S3 (CLIPPER_S3_BUCKET) and handed over as a 1-hour presigned link.
"""
import json
import os
import time
from pathlib import Path

from . import db, growth, media, paths

APPROVAL_TTL_S = 24 * 3600
GRAPH = "https://graph.facebook.com/v21.0"


def accounts():
    if not paths.ACCOUNTS.exists():
        return []
    return json.load(open(paths.ACCOUNTS))


def account(name):
    for a in accounts():
        if a["name"] == name:
            return a
    raise RuntimeError(f"no account '{name}' in {paths.ACCOUNTS}")


def approve(clip_id, approved_by):
    c = db.one("SELECT * FROM clips WHERE id=?", clip_id)
    if not c:
        raise RuntimeError(f"no clip {clip_id}")
    if c["status"] not in ("ready_for_approval", "approved"):
        raise RuntimeError(f"clip is '{c['status']}', not ready_for_approval")
    data = c.get("data") or {}
    if not (data.get("copy") or (c.get("title") and c.get("caption"))):
        raise RuntimeError("post copy missing — copywriter must write it first")
    chk = data.get("copy_check")
    if data.get("copy") and not (chk and chk.get("ok")):
        raise RuntimeError("copy hasn't passed check_copy — fix the problems first")
    job = db.one("SELECT streamer FROM jobs WHERE id=?", c["job_id"])
    growth.assert_creator_ok((job or {}).get("streamer"))
    db.set_clip(clip_id, status="approved", approved_at=time.time(), approved_by=approved_by)
    return {"clip_id": clip_id, "status": "approved"}


def _check_gate(c, scheduled=False):
    if c["status"] == "taken_down":
        raise RuntimeError("refused: clip was taken down")
    if c["status"] not in ("approved", "scheduled", "published"):
        raise RuntimeError("refused: clip is not approved by a human (/publish asks first)")
    if not scheduled and (not c.get("approved_at") or time.time() - c["approved_at"] > APPROVAL_TTL_S):
        raise RuntimeError("refused: approval is older than 24 h — re-approve with /publish")


def _copy_for(c, platform):
    entry = ((c.get("data") or {}).get("copy") or {}).get(platform)
    if entry:
        return entry
    desc = (c.get("caption") or "") + ("\n\n" + c["hashtags"] if c.get("hashtags") else "")
    return {"title": c.get("title") or "", "description": desc, "caption": (c.get("title") or "") + "\n\n" + desc}


def schedule(clip_id, platform, account_name, at_epoch):
    """Queue an approved clip for a time. The approval is checked NOW; run_due_posts posts it later."""
    c = db.one("SELECT * FROM clips WHERE id=?", clip_id)
    _check_gate(c)
    acc = account(account_name)
    if acc["platform"] != platform:
        raise RuntimeError(f"account {account_name} is {acc['platform']}, not {platform}")
    if at_epoch < time.time() - 60:
        raise RuntimeError("that time is in the past")
    if db.one("SELECT id FROM posts WHERE clip_id=? AND account=? AND status IN ('published','scheduled')",
              clip_id, account_name):
        raise RuntimeError("already published or scheduled to that account")
    pid = db.exec_("INSERT INTO posts(clip_id, platform, account, status, scheduled_at) VALUES (?,?,?,?,?)",
                   clip_id, platform, account_name, "scheduled", at_epoch)
    db.set_clip(clip_id, status="scheduled")
    from datetime import datetime
    from zoneinfo import ZoneInfo
    tz = growth.get_page()["timezone"]
    return {"post_id": pid, "clip_id": clip_id, "platform": platform, "account": account_name,
            "at": datetime.fromtimestamp(at_epoch, ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M ") + tz}


def due_posts():
    return db.many("SELECT * FROM posts WHERE status='scheduled' AND scheduled_at<=? ORDER BY scheduled_at",
                   time.time())


def publish(clip_id, platform, account_name, scheduled_post_id=None):
    c = db.one("SELECT * FROM clips WHERE id=?", clip_id)
    _check_gate(c, scheduled=scheduled_post_id is not None)
    job = db.one("SELECT streamer FROM jobs WHERE id=?", c["job_id"])
    growth.assert_creator_ok((job or {}).get("streamer"))
    acc = account(account_name)
    if acc["platform"] != platform:
        raise RuntimeError(f"account {account_name} is {acc['platform']}, not {platform}")
    if db.one("SELECT id FROM posts WHERE clip_id=? AND account=? AND status='published'",
              clip_id, account_name):
        raise RuntimeError("already published to that account")
    final = db.clip_data(clip_id)["final"]
    cp = _copy_for(c, platform)
    try:
        if platform == "youtube":
            rid, url = _youtube_upload(acc, final, cp.get("title", ""), cp.get("description") or cp.get("text", ""))
        elif platform == "instagram":
            rid, url = _instagram_upload(acc, final, cp.get("caption") or cp.get("text", ""))
        else:
            raise RuntimeError(f"no uploader for {platform} — use export_post_kit and upload by hand or Buffer")
    except Exception as e:
        if scheduled_post_id:
            db.exec_("UPDATE posts SET status='failed', error=? WHERE id=?", str(e)[-500:], scheduled_post_id)
        raise
    if scheduled_post_id:
        db.exec_("UPDATE posts SET remote_id=?, url=?, status='published', posted_at=? WHERE id=?",
                 rid, url, time.time(), scheduled_post_id)
    else:
        db.exec_("INSERT INTO posts(clip_id, platform, account, remote_id, url, status, posted_at) "
                 "VALUES (?,?,?,?,?,?,?)", clip_id, platform, account_name, rid, url, "published", time.time())
    if not db.one("SELECT id FROM posts WHERE clip_id=? AND status='scheduled'", clip_id):
        db.set_clip(clip_id, status="published")
    return {"clip_id": clip_id, "platform": platform, "account": account_name, "id": rid, "url": url}


# ------------------------------------------------------------------ YouTube

def _yt_creds(acc):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    tok = paths.CREDS / f"youtube_{acc['name']}_token.json"
    if not tok.exists():
        raise RuntimeError(f"no token for {acc['name']}: run scripts/auth_youtube.py {acc['name']}")
    creds = Credentials.from_authorized_user_file(str(tok))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        tok.write_text(creds.to_json())
    return creds


def _youtube_upload(acc, path, title, desc):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    yt = build("youtube", "v3", credentials=_yt_creds(acc), cache_discovery=False)
    body = {"snippet": {"title": title[:100], "description": desc[:4900], "categoryId": "20"},
            "status": {"privacyStatus": acc.get("privacy", "public"), "selfDeclaredMadeForKids": False}}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(path, chunksize=-1, resumable=True,
                                                        mimetype="video/mp4"))
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            media.log(f"upload {int(status.progress() * 100)}%")
    vid = resp["id"]
    return vid, f"https://youtube.com/shorts/{vid}"


# ------------------------------------------------------------------ Instagram

def _public_url(path):
    import boto3
    bucket = os.environ.get("CLIPPER_S3_BUCKET")
    if not bucket:
        raise RuntimeError("set CLIPPER_S3_BUCKET — Instagram needs the video at a public URL")
    key = f"live-clipper/{Path(path).parent.name}/{Path(path).name}"
    s3 = boto3.client("s3")
    s3.upload_file(path, bucket, key, ExtraArgs={"ContentType": "video/mp4"})
    return s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key},
                                     ExpiresIn=3600)


def _ig_token(acc):
    tok = os.environ.get(acc.get("token_env", ""))
    if not tok:
        raise RuntimeError(f"set the env var {acc.get('token_env')} to the Instagram access token")
    return tok


def _instagram_upload(acc, path, caption):
    import requests
    tok, uid = _ig_token(acc), acc["ig_user_id"]
    url = _public_url(path)
    r = requests.post(f"{GRAPH}/{uid}/media", data={"media_type": "REELS", "video_url": url,
                                                    "caption": caption[:2200], "access_token": tok},
                      timeout=60)
    r.raise_for_status()
    cid = r.json()["id"]
    for _ in range(60):                       # up to ~10 min of server-side processing
        s = requests.get(f"{GRAPH}/{cid}", params={"fields": "status_code", "access_token": tok},
                         timeout=30).json()
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram processing failed: {s}")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram processing timed out")
    r = requests.post(f"{GRAPH}/{uid}/media_publish", data={"creation_id": cid, "access_token": tok},
                      timeout=60)
    r.raise_for_status()
    mid = r.json()["id"]
    link = requests.get(f"{GRAPH}/{mid}", params={"fields": "permalink", "access_token": tok},
                        timeout=30).json().get("permalink", "")
    return mid, link


# ------------------------------------------------------------------ Feedback

def _norm(platform, st):
    """Normalise to views/likes/comments/shares/saves. Missing stays missing — never guess."""
    def num(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    if platform == "youtube":
        m = {"views": st.get("viewCount"), "likes": st.get("likeCount"), "comments": st.get("commentCount")}
    else:
        m = {"views": st.get("views"), "likes": st.get("like_count"), "comments": st.get("comments_count"),
             "shares": st.get("shares"), "saves": st.get("saved"), "reach": st.get("reach")}
    return {k: num(v) for k, v in m.items() if num(v) is not None}


def fetch_stats(job_id=None):
    """Read stats and file them under the 12 h / 24 h / 72 h bucket the post's age falls in."""
    q = "SELECT p.* FROM posts p JOIN clips c ON c.id=p.clip_id WHERE p.status='published'"
    rows = db.many(q + (" AND c.job_id=?" if job_id else ""), *([job_id] if job_id else []))
    out = []
    for p in rows:
        try:
            acc = account(p["account"])
            if p["platform"] == "youtube":
                from googleapiclient.discovery import build
                yt = build("youtube", "v3", credentials=_yt_creds(acc), cache_discovery=False)
                it = yt.videos().list(part="statistics", id=p["remote_id"]).execute()["items"]
                raw = it[0]["statistics"] if it else {}
            else:
                import requests
                raw = requests.get(f"{GRAPH}/{p['remote_id']}",
                                   params={"fields": "like_count,comments_count",
                                           "access_token": _ig_token(acc)}, timeout=30).json()
                ins = requests.get(f"{GRAPH}/{p['remote_id']}/insights",
                                   params={"metric": "views,reach,saved,shares",
                                           "access_token": _ig_token(acc)}, timeout=30).json()
                for m in ins.get("data", []):
                    raw[m["name"]] = (m.get("values") or [{}])[0].get("value")
            st = _norm(p["platform"], raw)
            age_h = (time.time() - (p["posted_at"] or time.time())) / 3600
            stats = p.get("stats") if isinstance(p.get("stats"), dict) else {}
            reads = stats.get("reads", {})
            bucket = "72h" if age_h >= 72 else "24h" if age_h >= 24 else "12h" if age_h >= 12 else None
            if bucket and bucket not in reads:          # first read past each mark is the one kept
                reads[bucket] = st
            stats = {"reads": reads, "latest": st, "age_h": round(age_h, 1)}
            db.exec_("UPDATE posts SET stats=?, stats_at=? WHERE id=?", json.dumps(stats), time.time(), p["id"])
            out.append({"clip_id": p["clip_id"], "platform": p["platform"], "age_h": round(age_h, 1),
                        "latest": st, "reads": reads})
        except Exception as e:                 # noqa: BLE001
            out.append({"clip_id": p["clip_id"], "platform": p["platform"], "error": str(e)})
    return out
