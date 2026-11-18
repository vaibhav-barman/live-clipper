# Changelog

## 0.3.0 — 2026-11-18
- `/live-clipper:clip-and-post <link> [--schedule]`: the one-link autopilot, then a single checklist
  of finished clips; ticked clips are approved and posted to YouTube + Instagram (or scheduled).
- Windows support: `.mcp.json` launches `scripts/run_server.py` via `${CLIPPER_PYTHON:-python3}`;
  cross-platform `scripts/setup.py` (sets `CLIPPER_PYTHON` on Windows); background tasks use
  Windows process groups, a real liveness probe and `taskkill /T` to stop; UTF-8 everywhere for file
  and subprocess text; `reverb_throw.sh` ported to `reverb_throw.py`; `scripts/clip.cmd` / `clip.ps1`.
  `setup.sh` / `run_server.sh` remain as shims.
- Delivered clips now land in `<out>/live-clipper/<creator>/<date>_<nn>_<title>.mp4` (a custom
  `--out` gets a `live-clipper` folder inside it). Default folder is `~/Movies/live-clipper` on
  macOS and `~/Videos/live-clipper` on Windows/Linux. Same-day name clashes get a `-2` suffix.

## 0.2.1 — 2026-11-18
- One-link autopilot: `/live-clipper:live-clipper <link> [--out DIR]` detects live/VOD, asks nothing, delivers clips to your folder (`deliver_clip`, `probe_source`, `page.output_dir`), and `scripts/clip` for headless Terminal runs.

## 0.2.0 — 2026-11-18
- Page side, inspired by Parker's (@DotComParker) clipping-page playbook: page profile, creator
  permissions, same-day takedowns, per-platform copy enforced by `check_copy`, covers, scheduling
  (`schedule_post`, `run_due_posts`), post kits for TikTok/X/Threads/Buffer, 12/24/72 h stat reads,
  `scoreboard.csv`, `learning.md`, daily report with one test a day, rush mode for launch days.
- New: `growth-planner` agent; `page-playbook` and `growth-loop` skills; commands
  `/clip-page-setup`, `/clip-creators`, `/clip-takedown`, `/clip-report`, `/clip-post-due`.
- Hook windows default to 7–30 s; spoiler and pillar flags; transform and spoiler checks in review.

## 0.1.0 — 2026-11-18 (alpha)
- First release: 14 sub-agents, 7 commands, 11 skills, `clipper` MCP server (31 tools).
- VOD and near-live clipping, envelope-exact cuts, cut audit, facecam detection, three 9:16
  layouts, captions, review gate, approval-gated YouTube Shorts / Instagram Reels publishing,
  feedback loop for rubric weights.
