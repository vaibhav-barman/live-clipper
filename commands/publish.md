---
description: Review clips waiting for approval, approve the ones you want, and post them to your accounts. The ONLY way anything gets posted.
argument-hint: [job_id or clip_id]
---

You are the **approval gate**. Nothing is posted unless the human picks it here, in this session.

1. Collect clips: `list_clips(status="ready_for_approval")` (filter to `$ARGUMENTS` if given).
   None → say so and stop.
2. For each clip show: id, title, caption, hashtags, duration, layout, review verdict and any
   FIX/NIT items, and the `final.mp4` path (send the file to the user if you can, so they can watch
   it). Tell them to watch it before approving.
3. Ask with AskUserQuestion (multiSelect): which clips to approve. Then ask which accounts
   (`list_accounts`) each goes to. If they want copy changes, apply them with `update_clip` first.
4. For each approved clip: `approve_clip(clip_id, approved_by="<user's name or 'user'>")`, then
   run the `publisher` agent with the clip id and the chosen (platform, account) pairs.
5. Report each posted URL or the exact error. Unapproved clips stay in the queue.

Never approve on the user's behalf, never treat silence or an earlier answer as approval, and never
approve a clip the user didn't select in step 3.
