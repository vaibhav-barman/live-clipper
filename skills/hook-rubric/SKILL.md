---
name: hook-rubric
description: "How hook-scout scores candidate stream moments 0–10 for short-form potential, picks a rough window, and rejects moments that need outside context. Carries the scoring rubric, the window rules (15–60 s, payoff inside, first 2 s must hook), the overlap rule, and the allowed payoff tease. Use whenever candidate moments are scored or a clip window is chosen."
---

# HOOK RUBRIC — is this moment a clip?

> **THE JOB:** read ±30 s of transcript and signals around each candidate, score it, give a one-line
> reason, propose a window. A score without a reason is rejected by the loop check.

## Inputs (from the ledger, never from video)

- transcript words with times (voice stem), ±30 s around the candidate
- signals: loudness spike (dB over the rolling median), chat messages/sec vs baseline, emote bursts,
  scene cuts, keyword hits
- at most 3 still frames per candidate (only when the transcript alone is ambiguous)

## The score (0–10, sum of five parts)

| part | 0 | 1 | 2 |
|---|---|---|---|
| **Hook** — do the first 2 s grab on their own? | slow build-up | interesting but slow | instant: a shout, a reveal, a question, a fail |
| **Payoff** — is there a clear peak/punchline? | none | soft | unmistakable |
| **Self-contained** — makes sense with zero context? | needs the last hour | needs one line of setup | stands alone |
| **Reaction** — does the streamer/chat react? | flat | some | big (signals confirm it) |
| **Shareability** — would someone send it to a friend? | no | maybe | yes |

Keep only **≥ 7**. Below that, log it as `rejected` with the reason so the Feedback graph can learn.

## The window

- **15–60 s.** Shorter only if the whole moment is genuinely complete in less.
- **Start ≤ 2 s before the hook line**, not at the setup three minutes earlier.
- **End on the payoff's release** (the laugh dying, the sentence ending), never mid-reaction.
- **One idea per clip.** Two peaks 40 s apart are two clips if each stands alone.

## Overlap rule

Never score two windows that overlap. If two candidates overlap, keep the higher score and widen it
only if the result still obeys the window rules.

## The payoff tease (allowed, with limits)

A 0.8–1.5 s flash of the payoff at frame 0, then the clip plays **in order** from the hook. It must
read as an obvious repeat (the moment plays again in full later). Never use a tease to build a claim
the stream didn't make. Mark the clip `tease: true` so the cutter builds it.

## Reject outright

- anything needing context the clip can't show (inside jokes, "as I said earlier")
- moments that are mostly someone else's copyrighted video/music playing on stream
- private information on screen (addresses, DMs, phone numbers) — or flag for a blur
- harassment of a person, or anything the streamer asked chat not to clip
