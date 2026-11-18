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

from . import db, media, paths

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
    if not (c.get("title") and c.get("caption")):
        raise RuntimeError("post copy missing — copywriter must set title and caption first")
    db.set_clip(clip_id, status="approved", approved_at=time.time(), approved_by=approved_by)
    return {"clip_id": clip_id, "status": "approved"}


def _check_gate(c):
    if c["status"] not in ("approved", "published"):
        raise RuntimeError("refused: clip is not approved by a human (/publish asks first)")
    if not c.get("approved_at") or time.time() - c["approved_at"] > APPROVAL_TTL_S:
        raise RuntimeError("refused: approval is older than 24 h — re-approve with /publish")


def publish(clip_id, platform, account_name):
    c = db.one("SELECT * FROM clips WHERE id=?", clip_id)
    _check_gate(c)
    acc = account(account_name)
    if acc["platform"] != platform:
        raise RuntimeError(f"account {account_name} is {acc['platform']}, not {platform}")
    if db.one("SELECT id FROM posts WHERE clip_id=? AND account=? AND status='published'",
              clip_id, account_name):
        raise RuntimeError("already published to that account")
    final = db.clip_data(clip_id)["final"]
    desc = c["caption"] + ("\n\n" + c["hashtags"] if c.get("hashtags") else "")
    if platform == "youtube":
        rid, url = _youtube_upload(acc, final, c["title"], desc)
    elif platform == "instagram":
        rid, url = _instagram_upload(acc, final, c["title"] + "\n\n" + desc)
    else:
        raise RuntimeError(f"unknown platform {platform}")
    db.exec_("INSERT INTO posts(clip_id, platform, account, remote_id, url, status, posted_at) "
             "VALUES (?,?,?,?,?,?,?)", clip_id, platform, account_name, rid, url, "published", time.time())
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

def fetch_stats(job_id=None):
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
                st = it[0]["statistics"] if it else {}
            else:
                import requests
                st = requests.get(f"{GRAPH}/{p['remote_id']}",
                                  params={"fields": "like_count,comments_count",
                                          "access_token": _ig_token(acc)}, timeout=30).json()
                ins = requests.get(f"{GRAPH}/{p['remote_id']}/insights",
                                   params={"metric": "views,reach,saved,shares",
                                           "access_token": _ig_token(acc)}, timeout=30).json()
                for m in ins.get("data", []):
                    st[m["name"]] = (m.get("values") or [{}])[0].get("value")
            db.exec_("UPDATE posts SET stats=?, stats_at=? WHERE id=?", json.dumps(st), time.time(), p["id"])
            out.append({"clip_id": p["clip_id"], "platform": p["platform"], "stats": st})
        except Exception as e:                 # noqa: BLE001
            out.append({"clip_id": p["clip_id"], "platform": p["platform"], "error": str(e)})
    return out
