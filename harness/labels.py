"""Synthetic churn labels -> harness/out/labels.csv.   ALL LABELS AND RATES ARE SYNTHETIC.

Inputs: harness/out/features.csv (run features.py first) + the judge sandbox (read-only) for toy_p.

Primary label (plan-doc calibration recipe, adapted; see DATA_README.md):
  logit(monthly_hazard) = b0 + SHRINK * sum(coef * term)
  b0 solved by bisection so mean monthly_hazard over the 5,000 regular (non-persona) accounts = 0.990%
  (T-Mobile postpaid account churn, Q2 2026). p_true_90d = 1 - (1 - monthly_hazard)^3.
  churn_90d = 1[u < p_true_90d], u = per-account uniform from sha256(seed, account_id) -> order independent.
Toy columns (ranking checks only, never for charts):
  toy_p = exact sandbox datagen/reference_model.py probability (native horizon: 90 days), computed with the
  sandbox's own feature SQL (datagen/labels.py). toy_churn = OUR seeded draw of toy_p (the judges' draws need
  their private salt and are not reproducible).
Deterministic: python harness/labels.py [--recipe tuned|doc]   (both write out/labels.csv, same columns)
"""
from __future__ import annotations

import hashlib
import sys as _sys

_sys.dont_write_bytecode = True  # do not drop .pyc into the sandbox clone when importing datagen
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from features import find_db  # noqa: E402

FEATURES = HERE / "out" / "features.csv"
OUT = HERE / "out" / "labels.csv"
TARGET_MONTHLY = 0.0099
SEED_LABEL = "tm-churn-2026-label"
SEED_TOY = "tm-churn-2026-toy"
THREAT = 1.15  # competitor + port-out multiplier (Verizon loyalty push 2026-06-16), per plan doc
SHRINK = 0.5  # global multiplier on all coefficients below (not b0). Rank-neutral; keeps monthly hazards plausible
              # (max ~0.5 instead of ~0.94) so mean 90d p lands near 1-(1-0.0099)^3 = 2.94%. See DATA_README.

# (column/term name, coefficient, description). Terms are built in terms().
COEFS = [
    ("support_90d", 0.15, "support contacts, last 90d (toy uses 0.45; cut so resolved/happy contact is not risk)"),
    ("unresolved_90d", 0.45, "unresolved contacts, last 90d"),
    ("negative_contacts_90d", 0.30, "contacts with sentiment < 0, last 90d"),
    ("neg_sentiment", 0.80, "max(0, -avg_sentiment) over all contacts (toy term)"),
    ("bill_increase_pct", 4.00, "max(0, last bill / prior avg - 1) (toy term)"),
    ("competitor_research_x", 2.20 * THREAT, "competitor_research_score x1.15 threat (toy 2.2)"),
    ("port_out_inquiry_x", 1.20 * THREAT, "port_out_inquiry x1.15 threat (toy 1.2)"),
    ("tenure_capped60", -0.01, "min(tenure_months, 60) (toy term)"),
    ("plan_misfit_share", 0.70, "share of lines over cap or light on premium (toy term)"),
    ("early_tenure", 0.90, "tenure_months < 12"),
    ("no_financing", 0.60, "no financed lines"),
    ("no_autopay", 0.30, "autopay = 0"),
    ("troubled_4plus", 0.50, "4+ contacts in 90d AND at least one unresolved or negative (doc: '4+ contacts')"),
    ("max_device_age_months_f", 0.02, "max device age in months (0 if no dated device)"),
    ("extra_lines", -0.15, "n_lines - 1"),
    ("app_sessions_30d", -0.06, "app sessions last 30d (doc -0.02; raised so engaged users read as safe)"),
    ("low_app_use", 1.00, "app_sessions_30d <= 3 (silent disengagement; added)"),
    ("promo_expired_recent", 0.60, "promo_expired bill change in last 3 months (added; doc lists promo_expired as a churn field)"),
    ("billing_contacts_90d", 0.10, "billing-topic contacts, 90d"),
    ("device_contacts_90d", 0.05, "device-topic contacts, 90d"),
    ("cancel_inquiries_270d", 0.25, "cancellation-inquiry contacts, 270d"),
]

COEFS_TUNED = COEFS

