"""
Pull replies from the SSR'd HTML.

Threads embeds GraphQL payloads inside <script> tags as JSON. We:
  1. Load the page with Playwright (need a real browser to get the SSR HTML —
     a plain requests.get() returns a stub).
  2. Extract every JSON blob from <script> tags.
  3. Walk each blob looking for objects that look like reply nodes
     (have a `caption.text` and an `author`/`user`).
  4. Dedupe by post id and emit a clean JSONL of replies.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

from playwright.sync_api import sync_playwright

POST_URL = "https://www.threads.com/@radthanael/post/DX0AeUTEZs5"
HERE = Path(__file__).parent


@dataclass
class Reply:
    pk: str
    code: str | None
    username: str
    text: str
    like_count: int | None
    reply_count: int | None
    taken_at: int | None  # unix seconds

    def __hash__(self) -> int:
        return hash(self.pk)


def fetch_html() -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 1600},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        page = ctx.new_page()
        page.goto(POST_URL, wait_until="domcontentloaded", timeout=30_000)
        # Let any post-hydration fetches drop their JSON into the DOM too.
        page.wait_for_timeout(4_000)
        html = page.content()
        browser.close()
        return html


def iter_script_jsons(html: str):
    """Yield each JSON object embedded in <script> tags."""
    # Threads uses <script type="application/json" data-sjs>...</script>
    pattern = re.compile(
        r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
        re.DOTALL,
    )
    for m in pattern.finditer(html):
        raw = m.group(1)
        try:
            yield json.loads(raw)
        except json.JSONDecodeError:
            continue


def walk(node, found: dict[str, Reply]) -> None:
    """Depth-first walk; collect anything that looks like a Threads post."""
    if isinstance(node, dict):
        # Reply node shape (from observed Threads payloads):
        #   { pk, code, caption: {text}, user: {username}, like_count,
        #     text_post_app_info: {direct_reply_count}, taken_at }
        pk = node.get("pk") or node.get("pk_id")
        caption = node.get("caption")
        user = node.get("user")
        if (
            pk
            and isinstance(caption, dict)
            and caption.get("text")
            and isinstance(user, dict)
            and user.get("username")
        ):
            tpa = node.get("text_post_app_info") or {}
            reply = Reply(
                pk=str(pk),
                code=node.get("code"),
                username=user["username"],
                text=caption["text"],
                like_count=node.get("like_count"),
                reply_count=tpa.get("direct_reply_count"),
                taken_at=node.get("taken_at"),
            )
            # Prefer the richest version (one with the most populated fields).
            existing = found.get(reply.pk)
            if existing is None or _score(reply) > _score(existing):
                found[reply.pk] = reply
        for v in node.values():
            walk(v, found)
    elif isinstance(node, list):
        for v in node:
            walk(v, found)


def _score(r: Reply) -> int:
    return sum(
        1 for v in (r.code, r.like_count, r.reply_count, r.taken_at) if v is not None
    )


def main() -> None:
    html_path = HERE / "probe" / "headless.html"
    if "--cached" in sys.argv and html_path.exists():
        print(f"using cached html ({html_path.stat().st_size} bytes)")
        html = html_path.read_text()
    else:
        print("fetching live...")
        html = fetch_html()
        html_path.parent.mkdir(exist_ok=True)
        html_path.write_text(html)

    print(f"html size: {len(html)} bytes")

    found: dict[str, Reply] = {}
    n_scripts = 0
    for blob in iter_script_jsons(html):
        n_scripts += 1
        walk(blob, found)
    print(f"parsed {n_scripts} <script> JSON blobs")
    print(f"found {len(found)} unique posts (incl. the OP)")

    out = HERE / "replies.jsonl"
    with out.open("w") as f:
        for r in found.values():
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
