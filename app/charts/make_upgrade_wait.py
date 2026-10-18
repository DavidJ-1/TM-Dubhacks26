"""'Upgrade now or wait?' chart for the demo (tm-ui lane). ALL DATA SYNTHETIC.

One command (from repo root):  python app/charts/make_upgrade_wait.py [--line LN-PERSONA-29-1]

Input   line_tradein.csv from harness/out/ first, then the tracked demo_data/ (fresh clone). TM_OUT_DIR=/path
        adds a directory in front. Repo-relative paths only.
Output  app/charts/06_upgrade_or_wait.png (1600x900) + 06_upgrade_or_wait.html (self-contained)
        app/charts/upgrade_wait_summary.json (featured-line numbers + decision / wait_verdict counts)

Column names are resolved from the file header at run time (with or without a _cents suffix), so a column
rename by tm-offers only needs a rerun. A missing column stops the script with a clear message.

Deliberately NOT shown: delta_cents, cost_now_cents, cost_wait_cents. Their math counts the remaining phone
balance as money saved by waiting, which it is not: the balance is owed whether you upgrade now or later.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
NAME = "06_upgrade_or_wait"
FEATURED = "LN-PERSONA-29-1"

MAGENTA, PLUM, CREAM = "#E20074", "#1A1220", "#F7F1EA"
PINK, MUTED, GRID = "#F59AC8", "#8C7F8F", "#E6DCD2"
FOOT = ("SYNTHETIC: fictional judge-sandbox line with simulated financing and trade-in values. "
        "Not real T-Mobile customers, devices or prices.")

HORIZONS = [("now", "Now"), ("6m", "In 6 months"), ("12m", "In 12 months")]
KINDS = {  # kind -> accepted stems (first match wins); each may carry a _cents / _usd suffix
    "tradein": ["tradein_value", "trade_in_value", "tradein"],
    "balance": ["balance", "financing_balance", "remaining_balance"],
    "net": ["net", "net_tradein", "tradein_net"],
    "promo": ["promo", "promo_value", "tradein_promo"],
}
SCALARS = {
    "line_id": ["line_id"], "device_name": ["device_name"], "decision": ["decision"],
    "wait_verdict": ["wait_verdict"], "wait_until": ["wait_until"],
    "months_left": ["financing_months_remaining"], "installment": ["monthly_installment"],
    "value_at_payoff": ["tradein_value_at_payoff"], "data_note": ["data_note"],
}


def die(msg: str):
    sys.exit(f"make_upgrade_wait: ERROR: {msg}")


def find_input() -> Path:
    dirs = [Path(os.environ["TM_OUT_DIR"])] if os.environ.get("TM_OUT_DIR") else []
    dirs += [REPO / "harness" / "out", REPO / "demo_data"]
    for d in dirs:
        p = d / "line_tradein.csv"
        if p.exists():
            return p
    die("line_tradein.csv not found in " + ", ".join(rel(d) for d in dirs) + " (tm-offers writes it via harness/offers.py)")


def rel(p) -> str:
    try:
        return str(Path(p).resolve().relative_to(REPO))
    except ValueError:
        return str(p)


def resolve(cols: list[str], stems: list[str], horizon: str | None = None) -> str | None:
    for stem in stems:
        base = f"{stem}_{horizon}" if horizon else stem
        for c in cols:
            if re.fullmatch(re.escape(base) + r"(_cents|_usd)?", c):
                return c
    return None


def money(row, col) -> float:
    v = float(row[col])
    return v / 100 if col.endswith("_cents") else v


def usd(v: float) -> str:
    return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"


def esc(t: str) -> str:
    """Plotly/kaleido renders text between two '$' as LaTeX; use the HTML entity in figure text."""
    return t.replace("$", "&#36;")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--line", default=FEATURED)
    args = ap.parse_args()
    src = find_input()
    df = pd.read_csv(src)
    cols = list(df.columns)

    # ---- resolve every column we need from the header (fail clearly) ----
    hc, missing = {}, []
    for h, _ in HORIZONS:
        for k, stems in KINDS.items():
            c = resolve(cols, stems, h)
            hc[(k, h)] = c
            if c is None:
                missing.append(f"{stems[0]}_{h}[_cents]")
    sc = {}
    for k, stems in SCALARS.items():
        sc[k] = resolve(cols, stems)
        if sc[k] is None and k not in ("value_at_payoff", "installment", "data_note"):
            missing.append(stems[0])
    if missing:
        die(f"{rel(src)} is missing column(s): {', '.join(missing)}.\n  Columns present: {', '.join(cols)}")

    rows = df[df[sc["line_id"]] == args.line]
    if rows.empty:
        die(f"line {args.line} not found in {rel(src)} ({len(df)} lines)")
    r = rows.iloc[0]

    pts = []
    for h, label in HORIZONS:
        t, b, n, pr = (money(r, hc[(k, h)]) for k in ("tradein", "balance", "net", "promo"))
        pts.append(dict(horizon=h, label=label, tradein=t, balance=b, net=n, promo=pr, credit=t + pr))
    now, m6 = pts[0], pts[1]
    months_left = int(r[sc["months_left"]]) if pd.notna(r[sc["months_left"]]) else None
    wait_until = str(r[sc["wait_until"]]) if pd.notna(r[sc["wait_until"]]) else ""
    decision = str(r[sc["decision"]])
    verdict_raw = str(r[sc["wait_verdict"]])
    device = str(r[sc["device_name"]])
    payoff_val = money(r, sc["value_at_payoff"]) if sc["value_at_payoff"] and pd.notna(r[sc["value_at_payoff"]]) else None

    # ---- plain one-line verdict. Balance is owed either way, so it is never counted as savings. ----
    if decision.startswith("wait") and wait_until:
        when = pd.Timestamp(wait_until).strftime("%b %-d, %Y")
        if m6["credit"] > now["credit"]:
            promo = f"${m6['promo']:,.0f}"
            verdict = (f"Wait until {when}. After the last {months_left} payments, trade-in credit is "
                       f"{usd(m6['credit'])} in 6 months (incl. {promo} promo) vs {usd(now['credit'])} today.")
        else:
            verdict = f"Wait until {when}, when the phone is paid off."
    elif decision == "upgrade_now":
        verdict = f"Upgrade now: today's trade-in credit is {usd(now['credit'])}, and it only drops from here."
    else:
        verdict = "Keep the phone: no upgrade or wait offer beats doing nothing."
    note = (f"The {usd(now['balance'])} left on the phone is owed whether you upgrade now or later, "
            "so it is not counted as savings.") if now["balance"] > 0 else ""

    # ---- summary counts across all lines ----
    dec_counts = df[sc["decision"]].fillna("(blank)").value_counts()
    ver_counts = df[sc["wait_verdict"]].fillna("(blank)").value_counts()

    # ---- figure ----
    fig = make_subplots(rows=1, cols=2, column_widths=[0.70, 0.30], horizontal_spacing=0.06,
                        specs=[[{"type": "xy"}, {"type": "table"}]])
    xs = [p["label"] for p in pts]
    fig.add_bar(x=xs, y=[p["tradein"] for p in pts], name="Trade-in value", marker_color=MAGENTA,
                text=[usd(p["tradein"]) for p in pts], textposition="outside", row=1, col=1,
                hovertemplate="%{x}: trade-in value %{y:$,.2f}<extra>synthetic</extra>")
    fig.add_bar(x=xs, y=[p["balance"] for p in pts], name="Balance still owed on phone", marker_color=PLUM,
                text=[usd(p["balance"]) for p in pts], textposition="outside", row=1, col=1,
                hovertemplate="%{x}: balance owed %{y:$,.2f}<extra>synthetic</extra>")
    fig.add_bar(x=xs, y=[p["net"] for p in pts], name="Net (trade-in minus balance)", marker_color=PINK,
                marker_line_color=MAGENTA, marker_line_width=1.5,
                text=[usd(p["net"]) for p in pts], textposition="outside", row=1, col=1,
                hovertemplate="%{x}: net %{y:$,.2f}<extra>synthetic</extra>")
    ymax = max(max(p["tradein"], p["balance"], p["net"]) for p in pts) * 1.32
    for i, p in enumerate(pts):
        if p["promo"] > 0:
            fig.add_annotation(x=xs[i], y=ymax * 0.97, xref="x", yref="y", showarrow=False,
                               text=esc(f"<b>+${p['promo']:,.0f}</b> trade-in promo"), font=dict(color=MAGENTA, size=15))
        elif i == 0:
            fig.add_annotation(x=xs[i], y=ymax * 0.97, xref="x", yref="y", showarrow=False,
                               text="No trade-in promo yet", font=dict(color=MUTED, size=15))
    if decision.startswith("wait") and wait_until and months_left is not None:
        xpos = 0.5  # category axis (Now=0, 6m=1): marker sits in the gap between Now and 6 months
        fig.add_shape(type="line", x0=xpos, x1=xpos, y0=0, y1=ymax * 0.80, xref="x", yref="y",
                      line=dict(color=MAGENTA, width=3, dash="dash"))
        lab = f"<b>Wait until {wait_until}</b><br>last of {months_left} payments"
        if payoff_val is not None:
            lab += f"<br>trade-in then: {usd(payoff_val)}"
        fig.add_annotation(x=xpos, y=ymax * 0.80, xref="x", yref="y", text=esc(lab), showarrow=False, yanchor="bottom",
                           font=dict(color=PLUM, size=13), bgcolor=CREAM, bordercolor=MAGENTA, borderwidth=1)

    trows = [("<b>Decision</b>", "")] + [(f"  {k}", f"{v:,}") for k, v in dec_counts.items()] + \
            [("<b>Wait verdict</b>", "")] + [(f"  {k}", f"{v:,}") for k, v in ver_counts.items()] + \
            [("<b>Lines</b>", f"<b>{len(df):,}</b>")]
    fig.add_trace(go.Table(
        columnwidth=[0.7, 0.3],
        header=dict(values=["<b>All lines (synthetic)</b>", "<b>Count</b>"], fill_color=PLUM,
                    font=dict(color=CREAM, size=15), align=["left", "right"], height=34),
        cells=dict(values=[[a for a, _ in trows], [b for _, b in trows]], fill_color=CREAM,
                   font=dict(color=PLUM, size=14), align=["left", "right"], height=30, line_color=GRID)),
        row=1, col=2)

    title = f"Upgrade now or wait?  {device}, {months_left} payments left  ({args.line})"
    fig.update_layout(
        width=1600, height=900, paper_bgcolor=CREAM, plot_bgcolor=CREAM, barmode="group", bargap=0.28,
        font=dict(family="DejaVu Sans, Arial, sans-serif", color=PLUM, size=14),
        title=dict(text=f"<b>{esc(title)}</b><br><span style='font-size:22px;color:{MAGENTA}'><b>{esc(verdict).replace('. ', '.<br>', 1)}</b></span>"
                        + (f"<br><span style='font-size:15px;color:{PLUM}'>{esc(note)}</span>" if note else ""),
                   x=0.03, y=0.965, font=dict(size=26)),
        margin=dict(l=70, r=40, t=200, b=150),
        legend=dict(orientation="h", x=0.0, y=-0.07, font=dict(size=14)),
    )
    fig.update_yaxes(range=[0, ymax], tickprefix="$", tickformat=",.0f", gridcolor=GRID, zeroline=False,
                     title_text="Dollars (synthetic)", row=1, col=1)
    fig.update_xaxes(tickfont=dict(size=16), row=1, col=1)
    foot = esc(FOOT + f"<br>Source: {rel(src)}. Not shown on purpose: delta / cost_now / cost_wait (being corrected).")
    fig.add_annotation(xref="paper", yref="paper", x=0, y=-0.21, showarrow=False, xanchor="left", align="left",
                       text=foot, font=dict(size=12, color=MUTED))

    png, html = HERE / f"{NAME}.png", HERE / f"{NAME}.html"
    fig.write_html(html, include_plotlyjs=True, full_html=True)
    fig.write_image(png, width=1600, height=900, scale=1)

    summary = {
        "data": "SYNTHETIC", "source": rel(src), "columns_used": {f"{k}_{h}": c for (k, h), c in hc.items()} | sc,
        "featured_line": {"line_id": args.line, "device": device, "months_left": months_left, "wait_until": wait_until,
                          "decision": decision, "wait_verdict": verdict_raw, "tradein_value_at_payoff_usd": payoff_val,
                          "points_usd": pts, "verdict": verdict, "note": note},
        "decision_counts": dec_counts.to_dict(), "wait_verdict_counts": ver_counts.to_dict(), "lines": len(df),
        "not_shown": ["delta_cents", "cost_now_cents", "cost_wait_cents"],
    }
    (HERE / "upgrade_wait_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print("wrote", rel(png), "and", rel(html))
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()
