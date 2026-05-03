# Donner Party — Threads reply analysis

A pipeline that scrapes the replies to [@radthanael's Threads post](https://www.threads.com/@radthanael/post/DX0AeUTEZs5) asking whether non-west-coast readers had heard of the Donner Party, classifies each reply with Claude, and renders the results as a small static site.

**See the published showcase at `docs/index.html`** (or via GitHub Pages once deployed).

## What's in here

| File | What it does |
|---|---|
| `recon.py` | Initial network-interception probe — captures GraphQL JSON responses to disk for offline inspection. |
| `probe.py` | Quick utility that loads the post page and saves the rendered HTML + a screenshot. |
| `extract.py` | Parses the embedded SSR JSON blobs in the post page HTML for an initial sample of replies. |
| `login.py` | One-shot headed Playwright session that opens Chromium, lets you log into Threads manually, and saves the resulting auth state to `state.json`. |
| `paginate.py` | Uses the saved `state.json` to scrape all top-level replies via authenticated pagination (scroll triggers + "View more replies" clicks). Captures GraphQL responses on the fly and walks them for reply objects. |
| `extract_fields.py` | Async batch — sends each reply to Claude Opus 4.7 with a Pydantic structured-output schema. Extracts `location_country`, `us_state`, `knew_donner` (yes/no/partial/unspecified), `learned_from` (school/media/family/other), and a verbatim evidence quote. |
| `chart.py` | Generates four Plotly visualisations: US choropleth, top-N location bar, country bar, learned-from bar. |
| `build_site.py` | Renders the showcase: `docs/index.html` with all four charts inlined, plus standalone `.html` and `.png` copies. |

## Running it yourself

```bash
uv sync
uv run playwright install chromium

# 1. Log in once — opens a headed browser. Press Enter when you're logged in.
uv run python login.py

# 2. Scrape replies (~5–10 min). Writes replies_full.jsonl.
uv run python paginate.py

# 3. Classify each reply with Claude (~3–4 min, requires ANTHROPIC_API_KEY).
uv run python extract_fields.py

# 4. Build the showcase site.
uv run python build_site.py
```

## A note on the data

Replies were collected from a public Threads post via a personal logged-in browser session. The raw reply text and per-username identifiers contain PII and are deliberately excluded from this repository (see `.gitignore`). Only the aggregate counts and percentages — i.e., the chart artefacts — are committed.

If you want to reproduce the analysis, you'll need to scrape the post yourself with your own Threads account.

## Cost

Running the extraction step against ~1,000 replies with Claude Opus 4.7 costs roughly $5 in API credits. For a higher-volume version, swap to Claude Haiku 4.5 in `extract_fields.py` (cuts cost by ~5× with minimal quality loss for this kind of structured extraction).
