# Third-party notices

## Adapted editing skills

Several files in `skills/` (and the scripts under `skills/shortform-cutaway/scripts/`,
`skills/take-geometry/scripts/measure_take.py` and `skills/shortform-finish/scripts/reverb_throw.py`)
are adapted from a short-form video creator's editing skills. `skills/ADAPTED.md` lists exactly
what was kept and what was changed in each one.

> **TODO before making this repository public:** replace this paragraph with the original
> author's name, a link to the source, and the licence those skills were shared under. If that
> licence doesn't allow redistribution of adapted versions, remove the adapted files (or get the
> author's permission) before publishing. The MIT licence in `LICENSE` covers only the code
> written for this plugin.

## Page playbook inspiration

`skills/page-playbook` and `skills/growth-loop` (and the page features in `server/clipper/growth.py`)
are inspired by the "Faceless GTA 6 Clipping Page: Full Setup Prompt" by Parker
(@DotComParker on X, shared publicly Nov 17, 2026:
https://x.com/DotComParker/status/2122708338039250992), as transcribed by AI Automation Society.
The rules were rewritten for this plugin; no text is reproduced verbatim beyond short rule names.
All credit for the original playbook to him.

## Runtime dependencies

Installed by `scripts/setup.sh`; not included in this repository. Each is under its own licence:
FastMCP, NumPy, OpenCV, yt-dlp, Streamlink, Requests, Google API Python Client,
google-auth-oauthlib, Boto3, WhisperX, Demucs, and FFmpeg (installed separately).
