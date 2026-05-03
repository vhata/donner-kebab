"""
Build the showcase site at docs/ — a single-page narrative with all four
charts embedded inline, plus standalone .html and .png copies of each chart.

Outputs:
    docs/index.html           — the showcase page
    docs/donner_*.html        — individual interactive charts
    docs/donner_*.png         — static PNG copies (for embedding elsewhere)

Usage:
    uv run python build_site.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import plotly.io as pio

import chart as c  # reuse chart functions

sys.stdout.reconfigure(line_buffering=True)

HERE = Path(__file__).parent
SITE_DIR = HERE / "docs"
SITE_DIR.mkdir(exist_ok=True)

POST_URL = "https://www.threads.com/@radthanael/post/DX0AeUTEZs5"


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Did Threads repliers know about the Donner Party?</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
  <style>
    :root {{ color-scheme: light; }}
    body {{
      font: 17px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
      max-width: 920px;
      margin: 2.5rem auto 4rem;
      padding: 0 1.25rem;
      color: #222;
      background: #fafafa;
    }}
    h1 {{ font-size: 2.1rem; line-height: 1.2; margin-bottom: 0.25rem; }}
    h2 {{ margin-top: 3rem; padding-bottom: 0.4rem; border-bottom: 1px solid #ddd; font-size: 1.5rem; }}
    h3 {{ margin-top: 2rem; font-size: 1.15rem; color: #444; }}
    .meta {{ color: #666; font-size: 0.95rem; margin-top: 0.25rem; }}
    .stat {{ font-size: 1.5rem; font-weight: 600; color: #2E7D32; }}
    .stat-row {{ display: flex; gap: 2rem; flex-wrap: wrap; margin: 1rem 0 2rem; }}
    .stat-card {{ background: white; border: 1px solid #e0e0e0; border-radius: 8px; padding: 1rem 1.25rem; min-width: 180px; }}
    .stat-card .num {{ font-size: 2rem; font-weight: 700; color: #2E7D32; line-height: 1; }}
    .stat-card .label {{ font-size: 0.85rem; color: #666; text-transform: uppercase; letter-spacing: 0.04em; margin-top: 0.3rem; }}
    .chart {{ margin: 2rem -0.5rem; background: white; border: 1px solid #e8e8e8; border-radius: 8px; padding: 0.5rem; }}
    .chart-caption {{ font-size: 0.9rem; color: #555; margin: 0.5rem 0.75rem 1rem; }}
    blockquote {{ border-left: 3px solid #999; padding: 0.25rem 1rem; color: #444; font-style: italic; margin: 1.5rem 0; }}
    a {{ color: #1565C0; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .disclosure {{ background: #fff8e1; border-left: 4px solid #f9a825; padding: 0.9rem 1.1rem; margin: 2rem 0; border-radius: 4px; font-size: 0.95rem; }}
    code {{ background: #f0f0f0; padding: 0.1em 0.35em; border-radius: 3px; font-size: 0.92em; }}
    footer {{ margin-top: 4rem; padding-top: 1.5rem; border-top: 1px solid #ddd; color: #888; font-size: 0.9rem; }}
    ul.sources {{ padding-left: 1.5rem; }}
    ul.sources li {{ margin: 0.3rem 0; }}
  </style>
</head>
<body>

<h1>Did Threads repliers know about the Donner Party?</h1>
<p class="meta">An analysis of {n_total} replies to <a href="{post_url}">@radthanael's post</a>.</p>

<h2>The story</h2>
<p>Nathanael was visiting friends in Richmond, Virginia. The conversation drifted, as it does, to a topic that reminded him of cannibalism — so he said, "Ahh, like the Donner Party." His friends, lifelong East Coasters, looked at him blankly. He explained: the wagon train, the Sierra Nevada, the winter of 1846, the cannibalism. They had no memory of it.</p>

<p><a href="{post_url}">He posted about it</a> and asked his readers a question:</p>

<blockquote>If you grew up outside the west coast, have you heard of The Donner Party, and where did you learn about them?</blockquote>

<p>The post got around two thousand eight hundred replies (counting nested ones). This page summarises the {n_total} top-level replies analysed for location and prior knowledge.</p>

<h2>Headline finding</h2>

<div class="stat-row">
  <div class="stat-card">
    <div class="num">{pct_yes:.0f}%</div>
    <div class="label">of clear answers said yes</div>
  </div>
  <div class="stat-card">
    <div class="num">{pct_us:.0f}%</div>
    <div class="label">US repliers, yes rate</div>
  </div>
  <div class="stat-card">
    <div class="num">{pct_intl:.0f}%</div>
    <div class="label">non-US repliers, yes rate</div>
  </div>
  <div class="stat-card">
    <div class="num">{n_clear}</div>
    <div class="label">clear yes/no/partial answers</div>
  </div>
</div>

<p>Nathanael's Richmond friends were not representatives of an East Coast knowledge gap. They were <strong>genuine outliers</strong>. The vast majority of repliers — including those from Britain, Canada, Australia, New Zealand, and over a dozen other countries — knew about the Donner Party.</p>

<h2>Where repliers came from</h2>
<p>States are coloured by the share of repliers from that state who said yes, calculated only over clear answers (yes/no/partial). Sarcastic and unclear replies are excluded from the denominator. Hover for details.</p>

<div class="chart">{chart_choropleth}</div>
<p class="chart-caption">Iowa is the only US state visibly lighter — driven in part by the now-famous "I grew up in Iowa and I've never heard of the Donners until this post. Wild!" reply. South Dakota is grey: no replies received from there.</p>

<h2>Top 30 locations by reply count</h2>

<div class="chart">{chart_bar}</div>
<p class="chart-caption">California leads, then Virginia (with several "no" answers — possibly including Nathanael's original interlocutors), New York, Britain, Ohio, Pennsylvania. The "US" bar represents repliers identified as American who didn't name a state.</p>

<h2>International repliers</h2>

<div class="chart">{chart_countries}</div>
<p class="chart-caption">{n_intl} replies from outside the US, across {n_countries} countries. Britain alone contributed forty replies — the Donner Party has surprisingly broad international reach for an 1846 American disaster.</p>

<h2>Where did they learn it?</h2>

<div class="chart">{chart_learned}</div>
<p class="chart-caption">Among repliers who said they knew, school is the dominant pathway when stated. {n_unspecified_source} didn't mention a source.</p>

<h2>The reframing</h2>
<p>The original premise — that this might be a regional knowledge gap — does not survive the data. Knowledge of the Donner Party is, near as the data shows, geographically uniform across both US states and English-speaking countries.</p>

<p>The dominant <em>source</em> is school. So the more interesting question this dataset posed back at Nathanael is not <em>where</em> people grew up, but <em>which curricula did or didn't cover this</em>. His Richmond friends are not just "East Coasters who didn't know" — they're people the school curriculum did not reach. That's a different and arguably more interesting question.</p>

<h2>Methodology</h2>
<p>Replies were collected from the original post via a logged-in browser session driven by Playwright, paginating through the GraphQL endpoint until exhausted. Each reply was then sent to <a href="https://www.anthropic.com/claude/opus">Claude Opus 4.7</a> with a structured-output schema asking for: location, whether they knew, where they learned, and a verbatim evidence quote.</p>

<p>The full pipeline — scrape, extract, chart, build site — is in the <a href="https://github.com/jhitchcock/donner-threads-analysis">accompanying GitHub repo</a> (link will work once published). It runs end-to-end in about ten minutes from a logged-in session.</p>

<div class="disclosure">
<strong>How the data was obtained.</strong> Replies were scraped from a public Threads post via a personal logged-in browser session. The raw reply text and per-reply identifiers are not included in this published repository — only aggregate counts and percentages. No reply text or username is ever shown on this page.
</div>

<h2>Caveats</h2>
<ul>
<li>Replies that didn't state a location couldn't be placed on the map. {n_unspecified_loc} of {n_total} fell into this bucket.</li>
<li>The "yes/no/partial/unspecified" classification was made by an LLM. Spot-checks against a sample of replies showed it to be accurate, but a small error rate is unavoidable.</li>
<li>Sample sizes for some states and countries are small (single digits). Hover the choropleth or read the bar chart for absolute counts before reading too much into a percentage.</li>
<li>Replies-to-replies (nested sub-thread comments) were excluded — only top-level replies are analysed here.</li>
</ul>

<footer>
Built {build_date} with Python, Playwright, Claude, Plotly, and a great deal of curiosity about a wagon train.
</footer>

</body>
</html>
"""


