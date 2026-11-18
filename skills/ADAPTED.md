# Skills for the live-clipper plugin

These skills were adapted from a short-form creator's editing skills for clipping **other people's live
streams** into 9:16 shorts. Each skill keeps the original's core method and measured numbers, and
removes that creator's personal setup (accounts, brand colours, SSD paths, Remotion repo, house library).

| skill | adapted from | essence kept | what changed |
|---|---|---|---|
| `clip-router` | `reel-edit` | execute-not-recite, fixed pipeline order, hard rules for every format, review gate | stream layouts replace creator formats; honesty + credit rules; clip count is a cap |
| `hook-rubric` | (new) | — | scoring rubric for stream moments |
| `shortform-cutaway` | `shortform-cutaway` v2 | WhisperX for *what*, envelope for *where*, red thread, dead ends | Demucs voice stem; trim only, never reorder meaning; ffmpeg route |
| `cut-audit` | `cut-audit` | "the transcript is not evidence", all 8 gates + thresholds | runs on the voice stem; second-voice + alert gates; recalibrate note |
| `take-geometry` | `take-geometry` | distributions, detectors that lie, solve-don't-nudge, headroom, alpha guard | Step 0 finds the facecam; facecam ≤ 2.25×, gameplay ≤ 1.1× |
| `stream-layouts` | `split-screen` + `caption-edit` | stable frame, lane caption-only, hard cuts, no zoom at cuts, hook budget, stamps not pills | Split / Full-frame / Gameplay-only; solved card heights; credit close replaces Follow card |
| `shortform-finish` | `shortform-finish` v2 | nothing animates across a cut, static punch alternation, exp fades, sizes, levels | ffmpeg default; gameplay rules; no music beds |
| `caption-align` | `caption-align` | three clocks, derive→force-align→pause audit, run rules, section anchors | `cut.json` map; voice stem; second voices, profanity |
| `sfx-design` | `sfx-design` | peak scheduling, sound by motion, final-domain volume, measurement trap, residual check | build-your-own catalogue (`sfx_catalog.py`); ffmpeg `amix normalize=0`; lower density |
| `render-ops` | `render-ops` | frozen frames, audio drift fix, loudness on the encoded file, frame-count check, delete rules | ffmpeg only; Remotion bundle/entry material removed |
| `page-playbook` | Parker's (@DotComParker) clipping-page prompt | credit ≠ permission, transform, spoilers, never-list, copy rules, takedowns | enforced in code (`check_copy`, permissions, gates) |
| `growth-loop` | same prompt | 12/24/72 h reads, one test a day, daily/weekly reviews, learning.md | automated reads, scoreboard export |
| `reel-review` | `reel-review` | script measures / model judges, different model, BLOCKER/FIX/NIT, honest reading | ships `review_reel.py` (the original referenced it but didn't include it) |

Left out entirely: `vlog-edit`, `longform-edit`, `broll-style-edit`, `card-list-edit`, `whiteout-edit`,
`paper-drawer-edit`, `layered-head-edit` (the creator's own formats), `genvideo`, `omni-restyle`
(generating/restyling a streamer's footage misrepresents them), `broll-select`, `mg-kit`,
`screen-capture`, `design-asset` (depend on his library or screen recordings), `asset-plan` (its
real-numbers rule lives on in `clip-router`).

**Before publishing the plugin:** confirm the original skills' licence allows redistribution of
adapted versions, and credit the source as it requires.

## Requirements

- ffmpeg + ffprobe, Python 3 with numpy (all scripts)
- opencv-python (`take-geometry/scripts/measure_take.py`)
- Python ≤ 3.12 venv with `whisperx` and `demucs` (cut + captions)
- `OPENAI_API_KEY` for `probe.py`, `isowords.py`, `listen_back.py` (or swap to a local Whisper)
