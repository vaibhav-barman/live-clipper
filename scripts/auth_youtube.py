#!/usr/bin/env python3
"""One-time YouTube login for a posting account. Opens a browser; stores a refresh token.

    ~/.live-clipper/venv/bin/python scripts/auth_youtube.py main-yt
    Windows: %USERPROFILE%\\.live-clipper\\venv\\Scripts\\python.exe scripts\\auth_youtube.py main-yt

Needs ~/.live-clipper/credentials/youtube_client_secret.json — an OAuth 2.0 *Desktop* client from
Google Cloud Console with the YouTube Data API v3 enabled.
"""
import os
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]
home = Path(os.environ.get("CLIPPER_HOME", Path.home() / ".live-clipper")).expanduser()
if len(sys.argv) != 2:
    sys.exit(__doc__)
secret = home / "credentials" / "youtube_client_secret.json"
if not secret.exists():
    sys.exit(f"missing {secret}")
creds = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES).run_local_server(port=0)
out = home / "credentials" / f"youtube_{sys.argv[1]}_token.json"
out.write_text(creds.to_json(), encoding="utf-8")
os.chmod(out, 0o600)
print(f"saved {out}")