def main():
    df = c.load("extracted_full.jsonl")
    print(f"loaded {len(df)} extractions")

    # Summary stats for the page
    n_total = len(df)
    clear = df[df["knew_donner"].isin(["yes", "no", "partial"])]
    n_clear = len(clear)
    pct_yes = (clear["knew_donner"] == "yes").mean() * 100 if n_clear else 0

    us = df[df["location_country"] == "US"]
    intl = df[(df["location_country"] != "US") & (df["location_country"] != "unspecified")]
    us_clear = us[us["knew_donner"].isin(["yes", "no", "partial"])]
    intl_clear = intl[intl["knew_donner"].isin(["yes", "no", "partial"])]
    pct_us = (us_clear["knew_donner"] == "yes").mean() * 100 if len(us_clear) else 0
    pct_intl = (intl_clear["knew_donner"] == "yes").mean() * 100 if len(intl_clear) else 0

    n_intl = len(intl)
    n_countries = intl["location_country"].nunique()
    n_unspecified_loc = (df["location_country"] == "unspecified").sum()

    knew = df[df["knew_donner"] == "yes"]
    n_unspecified_source = (knew["learned_from"] == "unspecified").sum()

    # Build charts (reuse functions from chart.py)
    figs = {
        "choropleth": c.choropleth(df),
        "bar": c.bar_by_location(df, top_n=30),
        "countries": c.bar_by_country(df),
        "learned": c.bar_learned_from(df),
    }

    # Render each as inline div (no embedded plotly.js — page loads it once from CDN)
    chart_divs = {}
    for name, fig in figs.items():
        chart_divs[name] = pio.to_html(
            fig,
            include_plotlyjs=False,
            full_html=False,
            div_id=f"chart-{name}",
            default_height=str(int(fig.layout.height or 600)) + "px",
        )

    # Also write standalone interactive HTMLs and PNGs into docs/
    for name, fig in figs.items():
        fig.write_html(SITE_DIR / f"donner_{name}.html")
        fig.write_image(
            SITE_DIR / f"donner_{name}.png",
            width=1400 if name in ("bar", "learned") else 1200,
            height=fig.layout.height or 720,
            scale=2,
        )

    from datetime import date
    page = PAGE_TEMPLATE.format(
        n_total=n_total,
        n_clear=n_clear,
        pct_yes=pct_yes,
        pct_us=pct_us,
        pct_intl=pct_intl,
        n_intl=n_intl,
        n_countries=n_countries,
        n_unspecified_loc=n_unspecified_loc,
        n_unspecified_source=n_unspecified_source,
        post_url=POST_URL,
        chart_choropleth=chart_divs["choropleth"],
        chart_bar=chart_divs["bar"],
        chart_countries=chart_divs["countries"],
        chart_learned=chart_divs["learned"],
        build_date=date.today().isoformat(),
    )
    out = SITE_DIR / "index.html"
    out.write_text(page)
    print(f"wrote {out}")
    print(f"     standalone charts in {SITE_DIR}/donner_*.html and donner_*.png")


if __name__ == "__main__":
    main()
