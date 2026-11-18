---
description: Publish scheduled posts whose time has come. Safe to run often (e.g. as a scheduled task every 15 minutes).
---

Call clipper `run_due_posts()`. For each started task poll `task_status(task_id, wait_s=50)` and
report the URL or the error. If nothing is due, say when the next scheduled post is
(`daily_summary` → `scheduled`). This only posts clips the user already approved and scheduled in
/publish.
