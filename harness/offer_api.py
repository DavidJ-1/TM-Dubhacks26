"""Thin per-account API over the offers.py EV engine, for the demo's live toggles (tm-offers).

    from offer_api import choose_offer, prepared_row
    row = prepared_row("ACC-PERSONA-21")          # engine-ready row (all fields evaluate_account needs)
    row["port_out_inquiry"] = 0                     # apply a UI toggle
    out = choose_offer(row, p_churn=0.017)          # p_churn from churn_scorer.score_account on the toggled row
    out["action"], out["candidates"]                # chosen label + ranked candidate table (DataFrame)

Pure: reads the sandbox read-only and harness/out (or demo_data/) once, caches, never writes. All numbers synthetic.
"""
from __future__ import annotations

import functools
from pathlib import Path

import numpy as np
import pandas as pd

import offers as O
import offer_detectors as det

_ROOT = Path(__file__).resolve().parent.parent


def _first(*names: str) -> Path:
    for base in (O.OUT_DIR, _ROOT / "demo_data"):
        for n in names:
            if (base / n).exists():
                return base / n
    raise FileNotFoundError(f"none of {names} in {O.OUT_DIR} or demo_data/")


@functools.lru_cache(maxsize=1)
def _engine():
    """Build the same prepared account frame offers.main() builds (without writing anything)."""
    conn = det.connect_ro()
    cat = det.load_catalog(conn)
    facts = det.build_account_facts(conn)
    feat = O.OUT_DIR / "features.csv"
    facts, _ = det.apply_features_csv(facts, feat if feat.exists() else _first("features.csv"))
    enr = O.OUT_DIR / "enrichment.csv"
    facts, _ = det.apply_enrichment(facts, enr if enr.exists() else _first("enrichment.csv"))
    churn = pd.read_csv(_first("churn_scores.csv"))
    df = facts.merge(churn[[c for c in O.CHURN_COLS if c in churn.columns]], on="account_id", how="left")
    df["p_churn_90d"] = df["p_churn_90d"].fillna(df["p_churn_90d"].median())
    plans = cat["plans"]
    df["all_low_use_premium_any"] = df["um_plan_overpay"]
    df["um_plan_overpay"] = [bool(r["um_plan_overpay"] or O.right_size_option(r, plans) is not None
                                  or O.variant_option(r, plans) is not None) for _, r in df.iterrows()]
    df["upgrade_moment"] = df[det.UPGRADE_MOMENT_COLS].any(axis=1)
    import upgrade_gate as ug
    gs = ug.load() if O.CONFIG["UPGRADE_GATE"] else None
    if gs is not None:
        df = df.merge(gs[["account_id", "upgrade_pct", "in_top15"]], on="account_id", how="left")
        df["in_top15"] = df["in_top15"].fillna(False).astype(bool)
    else:
        df["upgrade_pct"], df["in_top15"] = np.nan, True
    df["upgrade_candidate"] = df["upgrade_moment"] & df["in_top15"]
    lt = pd.read_csv(_first("line_tradein.csv"))
    tv = lt[(lt["net_now_cents"] > 0) | ((lt["financing_balance_cents"] == 0) & (lt["tradein_value_now_cents"] > 0))]
    df["n_tradein_value_lines"] = df["account_id"].map(tv.groupby("account_id").size()).fillna(0).astype(int)
    wcol = next((c for c in ("decision", "wait_verdict") if c in lt.columns), None)   # mirrors offers.prepare()
    w = (lt[lt[wcol].astype(str) == "wait_until_payoff"] if wcol == "decision" else lt[lt[wcol] == "wait"]) \
        if wcol else lt.iloc[0:0]
    df["n_wait_lines"] = df["account_id"].map(w.groupby("account_id").size()).fillna(0).astype(int)
    return df.set_index("account_id", drop=False), cat["promotions"], plans


def prepared_row(account_id: str) -> pd.Series:
    """Engine-ready copy of one account's row; edit fields on it to simulate a toggle."""
    df, _, _ = _engine()
    return df.loc[account_id].copy()


def choose_offer(account_row: pd.Series, p_churn: float | None = None) -> dict:
    """Run the real chooser on one (possibly toggled) row. Returns action label/code, EV, reason,
    why_this_offer, en/es message, and the ranked candidates (same columns as offer_candidates.csv)."""
    _, promos, plans = _engine()
    row = account_row.copy()
    if p_churn is not None:
        row["p_churn_90d"] = float(p_churn)
    offers, cands = O.choose(pd.DataFrame([row]), promos, plans)
    o = offers.iloc[0]
    res = O.DETAILS[o["account_id"]]["res"]
    msg = {}
    try:
        import offer_messages as om
        for lang in ("en", "es"):
            msg[lang] = om.build_message(row, o["action_code"], res, promos, plans, lang)
    except Exception as e:  # message is optional for the toggle view
        msg = {"en": "", "es": "", "error": str(e)}
    return {"action": o["action"], "action_code": o["action_code"], "expected_value": o["expected_value"],
            "reason": o["reason"], "why_this_offer": o["why_this_offer"], "promo_skus": o["promo_skus"],
            "p_churn_90d": row["p_churn_90d"], "message_en": msg.get("en", ""), "message_es": msg.get("es", ""),
            "candidates": cands.sort_values("rank"), "data_note": "synthetic/simulated"}
