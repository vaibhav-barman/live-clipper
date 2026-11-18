---
description: Review clips waiting for approval, approve the ones you want, and post now, schedule, or export a post kit. One of the two ways anything gets posted (the other is /clip-and-post, which ends in this same approval step).
argument-hint: [job_id or clip_id]
---

You are the **approval gate**. Nothing is posted unless the human picks it here, in this session.
**First:** load the `page-playbook` skill.

1. Collect clips: `list_clips(status="ready_for_approval")` (filter to `$ARGUMENTS` if given).
   None → say so and stop.
2. For each clip show: id, score, layout, duration, review verdict + FIX/NIT items, spoiler flag,
   the creator and their permission status, the copy per platform (`data.copy`) with its
   `check_copy` result, the cover, and the `final.mp4` path (send the file if you can). Tell them
   to watch it before approving. Creators with `unknown` permission get a one-line reminder.
3. Ask with AskUserQuestion (multiSelect): which clips to approve. Apply copy edits they ask for
   with `update_clip`, then `check_copy` again.
4. For each approved clip ask where and when: per platform → account (`list_accounts`) and
   **now** / **a time** (suggest the growth-planner's slots) / **post kit** (TikTok, X, Threads, or
   Buffer).
5. `approve_clip(clip_id, approved_by="<user's name or 'user'>")`, then run the `publisher` agent
   with the clip id and the chosen (platform, account, when) list.
6. Report each URL, scheduled time, or kit folder. Remind them to run /clip-post-due (or set it as a
   scheduled task) if anything is scheduled.

Never approve on the user's behalf, never treat silence or an earlier answer as approval, and never
approve a clip the user didn't select in step 3.
