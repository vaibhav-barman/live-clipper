---
description: Pull 12/24/72 h stats, export the scoreboard, review what worked by pillar, slot and platform, and decide which lessons and rubric changes to keep.
argument-hint: [--weekly]
---

**First:** load the `growth-loop` skill.

1. Run the `feedback-analyst` agent (tell it whether this is the weekly review: `$ARGUMENTS`).
2. Show its evidence table, proposed learning.md rules and proposed rubric weights next to the
   current ones (`get_rubric`). Point out the scoreboard file (`~/.live-clipper/scoreboard.csv`).
3. Ask the user (AskUserQuestion): which lessons to keep and whether to apply, adjust, or skip the
   weights. Write kept lessons with `add_learning` and apply approved weights with `set_rubric`.
