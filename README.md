<p align="center"><img src=".claude-plugin/icon.png" width="120" alt="live-clipper icon"></p>

<h1 align="center">live-clipper</h1>

<p align="center"><b>Paste a stream link. Get vertical shorts that are cut, captioned and reviewed, ready to post.</b><br>
A Claude Code plugin built as a software factory: 14 sub-agents, 11 skills, one MCP server.</p>

<p align="center">
<img src="https://img.shields.io/badge/Claude%20Code-plugin-orange" alt="Claude Code plugin">
<img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT license">
<img src="https://img.shields.io/badge/status-alpha-yellow" alt="alpha">
<img src="https://img.shields.io/badge/python-3.10--3.12-green" alt="Python 3.10-3.12">
</p>

<!-- Put your demo here: a 30-60 s screen recording of /clip-vod producing clips, plus one finished clip.
     ![demo](docs/demo.gif) -->

```
/plugin marketplace add vaibhav-barman/live-clipper
/plugin install live-clipper@live-clipper-marketplace
/live-clipper:clip-setup
/live-clipper:clip-vod https://www.twitch.tv/videos/... --clips 5 --streamer NAME --platform Twitch
```

## How it works

The plugin turns live streams and VODs into vertical shorts (1080×1920) using a **software-factory**
design. Single-agent **loops** (do → check → fix) are chained into **graphs** (Ingest, Production,
Distribution, Feedback), and the graphs run together as a **factory** that shares one SQLite ledger.

Agents decide; deterministic tools do the work. The `clipper` MCP server handles the media (ffmpeg,
yt-dlp, streamlink, Demucs, WhisperX, OpenCV) and keeps the ledger. The 14 sub-agents handle the
judgement calls: which moment, where to cut, what the stamp says, whether a clip passes review.

```
/clip-vod or /clip-live  (the factory manager, your main session)
│
├─ Graph 1 · Ingest        stream-watcher → transcriber → signal-analyst
├─ Graph 2 · Production    hook-scout → clip-cutter ⇄ cut-auditor → layout-geometer
│                          → vertical-editor → captioner → renderer ⇄ quality-critic
├─ Graph 3 · Distribution  copywriter → (you approve in /publish) → publisher
└─ Graph 4 · Feedback      feedback-analyst → rubric weights (you approve)
```

**What makes the clips good:** cuts land on the voice waveform, not on transcript timestamps, so no
clipped words. Every cut is checked by audio energy, because a transcript can hide a doubled line.
The facecam is measured, never guessed, so the face keeps its headroom. Nothing moves across a cut.
Captions are force-aligned and kept to three words or fewer. A second model reviews every render
before you see it.

## Status: alpha

Tested: the full pipeline on a synthetic stream (ingest → signals → scoring → cut → assembly →
captions → split / full-frame / gameplay renders → review), the approval gate, the MCP server over
stdio, and `claude plugin validate`.
Not yet tested on real streams: Demucs/WhisperX speech, facecam detection on real faces, live
recording, YouTube/Instagram uploads. Please open an issue with your logs if something breaks.

## What's inside

| folder | contents |
|---|---|
| `.claude-plugin/` | `plugin.json` (manifest) and `marketplace.json` (so the repo can be installed as a marketplace) |
| `agents/` | 14 sub-agents, one job each, with a loop check each |
| `commands/` | `/clip-setup`, `/clip-vod`, `/clip-live`, `/clip-stop`, `/clip-status`, `/publish`, `/clip-feedback` |
| `skills/` | 11 skills: the rules every agent follows (`ADAPTED.md` lists what each one keeps from its source) |
| `server/` | the `clipper` MCP server: 31 tools, a background task runner, the SQLite ledger |
| `scripts/` | `setup.sh`, `run_server.sh`, `auth_youtube.py` |
| `.mcp.json` | starts the server when the plugin is enabled |

Your data never lives in the plugin folder. Everything goes under `~/.live-clipper/` (set
`CLIPPER_HOME` to move it): `ledger.sqlite`, `jobs/<job>/clips/<clip>/…`, `credentials/`,
`accounts.json`, `sfx/`, `logs/`.

## Install

