---
name: page-playbook
description: "How the clip page itself runs: page identity and voice, credit-and-permission rules (credit is not permission), the transform rule (a credit or watermark alone is not enough), spoilers, leaks/piracy/early-play bans, not-affiliated wording, platform policies for monetising, per-platform copy rules and templates, length limits, and same-day takedowns. Use whenever writing post copy, choosing what to clip, picking a cover, or handling a creator request."
---

# PAGE PLAYBOOK — run the page people trust

> **THE ESSENCE:** grow through **speed and trust**, never leaks or fake news. Every clip is
> credited, transformed, accurate, and posted only with the creator's blessing and the user's yes.

Adapted with credit from Parker's (@DotComParker) faceless clipping-page setup prompt (shared
publicly Nov 17, 2026, transcribed by AI Automation Society). Kept: identity, credit/permission,
transform, spoiler, safety, copy and takedown rules. Changed: everything here is enforced in code
where it can be (`check_copy`, creator permissions, the approval gate, `record_takedown`).

## 1. Identity (from `get_page`)

- Distinct, searchable name; never copy a big page's display name (reads as impersonation).
- Bio wording: what we post + "Fan page. Not affiliated with <publisher/creator>." Never "official".
- Avatar and banner are our own art — never a publisher logo or official key art.
- **One niche angle** (funny moments / tips & hidden spots / fast news / cars). The scout favours
  moments that fit it; off-angle clips need a reason.
- Voice: hype but clean, short punchy headlines, sentence case, **one emoji max** (the 🎥 credit
  camera doesn't count). Never clickbait something the clip doesn't deliver.

## 2. Credit and permission

1. **Public content only.** Skip anything protected, deleted, or taken down.
2. **Credit every clip on its own line:** `🎥 @creator` (format in `page.credit_format`). Credit
   the person who made it, not the account that reposted it.
3. **Credit is not permission.** Record each creator with `upsert_creator`: `granted` creators
   first; `unknown` → suggest the user asks ("Love this clip, ok if we share it with credit?");
   `denied`/`blocked` → the server refuses jobs and posts.
4. **Takedown requests: same day, no argument.** `/clip-takedown` → `record_takedown` cancels
   scheduled posts, blocks the creator, and lists URLs the user deletes today. Log, then never use
   that creator again without permission.

## 3. Transform it — every clip adds value

Instagram removes accounts from recommendations if they mostly repost others' content without
enhancing it materially, and a watermark, border or credit alone doesn't count. So every clip
carries **all** of: a hook stamp in the first second, tight trim (dead air out, ends on the payoff),
burned-in captions, and our framing (the stamp, a label, a tip, or commentary). A plain re-upload
of someone's video is never shipped. The quality-critic checks this.

## 4. Spoilers and sensitive frames

- Story moments in launch week: **no spoiler in the hook, the stamp, the title or the cover.** The
  scout sets `spoiler: true`; `check_copy` then requires "SPOILER" in the caption.
- Prefer driving, map, graphics, NPC and funny moments over story beats around launches.
- Skip nudity frames entirely; mark sensitive media where platforms require it.

## 5. Never

- Leaks, datamined files, leaked builds/maps/tracklists, pirated copies, "how to play early"
  tricks, exploits. If you can't tell whether footage is official or leaked, don't use it.
- Naming leak outlets or rumour sources. Rumours are out by default; if the user approves one it
  starts with "RUMOR:".
- AI-generated "gameplay" or "screenshots" passed off as real. Fake giveaways, "free copy" posts.
- Copy that reads as official publisher communication.
- Invented numbers. Every number in copy is read off the clip or an official source.

## 6. Money and platform policy (tell the user before they monetise)

- YouTube's reused-content policy applies **even with the original creator's permission** —
  transformation matters more than permission for monetisation.
- Game publishers set their own rules for footage (e.g. Rockstar's policy covers non-commercial
  use). Read the publisher's policy before monetising game footage.
- Treat "$X a month" claims with suspicion; pay-per-view rates are low and capped per clip.

## 7. Copy rules per platform (enforced by `check_copy`)

| platform | shape | hashtags | limits |
|---|---|---|---|
| X | headline, blank line, credit line last | **none** | 280 chars; video ≤ 140 s (non-Premium) |
| Instagram | hook line, 1–2 sentences of value, credit line, then tags | **3–5** (max 5) | 2,200 chars; keep Reels < 3 min |
| YouTube Shorts | title (≤ 100, aim ≤ 60) + description with credit + a few tags | 1–5 incl. #shorts | ≤ 3 min |
| TikTok | short caption + credit + a few tags | 1–5 | ≤ 3 min here |
| Threads | short text + credit | 0–1 | ≤ 5 min |

- Don't repeat an opening line within 7 days (`check_copy` flags it).
- Write copy as `data.copy` = `{platform: {title?, description?, caption?, text?}}` via `update_clip`.

**Clip template**
```
<one-line hook or reaction>

🎥 @creator
```
**Instagram**: hook line, value sentence, blank line, `🎥 @creator`, then 3–5 tags.

## 8. Length and specs

Default **7–30 s** for most clips (up to 60 s when the moment needs it). 9:16, 1080×1920, MP4
H.264 + AAC. Skip 4K. Pick the cover with `set_cover` — a readable, non-spoiler frame.

## 9. Uploading

- Upload the **file**, never a link to someone else's post.
- YouTube and Instagram upload from the plugin. TikTok, X, Threads: `export_post_kit` → upload by
  hand or Buffer. Buffer and other automations need a **direct, public, permanent HTTPS URL to the
  MP4** — not a share page, a local path, or an expiring link.
- Breaking moments: post now. Everything else: `schedule_post` at the times the data says work.
