---
name: growth-loop
description: "The learning loop for the clip page: log every post, read metrics at 12 h / 24 h / 72 h, run ONE one-variable test per day, no verdict under 24 h, daily and weekly reviews by pillar, slot and platform, write lessons as rules in learning.md, and judge posts on non-follower reach. Use for daily reports, weekly reviews, picking today's test, and proposing rubric changes."
---

# GROWTH LOOP — make every post teach the next one

Adapted with credit from Parker's (@DotComParker) faceless clipping-page setup prompt. Kept: the
scoreboard columns, 12/24/72 h reads, one test a day, the daily and weekly reviews, learning.md.
Changed: reads are automated (`fetch_stats` files each read in its age bucket) and the scoreboard
is exported from the ledger (`export_scoreboard`).

## The rules

1. **Never guess a number.** If a metric isn't available it stays blank. A blank is honest; a
   plausible number poisons every later decision.
2. **Reads at 12 h, 24 h, 72 h.** `fetch_stats` keeps the first read past each mark. Call it a
   few times a day (`/clip-report` does).
3. **One test per day, one variable.** Hook style, clip length, posting time, caption length,
   layout (split vs gameplay-only), tease vs no tease. Name it (`length-15-vs-30`) and tag the
   day's clips with `update_clip(..., {"data": {"test_name": ...}})`.
4. **No verdict under 24 h.** Prefer the 72 h read if the post is still moving.
5. **Judge on reach to non-followers**, not follower count. A new page grows from people who don't
   follow it yet. Early engagement on a re-purposed account will be low — that's expected.
6. **Daily review (evening):** best and worst post, one lesson written as a RULE, tomorrow's test.
7. **Weekly review:** top 3 and bottom 3, median views by pillar, slot and platform. Double down on
   what's above median; cut or rework what's been below median for a full week; pick next week's
   tests. Write it under "Weekly reviews".
8. **learning.md is the memory.** `add_learning("Current Rules", ...)` only with evidence (n, the
   median difference). Scouts and copywriters read Current Rules before deciding.
9. **Study 3–5 bigger pages weekly** (the user tells you which): copy formats, hooks and timing —
   never wording.
10. **Quality beats volume.** Skip a slot rather than post something weak or unverified.

## Starting rules (test them, they aren't law)

From a real GTA fan page's early weeks: official trailer clips beat number-only text posts;
credited creator clips and HOW-TO utility posts pull saves and shares; emotional one-liners pull big
like ratios. For this plugin's clips, start testing: hook stamp ≤ 5 words vs longer; 15 s vs 30 s;
split vs gameplay-only; late-morning vs early-evening posting.

## Daily report shape (to the user)

```
Posted: 4 (YT 2, IG 2) · Top: <clip> 12.4k views at 24h (IG)
Lesson: <one rule>
Tomorrow's test: <name> — <variable A> vs <variable B>
Waiting for you: 3 clips to approve · 1 takedown to confirm
```
