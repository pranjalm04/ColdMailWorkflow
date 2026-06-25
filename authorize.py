"""One-off helper to (re)authorize Gmail send access and cache credentials/token.json.

Run this directly in a normal terminal (NOT inside another tool), so the browser can open:

    .venv\\Scripts\\python.exe authorize.py

If the browser does not open on its own, copy the printed URL into a browser manually,
approve the 'Send email on your behalf' scope, and this script will finish and write the token.
"""

import sys

from google_auth_oauthlib.flow import InstalledAppFlow

from cold_mail_workflow.config import CREDENTIALS_PATH, GMAIL_SCOPES, TOKEN_PATH


def main() -> int:
    if not CREDENTIALS_PATH.exists():
        print(f"Missing OAuth client secret: {CREDENTIALS_PATH}", file=sys.stderr)
        return 1

    print(f"Authorizing scopes: {GMAIL_SCOPES}")
    print("A browser window should open. If it does not, copy the URL printed below into a browser.\n")

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), GMAIL_SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    print(f"\nSUCCESS: token cached at {TOKEN_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
