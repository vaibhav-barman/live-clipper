---
description: ONE LINK → clips → YouTube + Instagram. Runs the autopilot, then asks you ONCE which clips to post, and uploads the ones you tick. Nothing posts without that tick.
argument-hint: <link> [--clips 5] [--out ~/folder] [--minutes 120] [--rush] [--schedule]
---

Clip-and-post run for `$ARGUMENTS`. This is `/live-clipper:live-clipper` followed by
`/live-clipper:publish` in one go, with a single approval question at the end. Load `clip-router`
and `page-playbook` first and follow their rules — this command removes steps, never gates.

**0. Preflight (before any heavy work, no questions):**
- `list_accounts()` → pick the YouTube and Instagram accounts. If a platform has none, say so in
  one line ("no Instagram account in accounts.json — will post YouTube only") and carry on; if
  neither exists, say clips will still be made and point to /live-clipper:clip-setup, and go on.
- `plugin_info().tools`: if `google_api` (YouTube) is False, or `boto3` / `CLIPPER_S3_BUCKET`
  (Instagram) is missing, note it now so the user can fix it while clips render.

**1–5. Make the clips:** run `/live-clipper:live-clipper` steps 1–5 exactly (probe → creator check →
`create_job` → VOD or live pipeline → copywriter → `deliver_clip` with a one-line ✓ per clip).
Clips land in `<output>/live-clipper/<creator>/`. Do not ask anything during this part.

**6. The one approval question.** When every clip is either `ready_for_approval` or `needs_human`:
- Show a compact table: id, delivered file name, score, duration, review verdict, spoiler flag,
  and the YouTube title + Instagram caption first line (`data.copy`). Give the folder path and
  tell them to watch the files before ticking.
- If the creator's permission is not `granted`, say so on one line above the question
  ("permission for @x is <status> — only post if you have it").
- AskUserQuestion, **multiSelect**, one option per clip ("02 · He did NOT see that · 8.4 · 0:38"),
  question: "Which clips should I post to YouTube + Instagram now?" Add a second single-select
  question only if `--schedule` was passed: "Post now, or use the growth-planner's next slots?"
- Nothing ticked (or they dismiss it) → stop. Report the folder and say
  `/live-clipper:publish` can post them later. Silence is never a yes.

**7. Post what was ticked — and only that:**
- For each ticked clip: `approve_clip(clip_id, approved_by="<user's name or 'user'>")`.
- Run the `publisher` agent with the clip id and the list `(youtube, <yt account>, now|slot)`,
  `(instagram, <ig account>, now|slot)` — only platforms that have an account. With `--schedule`,
  get slots from the `growth-planner` agent first.
- Copy edits the user typed in the "Other" box → `update_clip` + `check_copy` before approving.

**8. Final report:** folder path; per clip → file, YouTube URL, Instagram URL (or scheduled time,
or the exact error); unticked and `needs_human` clips with reasons; the permission note if it
applies. If anything was scheduled, remind them to run /live-clipper:clip-post-due (or schedule it).

Hard rules: never approve a clip the user didn't tick in step 6 of THIS run; never post for a
denied/blocked creator; a failed upload is retried at most once (a duplicate post is worse than a
delay); TikTok / X / Threads are not posted here — use /live-clipper:publish for post kits.
