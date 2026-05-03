"""
For each reply in the input JSONL, ask Claude Opus 4.7 to extract structured
fields: location, knew/didn't-know status, where they learned, evidence quote.

Uses AsyncAnthropic with bounded concurrency for throughput. Writes one JSON
line per reply to the output JSONL — flushed incrementally so a crash partway
through doesn't lose progress.

Usage:
    uv run python extract_fields.py                                    # full corpus
    uv run python extract_fields.py --input replies.jsonl --output extracted.jsonl  # small set
    uv run python extract_fields.py --concurrency 5                    # gentler
    uv run python extract_fields.py --resume                           # skip already-done usernames
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel, Field

sys.stdout.reconfigure(line_buffering=True)

HERE = Path(__file__).parent
MODEL = "claude-opus-4-7"


class ExtractedFields(BaseModel):
    location_raw: Optional[str] = Field(
        default=None,
        description=(
            "Location as the replier states it, verbatim if possible "
            "(e.g. 'CT', 'Iowa', 'Netherlands', 'Fairfax, VA'). "
            "null if no location is given."
        ),
    )
    location_country: str = Field(
        description=(
            "ISO 3166-1 alpha-2 country code (US, GB, NL, CA, AU, etc.) "
            "or 'unspecified'. If a US state is named without explicit country, "
            "infer 'US'."
        ),
    )
    us_state: Optional[str] = Field(
        default=None,
        description=(
            "USPS 2-letter state code (CA, NY, TX, etc.) IF AND ONLY IF the "
            "replier indicates they are from / live in / grew up in a US state. "
            "null otherwise."
        ),
    )
    knew_donner: Literal["yes", "no", "partial", "unspecified"] = Field(
        description=(
            "Did the replier know about the Donner Party before the post? "
            "'yes' = explicitly knew. 'no' = explicitly didn't know. "
            "'partial' = vague awareness only (heard the name, no details). "
            "'unspecified' = cannot tell from the reply."
        ),
    )
    learned_from: Literal["school", "family", "media", "other", "unspecified"] = Field(
        description=(
            "Where they learned about the Donner Party, if mentioned. "
            "'school' = school/university curriculum. "
            "'family' = relatives, ancestry, oral history. "
            "'media' = TV/movies/books/podcasts/games (incl. Oregon Trail). "
            "'other' = any other source (travel, monuments, etc.). "
            "'unspecified' = source not mentioned."
        ),
    )
    evidence: str = Field(
        description=(
            "A short verbatim quote (≤120 chars) from the reply that justifies "
            "the knew_donner classification. Empty string if the reply is "
            "irrelevant or contains nothing supporting the classification."
        ),
    )


SYSTEM_PROMPT = """You are extracting structured information from replies to a Threads post.

The original poster (Nathanael, @radthanael) shared a story about being in Virginia and discovering that his East Coast friends had never heard of the Donner Party — the 1846 wagon train that resorted to cannibalism in the Sierra Nevada. He then asked his readers:

> "If you grew up outside the west coast, have you heard of The Donner Party, and where did you learn about them?"

Your job: for each reply, extract structured fields per the provided schema.

Be conservative. When a reply is sarcastic, off-topic, or genuinely ambiguous, prefer "unspecified" over guessing. The evidence field should quote the reply verbatim — do not paraphrase.

For location: prefer the most specific the reply gives. If they say "I grew up in CT", us_state is "CT" and location_country is "US". If they say "Netherlands here", location_country is "NL" and us_state is null. Recognize common shorthand (e.g., "PNW" = Pacific Northwest = US; "the South" = US)."""


async def extract_one(
    client: anthropic.AsyncAnthropic, reply_text: str
) -> ExtractedFields:
    response = await client.messages.parse(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Reply:\n\n{reply_text}"}],
        output_format=ExtractedFields,
    )
    return response.parsed_output


async def worker(
    name: int,
    client: anthropic.AsyncAnthropic,
    sem: asyncio.Semaphore,
    queue: asyncio.Queue,
    results: list,
    out_file,
    out_lock: asyncio.Lock,
    progress: dict,
):
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            return
        i, reply = item
        async with sem:
            try:
                fields = await extract_one(client, reply["text"])
            except anthropic.APIError as e:
                progress["errors"] += 1
                print(f"  [worker {name}] @{reply['username']:<25} ERROR: {e}", file=sys.stderr)
                queue.task_done()
                continue
            row = {
                "username": reply["username"],
                "text": reply["text"],
                "like_count": reply.get("like_count"),
                "reply_count": reply.get("reply_count"),
                **fields.model_dump(),
            }
            async with out_lock:
                out_file.write(json.dumps(row, ensure_ascii=False) + "\n")
                out_file.flush()
                progress["done"] += 1
                if progress["done"] % 25 == 0 or progress["done"] == progress["total"]:
                    elapsed = time.time() - progress["start"]
                    rate = progress["done"] / elapsed if elapsed > 0 else 0
                    remaining = (progress["total"] - progress["done"]) / rate if rate > 0 else 0
                    print(
                        f"  {progress['done']}/{progress['total']} "
                        f"({rate:.1f}/s, ~{remaining:.0f}s left, errors={progress['errors']})"
                    )
            results.append(row)
        queue.task_done()


async def main_async(args):
    in_path = HERE / args.input
    out_path = HERE / args.output

    rows = [json.loads(l) for l in in_path.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if r["username"] != "radthanael"]
    print(f"loaded {len(rows)} non-OP replies from {in_path.name}")

    if args.resume and out_path.exists():
        done_pks = {
            json.loads(l)["username"] + "|" + json.loads(l)["text"][:60]
            for l in out_path.read_text().splitlines()
            if l.strip()
        }
        before = len(rows)
        rows = [r for r in rows if (r["username"] + "|" + r["text"][:60]) not in done_pks]
        print(f"  resuming: {before - len(rows)} already done, {len(rows)} remaining")
        mode = "a"
    else:
        mode = "w"

    if not rows:
        print("nothing to do.")
        return

    print(f"extracting with {MODEL}, concurrency={args.concurrency}")
    client = anthropic.AsyncAnthropic()
    sem = asyncio.Semaphore(args.concurrency)
    queue: asyncio.Queue = asyncio.Queue()
    for i, r in enumerate(rows):
        await queue.put((i, r))
    for _ in range(args.concurrency):
        await queue.put(None)

    results: list = []
    progress = {"done": 0, "total": len(rows), "errors": 0, "start": time.time()}
    out_lock = asyncio.Lock()

    with out_path.open(mode) as out_file:
        workers = [
            asyncio.create_task(
                worker(i, client, sem, queue, results, out_file, out_lock, progress)
            )
            for i in range(args.concurrency)
        ]
        await queue.join()
        for w in workers:
            await w

    elapsed = time.time() - progress["start"]
    print(
        f"\ndone: {progress['done']}/{progress['total']} extractions in {elapsed:.0f}s "
        f"({progress['errors']} errors) → {out_path}"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="replies_full.jsonl")
    parser.add_argument("--output", default="extracted_full.jsonl")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
