---
name: cut-audit
description: "Prove a clip's cut is actually clean before it is styled or rendered. ASR cannot hear a false start — it de-duplicates immediate repeats — so this skill gates on ENERGY and SPECTRUM of the voice stem instead: stretched-word screening, syllable-budget folds, the clip-list screen, onset-vs-word ratio, spectral self-similarity (repeat scan), per-burst isolated probes, and the tail/head release audit. Use after every cut, whenever a doubled or clipped word is suspected, and whenever one caption is persistently out of sync."
---

# CUT AUDIT — the transcript is not evidence

> **THE ONE FACT:** an ASR language model is built to produce fluent text, so **two identical adjacent
> phrases decode as one**. A clean transcript proves nothing. In the original project, **five separate
> transcripts** called a cut clean that had two doubled lines in the first 20 seconds. A human found
> them by listening.

**Streamers restart lines constantly**, talk over game audio, and get interrupted by alerts and TTS
donations. Assume there are more problems than you found.

Adapted from the creator's skill. **Kept:** every gate and its measured threshold. **Changed:** all
energy reads run on the **Demucs voice stem** (`a.wav` from `shortform-cutaway`), never on the mix —
on the mix, a gunshot is a "syllable" and a music bed is "speech". Thresholds were measured on a
talking-head mic; **re-calibrate them on your first 3–5 stream clips** and note the new values here.

## The gates, in order

Run all of them. Each catches a class the others structurally cannot. Loop: any FAIL → back to the
cutter with the evidence, max 2 rounds, then flag the clip for a human.

### 1. Stretched-word screen (before beats are written)

Any word longer than ~1 s is an artifact: the aligner smeared one word across a hidden pause or a retake.

- Flag every word with `end − start > 1.0 s`; **at a clip EDGE, probe regardless of length**; for a
  short function word, **> 0.55 s** is already suspicious.
- Resolve each against an **RMS energy map** (40–50 ms hops), **never against a second
  transcription** — re-aligning disagrees with itself, and a small model under ~5 s hallucinates.
- Patch `s`/`e` in a **copy** of the alignment json, with a comment naming the evidence.

**Screen by SYLLABLE BUDGET too.** A 0.52 s word once hid a whole folded sentence. Walk each RMS speech
run: does the text assigned to it plausibly fill it? Compare voiced-blob count (≈ one per syllable)
against the text.

**The mirror artifact: an UNDER-RUN word end invents a false gap**, and the builder cuts inside a
phrase. Before locking `GAP`, check the smallest inter-word gap the builder will cut on against
energy. **Merging a gap can never clip a word, only cutting can** — when ambiguous, err toward the
larger `GAP`.

### 2. The clip-list screen (free, before anything renders)

Look at the CLIP list, not the word list. **A clip under ~25 frames whose text is a single word is
almost always a swallowed false start** — visible in the builder's stderr before a frame renders.

### 3. Onset-vs-word ratio, per piece

```
ratio = (syllable onsets: >1.45× rise over 20 ms, ≥ 0.12 s apart) / (words in that piece)
```
Clean → **0.85–1.15**. A doubled take → **~2.0**. Also: aligner's last word-end vs the envelope's last
speech — **a gap > 0.6 s means the aligner collapsed the piece**; distrust its word times.

### 4. Spectral self-similarity — the gate that catches a prefix false start

Split the voice into speech bursts from the envelope, **joining only gaps < 0.08 s** (a wider join
merges a false start into its redo and hides it). DTW-compare each burst's log-mel frames against the
**head of the next burst**.

Measured originally: real false-start/redo pairs **0.83–0.91**; unrelated speech **~0.66**. Gate at
**0.78**. `reel-review/scripts/review_reel.py --voice a_cut.wav` runs this same scan on the render as
a FAIL gate.

### 5. Per-BURST isolated probes (not per-window)

**Any probe wide enough to contain both halves of a repeat lets the model merge them.** Segment by
energy (threshold ≈ noise floor + 14 dB, min 0.22 s, merge gaps < 0.18 s), transcribe **each burst
alone**, flag adjacent bursts whose first word matches.

- A sub-second fragment transcribes as nonsense alone — **judge it by position and energy, not words.**
- A genuine parallel construction ("in round 2… in round 3…") will flag and must be kept.
- **Probe quiet regions LOUDER** (`volume=6dB`). Quiet false starts are invisible otherwise.
- **When the RMS map calls a "silence" speech, PROBE it — do not reason it away.** That exact
  rationalisation cost two full re-renders originally.

### 6. Padded micro-probes — decisive, and dangerous

Short padded windows (0.6–1.2 s, ~0.6 s silence pad) are **unreliable for discovering** what was said
but **decisive for choosing between two hypotheses** the energy map already bracketed. **But padded
probes HALLUCINATE REPEATS** — a repeat heard only in a padded probe is not evidence; confirm with an
unpadded ≥ 2.5 s window plus the energy map.

### 7. The assembled-cut listen-back

Re-transcribing the assembled cut is **the right alarm and never the right diagnosis.** Whisper invents
words to make a splice grammatical and puts a fold on the wrong side of the join. It is still a useful
net for repeats landing in two **different** pieces.

### 8. Tail / head release audit (every boundary, before the first render)

Phoneme alignment marks a word's END before its audible decay finishes. For every boundary: decode the
voice stem around the cut (RMS per 20 ms), flag voice-active-at-cut, find the release (first ~100 ms
below threshold), extend to `release + 0.10`, **capped at `next_dropped_word_onset − 0.06`**. Flag
HEADS where voice runs before the piece start.

- `NO RELEASE` — you cut mid-flow. Extend through the phrase or move the cut.
- Voice after the cut can be the NEXT restart's onset, not a decay — compare against the words.
- An END+HEAD flag at nearly the same source time = you split continuous speech. Merge or butt them.

## Stream-specific gates

- **Second voices.** Duo streams, Discord calls, TTS donations, game dialogue. Demucs keeps all human
  voices in the vocal stem. Before trusting a burst as "the streamer", check it against the facecam
  (mouth moving?) or a speaker-diarisation pass. Never cut a co-streamer's line in half to keep the
  streamer's.
- **Alerts and music with vocals** leak into the stem. A burst that matches a known alert sound or
  sits under a lyric is not speech.

## Take selection

**Keep the COMPLETE take and drop the attempt** — never both, never the attempt just because it came
first. **The inverse repair exists:** a 0.14 s opening burst can be the real first word. Before dropping
any sub-0.3 s opening burst, transcribe the hook WITHOUT it: if the line loses its subject, the burst
was the take.

## After a repair — three independent consequences

1. **Neighbouring word TIMINGS drift.** Pin the repaired region's captions to the delivered audio
   (`caption-align`); elsewhere the source arithmetic wins.
2. **The boundary word's TEXT can be wrong** — the aligner may have spent the label on a discarded
   burst. Fix with a **source-time override** keyed to seconds, not word index:
   `TIME_FIX = [(41.80, 41.95, "Here's")]`.
3. **Re-align each rebuilt span IN ISOLATION** and splice the corrected word times back before
   regenerating captions.

## Assembly

- **The concat must be CFR.** A VFR concat undercounts `nb_frames` and silently clips the last word.
  Use the concat **filter** (the demuxer duplicates the head frame).
- **Never cut a sentence's internal pause.** The internal-silence rule exists to expose hidden
  restarts, not to remove emphasis.

## Two standing tells

- **A persistent single-caption sync outlier is a prime suspect for a collapsed repeat**, not a matcher
  artifact.
- **When a human flags a repeated phrase, go straight to a 50 ms RMS map plus an independent ASR engine
  on that window.**
