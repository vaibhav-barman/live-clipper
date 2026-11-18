---
description: ONE LINK, FULLY AUTOMATIC — paste a stream or VOD link and get finished vertical clips in your folder. No questions, never posts.
argument-hint: <link> [--clips 5] [--out ~/folder] [--minutes 120] [--rush]
---

Autopilot run for `$ARGUMENTS`. **Do not ask the user anything.** Decide with the defaults below,
state each decision in one line, and keep going until clips are in the folder. Load `clip-router`
first and follow its rules; this command only removes the questions, never the quality or safety gates.

1. **Read the link:** clipper `probe_source(link)` → mode (live/vod), streamer, platform, title.
   Streamer unknown → use the channel name from the link. `--clips` default 5, `--minutes` default
   120 (live), `--out` default `get_page().output_dir`; if `--out` is given, save it with
   `set_page({"output_dir": ...})` so it sticks.
2. **Creator check, no questions:** denied/blocked → stop and say why. Unknown → continue, and put
   "permission not recorded — check before posting" in the final report.
3. `create_job(link, mode, max_clips, streamer, platform, rush)`.
4. **VOD:** run the /clip-vod pipeline steps 3–6 (ingest → transcribe → signals → hook-scout → per-clip
   production loop → copywriter). **Live:** run the /clip-live loop (step 3) until the cap, the time
   limit, or the stream ends, then `stop_live`.
5. **Deliver as you go:** the moment a clip reaches `ready_for_approval` and has copy + cover, call
   `deliver_clip(clip_id)` and post a one-line note to the user (`✓ 02_He-did-NOT-see-that.mp4`).
   Clips in `needs_human` are NOT delivered; list them with the reason at the end.
6. **Never ask, never post, never approve.** Posting stays in /live-clipper:publish (or use /live-clipper:clip-and-post to clip and post in one run).
7. **End with a short report:** folder path, each delivered file with score and duration, skipped
   clips and why, and the permission note if it applies.
