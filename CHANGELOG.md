# Changelog

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
