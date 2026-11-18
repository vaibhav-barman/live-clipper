---
description: Show live-clipper jobs and clips — what's recording, in production, waiting for approval, published.
argument-hint: [job_id]
---

Show status for `$ARGUMENTS` (empty → the 5 most recent jobs via clipper `list_jobs`).
For each job: `get_job` → source, mode, status, recorded minutes, candidate counts, and a table of
clips (id, status, score, layout, review verdict). Then list clips in `ready_for_approval` and
`needs_human` across jobs (`list_clips(status=...)`). Keep it to tables; no commentary.
