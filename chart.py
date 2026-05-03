"""
Build visualisations from extracted_full.jsonl.

Outputs:
  1. donner_choropleth.{html,png} — US states colored by % who knew, with
     pct calculated only over CLEAR answers (yes/no/partial), excluding
     'unspecified' from the denominator. Cells annotated with knew/total.
  2. donner_bar.{html,png} — top 30 locations by reply count, stacked
     by knew/no/partial/unspecified.
  3. donner_countries.{html,png} — non-US repliers by country.
  4. donner_learned.{html,png} — where US repliers who knew learned about it.

Usage:
    uv run python chart.py                                # full corpus
    uv run python chart.py --input extracted.jsonl        # demo set
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

sys.stdout.reconfigure(line_buffering=True)
HERE = Path(__file__).parent

KNEW_COLORS = {
    "yes": "#2E7D32",
    "no": "#C62828",
    "partial": "#F9A825",
    "unspecified": "#9E9E9E",
}
KNEW_ORDER = ["yes", "partial", "no", "unspecified"]
LEARNED_COLORS = {
    "school": "#1565C0",
    "media": "#7B1FA2",
    "family": "#EF6C00",
    "other": "#00838F",
    "unspecified": "#9E9E9E",
}


def load(input_name: str) -> pd.DataFrame:
    p = HERE / input_name
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    return pd.DataFrame(rows)


def choropleth(df: pd.DataFrame) -> go.Figure:
    us = df[df["us_state"].notna()].copy()
    by_state = us.groupby("us_state").agg(
        n=("username", "count"),
        n_yes=("knew_donner", lambda s: (s == "yes").sum()),
        n_no=("knew_donner", lambda s: (s == "no").sum()),
        n_partial=("knew_donner", lambda s: (s == "partial").sum()),
        n_unspec=("knew_donner", lambda s: (s == "unspecified").sum()),
    ).reset_index()
    by_state["n_clear"] = by_state["n_yes"] + by_state["n_no"] + by_state["n_partial"]
    by_state["pct_knew"] = (
        by_state["n_yes"] / by_state["n_clear"].where(by_state["n_clear"] > 0) * 100
    ).round(0)
    by_state["label"] = by_state.apply(
        lambda r: f"{int(r['n_yes'])}/{int(r['n_clear'])}" if r["n_clear"] > 0 else "—",
        axis=1,
    )

    fig = px.choropleth(
        by_state,
        locations="us_state",
        locationmode="USA-states",
        color="pct_knew",
        scope="usa",
        color_continuous_scale="RdYlGn",
        range_color=(0, 100),
        labels={"pct_knew": "% who knew"},
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{location}</b><br>"
            "Total replies: %{customdata[0]}<br>"
            "Knew: %{customdata[1]} | Didn't: %{customdata[2]} | Partial: %{customdata[3]} | Unclear: %{customdata[4]}<br>"
            "Share who knew (of clear answers): %{customdata[5]}%"
            "<extra></extra>"
        ),
        customdata=by_state[["n", "n_yes", "n_no", "n_partial", "n_unspec", "pct_knew"]].values,
    )
    fig.update_layout(
        title=dict(
            text=(
                "Did Threads repliers know about the Donner Party?<br>"
                f"<sub>By US state ({len(us)} US repliers across {len(by_state)} states). "
                "Color = % of clear answers that said 'yes'. "
                "Unclear/sarcastic replies excluded from the denominator.</sub>"
            ),
            x=0.5,
        ),
        margin=dict(t=90, b=40, l=20, r=20),
        coloraxis_colorbar=dict(title="% knew", ticksuffix="%"),
    )
    return fig


def bar_by_location(df: pd.DataFrame, top_n: int = 30) -> go.Figure:
    df = df.copy()
    df["location"] = df.apply(
        lambda r: r["us_state"] if pd.notna(r["us_state"]) else r["location_country"],
        axis=1,
    )
    df = df[df["location"] != "unspecified"]
    by_loc_knew = (
        df.groupby(["location", "knew_donner"]).size().unstack(fill_value=0)
    )
    by_loc_knew = by_loc_knew.reindex(columns=KNEW_ORDER, fill_value=0)
    by_loc_knew["total"] = by_loc_knew.sum(axis=1)
    by_loc_knew = by_loc_knew.sort_values("total", ascending=False).head(top_n)
    by_loc_knew = by_loc_knew.sort_values("total", ascending=True)  # plotly h-bar

    fig = go.Figure()
    for status in KNEW_ORDER:
        fig.add_trace(go.Bar(
            y=by_loc_knew.index,
            x=by_loc_knew[status],
            name=status,
            orientation="h",
            marker_color=KNEW_COLORS[status],
            hovertemplate=f"<b>%{{y}}</b><br>{status}: %{{x}}<extra></extra>",
        ))
    fig.update_layout(
        barmode="stack",
        title=dict(
            text=(
                f"Top {len(by_loc_knew)} locations by reply count<br>"
                f"<sub>{len(df)} replies with identified locations. "
                "US states use 2-letter codes; international uses ISO country codes.</sub>"
            ),
            x=0.5,
        ),
        xaxis_title="Number of replies",
        yaxis_title="Location",
        margin=dict(t=90, b=40, l=80, r=20),
        legend=dict(title="Knew Donner Party?", orientation="h", y=-0.12),
        height=max(400, 22 * len(by_loc_knew) + 200),
    )
    return fig


def bar_by_country(df: pd.DataFrame) -> go.Figure:
    intl = df[(df["location_country"] != "US") & (df["location_country"] != "unspecified")].copy()
    if intl.empty:
        # placeholder
        fig = go.Figure()
        fig.add_annotation(text="No non-US replies with identified countries.",
                           xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig
    by_c_knew = (
        intl.groupby(["location_country", "knew_donner"]).size().unstack(fill_value=0)
    )
    by_c_knew = by_c_knew.reindex(columns=KNEW_ORDER, fill_value=0)
    by_c_knew["total"] = by_c_knew.sum(axis=1)
    by_c_knew = by_c_knew.sort_values("total", ascending=True)

    fig = go.Figure()
    for status in KNEW_ORDER:
        fig.add_trace(go.Bar(
            y=by_c_knew.index,
            x=by_c_knew[status],
            name=status,
            orientation="h",
            marker_color=KNEW_COLORS[status],
            hovertemplate=f"<b>%{{y}}</b><br>{status}: %{{x}}<extra></extra>",
        ))
    fig.update_layout(
        barmode="stack",
        title=dict(
            text=(
                f"International repliers by country<br>"
                f"<sub>{len(intl)} non-US replies across {len(by_c_knew)} countries.</sub>"
            ),
            x=0.5,
        ),
        xaxis_title="Number of replies",
        yaxis_title="Country (ISO 3166-1 alpha-2)",
        margin=dict(t=80, b=40, l=80, r=20),
        legend=dict(title="Knew Donner Party?", orientation="h", y=-0.15),
        height=max(360, 26 * len(by_c_knew) + 200),
    )
    return fig


def bar_learned_from(df: pd.DataFrame) -> go.Figure:
    knew = df[df["knew_donner"] == "yes"].copy()
    counts = knew["learned_from"].value_counts()
    order = ["school", "media", "family", "other", "unspecified"]
    counts = counts.reindex([c for c in order if c in counts.index])

    fig = go.Figure(go.Bar(
        x=counts.index,
        y=counts.values,
        marker_color=[LEARNED_COLORS[c] for c in counts.index],
        text=counts.values,
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>%{y} repliers<extra></extra>",
    ))
    fig.update_layout(
        title=dict(
            text=(
                f"Where did repliers who knew about the Donner Party learn it?<br>"
                f"<sub>{len(knew)} repliers who said 'yes'. "
                "Many leave the source unspecified.</sub>"
            ),
            x=0.5,
        ),
        xaxis_title="Source",
        yaxis_title="Number of repliers",
        margin=dict(t=80, b=40, l=60, r=20),
        height=460,
    )
    return fig


def write_pair(fig: go.Figure, name: str, width: int = 1200) -> None:
    html_path = HERE / f"{name}.html"
    png_path = HERE / f"{name}.png"
    fig.write_html(html_path)
    fig.write_image(png_path, width=width, height=fig.layout.height or 720, scale=2)
    print(f"  wrote {html_path.name} + {png_path.name}")


def print_summary(df: pd.DataFrame) -> None:
    print("\n=== summary ===")
    print(f"total replies analyzed: {len(df)}")
    knew_counts = df["knew_donner"].value_counts()
    print(f"knew_donner: {dict(knew_counts)}")
    clear = df[df["knew_donner"].isin(["yes", "no", "partial"])]
    if len(clear):
        pct = (clear["knew_donner"] == "yes").mean() * 100
        print(f"  of {len(clear)} clear answers: {pct:.0f}% said yes")
    us = df[df["location_country"] == "US"]
    intl = df[(df["location_country"] != "US") & (df["location_country"] != "unspecified")]
    print(f"US: {len(us)}, non-US (identified): {len(intl)}, unspecified location: {(df['location_country'] == 'unspecified').sum()}")

    us_clear = us[us["knew_donner"].isin(["yes", "no", "partial"])]
    intl_clear = intl[intl["knew_donner"].isin(["yes", "no", "partial"])]
    if len(us_clear):
        print(f"  US clear-answer 'yes' rate: {(us_clear['knew_donner'] == 'yes').mean() * 100:.0f}% (n={len(us_clear)})")
    if len(intl_clear):
        print(f"  non-US clear-answer 'yes' rate: {(intl_clear['knew_donner'] == 'yes').mean() * 100:.0f}% (n={len(intl_clear)})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="extracted_full.jsonl")
    parser.add_argument("--top-n", type=int, default=30)
    args = parser.parse_args()

    df = load(args.input)
    print(f"loaded {len(df)} extracted replies from {args.input}")
    print_summary(df)

    print("\n=== writing charts ===")
    write_pair(choropleth(df), "donner_choropleth")
    write_pair(bar_by_location(df, top_n=args.top_n), "donner_bar")
    write_pair(bar_by_country(df), "donner_countries")
    write_pair(bar_learned_from(df), "donner_learned")


if __name__ == "__main__":
    main()
