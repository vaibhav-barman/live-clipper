---
name: clip-router
description: "THE ROUTER — start every clip job here. Picks the vertical layout for each clip (gaming + facecam split / IRL full-frame / no-cam gameplay), enforces the pipeline order (hook-scout → cut → cut audit → geometry → finish → captions → SFX → render → review), names which skill owns each stage, and carries the non-negotiable rules and the standing deliverables. Use at the start of /clip-live, /clip-vod, or any request to turn a stream moment into a short."
---

# CLIP ROUTER — the factory manager's rulebook

> **THE META-RULE:** skills are loaded to be **EXECUTED, not recited.** The rules below exist because
> each one was broken at half strength somewhere and cost a re-render. Loading a skill is not the
> same as following it. If a skill has a checklist, make a todo per item, per clip.

Adapted from a creator's `reel-edit` router. The essence kept: a fixed pipeline order, one skill per
stage, hard rules that apply in every format, and nothing ships without a review gate. What changed:
the source is **someone else's live stream**, not the creator's own take, so honesty and credit rules
are added and the creator-specific formats are gone.

## Step 0 — the page and the creator (before any job)

- `get_page()` — if `configured` is false, suggest `/clip-page-setup` (the clips still work; the
  copy gets better with a page voice, niche and platforms).
- The creator's permission (`list_creators`): `granted` → go; `unknown`/`asked` → tell the user
  that credit is not permission and offer to record it once they've asked; `denied`/`blocked` →
  the server refuses the job. Never route around it.
- Load `page-playbook` for anything that touches copy, covers, credit or takedowns, and
  `growth-loop` for reports, tests and reviews.

## Rush mode (launch day / big drops) — `create_job(..., rush=true)`

Speed first, honesty unchanged. In rush mode: the scout takes the first strong non-story moments,
windows stay short (7–20 s), the editor turns SFX off and keeps the default finish, and clips go to
approval as each one passes — **the review gate and the approval gate stay exactly the same**. Aim:
moment → clip in approval within ~15–30 minutes. Never "be first" with leaked or pre-unlock footage.

## Step 1 — pick the layout, per clip

Decide from the footage, not from taste. `take-geometry` measures; `stream-layouts` builds.

| If the clip… | Layout | Skill |
|---|---|---|
| is gameplay with a visible facecam, and the facecam crop is ≥ 360 px tall in the source | **Split**: gameplay card on top, caption lane, facecam card below | `stream-layouts` § Split |
| is IRL / just chatting / one camera, the person IS the shot | **Full-frame**: one static 9:16 crop of the shot, overlays only | `stream-layouts` § Full-frame |
| is gameplay with no facecam, or a facecam too small to enlarge cleanly | **Gameplay-only**: gameplay card on a blurred fill of itself | `stream-layouts` § Gameplay-only |

**One disambiguation that goes wrong:** a facecam that is visible but tiny (< 360 px tall in a
1080p source) upscales into mush at 9:16. Use Gameplay-only and keep the facecam inside the
gameplay crop if it fits, rather than blowing it up.

## Step 2 — run the pipeline, in order

```
0. SCORE        hook-scout + `hook-rubric`       which moments, why, rough windows
1. CUT          `shortform-cutaway`              WhisperX words → envelope-exact edges
2. CUT AUDIT    `cut-audit`                      prove it — the transcript is NOT evidence
3. GEOMETRY     `take-geometry`                  find the facecam, measure the face, solve the fit
4. FINISH       `stream-layouts` + `shortform-finish`   layout, hook zoom, static punch-ins
5. CAPTIONS     `caption-align`                  source → cut map → force-align → pause audit
6. SOUND        `sfx-design`                     peak-aligned, levels for the final file
7. RENDER       `render-ops`                     ffmpeg, CFR, loudnorm on the encoded file
8. REVIEW GATE  `reel-review`                    script measures + a different model looks. NEVER skip.
```

**Stage 1 decides the clip. Every later stage treats the cut as sacred** — never re-pick moments or
move cut points while styling. If styling reveals a cut problem, send the clip back to stage 1.

**Every stage reads its inputs from and writes its outputs to the SQLite ledger** (`clips` row +
paths). An agent never relies on what another agent said in chat.

## Step 3 — the non-negotiables (every layout, every clip)

