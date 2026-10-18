"""Strategy comparison chart data (tm-ui). Simulated numbers.

Reads the efficacy lane's chart files at runtime (nothing hardcoded; follow experiments/efficacy/README.md):
  out/chart_bars.csv       business net in full company $ per policy, picked at one save rate, scored at several;
                           realized-outcome bootstrap whiskers; money back to customers as its own series
  out/chart_receipt.csv    receipt line (cheaper plans are never texted; money back on the bill)
  out/chart_breakeven.csv  break-even save rate for the headline bar
  policy_by_save_rate.csv  margin given up on purpose + customer savings (today's engine, chart-accounting row)
  headline_1478.csv        headline bar: kept value $1,478, new guardrail (nets at 5/10/22%, realized ranges,
                           break-even, message count); overrides the ret_10 bar when present
  chart_data.py            HI_NOTE / PERK_NOTE footnote strings, read with ast (never imported or run)
Folder override: TM_EFFICACY_DIR. Every loader returns None/empty when a file is missing or malformed, so the app
shows a quiet "pending" note instead of crashing. No path is ever shown on screen.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
HEADLINE_BAR = "ret_10"          # README: "Headline bar (bold): Retention-only, re-picked at 10%"
QA_ONLY = {"upsell_qa"}          # README: profit-ranked upsell row is Q&A only (rests on an upgrade-rate assumption)

# on-screen names only; values always come from the CSVs. Unknown keys fall back to the CSV label.
DISPLAY = {
    "shipped": "Shipped engine, full company dollars, retention only",
    "risk_credit": "Top 10% risk: $25 credit to everyone",
    "risk_best": "Top 10% risk: best fix for each",
    "ret_fixed44": "Retention offers only, picks assume 44%",
    "ret_10": "Retention offers only, re-picked at 10%",
    "receipt_only": "Cheaper plans on the receipt only, no texts",
    "texts_receipt": "Retention texts + cheaper plans on the receipt",
    "upsell_qa": "Profit-ranked incl. plan upgrades",
    "nothing": "Do nothing",
}


POLICY_CSV = Path(os.environ.get("TM_POLICY_BY_SAVE_RATE",
                                REPO.parent / "scratch_models" / "chart_check" / "policy_by_save_rate.csv"))
HEADLINE_CSV = Path(os.environ.get("TM_HEADLINE_CSV", REPO.parent / "scratch_models" / "economics" / "headline_1478.csv"))
SHIPPED_POLICY = "shipped_engine_chart_accounting"
OUTREACH_CSV = REPO / "docs" / "outreach" / "outreach_card.csv"


def base_dir() -> Path:
    return Path(os.environ.get("TM_EFFICACY_DIR", REPO / "experiments" / "efficacy"))


def _read(name: str) -> pd.DataFrame | None:
    p = base_dir() / "out" / name
    try:
        return pd.read_csv(p) if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def notes_from_script() -> dict:
    """HI_NOTE / PERK_NOTE string constants from chart_data.py, parsed (not executed)."""
    out = {}
    try:
        tree = ast.parse((base_dir() / "chart_data.py").read_text())
        for n in tree.body:
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
                for t in n.targets:
                    if isinstance(t, ast.Name) and t.id in ("HI_NOTE", "PERK_NOTE"):
                        out[t.id] = n.value.value
    except Exception:  # noqa: BLE001
        pass
    return out


def _col(g: pd.DataFrame, *names: str):
    return next((g[n] for n in names if n in g), pd.Series(np.nan, index=g.index))


def _read_abs(p: Path) -> pd.DataFrame | None:
    try:
        return pd.read_csv(p) if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def text_count() -> int | None:
    """How many of the messages go out as texts (the rest are in-app, email or a call), from the outreach file."""
    o = _read_abs(OUTREACH_CSV)
    if o is None or not {"outreach_reason", "message_en"}.issubset(o.columns):
        return None
    m = o.message_en.fillna("").astype(str).str.strip() != ""
    ch = o.outreach_reason.fillna("").astype(str).str.extract(r"Sent as:\s*([^.]+)", expand=False).str.strip().str.lower()
    return int((m & (ch == "text")).sum())


def headline_row() -> dict | None:
    """Headline bar from the kept-value $1,478 / new-guardrail run, or None (then chart_bars.csv's ret_10 is used)."""
    h = _read_abs(HEADLINE_CSV)
    need = {"kept_value", "guardrail", "contacts", "net_5", "net_10", "net_22", "breakeven_sr"}
    if h is None or not need.issubset(h.columns):
        return None
    kv = h.kept_value.astype(str).str.replace(",", "").str.extract(r"\$?(\d+)", expand=False)
    r = h[(kv == "1478") & h.guardrail.astype(str).str.lower().str.startswith("new")]
    if r.empty:
        return None
    r = r.iloc[0]
    nets = {0.05: float(r.net_5), 0.10: float(r.net_10), 0.22: float(r.net_22)}
    wh = {}
    for rt, k in ((0.10, "boot10"), (0.05, "boot5")):
        if all(f"{k}_{x}" in r for x in ("lo", "hi", "p_pos")) and pd.notna(r[f"{k}_lo"]):
            wh[rt] = (float(r[f"{k}_lo"]), float(r[f"{k}_hi"]), float(r[f"{k}_p_pos"]))
    return dict(nets=nets, whiskers=wh, messages=int(r.contacts), breakeven=float(r.breakeven_sr), texts=text_count())


def load_strategy() -> dict | None:
    b = _read("chart_bars.csv")
    if b is None or not {"bar", "label", "scored_save_rate", "business_net_full_usd"}.issubset(b.columns):
        return None
    b = b.copy()
    b["rate"] = _num(b.scored_save_rate)
    b["net"] = _num(b.business_net_full_usd)
    b["money_back"] = _num(_col(b, "customer_savings_usd"))
    b["r_lo"] = _num(_col(b, "realized_ci_lo", "realised_ci_lo"))
    b["r_hi"] = _num(_col(b, "realized_ci_hi", "realised_ci_hi"))
    b["r_p"] = _num(_col(b, "realized_p_net_pos", "realised_p_net_pos"))
    b["pending"] = b.get("status", pd.Series("", index=b.index)).astype(str).str.startswith("pending") | b.net.isna()
    hl = b.get("headline", pd.Series(False, index=b.index)).astype(str).str.lower() == "true"
    headline = float(b.loc[hl, "rate"].dropna().iloc[0]) if hl.any() else float(b.rate.min())
    dec = _num(b.loc[b.bar == HEADLINE_BAR, "decide_save_rate"]) if "decide_save_rate" in b else pd.Series(dtype=float)
    decide = float(dec.dropna().iloc[0]) if len(dec.dropna()) else None

    H = headline_row()
    rows, pending, qa = [], [], []
    for key, g in b.groupby("bar", sort=False):
        name = DISPLAY.get(key, str(g.label.iloc[0]))
        ok = g[~g.pending]
        if key == HEADLINE_BAR and H is not None:
            name += f" · {H['messages']:,} messages" + (f" ({H['texts']:,} by text)" if H.get("texts") is not None else "")
            nets = H["nets"]
            rows.append(dict(key=key, name=name, low=min(nets.values()), high=max(nets.values()),
                             rate_lo=min(nets), rate_hi=max(nets), nets=nets, whiskers=H["whiskers"],
                             headline=nets.get(headline, np.nan), money_back=np.nan, is_headline=True))
            continue
        if ok.empty:
            pending.append(name)
            continue
        h = ok[ok.rate == headline]
        hr = h.iloc[0] if len(h) else None
        row = dict(key=key, name=name, low=float(ok.net.min()), high=float(ok.net.max()),
                   rate_lo=float(ok.rate.min()), rate_hi=float(ok.rate.max()),
                   nets={float(r.rate): float(r.net) for r in ok.itertuples()},
                   whiskers={float(r.rate): (float(r.r_lo), float(r.r_hi), float(r.r_p))
                             for r in ok.itertuples() if pd.notna(r.r_lo) and pd.notna(r.r_hi)},
                   headline=float(hr.net) if hr is not None else np.nan,
                   money_back=float(hr.money_back) if hr is not None and pd.notna(hr.money_back) else np.nan,
                   is_headline=key == HEADLINE_BAR)
        (qa if key in QA_ONLY else rows).append(row)
    if not rows:
        return None
    return dict(rows=pd.DataFrame(rows), qa=qa, pending=pending, headline=headline, decide=decide,
                rates=sorted(b.loc[~b.pending, "rate"].dropna().unique().tolist()),
                breakeven=(H["breakeven"] if H is not None else breakeven_rate()), receipt=receipt_lines(),
                margin=margin_today(), headline_src="kept_value_1478" if H is not None else "chart_bars",
                notes=notes_from_script())


def breakeven_rate() -> float | None:
    be = _read("chart_breakeven.csv")
    if be is None or "true_save_rate_exact" not in be:
        return None
    v = _num(be.true_save_rate_exact).dropna()
    return float(v.iloc[0]) if len(v) else None


def receipt_lines() -> dict | None:
    r = _read("chart_receipt.csv")
    if r is None or "counts_in_headline" not in r:
        return None
    try:
        inh = r.counts_in_headline.astype(str).str.lower() == "true"
        y3 = _num(r.get("yearly_at_3pct_switch"))
        h = r[inh & (y3 > 0)].iloc[0]
        other = r[~inh]
        return dict(accounts=int(h.accounts), mid=float(h.yearly_at_3pct_switch), lo=float(h.yearly_at_2pct_switch),
                    hi=float(h.yearly_at_13pct_switch),
                    other_accounts=int(other.accounts.iloc[0]) if len(other) else None,
                    fallback=str(h.get("fallback", "False")).lower() == "true")
    except Exception:  # noqa: BLE001
        return None


def margin_today() -> dict | None:
    """Margin given up on purpose (cheaper-plan revenue handed back) and customer savings for today's engine, from
    policy_by_save_rate.csv (the single chart source), shipped_engine_chart_accounting rows."""
    v = _read_abs(POLICY_CSV)
    if v is None or not {"policy", "margin_given_up", "customer_savings"}.issubset(v.columns):
        return None
    o = v[v.policy.astype(str).str.strip() == SHIPPED_POLICY]
    m, c = _num(o.margin_given_up).dropna(), _num(o.customer_savings).dropna()
    if m.empty:
        return None
    return dict(margin=float(m.iloc[0]), savings=float(c.iloc[0]) if len(c) else np.nan)
