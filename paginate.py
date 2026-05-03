"""
Paginate through all replies on the Threads post using a saved authenticated
session (state.json from login.py).

Strategy:
  1. Load auth state, navigate to the post.
  2. Hook every JSON-ish response from threads.com — walk it for reply objects
     and accumulate by pk.
  3. Drive pagination by scrolling the last visible reply into view AND clicking
     any "View more replies" / "Show replies" buttons. Loop until N consecutive
     attempts produce no new replies.
  4. Write everything found to replies_full.jsonl.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from playwright.sync_api import Page, Response, sync_playwright

# Force line-buffered stdout so progress is visible when piped through tee.
sys.stdout.reconfigure(line_buffering=True)

POST_URL = "https://www.threads.com/@radthanael/post/DX0AeUTEZs5"
HERE = Path(__file__).parent
STATE_PATH = HERE / "state.json"
OUT_PATH = HERE / "replies_full.jsonl"
RAW_DUMP_DIR = HERE / "responses_full"

# Stop after this many scroll/click attempts produce no new replies.
PATIENCE = 6
# Hard cap on iterations so a runaway scroll can't go forever.
MAX_ITERATIONS = 600


@dataclass
class Reply:
    pk: str
    code: str | None
    username: str
    text: str
    like_count: int | None
    reply_count: int | None
    taken_at: int | None

    def __hash__(self) -> int:
        return hash(self.pk)


def _score(r: Reply) -> int:
    return sum(
        1 for v in (r.code, r.like_count, r.reply_count, r.taken_at) if v is not None
    )


def walk(node, found: dict[str, Reply]) -> int:
    """Depth-first walk; collect anything that looks like a Threads post.
    Returns the number of NEW (not-previously-seen) replies added."""
    new_count = 0
    if isinstance(node, dict):
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
            existing = found.get(reply.pk)
            if existing is None:
                found[reply.pk] = reply
                new_count = 1
            elif _score(reply) > _score(existing):
                found[reply.pk] = reply
        for v in node.values():
            new_count += walk(v, found)
    elif isinstance(node, list):
        for v in node:
            new_count += walk(v, found)
    return new_count


def setup_response_handler(page: Page, found: dict[str, Reply], stats: dict):
    """Attach a network listener that walks every JSON response from threads.com."""
    def on_response(response: Response) -> None:
        url = response.url
        if "threads.com" not in url:
            return
        ct = response.headers.get("content-type", "")
        if "json" not in ct and "javascript" not in ct:
            return
        try:
            body = response.body()
        except Exception:
            return
        if not any(n in body for n in (b"caption", b"thread_items", b"reply")):
            return
        try:
            blob = json.loads(body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            # Some responses are JS — try to extract embedded JSON heuristically.
            return
        added = walk(blob, found)
        stats["responses"] += 1
        if added:
            stats["last_new_at"] = stats["iterations"]
            print(f"    + {added} new ({len(found)} total)")
    page.on("response", on_response)


def trigger_pagination(page: Page) -> None:
    """Several strategies in sequence — at least one usually fires a fetch."""
    # 1. Page Down keystroke (Threads' scroll container responds to focus events).
    try:
        page.keyboard.press("End")
    except Exception:
        pass
    # 2. Scroll the last article into view, which forces a re-render boundary.
    try:
        page.evaluate(
            """() => {
                const articles = document.querySelectorAll('[role="article"], article');
                if (articles.length) {
                    articles[articles.length - 1].scrollIntoView({block: 'end', behavior: 'instant'});
                }
            }"""
        )
    except Exception:
        pass
    # 3. Click any visible "View more replies" / "Show replies" button.
    selectors = [
        'div[role="button"]:has-text("View more replies")',
        'div[role="button"]:has-text("Show more replies")',
        'div[role="button"]:has-text("View replies")',
        'span:has-text("View more replies")',
    ]
    for sel in selectors:
        try:
            buttons = page.locator(sel).all()
            for b in buttons[:5]:  # cap to avoid runaway clicks
                if b.is_visible():
                    b.click(timeout=1500)
                    page.wait_for_timeout(300)
        except Exception:
            pass


def main() -> None:
    if not STATE_PATH.exists():
        print(f"ERROR: {STATE_PATH} not found. Run login.py first.", file=sys.stderr)
        sys.exit(1)

    found: dict[str, Reply] = {}
    stats = {"responses": 0, "iterations": 0, "last_new_at": 0}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            storage_state=str(STATE_PATH),
            viewport={"width": 1280, "height": 1600},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        page = ctx.new_page()
        setup_response_handler(page, found, stats)

        print(f"navigating to {POST_URL}")
        page.goto(POST_URL, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(4_000)

        # Diagnostic: are we actually authenticated?
        body_text = page.evaluate("document.body.innerText")
        if "Log in to see more replies" in body_text:
            print("  ⚠️  Page still says 'Log in to see more replies' — auth state may not have taken effect.")
        if "Log in" in body_text and "Forgot password" in body_text:
            print("  ⚠️  Looks like we got the login page — state.json may be invalid or expired.")
        url_now = page.url
        if "/login" in url_now or "/accounts/login" in url_now:
            print(f"  ⚠️  Redirected to login URL: {url_now}")
            page.screenshot(path=str(HERE / "paginate_authfail.png"))
            print(f"  saved screenshot to paginate_authfail.png — bailing.")
            browser.close()
            sys.exit(2)
        print(f"  page title: {page.title()[:80]!r}")
        print(f"  initial load: {len(found)} replies captured from SSR")

        for i in range(1, MAX_ITERATIONS + 1):
            stats["iterations"] = i
            before = len(found)
            trigger_pagination(page)
            page.wait_for_timeout(1_500)
            iters_since_new = i - stats["last_new_at"]
            if iters_since_new >= PATIENCE:
                print(f"\n  no new replies in {PATIENCE} iterations — stopping at iter {i}")
                break
            if i % 5 == 0:
                print(f"  iter {i}: {len(found)} total ({stats['responses']} responses)")
        else:
            print(f"\n  hit MAX_ITERATIONS={MAX_ITERATIONS} — stopping")

        browser.close()

    print(f"\nfinal: {len(found)} unique replies, {stats['responses']} responses captured")
    with OUT_PATH.open("w") as f:
        for r in found.values():
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
