---
name: shortform-cutaway
description: "The CUT stage for stream clips. Turns a scored stream window into a tight, flowing cut: separate the voice from game audio, WhisperX finds the words, the model keeps the thread (trims dead air, chat reading and restarts — never reorders meaning), then every EDGE is decided on the voice envelope (release-based tails, onset-based heads, no cut back over a 'hm', micro-fades at every real cut), and an edge sweep + cut-audit prove it before anything is styled. Use for 'cut this moment', 'tighten it', and whenever a cut sounds abrupt, clips a word, or keeps a fumble. Does NOT do captions/layout/SFX (= shortform-finish, stream-layouts)."
---

# SHORTFORM CUTAWAY (stream edition) — the cut stage

> **THE JOB:** WhisperX tells you **which** words were said → the model decides what stays → the builder
> cuts on the **audio envelope**, not on the ASR's word times → every edge is swept and audited before
> styling. Output = a cut list (`cut.json`) + a matching MP4.

Adapted from the creator's v2 rough-cut skill. **The essence kept:** words from WhisperX, edges from the
envelope, every edge proven, the dead ends never repeated. **What changed for streams:** the envelope is
read off a **voice stem** (game audio and music ruin it), and the editor step may trim but must **never
rearrange the streamer's meaning**.

Stage 1 of the pipeline. Between this and styling sits **`cut-audit`** — never skip it.

## Why each rule exists (every line is a real miss in the original skill)

| naive rule | what shipped | rule here |
|---|---|---|
| tail = WhisperX end + 0.06 | last syllables lost ("absolutely [free]") | tail = envelope **release** + 0.06, capped before the NEXT word's **envelope onset** − 0.03 |
| head = WhisperX start − 0.04 | onsets cut (WhisperX started 0.4 s late) | head = the envelope onset found by walking back from the word |
| head searches back for 120 ms of quiet | walked over a separate "hm" and played it | never reach back over a separate voiced island (`islands()`) |
| beat END written by eye | 15 of ~200 ENDs were the START of the last word → word dropped | END = the last word's release; the builder warns when an END sits on a word start or inside a word |
| gaps measured on word times | an under-run word end invented a "silence" inside a phrase | split a beat only where the **envelope** is silent > GAP |
| contiguous pieces re-join | a dropped fragment came back | never re-join across a dropped word |
| hard cuts, raw | a click at cuts that land on voice | 15 ms fade-in / 25 ms fade-out on every real cut (skip source-contiguous joins) |
| trust WhisperX everywhere | on a 23-min take it drifted 15 s | on windows > 5 min, verify every piece with isolated-window ASR (`isowords.py`) |
| **(stream) envelope on the mixed track** | **gunfire and music read as "speech"; edges land on explosions** | **build the envelope from a Demucs voice stem; render from the original mix** |

## SETUP (once)

```bash
python3.11 -m venv ~/wx-env && ~/wx-env/bin/pip install whisperx demucs
export HF_HOME=~/wx-cache      # faster-whisper model + ~360 MB alignment model
```
WhisperX needs **Python ≤ 3.12** + torch. The scripts need only `numpy` (and `OPENAI_API_KEY` for
`probe.py` / `isowords.py` / `listen_back.py`, or swap those calls to a local Whisper).

## THE METHOD

**In the plugin:** `prepare_clip` (clipper MCP server) already does steps 1–2 into the clip folder
(`window.mp4`, `mix.wav`, `voice16k.wav`, `words.json` in WINDOW seconds) and `assemble_cut` does the
assembly from your `cut.json`. You run steps 3–7 with the scripts (`plugin_info` gives their paths).
The manual commands below are the same pipeline by hand.

```bash
W=work/<stream_id>/<clip_id>; mkdir -p "$W"; SRC=chunks/window.mp4   # the scored window ±5 s
# 1. voice stem (envelope + ASR) and the original mix (what we render)
ffmpeg -y -i "$SRC" -vn -ac 2 -ar 44100 "$W/mix.wav"
~/wx-env/bin/python -m demucs --two-stems=vocals -o "$W/sep" "$W/mix.wav"
ffmpeg -y -i "$W/sep/htdemucs/mix/vocals.wav" -ac 1 -ar 16000 "$W/a.wav"
# 2. words
HF_HOME=~/wx-cache ~/wx-env/bin/python scripts/whisperx_align.py "$W/a.wav" "$W/wx.json"
#    window > ~5 min? also: python3 scripts/isowords.py "$W/a.wav" "$W/iso.json"
# 3. EDITOR step (the model): read the words, write beats.txt — THE THREAD (below)
# 4. build on the envelope
python3 scripts/build_wx2.py "$W/a.wav" "$W/wx.json" "$W/beats.txt" 0.30 30 > "$W/cut.json"
#    read every WARN line; fix beats.txt and rebuild until none are left
# 5. sweep every edge
python3 scripts/edge_sweep.py "$W/cut.json" "$W/wx.json" [--iso "$W/iso.json"]
# 6. settle each doubtful flag (unpadded 1.5–3 s windows):
python3 scripts/probe.py "$W/a.wav" 10.1 12.9 57.6 58.5
# 7. listen to the assembled cut around every join
python3 scripts/listen_back.py "$W/cut.json"
# 8. hand to cut-audit; when it passes, assemble (below)
```
`python3 scripts/envtools.py a.wav 57.9` prints an ASCII envelope around any time — the fastest way to
see whether a word is whole (`#` loud, `+` voiced, `.` near threshold, space = quiet, `|` = the cut).

