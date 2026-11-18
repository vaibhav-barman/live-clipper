---
description: Stop a live-clipper live recording.
argument-hint: [job_id]
---

Stop the live recording for job `$ARGUMENTS` (if empty, use the most recent job from
clipper `list_jobs` whose mode is live). Call `stop_live(job_id)`, then `get_job(job_id)` and report
recorded minutes and the clips' statuses. Clips already in production are not affected.
