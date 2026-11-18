---
description: Handle a takedown request the same day — cancel scheduled posts, block the creator, list every live post to delete.
argument-hint: <clip_id or @creator> [reason]
---

A creator or rights holder asked us to remove something. Act today, no argument.

1. `record_takedown(clip_id=... or creator=..., reason=...)` from `$ARGUMENTS`.
2. Show the user every URL in `delete_these_now` as a checklist — they delete each in the platform
   app now (the APIs here can't delete posts).
3. When they confirm, `confirm_takedown(clip_id)` for each clip.
4. Remind them: that creator is now `blocked`; only unblock with `/clip-creators` if the creator
   later gives permission.
