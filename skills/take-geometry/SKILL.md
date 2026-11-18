---
name: take-geometry
description: "MANDATORY measurement before any layout on a new clip — find the facecam rectangle in the stream, sample every kept piece, measure hair-top / chin / head-cx as DISTRIBUTIONS, then SOLVE the facecam card fit, the gameplay crop and the clear caption bands from those numbers instead of nudging. Covers the headroom rule, the scale floor, swaying streamers, the detectors that lie, and the alpha-channel face guard. Use before placing any graphic, and whenever text lands on a face or a card crops hair."
---

# TAKE GEOMETRY (stream edition) — measure, then solve the layout

> **THE JOB:** before a single graphic is placed, know where the face, hair and hands actually are
> across the WHOLE clip — as distributions, not as one frame — and derive the card fit and the clear
> text bands arithmetically. Every layout rejection in the original project traced back to a number
> that was guessed or sampled too thinly.

**Nothing transfers between clips.** A streamer leans in, a scene switches, the facecam moves between
"starting soon", gameplay and "just chatting" scenes. Measure every clip. Cache per **stream + scene**
only after verifying it still holds.

Adapted from the creator's skill. **Kept:** distributions over single frames, the detector warnings,
solve-don't-nudge, headroom, the alpha guard, writing the numbers down. **Added:** Step 0 (find the
facecam inside a composited stream frame) and the facecam upscale limit.

## The two hard rules this serves

1. **Text lives inside the safe zone**: below y=220, above y=1470, 35 px sides, ~100 px clear on the
   right for the action rail. Imagery may cross; TEXT may not.
2. **Text must NEVER cover a face in ANY frame.** A ~6-frame flash is a defect. When no face-clear
   spot exists, **drop the element** rather than overlap it.

## Step 0 — find the facecam (stream only)

The facecam is a rectangle composited into the 16:9 stream frame, usually in a corner, often with a
border or rounded mask.

1. Sample ~20 frames across the clip. Run a face detector on each **full frame**.
2. Cluster the face boxes; the facecam is the region the cluster lives in. Refine its edges by
   looking for a **constant rectangle**: per-pixel temporal variance is high inside the camera and
   jumps at its border; overlay borders show as straight edges that never move.
3. Store `FACECAM = {x, y, w, h}` in source pixels, per stream + scene. **Confirm on a drawn-grid crop.**
   A detector-only box has put the cam on a face in the game before.
4. Faces inside gameplay (game characters, a video playing on stream) are **not** the facecam — reject
   clusters that don't stay put.
5. **Size check:** facecam `h < 360 px` in a 1080p source → too small for the Split layout (it would
   need > 2.25× upscale). Route to Gameplay-only (`stream-layouts`).

Then crop the facecam to its own file at native resolution and run the rest of this skill on it:
```bash
ffmpeg -i cut.mp4 -vf "crop=W:H:X:Y" -an facecam.mp4
python3 scripts/measure_take.py facecam.mp4 --beats beats.txt --card 1008x1050 --headroom 0.11
```

## Step 1 — sample correctly

**Sample the midpoint of EVERY kept piece, not 3 frames.** Three frames that agree will calibrate a fit
that is wrong for most of the clip.

- ~20 frames minimum, spanning every layout the fit will be used in.
- **Duration-weight** the samples, target the **median**.
- Sanity-check the extremes: at both sway ends the face must still read in-card.
- If the streamer **drifts** (leans in when excited — the payoff is exactly when it happens), say so
  and handle it (Special cases).

## Step 2 — the detectors that lie

| Detector | How it lies | What to do |
|---|---|---|
| **Haar face box bottom** | Is NOT the chin; a dark-row scan once found a collar 130 px too low | Judge the chin on a drawn-grid crop |
| **Haar box top** | Not the hairline; offset is per-person | Derive per streamer, or scan pixels when the background allows |
| **Dark-pixel hair scan** | Useless on a dark background (most streamer rooms) | Check background luma first; on dark rooms use the box offset + a guide line |
| **Headsets and caps** | Read as hair; move the "hair top" up 60–120 px | Measure to the top of the headset; it's what must not be cropped |
| **Green screens / blurred-background cams** | Edge halos read as hair | Use the alpha matte if the stream has one; otherwise the box offset |
| **Faces in the game** | A character's face registers as the streamer | Restrict detection to `FACECAM` |
| **Full-range colour** | `yuvj420p` shifts every threshold | `scale=in_range=pc:out_range=tv` before scanning |

