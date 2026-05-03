"""
Run this ONCE to capture an authenticated Threads session.

Opens a headed Chromium window. You log into Threads in it. Press ENTER
in the terminal when done — the session state (cookies + localStorage) is
saved to state.json. Subsequent paginate.py runs use state.json and don't
need this step again.
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
STATE = HERE / "state.json"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 1000},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        page = ctx.new_page()
        page.goto("https://www.threads.com/login")

        print()
        print("=" * 64)
        print(" A Chromium window has opened.")
        print(" Log into Threads in it (use whichever account you like).")
        print(" When you're logged in and can see your home feed,")
        print(" come back here and press ENTER.")
        print("=" * 64)

        try:
            input()
        except (EOFError, KeyboardInterrupt):
            print("Aborted — no state saved.", file=sys.stderr)
            browser.close()
            sys.exit(1)

        ctx.storage_state(path=str(STATE))
        print(f"\n✓ Saved session state to {STATE}")
        print("  You can close the browser window now (or it'll close shortly).")
        browser.close()


if __name__ == "__main__":
    main()