# Plan-doc line-205 recipe as written (no persona tweaks). toy terms + extras; competitor/port-out x1.15.
COEFS_DOC = [
    ("support_90d", 0.45, "support contacts, last 90d (toy term)"),
    ("neg_sentiment", 0.80, "max(0, -avg_sentiment) (toy term)"),
    ("bill_increase_pct", 4.00, "max(0, last bill / prior avg - 1) (toy term)"),
    ("competitor_research_x", 2.20 * THREAT, "competitor_research_score x1.15"),
    ("port_out_inquiry_x", 1.20 * THREAT, "port_out_inquiry x1.15"),
    ("tenure_capped60", -0.01, "min(tenure_months, 60) (toy term)"),
    ("plan_misfit_share", 0.70, "plan misfit share (toy term)"),
    ("early_tenure", 0.90, "tenure_months < 12"),
    ("no_financing", 0.60, "no financed lines"),
    ("no_autopay", 0.30, "autopay = 0"),
    ("contacts_4plus", 0.50, "4+ support contacts in 90d (unconditional)"),
    ("max_device_age_months_f", 0.02, "max device age in months"),
    ("extra_lines", -0.15, "n_lines - 1"),
    ("app_sessions_30d", -0.02, "app sessions last 30d"),
    ("billing_contacts_90d", 0.10, "billing-topic contacts, 90d"),
    ("device_contacts_90d", 0.05, "device-topic contacts, 90d"),
    ("cancel_inquiries_270d", 0.25, "cancellation-inquiry contacts, 270d"),
]
# shrink per recipe; doc shrink decided by DOC_MAX_HAZARD guard (see choose_shrink)
DOC_MAX_HAZARD = 0.5
RECIPES = {"tuned": COEFS_TUNED, "doc": COEFS_DOC}


def terms(f: pd.DataFrame) -> pd.DataFrame:
    t = pd.DataFrame(index=f.index)
    for c in ["support_90d", "unresolved_90d", "negative_contacts_90d", "bill_increase_pct", "plan_misfit_share",
              "app_sessions_30d", "billing_contacts_90d", "device_contacts_90d", "cancel_inquiries_270d"]:
        t[c] = f[c].fillna(0).astype(float)
    t["neg_sentiment"] = (-f["avg_sentiment"].fillna(0)).clip(lower=0)
    t["competitor_research_x"] = f["competitor_research_score"].astype(float)
    t["port_out_inquiry_x"] = f["port_out_inquiry"].astype(float)
    t["tenure_capped60"] = f["tenure_months"].clip(upper=60).astype(float)
    t["early_tenure"] = (f["tenure_months"] < 12).astype(float)
    t["no_financing"] = (f["n_financed_lines"] == 0).astype(float)
    t["no_autopay"] = (f["autopay"] == 0).astype(float)
    t["troubled_4plus"] = ((f["support_90d"] >= 4) & ((f["unresolved_90d"] > 0) | (f["negative_contacts_90d"] > 0))).astype(float)
    t["max_device_age_months_f"] = f["max_device_age_months"].fillna(0).astype(float)
    t["extra_lines"] = (f["n_lines"] - 1).astype(float)
    t["low_app_use"] = (f["app_sessions_30d"] <= 3).astype(float)
    t["promo_expired_recent"] = f["promo_expired_recent"].astype(float)
    t["contacts_4plus"] = (f["support_90d"] >= 4).astype(float)
    return t


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def solve_b0(score: np.ndarray, target: float) -> float:
    lo, hi = -20.0, 5.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if sigmoid(mid + score).mean() > target:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def uniform(seed: str, ids: pd.Series) -> np.ndarray:
    return np.array([int(hashlib.sha256(f"{seed}:{a}".encode()).hexdigest()[:15], 16) / 16**15 for a in ids])


def toy_probabilities() -> pd.Series:
    """Exact sandbox toy model, using the sandbox's own SQL + formula (imported read-only from the clone)."""
    db = find_db()
    sys.path.insert(0, str(db.parent.parent))
    from datagen import catalog, reference_model  # type: ignore
    from datagen import labels as dl  # type: ignore
    conn = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(dl._FEATURES_SQL, {"as_of": catalog.AS_OF.isoformat()}).fetchall()
        out = {r["account_id"]: reference_model.probability(r["account_id"], dl._features(r), conn) for r in rows}
    finally:
        conn.close()
    return pd.Series(out, name="toy_p")


