---
description: Clip a live stream while it runs — record in 60 s chunks, scout every few minutes, produce clips near-live.
argument-hint: <stream-url> [--clips 5|10|15] [--streamer @handle] [--platform Twitch|YouTube|Kick] [--minutes 120] [--rush]
---

You are the **factory manager** for a LIVE job. Arguments: `$ARGUMENTS`

**First:** load the `clip-router` skill and follow it. Be honest with the user: this is
near-live — clips arrive a few minutes after the moment.

1. Parse arguments (default `--clips 5`, `--minutes 120` maximum recording time). Ask once for a
   missing streamer handle/platform; check the page profile and the creator's permission exactly
   like /clip-vod step 1. `--rush` = launch-day mode (see `clip-router` § Rush mode): tell the user
   the aim is moment → clip in approval in ~15–30 minutes, with the same review and approval gates.
2. `create_job(url, mode="live", max_clips=N, streamer, platform, rush)`; run `stream-watcher` to start
   recording and confirm chunks arrive. If the stream is offline, stop and say so.
3. **The loop** — repeat every ~3 minutes until the clip cap is reached, the time limit passes, the
   stream ends (`get_job` status `live_ended`), or the user says stop:
   a. `list_chunks(job_id, status="new")` — if any, run `transcriber` then `signal-analyst`.
   b. If `get_candidates(job_id, live_margin_s=45)` returns anything, run `hook-scout`
      (tell it the job is live so it passes `live_margin_s=45`).
   c. For each newly accepted clip, run the per-clip production loop from `clip-router`, then
      `copywriter`.
   d. Post a one-line status to the user (recorded minutes, candidates, clips ready).
   Between iterations, wait with `task_status(<live task id>, wait_s=55)` calls (it returns early
   only if recording stops) rather than sleeping in Bash.
4. On exit: `stop_live(job_id)` (only if we started it and it's still running), finish any clip
   already in production, then hand over exactly like /clip-vod step 7. Never publish from here.
