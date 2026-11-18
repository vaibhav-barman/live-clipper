---
description: Pull stats for published clips and let the feedback-analyst propose hook-rubric weight changes.
---

1. Run the `feedback-analyst` agent.
2. Show its evidence table and proposed weights next to the current ones (`get_rubric`).
3. Ask the user (AskUserQuestion): apply, adjust, or skip. Apply only what they approve with
   `set_rubric(weights)`, and report the new weights.
