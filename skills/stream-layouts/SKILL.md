---
name: stream-layouts
description: "The three 9:16 layouts for stream clips and their rules: SPLIT (gameplay card on top, caption-only lane, facecam card below), FULL-FRAME (one static 9:16 crop of an IRL/just-chatting shot, overlays only), and GAMEPLAY-ONLY (gameplay card on a blurred fill). Carries the geometry and how to solve it, the layout grammar (hard cuts, no zoom at cuts), the hook's first-5-seconds budget, stamps-not-pills, and the credit close. Use when building any clip's layout after take-geometry has measured it."
---

# STREAM LAYOUTS — the frame is stable; the content carries the variety

> **THE ESSENCE (from the creator's split-screen and caption-edit formats):** the viewer's eyes never
> have to re-find the face. Novelty belongs in what the cards SHOW, never in the frame's architecture.
> And when the shot itself is the content, don't break it — ride on top of it.

The original split was settled over three rounds: a novel carve-up ("looks absolutely shit"), full-bleed
alternating ("the focus is shifting so frequently"), then **the 60-40 split** ("looks much better").
**Default to the split when there is a usable facecam.** Change only what the cards show.

`clip-router` picks the layout; `take-geometry` supplies `FACECAM`, `FACE_FIT` and the bands.

## Layout A — SPLIT (gameplay + facecam)

### Reference geometry (1080×1920, from the shipped creator format)

```
GAME card   x0   y0    1080×726     gameplay, full-bleed (no paper border)
LANE        y726 → y870             caption ONLY (~144–180 px)
FACE card   x36  y870  1008×1050    facecam, solved FACE_FIT
```

### Solve it per stream — never upscale past the limits

Stream facecams are small, so the reference numbers often can't be hit without mush. Solve:

1. `s_face` from `take-geometry` (floor from head position, **ceiling 2.25**).
2. `H_face = min(1050, visible_cam_height × s_face)`. Width stays 1008 (or 1080 full-bleed).
3. `H_game = 1920 − H_face − LANE − 36` (36 px bottom margin).
4. Gameplay crop: **scale ≤ 1.0 preferred, hard max 1.1**. If `H_game` would force more, give the
   extra height to a 1–2 px-blurred copy band of the gameplay, or shrink the lane to 144 px — never
   upscale further.
5. Record the solved `{GAME, LANE, FACE}` rects in the ledger; `review_reel.py --region` uses them.

**Which way does the streamer look?** If they face screen-right in their cam, nothing changes in the
split (the cam is centred), but any in-card graphic goes on the side they look toward.

### The lane is caption-only

The lane carries **the caption and nothing else**. A first pass that put a source line, a chip AND the
caption there rendered them on top of each other. Anything else the shot needs to say (a kill counter,
"CHAT:" quote, the game title) goes **inside the gameplay card**, on a gradient strip at its bottom
edge — never at the card's top under Instagram's username chrome.

**Captions never touch the head** — the lane ends ≥ 20 px above the face card.

## Layout B — FULL-FRAME (IRL / just chatting)

The shot is the content. **One static 9:16 crop per shot** (from a 1080p source that crop is
607×1080, so it enlarges ~1.78× — unavoidable for camera footage, which is why the source must be
1080p or better and the gameplay-scale limit doesn't apply here), solved from `take-geometry` (head x pinned,
headroom target), and then **overlays only**: no split, no punch-in waves, no constant tracking pan.

- **If the person walks out of the crop**, do not pan to follow. Cut (hard) to a re-solved static crop
  at the next sentence boundary. A slow, smoothed drift that **never changes velocity on a cut** is the
  only acceptable motion of the crop itself.
- **Two overlay bands, both measured:** a caption plate in the clear band (white 700-weight display type
  ≥ 78 px on a black plate or scrim), and a **top band of solid stamps** in the headroom.
- **Typography from frame one:** a top stamp naming what the viewer is about to see, gone when the
  moment itself takes over.
- **"Mostly raw" clips** (a long uncut rant): target **~10% of runtime** in any cutaways. If a card
  covers the frame, its ground must move (a drifting grid at ≥ 1.6 px/frame) or the frozen-frame check
  fails — a held card on a held background is a freeze.

## Layout C — GAMEPLAY-ONLY

Gameplay card (native crop, scale ≤ 1.0, hard max 1.1) centred in the frame, the rest filled with a
heavily blurred, darkened copy of the same gameplay. Captions in the clear band below the card. If a
small facecam exists, it stays **inside** the gameplay crop where it already is — never enlarged.

## Layout grammar (all three)

### Registers HARD CUT

**No opacity crossfade between layouts, ever.** At a crossfade both layers are partly transparent and the
base shows through both — three versions shipped like this originally before the cause was read instead
of guessed. Any layout renders **opaque from its first frame to its last**. In-layout swaps (one stamp
replacing another) **replace, never blend**.

**Cards must be opaque from frame one.** An opacity ramp on a card puts one frame of empty background at
every layout cut — a flash the review gate's +0.35 s sample cannot see; scene-change stills catch it.

### No zoom at cuts (HARD RULE, given twice)

> *"when there is zoom in and zoom outs between cuts, it looks bad, it shows that there is a cut."*

The base cut plays plain. **The test: does anything change velocity on the exact frame of a cut?**
Then it is banned. Static framing differences across a cut are fine (that's `shortform-finish`'s punch
alternation); motion across one is not.

### The one sanctioned transition: split ↔ full

A clip may grow the facecam card to full-frame for the payoff reaction (and shrink back). Only if your
renderer can do it frame-exact:
1. **The grow must LAND on a cut** so the next beat opens already full-frame.
2. **It lands on exactly the full-frame fit** (`FACE_FIT` scaled) — otherwise a visible pop.
3. **Captions must clear the grow** — the card travels up through the lane; fade the caption out 2
   frames before the move starts. Sample the grow window **every 4th frame**.
4. **Never fade the background underneath it.**
Default (ffmpeg route): a hard cut to the full-frame layout on the reaction's first word.

## The hook — first 5 seconds

**A visual event every ~0.5 s from 0 to 5 s.** On a stream clip the gameplay moves on its own, so the
events are: the zoom-out hook (`shortform-finish`), a top stamp, the first caption pop, a stamp slam on
the hook word, a kill-feed or chat highlight inside the card, and (if used) the payoff tease.

**Withhold the payoff.** If the result (the win, the reveal, the fail) is legible in the first ~2 s
outside the flagged tease, there's no reason to keep watching.

## Stamps, not pills

> *"the pill design looks bad and is unreadable"*

- Labels and verdicts are **solid rectangular stamps** — radius ~12, solid fill, white 700-weight
  **≥ 34 px** type. Never 999-radius pills; rounded chips over footage look AI-generated.
- **A stamp gets its own clear band, structurally** — reserved height in the layout, not a free corner
  over moving gameplay.
- On-screen text floors: captions **≥ 78 px**, stamps ≥ 34 px, a hero number ~150 px.

## The credit close (replaces the creator's Follow card — every clip)

The last 1.0–1.5 s carries a **credit strip**: the streamer's name/handle and platform ("Live on
Twitch · @name"), on the top band or the lane, plus (optionally) your clip channel's follow strip.

- **Real names and numbers only.** Never invent a follower count, never imply the streamer made the clip.
- **Tail air has a floor and a ceiling: 0.5–0.9 s** of resolved strip after the last word. Longer reads
  as a dead pause.
- **Check the source's last second first** — streams often cut to a scene switch or an alert. Cap the
  tail before it.
