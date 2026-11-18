---
name: sfx-design
description: "Place sound effects so they LAND on stream clips — schedule at event_frame minus the file's measured peak offset (not at its start), pick the sound by what is moving, and set volume for the FINAL file using the measured mix offset and delivery gain. Carries the volume formula, the stereo measurement trap, density limits for busy stream audio, the catalogue script that measures every SFX file, and the residual check that proves a cue fired. Use whenever SFX are added, whenever a cue lands late, and whenever a mix clips after normalisation."
---

# SFX DESIGN — landing the hit, at the right level

> **THE ESSENCE:** a sound effect is scheduled by its **peak**, chosen by **what moves**, levelled for
> **the final delivered file**, and **proven** to have fired. Everything else is taste.

Adapted from the creator's skill. **Kept:** peak scheduling, sound-by-motion, the final-domain volume
formula, the measurement trap, the residual check, retiming with captions. **Changed:** no 522-file
house library — you build your own catalogue with `scripts/sfx_catalog.py`; ffmpeg replaces Remotion
(so the mix offset is re-measured); density is lower because stream audio is already busy.

## 0. Build the catalogue (once, and whenever files change)

Use only SFX you're licensed to redistribute in posts (CC0 / royalty-free packs). Then:
```bash
python3 scripts/sfx_catalog.py sfx/ > sfx/catalog.json
```
Each entry: `file`, `peak_s` (argmax offset), `peak_dbfs`, `onset_s`, `dur_s`. **Schedule from this
file, never by eye.** 3–4 variants per kind (whoosh_01…04) so the rotation doesn't repeat.

## 1. Schedule at the PEAK, not at the file start

A file's transient does not sit at its start, so scheduling at the visual event lands the hit **late**.
```
start_s = event_s − peak_s
```
Originally measured: a click peaks at ~0.5 frames, a pop at ~7 frames, a swish at ~15 frames (60 fps).
A whoosh started at the event lands a quarter-second late.

## 2. Pick the sound by what is MOVING, not by taste

| motion | sound |
|---|---|
| the frame travels (hook zoom, split ↔ full grow) | **whoosh**, length matched to the move |
| something snapped in without moving (stamp, caption pop) | **click / pop** |
| a toggle, a checkmark, a counter tick | **tick** |
| the payoff stamp | **riser + hit** (sparingly) |

**Dial whooshes down. They are always too loud.**

## 3. Volume — set it for the FINAL domain

Between the volume you set and what the viewer hears:
1. **Mix offset** — what your mixer adds. With ffmpeg use `amix=inputs=N:normalize=0` (otherwise amix
   divides every input by N and all levels are wrong). Measure once: mix a −20 dBFS tone at volume 1.0
   and read the result; record `MIX_OFFSET_DB` here (expected ≈ 0 with `normalize=0`).
2. **Delivery gain** — what loudness normalisation adds. Stream audio usually sits near −16 to −20 LUFS,
   so reaching −14 adds +2 to +6 dB to everything, SFX included. Measure per clip.
3. **Hot files** — most one-shots peak within ~1.5 dB of full scale.

```
vol = 10 ^ ((target_final_dbfs − delivery_gain − MIX_OFFSET_DB − peak_dbfs) / 20)
```
A pop meant to land at −10 dBFS in the final file usually comes out around **0.06–0.1**. **Stamps sit
~4 dB under the streamer's loudest word.**

**Verify on the delivered file**, in a window with no speech:
```bash
ffmpeg -ss T -t 0.25 -i final.mp4 -af astats=measure_overall=Peak_level -f null -
```

### The measurement trap
**Decoding with `-ac 1` SUMS the channels** — an in-phase transient reads up to **+6 dB too hot**. Meter
with ffmpeg (`astats`, `ebur128=peak=true`) or decode channels separately.

## 4. Density — stream audio is already loud

- **~1 added transient per 2 s at most**, concentrated in the hook (first 5 s) and the payoff.
- ≤ 1 transient per 0.22 s anywhere; thin the rest.
- **Never stack a cue on a game explosion, gunshot or alert** — it masks both. Check the mix envelope
  at each cue time; move or drop the cue if the game is already peaking there.
- No music beds. The stream's own audio is the bed.

## 5. Prove the cue actually fired — the residual check

**Envelope-vs-envelope comparison of AAC against PCM is useless** (113 false spikes in 27 s originally).
Cross-correlate the render's audio against the pre-SFX mix (this also finds the **~42.7 ms AAC priming
lag**), **subtract it**, and list residual events against the cue schedule. That is the only check that
answers "did this cue land, and where".

## 6. Retime SFX whenever captions move

Cues were placed against caption frames and **drift with them**. Retime in the same pass as any
caption regeneration (`caption-align`).
