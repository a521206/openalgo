"""
Test: Cloudflare gzip compression vs plain JSON response.

Demonstrates why AmiBroker AFL received garbled responses and confirms
that removing Accept-Encoding: gzip from the AFL headers fixes the issue.

Usage:
    uv run python test_cloudflare_gzip.py
"""

import urllib.request
import urllib.error

# ── Configure these before running ──────────────────────────────────────────
BASE_URL = "https://noviceorderflowtrader.in"
API_KEY  = "7ec753fd3561f27f797ce1ec75f8e52c72c9275e615106c9cb72a1d4d2203ffd"          # paste your OpenAlgo API key
SYMBOL   = "NSE:NIFTY50-INDEX"
INTERVAL = "D"
FROM     = "2026-03-01"
TO       = "2026-03-31"
# ────────────────────────────────────────────────────────────────────────────

URL = (
    f"{BASE_URL}/api/v1/ticker/{SYMBOL}"
    f"?apikey={API_KEY}&interval={INTERVAL}&from={FROM}&to={TO}"
)


def send_request(label: str, extra_headers: dict) -> None:
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"{'='*60}")

    req = urllib.request.Request(URL, headers=extra_headers)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status          = resp.status
            content_enc     = resp.headers.get("Content-Encoding", "(none)")
            content_type    = resp.headers.get("Content-Type", "(none)")
            raw_bytes       = resp.read()

        print(f"HTTP Status      : {status}")
        print(f"Content-Encoding : {content_enc}")
        print(f"Content-Type     : {content_type}")
        print(f"Response bytes   : {len(raw_bytes)}")

        # Try to decode as UTF-8 text (will fail if gzip binary)
        try:
            text = raw_bytes.decode("utf-8")
            print(f"Readable JSON    : YES")
            print(f"Body preview     : {text[:200]}")
        except UnicodeDecodeError:
            print(f"Readable JSON    : NO  ← binary/compressed data (garbled in AmiBroker!)")
            print(f"First 20 bytes   : {raw_bytes[:20]}")

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP Error {e.code} : {body[:300]}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    print(f"Target URL: {URL}\n")

    # Scenario 1 – OLD AFL behaviour (sends Accept-Encoding: gzip)
    send_request(
        "OLD AFL (Accept-Encoding: gzip, deflate) — may get garbled",
        {"Accept-Encoding": "gzip, deflate"},
    )

    # Scenario 2 – FIXED AFL behaviour (no Accept-Encoding header)
    send_request(
        "FIXED AFL (no Accept-Encoding) — should return plain JSON",
        {},
    )

