---
name: render-ops
description: "Get a clip render out of ffmpeg and onto disk correctly — CFR at the exact fps, audio sliced by sample index (no drift across pieces), never bounding video with -t, frozen-frame detection, frame-count verification, two-pass loudnorm with encoder headroom measured on the ENCODED file at 48 kHz, and the namespace/delete rules for a workspace several clips share. Use before, during and after any render, and whenever a render freezes, drifts, clips its tail, or comes out too loud or too quiet."
---

# RENDER OPS (ffmpeg edition) — the render, and getting it out intact

> **THE ESSENCE:** a render that "succeeded" proves nothing. Frozen frames, drifting audio, a clipped
> last word and a hot true peak all survive a successful exit code. **Measure the delivered file.**

Adapted from the creator's Remotion render skill. **Kept:** frozen-frame detection, the audio-drift
cause and fix, loudness measured on the encoded file, the frame-count check, the shared-workspace rules.
**Dropped:** Remotion bundles, entry files and Node-API traps (the plugin renders with ffmpeg).

## Before you render

1. **One namespace per clip:** `work/<stream_id>/<clip_id>/` for every intermediate, `out/<clip_id>.mp4`
   for the deliverable. Never share a path between clips.
2. **Check who else is running:** `pgrep -fl ffmpeg`. Two renders writing one file produce a valid-looking
   mp4 with the wrong content (`moov atom not found` mid-session is the tell).
3. **Normalise the source first:** transcode the window to H.264, **CFR at the output fps (30)**, before
   any cutting. Never cut from a VFR stream recording.

## Audio drift across pieces

Cutting N pieces out of an AAC track with `-ss/-t` snaps each to an AAC frame boundary (1024 samples), so
audio lag **grows with every cut** (~0.6 frames per cut at 60 fps; +12 frames by 50 s originally) while the
video stays frame-exact. **Invisible to the usual checks** — it gets misreported as a caption problem.

**The fix:**
1. Decode the source audio to **one WAV** and slice it by **sample index** (`round(a * sr)`), concatenate
   the slices with their micro-fades. That is the voice/mix spine.
2. Build the video from pieces separately (concat **filter**, CFR).
3. `amix=normalize=0` the spine + SFX, `apad`, then **`atrim` the AUDIO only** to the video length.
   **Never bound the video with `-t`** — it silently dropped 7 frames off one render.

## Frozen frames

A render can repeat frames without erroring. **Detect on every delivered file:**
```bash
ffmpeg -v error -i out.mp4 -vf "tblend=all_mode=difference,signalstats,metadata=print:file=/tmp/s.txt" -an -f null -
# frames whose lavfi.signalstats.YAVG < 0.06 → frozen
```
Anything above ~0.5% needs investigating. On stream clips, a frozen run is usually a dropped-frame
stretch in the **source recording** — check the source at the same time before blaming the render.
`review_reel.py` runs this check.

## Loudness — measure the ENCODED file

`loudnorm` limits its own PCM output; the AAC encoder then reconstructs inter-sample peaks **above**
that ceiling.

| filter | encoded result (original measurements) |
|---|---|
| `loudnorm I=-14 TP=-1.5` | −14.8 LUFS / −0.5 dBTP |
| two-pass, `TP=-1.5` | −14.3 LUFS / **+0.3 dBTP** ← clipping |
| `+ alimiter=0.72`, TP=−2.5 | −15.1 / −1.7 ← too quiet |
| **two-pass, `TP=-3.0`, no limiter** | **−14.6 LUFS / −2.4 dBTP** ✓ |

1. Measure the finished mix WAV: `loudnorm=I=-14:TP=-3.0:LRA=11:print_format=json`.
2. Pass two with `measured_I/TP/LRA/thresh` + `offset` fed back. The extra 1.5 dB is the **encoder allowance**.
3. **Re-measure the ENCODED mp4**, never the filter's summary.
4. **Force `-ar 48000`** (`…,aresample=48000` + `-ar 48000`) — loudnorm resamples to 192 kHz internally and
   one deliverable shipped at 96 kHz.
5. **If loudnorm falls into DYNAMIC mode** (quiet input; LRA collapses, SFX pinned to the ceiling), pre-gain
   first so the normalisation stays linear.
6. **A missing number is not a pass.** If a script can't parse the true peak, verify by hand.

Stream audio is often already compressed and loud; check it isn't going *down* past −14 into mush, and
that game peaks aren't clipping after normalisation.

## After the render

- **Verify the frame count** against the cut: `nb_frames` (counted with `-count_frames`) must equal
  `round(total_dur * fps)`. A killed render leaves a partial mp4 that probes fine otherwise.
- Probe: 1080×1920, `yuv420p`, H.264, 30 fps CFR, AAC 48 kHz stereo.
- Then run `reel-review`. Never hand over an unreviewed render.

## Disk and deletes

- **Inspect in a SEPARATE call from the delete.** `ls DIR; rm -rf DIR` in one call means the listing
  arrives after the delete ran — this destroyed another session's finished deliverable once.
- Delete only your own clip's superseded intermediates. Raw stream chunks are retained per the
  ingest policy, not deleted by a render step.
- Treat `work/` as volatile: re-check an intermediate still exists right before the step that consumes it.
