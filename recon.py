"""
Phase 1: Open the Threads post and dump every JSON response from the API
so we can inspect the data shape offline.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import Response, sync_playwright

POST_URL = "https://www.threads.com/@radthanael/post/DX0AeUTEZs5"
OUT_DIR = Path(__file__).parent / "responses"
OUT_DIR.mkdir(exist_ok=True)

# Filenames need to be filesystem-safe; keep a counter for ordering.
counter = {"n": 0}


def safe_slug(url: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", url)
    return slug[:120]


def on_response(response: Response) -> None:
    url = response.url
    # Threads uses graphql.threads.com, www.threads.com/api, and a few others.
    # Capture anything that looks like an API call and returns JSON-ish.
    if "threads.com" not in url:
        return
    ct = response.headers.get("content-type", "")
    if "json" not in ct and "javascript" not in ct:
        return
    try:
        body = response.body()
    except Exception as e:
        print(f"  ! body fetch failed: {url[:80]} ({e})", file=sys.stderr)
        return

    # Only keep responses that contain something that looks like reply data.
    # We don't know the field name yet, so be permissive: any body mentioning
    # 'text_post' / 'reply' / 'thread_items' is interesting.
    needle_hits = sum(
        n in body for n in (b"text_post", b"reply", b"thread_items", b"caption")
    )
    if needle_hits == 0:
        return

    counter["n"] += 1
    fname = f"{counter['n']:04d}_{safe_slug(url)}.bin"
    (OUT_DIR / fname).write_bytes(body)
    print(f"  + saved [{needle_hits} hits] {fname}")


def main() -> None:
    headless = "--headed" not in sys.argv
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 1600},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        page = ctx.new_page()
        page.on("response", on_response)

        print(f"navigating to {POST_URL}")
        page.goto(POST_URL, wait_until="domcontentloaded", timeout=30_000)

        # Threads shows a login nag overlay; the post is still rendered behind it.
        # Give the page a moment to fetch initial content.
        page.wait_for_timeout(3_000)

        # Auto-scroll to trigger lazy-loading of replies.
        last_height = 0
        for i in range(20):
            page.evaluate("window.scrollBy(0, 1500)")
            page.wait_for_timeout(1_200)
            height = page.evaluate("document.body.scrollHeight")
            print(f"  scroll {i+1}: height={height}")
            if height == last_height and i > 3:
                print("  scroll height stable, stopping")
                break
            last_height = height

        print(f"\ncaptured {counter['n']} responses → {OUT_DIR}")
        browser.close()


if __name__ == "__main__":
    main()