1. **Never put text or graphics on a face, in any frame.** A ~6-frame flash counts. Enforce with
   the alpha guard (`take-geometry`), not with your eyes.
2. **Registers HARD CUT.** No opacity crossfade between layouts — a fade shows both through each other.
3. **Nothing animates across a cut boundary.** No zoom in/out at cuts; it advertises the cut. The
   test: does anything change velocity on the exact frame of a cut? Then it is banned.
4. **Never change what the streamer meant.** Trim dead air, chat reading, AFK time and repeats. Never
   reorder lines into a new claim, never splice two moments into one sentence, never cut a "not".
   A tease of the payoff in the first second is allowed only as an obvious repeat (see `hook-rubric`).
5. **No generated or restyled footage of the streamer.** No AI b-roll inserted into their stream, no
   face/body restyle. Real footage only.
6. **Do not upscale gameplay** — scale ≤ 1.0 preferred, hard max 1.1. Pre-crop at native resolution. The facecam is the only
   layer allowed to enlarge, and only up to 2.25× with lanczos (`stream-layouts`).
7. **Text inside the safe zone** — y220–1470, 35 px sides, ~100 px clear on the right for the action
   rail. Imagery may cross; text may not.
8. **Credit every clip.** Streamer name + platform on screen in the close, and `🎥 @creator` in every
   caption. Credit is not permission — see `page-playbook`.
9. **Real numbers only** — viewer counts, donations, scores, ranks. Read off the footage or the
   platform, never invented or rounded up.
10. **Respect the source's rules.** Only clip streamers who allow it, follow the platform's reuse
    rules, and keep the human approval gate on before anything posts.

## Step 4 — verify before anyone sees it

- **Look at the DELIVERABLE file**, not the timeline: scene-change stills land exactly on layout
  boundaries, where one-frame bugs live.
- **Plus fixed mid-beat stills** — scene-change sampling exaggerates empties; mid-beat stills are the
  counterweight.
- **Then the review gate** (`reel-review`): the deterministic script, then a vision reviewer on a
  **different model** from the editor. Fix every BLOCKER and re-render. The approver reviews a
  known-state file, never a surprise.

## Step 5 — the standing deliverables, per clip

Ship these unasked:

- the **render**, 1080×1920, CFR, loudnorm'd to −14 LUFS **measured on the encoded file**
- the **review report** (`report.md` + contact sheets) from `reel-review`
- the **post copy** per platform (`data.copy`), passing `check_copy`, plus a cover (`set_cover`)
- the ledger row updated to `ready_for_approval`

## Working in a shared workspace

Several clips (and sometimes several sessions) run at once.

- **Namespace everything per clip** — `work/<stream_id>/<clip_id>/…` for every intermediate. Never
  share a path between two clips.
- **Re-check your intermediates still exist** before each step that consumes them.
- **Inspect in a separate call from any delete.** `ls DIR; rm -rf DIR` in one call is not a check.

## The per-clip production loop (run by the orchestrator command)

Sub-agents can't launch sub-agents, so the command in the main session calls each agent with the
Agent tool (`live-clipper:<name>`), passing **only ids** (`clip_id`, `job_id`) plus any findings
from the previous round. Agents read the real state from the ledger.

```
clip-cutter ──► cut-auditor ──fail (≤2)──► clip-cutter
                    │ pass
                    ▼
            layout-geometer ──► vertical-editor ──► captioner ──► renderer ──► quality-critic
                                                                                 │
              BLOCKER → owning stage (≤2 rounds per clip): cut → clip-cutter (then re-audit),
              framing → layout-geometer, stamp/finish → vertical-editor,
              captions → captioner, loudness/frozen/frames → renderer
                                                                                 │ no BLOCKER
                                                                                 ▼
                                                                    ready_for_approval → copywriter
                                                                    (copy per platform → check_copy → cover)
```

- Track attempts on the clip (`update_clip(..., {"attempts": n})`). After 2 failed rounds at any
  gate, set `needs_human` with the findings and move on to the next clip.
- After any re-cut, everything downstream re-runs (captions and SFX are timed to the cut).
- A `failed` task is not a quality verdict: read the log, fix the cause (missing dependency, bad
  path), retry once, then `failed` with the error for the user.

## Clip count

`--clips N` is a **cap, not a quota**. Keep clips that score ≥ 7 and pass review, drop overlaps,
stop at N. A dull stream yields fewer clips — that is correct behaviour.
