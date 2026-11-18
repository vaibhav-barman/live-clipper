---
name: caption-align
description: "Get caption words onto the right frames and keep them there — derive frames from SOURCE word times through the cut's piece table (never from a re-transcribed cut), FORCE-ALIGN the caption text to the delivered audio with wav2vec2, then audit every run against the voice envelope for dead air. Carries the run-construction rules (≤3 words unconditional, never open on an article, ≥0.30 s, contiguous `to`), the section-anchor assertion and the stream rules for second voices and profanity. Use whenever captions are generated, retimed, rewritten, or reported out of sync."
---

# CAPTION ALIGN — the right words on the right frames

> **THE JOB:** three clocks are in play — the source stream, the concatenated cut, and the delivered
> render — and every caption bug in the original project came from reading a time off the wrong one.
> **Derive from the source, align to the render, audit against the waveform.**

Adapted from the creator's skill. **Kept:** the three-clock model, the pipeline, every run rule and its
reason, the pause audit. **Changed:** the cut map is `cut.json` (pieces `a`, `dur`) at 30 fps, the
envelope is the Demucs voice stem, and there are rules for second voices and profanity.

## The pipeline

```
source word times ──(cut.json map)──► caption frames ──(wav2vec2 force-align)──► final anchors
                                            │                                        │
                                            └──────► RMS pause audit ◄───────────────┘
```

## Step 1 — derive from SOURCE, never from a re-transcribed cut

```py
def tl(src_sec, pieces, fps=30):        # source seconds -> output frame
    t_out = 0.0
    for p in pieces:                    # pieces from cut.json, in output order
        if p["a"] - 1/fps <= src_sec < p["a"] + p["dur"]:
            return round((t_out + (src_sec - p["a"])) * fps)
        t_out += p["dur"]
    return None                         # word was cut — must not be captioned
```

**Why:** per-piece `-ss/-t` rounds independently, so a re-transcribed cut and the true map diverge at
every join and the error accumulates one way. It reached **−18 frames (0.3 s)** by the end of one reel.

- Walk captions and source words **in order and consume as you go**, so repeated words resolve to the
  right occurrence.
- Words the cut dropped break a naive walk — pin those by source second by hand.
- **Retime SFX cues and stamp boundaries in the same pass** — they drift with the captions.
- Re-transcription is the right tool for **checking**, never for **deriving**.

## Step 2 — force-align the caption text to the delivered audio

The caption text is authored (cleaned transcript), so hand wav2vec2 the **known text**:
```python
al = whisperx.align(
    [{"start": a, "end": b, "text": "<that section's words>"}, …],
    *whisperx.load_align_model(language_code="en", device="cpu"),
    whisperx.load_audio("cut_voice16k.wav"), "cpu")
```
Run it on the **voice stem of the cut**, one segment **per section**, bounded — so a co-streamer, a TTS
donation or game dialogue can never capture the streamer's words.

**Why:** a decoder guesses onsets around pauses. Five review runs failed at +30, +28, +23, −16, −15
frames with a good cut. After forced alignment: 43/43 matched, mean +5.7 f, worst +7 f.

### When the aligner itself drifts

WhisperX's aligner **smears a long segment** — one case ran the back half up to **2.9 s early**, and
every check missed it (the review gate re-transcribes with the same aligner and reproduces the drift).
**The reliable measurement:** transcribe **short windows in isolation** (5 s windows, 2 s overlap, +6 dB,
word timestamps, keep words whose start < 5 s). Distrust each window's first word (clamped to the edge),
and cross-check boundaries against the **20 ms RMS silence map**, which is ground truth. **The proof
that settles a disagreement: does the reading explain the whole envelope?**

## Step 3 — the RMS pause audit (every clip, before rendering)

```python
# 10 ms RMS envelope of the voice stem; threshold = floor + 0.45*(speech − floor)
# FLAG any caption run whose span is > 75% below threshold
```
A run over dead air **pops exactly when the streamer stops talking**. A pause **inside** one phrase is
invisible to phrase-boundary checks — split the run at the pause. `review_reel.py --captions` runs this
audit on the render too.

## Step 4 — run construction (the generator's rules)

| Rule | Why |
|---|---|
| **≤ 3 words, flushed unconditionally** | A grouper that flushes on "≥3 and not a function word" grows to four. Flush at 3; any later merge must re-check the cap. |
| **Never open a run with an article** | The sync checker matches the FIRST word and locks onto the wrong "a" — a false +17 f. |
| **Never end a run on a function word** | The article travels with its noun. |
| **≥ 0.30 s per run** | Below that it's a flash, not a caption. Merge offenders. |
| **`to` is EXCLUSIVE — equal to the next run's `from`** | `to = next.from − 1` leaves a one-frame hole at every boundary (~59 flickers in 44 s). |
| **Break on punctuation and pauses > 0.45 s** | |
| **Never split a sentence on its internal emphasis pause** | Cutting it reads as a jarring jump. |

## Step 5 — assert anchors by SECTION, not by ordinal

Any `anchor(word, nth)` is a latent bug: the nth is a guess about a transcript that gets edited. One
normalisation (`"3" → "three"`) moved a graphic **950 frames**. Assert each stamp's anchor word falls in
its expected section, and fail the build if not.

## Step 6 — every beat gets a caption

- Suppress a caption only when on-screen text is **literally** saying the same words.
- **Don't blank captions to dodge a layout problem** (`stream-layouts` grow rule).

## Size and grouping

Captions are **display type**: base ~72 px at 1080 wide, floor **≥ 78 px**, auto-shrink only for a rare
long line (`chars × size × 0.54` vs the 1010 px safe width). Big type won't fit beyond 3 words — that's
why runs are short. Full-phrase small captions held 2–3 s were rejected twice.

## Stream-specific rules

- **Second voices:** caption a co-streamer or donation TTS only when their line matters to the moment,
  in a different colour or with a name prefix ("CHAT:", "DUO:"). Never attribute their words to the
  streamer.
- **Profanity:** match the platform. Mask in captions (`f***`) and, if needed, bleep the audio in the
  same pass — and retime nothing else.
- **Game text / chat on screen** is not a caption. Don't caption what the viewer can already read.
- **Hindi / Hinglish streams:** force the right language model per span (English models silently
  translate). Decide per channel whether captions are translated English or romanised, and keep it
  consistent.