Requirements: macOS or Linux, **Python 3.10–3.12** (WhisperX doesn't support 3.13 yet), ffmpeg,
about 5 GB of disk for the speech models.

```bash
# macOS
brew install python@3.12 ffmpeg

# 1. add the plugin
/plugin marketplace add vaibhav-barman/live-clipper   # or a local clone: /path/to/live-clipper
/plugin install live-clipper@live-clipper-marketplace

# 2. install dependencies (venv in ~/.live-clipper/venv)
/live-clipper:clip-setup          # or: bash /path/to/live-clipper/scripts/setup.sh

# 3. restart Claude Code so the clipper MCP server starts
```

To publish, set up accounts once (see "Accounts" below). Clipping and reviewing work without them.

## Use

| command | what it does |
|---|---|
| `/live-clipper:clip-vod <url-or-file> --clips 5 --streamer NAME --platform Twitch` | full pipeline on a recorded stream |
| `/live-clipper:clip-live <url> --clips 10 --minutes 120 …` | record in 60 s chunks and clip near-live |
| `/live-clipper:clip-stop [job]` | stop a live recording |
| `/live-clipper:clip-status [job]` | jobs, clips, what's waiting for approval |
| `/live-clipper:publish [job-or-clip]` | watch, approve and post. **The only way anything gets posted** |
| `/live-clipper:clip-feedback` | stats → proposed rubric changes → you decide |

Each clip ends up in `~/.live-clipper/jobs/<job>/clips/<clip>/` as `final.mp4`, with
`review/report.md` and two contact sheets next to it, plus every intermediate (`cut.json`,
`captions.json`, `overlay.mov`, …) so any stage can be re-run.

Start with a VOD. `/clip-live` is near-live: a clip arrives a few minutes after the moment, because
each moment needs about 45 s of recording after it before it can be scored.

## Rules of use

These are built into the agents and the server. They're listed here so you know what to expect,
and so you don't work around them.

1. **Only clip streamers who allow it.** Follow their clipping policy and each platform's rules on
   reuse. The commands ask before starting if this isn't clear.
2. **Credit every clip.** Every clip ends with an on-screen credit strip (streamer + platform), and
   every caption carries a credit line. Set `--streamer` and `--platform` on every job.
3. **Nothing posts without you.** Clips stop at `ready_for_approval`. Only `/publish` can approve,
   only after you pick the clip in that session, and approval expires after 24 hours. The server
   refuses to upload anything else. Never add `approve_clip` or `publish_clip` to auto-allowed tools.
4. **Never change what the streamer meant.** The cutter trims dead air and restarts but never
   reorders lines or drops a negation. A short payoff preview at the start is allowed only as an
   obvious repeat.
5. **No fake footage.** No AI-generated or restyled footage of the streamer.
6. **Real numbers only.** Viewer counts, scores and donations in stamps or copy are read off the
   stream, never made up.
7. **`--clips N` is a cap, not a quota.** A dull stream gives fewer clips. Lowering `min_score` to
   force more clips makes the channel worse.
8. **Watch every clip before approving it.** The review gate catches a lot, but you are the last check.
9. **Keep credentials out of the plugin.** Tokens live in `~/.live-clipper/credentials/` (mode 700)
   and in environment variables. Never commit them.
10. **Don't post the same clip twice to one account.** The server blocks it; don't get around it by
    re-rendering.

## Accounts

`~/.live-clipper/accounts.json` (setup writes an example):

```json
[
  {"name": "main-yt", "platform": "youtube", "privacy": "public"},
  {"name": "main-ig", "platform": "instagram", "ig_user_id": "1784…", "token_env": "IG_TOKEN_MAIN"}
]
```

- **YouTube Shorts:** in Google Cloud, enable the YouTube Data API v3 and create an OAuth *Desktop*
  client. Save it as `~/.live-clipper/credentials/youtube_client_secret.json`, then run
  `~/.live-clipper/venv/bin/python scripts/auth_youtube.py main-yt` once per account. Uploads made
  by apps that haven't passed Google's audit may be forced private; set `"privacy": "private"`
  until yours is verified.
- **Instagram Reels:** needs an Instagram Business or Creator account linked to a Facebook Page and
  a long-lived access token with `instagram_content_publish`. Put the token in the env var named by
  `token_env`. Instagram fetches the video from a public URL, so set `CLIPPER_S3_BUCKET` (plus AWS
  credentials) and the server uploads there and passes a 1-hour presigned link.

## Sound effects (optional)

Put SFX you're licensed to use (CC0 or royalty-free) in `~/.live-clipper/sfx/`, with names that say
what they are (`whoosh_01.wav`, `pop_02.wav`), then build the catalogue:

```bash
~/.live-clipper/venv/bin/python skills/sfx-design/scripts/sfx_catalog.py ~/.live-clipper/sfx > ~/.live-clipper/sfx/catalog.json
```

Without a catalogue, clips render with the stream's audio only.

## Troubleshooting

- **"clipper" tools missing:** run setup, then restart Claude Code. `bash scripts/run_server.sh`
  should print a FastMCP banner. If it says "not set up", run setup again.
- **`voice_is_stem: false`:** Demucs isn't installed, so cutting and audits read the mixed audio.
  Run setup without `--lite`.
- **Facecam not found:** the layout-geometer looks at `facecam_check.jpg` and sets it by hand with
  `set_geometry`. OpenCV 5 has no Haar cascades; setup pins `opencv-python-headless<5`.
- **A clip stuck in `needs_human`:** read `data.audit` or `data.review` with `get_clip`, fix it by
  hand or adjust the beats, then re-run from that stage.
- **Logs:** `~/.live-clipper/logs/<task>.log` for every background task.

## Known limits

- Speech and separation run on CPU: roughly 1–3 minutes per clip on a MacBook Air (Demucs +
  WhisperX), and the fast scouting pass over a 3-hour VOD takes a while. Start with shorter VODs.
- Chat bursts are used when available: YouTube chat replay is downloaded automatically. Twitch chat
  isn't recorded yet (signals fall back to audio, scene cuts and keywords).
- Instagram metric names change between Graph API versions. If `fetch_stats` returns errors for
  Instagram, update the metric list in `server/clipper/publish.py`.
- The thresholds in `cut-audit` and `reel-review` were measured on talking-head audio. Recalibrate
  them on your first few stream clips (the skills say how).

## License and credit

MIT — see [LICENSE](LICENSE). Several skills are adapted from another creator's editing skills;
see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and `skills/ADAPTED.md`.

If live-clipper saves you editing time, a ⭐ helps other people find it.