## Step 3 — solve the facecam card fit (never nudge)

Footage scaled by `s` and offset `(dx, dy)` inside the card: `card_y = source_y·s + dy`.

**Horizontal — pin the HEAD's x, not the cam's centre.** Streamers sit off-centre in their own cam.
```
dx = cardWidth/2 − HEAD_CX·s
```
**Vertical — target HEADROOM. Do NOT centre the face.** Centring reads as a ceiling shot.
```
dy = HEADROOM − hairTop·s        // HEADROOM ≈ 11% of the card's visible height
```
Then **assert the TIGHTEST sampled frame still clears ~90 px**.

**The scale floor:** `dx ≤ 0` is required or the card shows the cam's edge: `s ≥ (cardWidth/2)/HEAD_CX`.
**The scale ceiling (stream):** `s ≤ 2.25` on the facecam. Prefer the **lowest** scale the floor
allows — sway amplitude in the card is `sway·s`, and every extra 0.1× softens the face.

Derive the constants in code (`FACE_FIT = {scale, dx, dy}`) so a re-measure re-solves the framing.

### The gameplay card

Crop the gameplay at **native resolution, scale ≤ 1.0 preferred, hard max 1.1** (`stream-layouts`
solves the card heights so this holds). The crop centre
follows **where the action is**: the crosshair for shooters (screen centre), the player character for
third-person, the minimap/HUD only if the moment is about it. Exclude the facecam rectangle and stream
overlays (alerts, chat box, sub goals) from the crop when they don't serve the moment.

### Special cases

- **Leaning streamer** (settles closer at the payoff): frame to the EARLY pieces and verify the late
  ones still fit, or carry two fits (`FIT_BUILD`, `FIT_PAYOFF`) switched at a hard cut.
- **Scene switch mid-clip** (cam moves or resizes): re-run Step 0 per scene; switch fits at the cut.
- **A punched full-frame layout**: the punch must not expose a frame edge —
  `|tx| ≤ 540 − 540/k` and `|ty| ≤ 960 − 960/k`. Scale **about the chin**, not the centre.

## Step 4 — derive the caption bands

Compute, don't type pixels:
```
CAPTION_FACE_Y = max(chin + 180, handTop + 96)
```
- **Hands, mics and controllers are the usual blockers.** A boom mic in front of the face kills the
  band below the chin; then captions live in the Split layout's lane, never on the cam.
- **Punch-in shrinks the band.** At 1.12 a hair top of y520 rises to y467: keep captions single-line
  under a punch.
- **Ink is invisible over video.** Anything over footage is white on a scrim.

## Step 5 — enforce with the alpha guard, not with your eyes

Render the graphics layer **alone** with alpha (`overlay.mov`, ProRes 4444 or PNG sequence), then:
```bash
python3 ../reel-review/scripts/review_reel.py render.mp4 --overlay overlay.mov --face-band 1180:1820
```
The review script reads the overlay's **alpha channel** and asserts zero opaque graphic pixels inside
the face band. It catches a stamp hanging 10 px into the band and the **one-frame layout seam**.

Two traps: **don't detect the face by dark pixels** (caption shadows false-positive as hair), and
**skip frames whose alpha coverage exceeds ~85%** (a deliberate full-frame graphic). **The guard cannot
see a crossfade** — one more reason layouts hard-cut.

## Step 6 — write it down

Every stream + scene's numbers go in the ledger (`geometry` table: `FACECAM`, `FACE_FIT`, bands,
date measured). It is why a later clip from the same stream starts from a verified fit instead of from
scratch — and still re-verifies it.
