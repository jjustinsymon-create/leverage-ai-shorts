#!/usr/bin/env python3
"""
YOUTUBE AUTHORIZATION — RUN THIS ONCE ON YOUR OWN COMPUTER.

Steps:
  1. Run: python auth_youtube.py
  2. A browser window opens — log in with your YouTube channel's Google account
  3. Click "Allow"
  4. Copy the JSON output
  5. Paste it into GitHub -> Settings -> Secrets -> YOUTUBE_TOKEN

Requirements: pip install google-auth-oauthlib
You also need client_secrets.json from Google Cloud Console (see setup guide).
"""

import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def main():
    print("Opening browser for YouTube authorization...")
    print("Log in with the Google account that owns your Leverage AI channel.\n")

    flow  = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
    creds = flow.run_local_server(port=8080, open_browser=True)

    output = {
        "token":         creds.token,
        "refresh_token": creds.refresh_token,
        "client_id":     creds.client_id,
        "client_secret": creds.client_secret,
    }

    print("\n" + "=" * 65)
    print("SUCCESS! Copy EVERYTHING below into GitHub Secrets as YOUTUBE_TOKEN:")
    print("=" * 65 + "\n")
    print(json.dumps(output))
    print("\n" + "=" * 65)
    print("Done. You only ever need to run this script once.")

if __name__ == "__main__":
    main()
