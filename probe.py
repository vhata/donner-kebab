"""Quick probe: what does the page actually look like when we land on it?"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

POST_URL = "https://www.threads.com/@radthanael/post/DX0AeUTEZs5"
OUT = Path(__file__).parent / "probe"
OUT.mkdir(exist_ok=True)


def run(headless: bool, tag: str) -> None:
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
        resp = page.goto(POST_URL, wait_until="domcontentloaded", timeout=30_000)
        print(f"[{tag}] status={resp.status if resp else '?'} final_url={page.url}")
        page.wait_for_timeout(4_000)
        title = page.title()
        html = page.content()
        body_text = page.evaluate("document.body.innerText").strip()[:500]
        print(f"[{tag}] title={title!r}")
        print(f"[{tag}] body_text[:500]={body_text!r}")
        (OUT / f"{tag}.html").write_text(html)
        page.screenshot(path=str(OUT / f"{tag}.png"), full_page=True)
        browser.close()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "headless"
    run(headless=(mode == "headless"), tag=mode)
