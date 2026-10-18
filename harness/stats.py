"""Population figures on the public sandbox score. Personas are left out of these rates."""

from __future__ import annotations

import pandas as pd


def _rate(frame: pd.DataFrame, mask: pd.Series) -> dict:
    group = frame.loc[mask]
    n = int(len(group))
    return {"n": n, "expected_churn": float(group["sandbox_p"].mean()) if n else 0.0}


def population_stats(frame: pd.DataFrame) -> dict:
    base = frame.loc[frame["is_persona"] == 0].copy()
    ordered = base.sort_values("sandbox_p", ascending=False)
    total = float(ordered["sandbox_p"].sum())
    bands = {}
    for label, frac in (("top_10", 0.10), ("top_20", 0.20), ("top_30", 0.30)):
        k = int(round(len(ordered) * frac))
        head = ordered.iloc[:k]
        bands[label] = {
            "n": k,
            "share_of_expected_churners": float(head["sandbox_p"].sum() / total) if total else 0.0,
            "mean_risk": float(head["sandbox_p"].mean()) if k else 0.0,
        }
    support_bins = []
    for label, mask in (
        ("0", base["support_90d"] == 0),
        ("1", base["support_90d"] == 1),
        ("2", base["support_90d"] == 2),
        ("3", base["support_90d"] == 3),
        ("4", base["support_90d"] == 4),
        ("5+", base["support_90d"] >= 5),
    ):
        item = _rate(base, mask)
        item["bin"] = label
        support_bins.append(item)
    deciles = []
    base = base.sort_values("sandbox_p")
    base["decile"] = pd.qcut(base["sandbox_p"].rank(method="first"), 10, labels=False) + 1
    for decile, group in base.groupby("decile"):
        deciles.append(
            {
                "decile": int(decile),
                "accounts": int(len(group)),
                "mean_risk": float(group["sandbox_p"].mean()),
                "share_of_expected_churners": float(group["sandbox_p"].sum() / total) if total else 0.0,
            }
        )
    segments = (
        base.groupby("segment")["sandbox_p"].agg(n="size", expected_churn="mean").reset_index().to_dict("records")
    )
    return {
        "accounts": int(len(base)),
        "expected_churn_rate": float(base["sandbox_p"].mean()),
        "expected_churners": total,
        "concentration": bands,
        "support_bins": support_bins,
        "deciles": deciles,
        "competitor_zero": _rate(base, base["competitor_research"] == 0),
        "competitor_high": _rate(base, base["competitor_research"] >= 0.75),
        "bill_up": _rate(base, base["bill_increase_pct"] > 0.05),
        "bill_flat": _rate(base, base["bill_increase_pct"] <= 0.05),
        "port_yes": _rate(base, base["port_out_inquiry"] == 1),
        "port_no": _rate(base, base["port_out_inquiry"] == 0),
        "tenure_long": _rate(base, base["tenure_months"] >= 36),
        "tenure_short": _rate(base, base["tenure_months"] < 12),
        "autopay_on": _rate(base, base["autopay"] == 1),
        "autopay_off": _rate(base, base["autopay"] == 0),
        "home_internet": _rate(base, base["has_home_internet"] == 1),
        "no_home_internet": _rate(base, base["has_home_internet"] == 0),
        "streaming": _rate(base, base["has_streaming"] == 1),
        "no_streaming": _rate(base, base["has_streaming"] == 0),
        "segments": segments,
        "cancellation_accounts": int((base["cancellation_inquiries"] > 0).sum()),
        "promo_expired_recent": int(base["promo_expired_recent"].sum()),
        "installment_ended_recent": int(base["installment_ended_recent"].sum()),
        "population_note": (
            "Rates are the mean public sandbox probability on the 5,000 non-persona accounts. "
            "They are expected 90-day churn on that scoring model, not a count of observed churners. "
            "The judges' private model is different and is not in this repo."
        ),
    }