def fit(T: pd.DataFrame, coefs, shrink: float, regular: np.ndarray):
    w = shrink * np.array([c for _, c, _ in coefs])
    score = T[[c for c, _, _ in coefs]].values @ w
    b0 = solve_b0(score[regular], TARGET_MONTHLY)
    return w, b0, sigmoid(b0 + score)


def build(recipe: str = "tuned"):
    f = pd.read_csv(FEATURES)
    coefs = RECIPES[recipe]
    T = terms(f)[[c for c, _, _ in coefs]]
    regular = (f["is_persona"] == 0).values
    if recipe == "tuned":
        shrink = SHRINK
        w, b0, h = fit(T, coefs, shrink, regular)
    else:  # doc: no halving unless max monthly hazard among regular accounts exceeds DOC_MAX_HAZARD
        shrink = 1.0
        w, b0, h = fit(T, coefs, shrink, regular)
        if h[regular].max() > DOC_MAX_HAZARD:
            shrink = SHRINK
            w, b0, h = fit(T, coefs, shrink, regular)
    p90 = 1 - (1 - h) ** 3
    lab = pd.DataFrame({
        "account_id": f["account_id"], "is_persona": f["is_persona"],
        "churn_90d": (uniform(SEED_LABEL, f["account_id"]) < p90).astype(int),
        "p_true_90d": p90.round(6), "monthly_hazard": h.round(6),
    })
    toy = toy_probabilities()
    lab["toy_p"] = lab["account_id"].map(toy).round(6)
    lab["toy_churn"] = (uniform(SEED_TOY, lab["account_id"]) < lab["toy_p"]).astype(int)
    # top-3 label drivers per account (largest positive contributions), for sanity/debug
    contrib = T.values * w
    names = np.array([c for c, _, _ in coefs])
    top = np.argsort(-contrib, axis=1)[:, :3]
    for k in range(3):
        lab[f"label_driver_{k + 1}"] = [names[i] if contrib[r, i] > 0 else "" for r, i in enumerate(top[:, k])]
    return lab, b0, shrink


PERSONAS = {"04": "high", "21": "high", "22": "high", "27": "high", "10": "low", "24": "low",
            "23": "", "25": "", "26": "", "28": ""}


def persona_report(lab: pd.DataFrame) -> str:
    r = lab.loc[lab["is_persona"] == 0, "p_true_90d"]
    out = []
    for k, exp in PERSONAS.items():
        p = lab.loc[lab["account_id"] == f"ACC-PERSONA-{k}", "p_true_90d"].iloc[0]
        pct = (r < p).mean() * 100
        ok = "" if not exp else (" OK" if (exp == "high" and pct >= 90) or (exp == "low" and pct <= 50) else " MISS")
        out.append(f"  persona {k} ({exp or '-'}): p_true_90d={p:.4f} pct={pct:.1f}{ok}")
    return "\n".join(out)


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--recipe", choices=sorted(RECIPES), default="tuned",
                    help="tuned (default, persona-aware) or doc (plan-doc line-205 as written)")
    args = ap.parse_args()
    lab, b0, shrink = build(args.recipe)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lab.to_csv(OUT, index=False)
    r = lab[lab["is_persona"] == 0]
    print(f"wrote {OUT} recipe={args.recipe} rows={len(lab)}  b0={b0:.4f}  shrink={shrink}")
    print(f"regular n={len(r)} mean monthly_hazard={r.monthly_hazard.mean():.5f} mean p_true_90d={r.p_true_90d.mean():.5f} "
          f"churn_90d positives={r.churn_90d.sum()} ({r.churn_90d.mean():.4f}); toy_p mean={r.toy_p.mean():.4f} "
          f"toy_churn={r.toy_churn.sum()}  max_h={r.monthly_hazard.max():.3f}  [ALL SYNTHETIC]")
    print("persona percentiles among 5,000 regular accounts (high OK if >=90th, low OK if <=50th):")
    print(persona_report(lab))


if __name__ == "__main__":
    main()
