---
description: One-time setup for live-clipper — install dependencies, check tools, explain accounts and SFX.
---

Set up the live-clipper plugin on this machine.

1. Find the plugin folder: it is the folder containing `scripts/setup.sh` for the live-clipper
   plugin (look under `~/.claude/plugins/` if you don't know it). Run
   `bash <plugin>/scripts/setup.sh` with the Bash tool and a long timeout (it downloads torch).
   If the user said "lite", pass `--lite`.
2. Show the tool check it prints. For anything `False`, give the one-line fix (brew/apt/pip).
3. Tell the user to restart Claude Code (so the `clipper` MCP server starts), then:
   - Posting accounts: edit `~/.live-clipper/accounts.json`; YouTube needs
     `credentials/youtube_client_secret.json` and `scripts/auth_youtube.py <account>`; Instagram
     needs a Business/Creator account, its user id, a token in the env var named in accounts.json,
     and `CLIPPER_S3_BUCKET` (plus AWS credentials) for the public video URL.
   - SFX (optional): licensed files in `~/.live-clipper/sfx`, then the `sfx_catalog.py` line setup printed.
4. Remind them of the rules in the plugin README ("Rules of use") in 3 bullets: only clip streamers
   who allow it, credit every clip, nothing posts without their approval in /publish.
