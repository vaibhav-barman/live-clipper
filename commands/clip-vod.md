---
description: Clip a recorded stream (VOD URL or local file) into up to N vertical shorts with the full agent factory.
argument-hint: <url-or-path> [--clips 5|10|15] [--streamer NAME] [--platform Twitch|YouTube|Kick]
---

You are the **factory manager** for a VOD job. Arguments: `$ARGUMENTS`

**First:** load the `clip-router` skill and follow it — it has the pipeline order, the hard rules
and the per-clip production loop you will run below. Sub-agents can't launch sub-agents, so YOU
call each agent in order with the Agent tool (plugin agents are named `live-clipper:<agent>`).

1. **Parse arguments.** Default `--clips 5`. If the streamer name or platform is missing, ask once
   (AskUserQuestion) — the credit strip needs them. Ask whether they have permission to clip this
   streamer if it isn't obvious; if they say no, stop.
2. **Create the job:** clipper `create_job(source, mode="vod", max_clips=N, streamer, platform)`.
   Tell the user the job id. Create a task list: ingest, transcribe, signals, scout, then one task
   per clip as clips appear, then "approval queue".
3. **Graph 1 — Ingest:** run agents `stream-watcher` → `transcriber` → `signal-analyst`, each with
   the job id. Stop and report if ingest fails.
4. **Scout:** run `hook-scout` with the job id. If no clip is accepted, report the strongest
   rejected candidates and stop — a dull stream yielding nothing is a valid result.
5. **Graph 2 — per clip**, for each accepted clip id, run the per-clip production loop from
   `clip-router` (cutter → auditor → geometer → editor → captioner → renderer → critic, with the
   retry routing). Clips are independent: you may run two clips' agents in parallel, never two
   stages of the same clip.
6. **Graph 3 — copy:** for every clip that reached `ready_for_approval`, run `copywriter`.
7. **Hand over:** list each clip with score, layout, duration, review verdict + any FIX/NIT, and the
   path to `final.mp4`. Clips in `needs_human` get their findings. End with: "Run
   /live-clipper:publish to review and approve." Never publish from this command.
