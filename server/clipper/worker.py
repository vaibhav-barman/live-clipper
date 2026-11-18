"""Runs one background task: python -m clipper.worker <task_id>."""
import json
import sys
import time
import traceback

from . import analysis, db, ingest, production, publish, render

KINDS = {
    "ingest_vod": lambda a: ingest.ingest_vod(a["job_id"]),
    "live_ingest": lambda a: ingest.live_ingest(a["job_id"]),
    "transcribe_chunks": lambda a: analysis.transcribe_chunks(a["job_id"], a.get("chunk_ids")),
    "analyze_signals": lambda a: analysis.analyze_signals(a["job_id"]),
    "prepare_clip": lambda a: production.prepare_clip(a["clip_id"]),
    "assemble_cut": lambda a: production.assemble_cut(a["clip_id"]),
    "render_clip": lambda a: render.render_clip(a["clip_id"], **a.get("options", {})),
    "review_clip": lambda a: render.review_clip(a["clip_id"]),
    "publish": lambda a: publish.publish(a["clip_id"], a["platform"], a["account"]),
}


def main(tid):
    t = db.one("SELECT * FROM tasks WHERE id=?", tid)
    args = t["args"] or {}
    try:
        res = KINDS[t["kind"]](args)
        db.exec_("UPDATE tasks SET status='done', result=?, finished=? WHERE id=?",
                 json.dumps(res, default=str), time.time(), tid)
        print("DONE", json.dumps(res, default=str)[:2000], flush=True)
    except Exception as e:                      # noqa: BLE001
        traceback.print_exc()
        db.exec_("UPDATE tasks SET status='failed', result=?, finished=? WHERE id=?",
                 json.dumps({"error": str(e)[-2000:]}), time.time(), tid)
        if t.get("clip_id") and t["kind"] in ("prepare_clip", "assemble_cut", "render_clip"):
            db.set_clip(t["clip_id"], status="failed")


if __name__ == "__main__":
    main(sys.argv[1])
