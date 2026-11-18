---
name: reel-review
description: "FINAL GATE before any clip goes to the approval queue. Runs the deterministic review script (specs, CFR, frame count, loudness on the encoded file, frozen frames, black frames, per-region motion, caption rules and dead-air audit, repeat scan on the voice, face guard and safe area from the overlay alpha) and then dispatches a vision reviewer on a DIFFERENT model that looks at contact sheets from every section. Use whenever a clip render is finished — before approval, never after."
---

# REEL REVIEW — the final gate

> **THE SPLIT:** a script measures what is *measurable*; an agent judges what is *judgement*. Never let
> the agent guess at numbers it can measure, and never let the script rule on taste. Both halves run,
> every time.

**A second model reviews the first model's work** — that is the point. If the editor agents run on one
model, the quality-critic runs on another. Never review your own edit inline.

Adapted from the creator's gate. **Kept:** the split, the different-model rule, BLOCKER/FIX/NIT, the
two sample points per section, and how to read the numbers honestly. **Added:** the script itself
(`scripts/review_reel.py`, which the original skill used but did not ship), rebuilt for stream clips.

## Step 1 — deterministic pass

```bash
python3 scripts/review_reel.py out/<clip>.mp4 --out work/<stream>/<clip>/review \
  --cut work/<stream>/<clip>/cut.json \
  --captions work/<stream>/<clip>/captions.json \
  --voice work/<stream>/<clip>/cut_voice16k.wav \
  --overlay work/<stream>/<clip>/overlay.mov --face-band 1180:1820 \
  --region game:1080:726:0:0 --region face:1008:1050:36:870
```
Every flag after the video is optional — a check whose input is missing is reported `SKIP`, never PASS.
Exit code **1 on any FAIL**, 0 otherwise. Output: `report.json`, `report.md`, `sheet_mid.jpg`,
`sheet_post.jpg`.

| check | what it catches |
|---|---|
| specs | wrong size/fps/codec/pix_fmt, audio not AAC 48 kHz stereo, duration outside 5–60 s |
| cfr | VFR output (avg ≠ declared frame rate) — clips the last word downstream |
| frames | frame count ≠ cut total × fps → a **clipped tail** or a killed render |
| loudness | integrated not −14 ±1 LUFS, true peak above −1 dBTP — **missing number = FAIL** |
| frozen | frames whose difference from the previous is ~zero; % frozen and longest run |
| black | black stretches (a missing card, a scene switch to nothing) |
| region motion | per region, % of frames that move. **< 30% is a WARN**, a prompt to look, not a bug |
| captions | ≤ 3 words, ≥ 0.30 s, no article opening, no 1-frame holes, no overlaps, **dead-air audit** on the voice |
| repeat scan | adjacent voice bursts that are spectrally the same (false start + redo) ≥ 0.78 |
| face guard | opaque overlay pixels inside the face band (frames > 85% opaque skipped) |
| safe area | overlay text ink outside y220–1470 / x35–980 |

It also samples two frames per section — **mid-beat** (steady state) and **+0.35 s after the boundary**
(catches ghosting and empty cards) — and tiles them into the two contact sheets.

## Step 2 — vision pass (different model)

Dispatch ONE reviewer agent on the other model. Hand it `report.md`, both sheets, the clip's layout name,
and the `clip-router` + `stream-layouts` rules. It must **Read every sheet** and rule on:

1. **Captions** — on every spoken beat? legible at phone size? inside the safe band? **never on a face**?
2. **Overflow / collision** — text crossing card edges, clipped at frame edges, stacked elements, anything
   crossing the right-side action rail or y220/y1470.
3. **Layout** — face framed with headroom (not centred, hair not cropped)? gameplay crop on the action?
   any card empty in its first second? any upscaled mush?
4. **Registers** — hard cuts, or a crossfade ghosting at a boundary?
5. **Honesty + credit** — credit strip present with the streamer's real name/platform? nothing that
   changes what the streamer said? no private info visible?

Output: **BLOCKER / FIX / NIT**, each with the frame/section, what is wrong, and the rule it breaks.
Require it to **say explicitly when it finds nothing** — no invented findings to look useful.

## Step 3 — act, then hand over

- BLOCKER → back to the stage that owns it (cut → `shortform-cutaway`, sync → `caption-align`, framing →
  `take-geometry`/`stream-layouts`, loudness/frozen → `render-ops`), re-render, re-review. Max 2 rounds,
  then flag for a human.
- FIX/NIT → recorded in the ledger with a recommendation for the approver.
- **Tell the approver what the gate found, including what you chose not to act on.**

## Reading the output honestly

- **Region motion below 30% is not automatically a bug** — a held reaction shot is legitimately still.
- **Caption offsets of a few frames are normal** after forced alignment. Worry at > 12, or a mean that
  trends one way through the clip.
- **Frozen frames on stream clips** often come from the source (dropped frames in the stream). Check the
  source before re-rendering.
- **The repeat scan's 0.78 threshold was measured on a talking-head mic.** Re-calibrate on your first
  stream clips; a chant or a repeated catchphrase will (correctly) flag and may be kept on purpose.
