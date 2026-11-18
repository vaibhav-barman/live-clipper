---
description: Set up the clip page — name, handle, niche angle, platforms, timezone, voice, posting rhythm, approval rules — so every agent writes and plans for it.
---

Set up (or update) the page profile. **First:** load the `page-playbook` skill.

1. Show the current profile (clipper `get_page`). Then ask, in ONE message, numbered:
   1. Page name and handle, and which platforms already exist (YouTube, Instagram, TikTok, X, Threads).
   2. The niche angle — one main lane (funny moments, tips & hidden spots, fast news, cars…).
   3. Timezone and the hours they're awake to approve posts.
   4. Posts per day per platform (suggest: Shorts 1–3, Reels 1–2, TikTok 1–3, X 4–6).
   5. What needs their approval (default and minimum: every post — the plugin never posts alone).
   6. Creators they already have permission from, and any to avoid.
   7. The game/creator brand they must say they're not affiliated with.
2. Save with `set_page(...)`; record creators with `upsert_creator` (`granted` only if the user
   says they have permission; avoided ones as `blocked`).
3. Give them their bio line ("<what we post>. Fan page, not affiliated with <X>."), and remind them:
   own avatar/banner (no official logos or key art), Instagram must be a Professional account to
   auto-publish, same handle everywhere if possible.
