---
name: shortform-finish
description: "The FINISH stage for stream clips — runs AFTER shortform-cutaway has locked (and cut-audit has proved) the cut, inside the layout from stream-layouts. Reframe, the zoom-out hook, static punch-ins on jump cuts, gated lens FX, exponential text fade-ins, captions at phone-scale sizes, sound design peak-aligned at the right level, and loudness at −14 LUFS measured on the encoded file. The cut is sacred — this skill never re-picks moments or moves cut points. Use for 'make it pop', 'add a zoom', 'add sound design', 'finish this clip', 'the SFX are too loud'."
---

# SHORTFORM FINISH (stream edition) — the styling stage

> **THE JOB:** make a LOCKED cut look and sound finished — framing, motion, type, captions, SFX,
> loudness. The cut is decided upstream; this skill never re-picks moments or moves cut points.

Adapted from the creator's v2 finishing skill. **Kept:** every rule learned from a rejection (left
column below), the measured sizes and levels, the review gate. **Changed:** ffmpeg is the default
renderer, screen-recording rules are replaced by gameplay rules, music beds are off (stream clips
already carry the stream's audio).

## Why each rule exists (each from a real rejection)

| naive approach | the verdict | rule |
|---|---|---|
| punch-in/out **wave across cuts** | "shows that there is a cut" | **nothing animates across a cut.** Jump cuts alternate a STATIC 1.00 / 1.12 framing |
| slow push-in on a still image | "the constant zooming in looks odd" | static framing; let the content move (gameplay already does) |
| SFX at file level | "reduce the SFX by 4 dB" | set levels from the formula, then **trim the whole kit together** |
| one sound per kind | repetitive | 3–4 **variants per kind**, rotated; ≤ 1 transient per 0.22 s |
| text at "readable" sizes | unreadable on a phone | measured floors: captions ≥ 78 px on 1080×1920, stamps ≥ 34 px |

## WORK ON A DUPLICATE — never the locked cut.

## TECHNIQUE 1 — MOTION THAT NEVER CROSSES A CUT

### The zoom-OUT hook (opening only)
Scale `1.3 → 1.0`, front-loaded ease-out (at 30 fps): `[0]=1.3 [7]=1.13 [17]=1.05 [32]=1.01 [50]=1.0`.
**Centre-lock** on the face (Full-frame) or the action (Split game card) — an off-centre pull-back
exposes the frame edge. It starts on frame 0 of the first piece: it is the opening, not a transition.
In ffmpeg: `zoompan` or a `scale`+`crop` with an expression on `n`, applied only to the first piece.

### Jump cuts inside one moment: STATIC punch alternation
Consecutive pieces alternate **1.00 / 1.12** framing (anchored on the face from `take-geometry`, or on
the crosshair in the game card). Each side of the cut is still; the size change hides the jump.
**Never a zoom that is moving at the cut.** Respect the punch bounds:
`|tx| ≤ 540 − 540/k`, `|ty| ≤ 960 − 960/k`.

### Lens FX only DURING a move
Zoom blur / chromatic aberration peak during the fast part of the hook and return to 0 at rest. Never
blur the whole clip. Every zoom wants a whoosh, peak-aligned.

### Gameplay
Gameplay moves on its own — never add a push-in "to keep it alive". If the gameplay is static (a menu,
a loading screen), that's a cut problem: send it back to the cutter rather than animating over it.

## TECHNIQUE 2 — EXPONENTIAL TEXT FADE-IN
Never linear. `opacity = 1 − e^(−k·t)` with a ~10 px rise and blur-to-sharp on the same ease-out; exit =
lift + blur-out. **A graphic must be FULL in its first frame of use** when it carries the punch line —
a payoff word caught mid-fade reads as a defect.

## TECHNIQUE 3 — THE AUTHORITY STACK (for the hook stamp)
Bold, tight tracking (≈ −0.04 em), words rise out of a soft fog and speed-ramp to a settle, exit = lift
+ blur-out. One warm accent colour for the "editor voice"; streamer quotes stay white.

## CAPTIONS (rules live in `caption-align`)
- Frames from the **source word times** mapped through the cut (never re-transcribe the cut).
- 1–3 words, ≥ 78 px, in the band `take-geometry` derived; never over a face.
- Every spoken beat gets a caption (no 1-frame holes); no caption over measured dead air.
- Render captions into the **overlay layer** (alpha) so the face guard can check them.

## ON-SCREEN ASSET RULES
0. **Look at the asset** before using it. 1. It appears **only while its line is said**. 2. Small,
clustered in negative space, popped in ~3 frames apart, never over a face. 3. Every animated element
gets its own small SFX. 4. **Layouts hard-cut** (`stream-layouts`). 5. **Never text on a face.**

## TECHNIQUE 4 — SOUND DESIGN (details in `sfx-design`)
**Pick the sound by what MOVES:** whoosh = a move (length matched) · click/pop = a snap-in · tick = a
toggle or a word landing · riser + hit = the payoff stamp. Not on plain cuts.
**Schedule at the PEAK:** `start = event − peak_offset`.
**Set levels for the FINAL domain:** `vol = 10^((target_final − delivery_gain − mix_offset − file_peak)/20)`.
**Stream audio is already loud and busy** (game SFX, music): keep added SFX sparse — the hook, stamps,
the payoff. If a cue fights a game explosion, drop the cue.

## LOUDNESS + DELIVERY (details in `render-ops`)
- Final at **−14 LUFS integrated, ≤ −1 dBTP**, measured **on the encoded file**, 48 kHz.
- Every dialogue cut carries its micro-fade from `cut.json` — no clicks.

## AUDITION WORKFLOW
For the hook, render 2–3 alternatives (stamp copy, zoom start, tease or no tease) and let the critic
compare them. Keep the losers out of the ledger's deliverables.

## ⛔ NOT DONE UNTIL THE REVIEW GATE PASSES
Run **`reel-review`**: the deterministic script, then a **different model** over sampled frames from
every section. Check every finding against full-res frames — the reviewer sometimes samples a frame
before a graphic lands — and fix every real BLOCKER first.

## SCOPE
**DOES:** reframe · hook zoom · static punch-ins · gated lens FX · text looks · captions placement · SFX
+ levels · loudness · delivery.
**DOES NOT (→ `shortform-cutaway`):** pick moments · move cut points · remove silences.
