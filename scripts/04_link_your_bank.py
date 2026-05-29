#!/usr/bin/env python3
"""
Open Plaid Link locally to connect a real bank (Production).

Usage:
  set PLAID_ENV=production and your Production secret in .env
  python scripts/04_link_your_bank.py

After Link succeeds, copy the public_token and run:
  python scripts/02_exchange_public_token.py <public_token> my-bank
  python scripts/03_sync_transactions.py
"""

from __future__ import annotations

import json
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plaid.model.country_code import CountryCode
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products

from plaid_client import get_plaid_client, require_env

PORT = int(os.getenv("PLAID_LINK_PORT", "8765"))
REDIRECT_URI = os.getenv("PLAID_REDIRECT_URI") or f"http://localhost:{PORT}/"
USE_REDIRECT = os.getenv("PLAID_REDIRECT_URI") is not None


def create_link_token() -> str:
    client = get_plaid_client()
    user_id = os.getenv("PLAID_USER_ID", "user-1")

    kwargs: dict = {
        "products": [Products("transactions")],
        "client_name": "MMM Transactions",
        "country_codes": [CountryCode("US")],
        "language": "en",
        "user": LinkTokenCreateRequestUser(client_user_id=user_id),
        "transactions": {"days_requested": int(os.getenv("PLAID_DAYS_REQUESTED", "90"))},
    }
    if USE_REDIRECT:
        kwargs["redirect_uri"] = REDIRECT_URI

    response = client.link_token_create(LinkTokenCreateRequest(**kwargs))
    return response.to_dict()["link_token"]


def make_html(link_token: str) -> bytes:
    page = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Connect your bank</title>
  <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 40rem; margin: 2rem auto; padding: 0 1rem; }}
    pre {{ background: #f4f4f4; padding: 1rem; overflow-x: auto; }}
    button {{ font-size: 1rem; padding: 0.5rem 1rem; cursor: pointer; }}
  </style>
</head>
<body>
  <h1>Connect your bank</h1>
  <p>Plaid Link opens in a popup. When finished, your <code>public_token</code> appears below.</p>
  <button id="open">Open Plaid Link</button>
  <div id="out"></div>
  <script>
    const linkToken = {json.dumps(link_token)};
    const handler = Plaid.create({{
      token: linkToken,
      onSuccess: (public_token, metadata) => {{
        const cmd = `python scripts/02_exchange_public_token.py ${{public_token}} my-bank`;
        document.getElementById('out').innerHTML =
          '<h2>Success</h2><p>Institution: ' + (metadata.institution?.name || '') + '</p>' +
          '<pre>public_token:\\n' + public_token + '\\n\\nNext:\\n' + cmd + '\\n\\nThen:\\npython scripts/03_sync_transactions.py</pre>';
      }},
      onExit: (err, metadata) => {{
        if (err) {{
          document.getElementById('out').innerHTML =
            '<pre style="color:#a00">Link exited: ' + JSON.stringify(err, null, 2) + '</pre>';
        }}
      }},
    }});
    document.getElementById('open').onclick = () => handler.open();
    handler.open();
  </script>
</body>
</html>"""
    return page.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    link_token: str = ""

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/oauth.html"):
            body = make_html(self.link_token)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    env = os.getenv("PLAID_ENV", "sandbox").lower()
    if env == "sandbox":
        print("PLAID_ENV=sandbox uses fake banks only.")
        print("To link YOUR accounts, set PLAID_ENV=production and use your Production secret.")
        print("Continue anyway only if you are testing sandbox Link UI.\n")

    if env == "production":
        secret = os.getenv("PLAID_SECRET", "")
        if "sandbox" in secret.lower():
            print("Warning: PLAID_ENV=production but your secret looks like a sandbox secret.")
            print("Use the Production secret from dashboard.plaid.com → Team Settings → Keys.\n")

    print("Creating link token...")
    Handler.link_token = create_link_token()

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}/"
    print(f"Serving Link at {url}")
    if env == "production":
        print(
            "If your bank uses OAuth, set PLAID_REDIRECT_URI in .env and register it in the Dashboard, e.g.\n"
            f"  PLAID_REDIRECT_URI=http://localhost:{PORT}/\n"
        )
    print("Press Ctrl+C to stop.\n")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