### Step 3 — THE THREAD (only the model can do this)

Write `beats.txt`, one beat per line `START END label`. For a stream clip the story is already there;
the job is to **remove what slows it, not to rewrite it**: hook → build → payoff → reaction.

- **Keep the moment in order.** No moving a line earlier to make a better hook. The only exception is
  the flagged payoff tease from `hook-rubric` (a short repeat at frame 0, then the clip in order).
- **Drop:** dead air, reading chat aloud when it isn't the joke, "wait, let me…" restarts, AFK gaps,
  ad-break or sponsor reads, ums before a line.
- **Keep:** every word that carries the meaning, the streamer's own reaction, and **any negation**.
  If dropping a word changes what they said ("I'm **not** quitting"), it stays.
- **Restarts:** the later take usually wins, but a later take can be a *prefix* of a restart — probe
  before trusting it.
- **END = where the last kept word RELEASES**, not where the next word starts. `build_wx2` warns; obey it.
- **A sentence's internal pause is not a silence to cut.** Cutting a 0.2 s emphasis pause reads as a
  jarring jump.
- **GAP** (envelope silence that splits a beat): **0.30** punchy · **0.45** for a calmer streamer.
  Inter-beat gaps in natural speech are ≥ 0.6 s; anything flagged at 0.3–0.5 s deserves a listen.
- **Gameplay-only beats** (no speech, the action is the point): `build_wx2.py` is speech-only and
  will drop them. Leave them out of `beats.txt`, then add each as a piece in `cut.json` by hand
  (`a`, `b`, `dur`, `beat: "GAME"`, fades true), with its ends placed on the video's own scene cuts
  (`motion_score.py` helps pick an in-point that is already moving).

### Assemble (ffmpeg, the plugin's route)

Render each piece from the **original mix** with `-ss a -t dur`, `afade` in/out where the piece says
`fade_in`/`fade_out`, then concat with the **concat filter** and a re-encode to **CFR 30 fps**. Drive
the loop from Python, not a bash `while read`. Reframing is NOT done here — `stream-layouts` does it
on the assembled cut, so the layout can change only at hard cuts.

Other editors (Resolve, Premiere EDL, Remotion, HyperFrames) can consume `cut.json` the same way:
pieces are `a` (source start, s) + `dur` (s), fades flagged per edge.

## Long windows (> 5 min, or several takes in one window)

- Run `isowords.py` and `edge_sweep.py --iso`. When WhisperX and the isolated words disagree by > 1 s,
  trust the isolated time for **where** and the envelope for **the edge**.
- Keep the cut **as data** (`(id, a, b, opts)` + `DROP` ranges + `HEAD_FIX`/`TAIL_FIX` per piece id) so
  every decision is reviewable and every rebuild reproduces it.

## ⛔ DEAD ENDS (do not repeat)

1. **Whisper segments as the silence cutter** — they smooth over think-pauses.
2. **Fixed-dB silencedetect** — clips quiet words; fails when mic distance or game volume varies.
3. **faster-whisper or WhisperX word times for edges** — ends early, starts late.
4. **Trusting a clean transcript** — ASR de-duplicates an immediate repeat (`cut-audit`).
5. **Padded short probes** — silence padding makes Whisper loop and "hear" repeats that aren't there.
6. **Re-joining neighbours blindly** — a dropped fragment comes back.
7. **(stream) The envelope of the mixed track** — game SFX and music look like speech.

## SCOPE

**DOES:** voice separation · word alignment · the thread · envelope-exact edges · micro-fades · edge
sweep · probes · listen-back · `cut.json` + an MP4.
**DOES NOT:** captions · layout/reframe · punch-ins · SFX · loudness (→ `stream-layouts`,
`shortform-finish`, `caption-align`, `sfx-design`, `render-ops`).

Scripts: **`build_wx2.py`** (builder) · `envtools.py` · `edge_sweep.py` · `probe.py` · `isowords.py` ·
`listen_back.py` · `whisperx_align.py` · `motion_score.py` (in-points for GAME beats).
