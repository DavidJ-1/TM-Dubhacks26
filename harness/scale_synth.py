"""Scale the sandbox to N synthetic accounts with a Gaussian copula -> harness/out/scaled/

"N synthetic accounts generated from the sandbox's distributions": each row is NEW synthetic data, not a
sandbox customer. Marginals = empirical distributions of the 5,000 regular sandbox accounts (features.csv);
dependence = rank (normal-score) correlation matrix. ALL LABELS AND RATES ARE SYNTHETIC.

Outputs (never touches out/features.csv or out/labels.csv):
  out/scaled/features_scaled.csv  same columns as features.csv (+ enrichment columns if out/enrichment.csv exists)
  out/scaled/labels_scaled.csv    same columns as labels.csv; same labels.py recipe (tuned churn + upgrade), b0s
                                  re-solved on the synthetic rows (0.99%/month churn, 6%/90d upgrade)
  out/scaled/FIDELITY.md          KS per column, correlation-matrix difference, base rates, TSTR AUC
Run: python harness/scale_synth.py [--n 50000] [--seed 2026] [--no-fidelity]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import labels as L  # noqa: E402
from features import find_db  # noqa: E402

OUT_DIR = HERE / "out" / "scaled"
ENRICH = HERE / "out" / "enrichment.csv"

CATEGORICAL = ["segment", "language", "contact_preference", "credit_tier", "discount_group", "plan_sku"]
CREDIT_ORDER = ["subprime", "near_prime", "prime"]
# derived after sampling (not modelled directly)
DERIVED = ["account_id", "is_persona", "plan_family", "plan_tier", "plan_data_cap_gb", "plan_is_unlimited",
           "plan_price_cents", "financing_ends_within_3m", "support_90d"]
TOPICS = ["billing_contacts_90d", "device_contacts_90d", "plan_change_contacts_90d", "network_contacts_90d",
          "cancellation_inquiry_contacts_90d"]
# conditional columns: modelled only on rows where condition holds; otherwise set to the fill value
FIN_COLS = ["financing_balance_total_cents", "monthly_installment_total_cents", "max_financing_months_remaining",
            "min_financing_months_left_financed"]
DEV_COLS = ["max_device_age_months", "mean_device_age_months"]
COND = {**{c: ("financed", 0) for c in FIN_COLS},
        **{c: ("has_dated_device", np.nan) for c in DEV_COLS},
        "avg_sentiment": ("any_contact_270d", 0.0), "min_sentiment_270d": ("any_contact_270d", 0.0),
        "days_since_last_contact": ("any_contact_270d", 999),
        "avg_sentiment_90d": ("any_contact_90d", 0.0)}


def conditions(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "financed": df["n_financed_lines"] > 0,
        "has_dated_device": df["n_byod_lines"] < df["n_lines"],
        "any_contact_270d": df["support_270d"] > 0,
        "any_contact_90d": df[TOPICS].sum(axis=1) > 0 if "support_90d" not in df else df["support_90d"] > 0,
    })


def nearest_psd_corr(C: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    w, V = np.linalg.eigh((C + C.T) / 2)
    C2 = V @ np.diag(np.clip(w, eps, None)) @ V.T
    d = np.sqrt(np.diag(C2))
    return C2 / np.outer(d, d)


class Copula:
    def fit(self, df: pd.DataFrame, rng: np.random.Generator):
        self.cols, self.kind, self.support, self.cat_levels = [], {}, {}, {}
        Z = {}
        cond = conditions(df)
        bill_ref = df["last_bill_cents"]
        n = len(df)
        for c in df.columns:
            if c in DERIVED:
                continue
            x = df[c]
            mask = pd.Series(True, index=df.index)
            if c in COND:
                mask = cond[COND[c][0]]
            if c in CATEGORICAL:
                if c == "credit_tier":
                    levels = CREDIT_ORDER
                else:  # order levels by mean bill so the ordinal code carries some meaning
                    levels = list(bill_ref.groupby(x).mean().sort_values().index)
                self.cat_levels[c] = levels
                x = x.map({v: i for i, v in enumerate(levels)}).astype(float)
                self.kind[c] = "cat"
            else:
                self.kind[c] = "int" if pd.api.types.is_integer_dtype(df[c]) else "float"
            if x[mask].isna().any():  # natural blanks (e.g. prior bill) -> separate missingness indicator
                ind = f"{c}__isna"
                self.cols.append(ind); self.kind[ind] = "int"
                v = x.isna().astype(float)
                self.support[ind] = np.sort(v.values)
                Z[ind] = self._scores(v, pd.Series(True, index=df.index), rng)
                mask = mask & x.notna()
            self.cols.append(c)
            self.support[c] = np.sort(x[mask].values.astype(float))
            Z[c] = self._scores(x, mask, rng)
        Zdf = pd.DataFrame(Z)[self.cols]
        C = Zdf.corr(min_periods=30).fillna(0).to_numpy(copy=True)
        np.fill_diagonal(C, 1.0)
        self.corr = nearest_psd_corr(C)
        self.n_train = n
        return self

    @staticmethod
    def _scores(x: pd.Series, mask: pd.Series, rng) -> pd.Series:
        z = pd.Series(np.nan, index=x.index)
        v = x[mask].values.astype(float)
        jitter = rng.random(len(v))  # random tie-breaking -> continuous normal scores
        order = np.lexsort((jitter, v))
        ranks = np.empty(len(v)); ranks[order] = np.arange(1, len(v) + 1)
        z[mask] = stats.norm.ppf(ranks / (len(v) + 1))
        return z

    def sample(self, n: int, rng) -> pd.DataFrame:
        Zs = rng.multivariate_normal(np.zeros(len(self.cols)), self.corr, size=n, method="eigh")
        U = stats.norm.cdf(Zs)
        out = {}
        for j, c in enumerate(self.cols):
            s = self.support[c]
            idx = np.minimum((U[:, j] * len(s)).astype(int), len(s) - 1)  # inverse empirical CDF
            out[c] = s[idx]
        df = pd.DataFrame(out)
        for c in [c for c in self.cols if c.endswith("__isna")]:
            base = c[: -len("__isna")]
            df.loc[df[c] == 1, base] = np.nan
            df = df.drop(columns=c)
        for c, levels in self.cat_levels.items():
            df[c] = np.array(levels, dtype=object)[df[c].astype(int).values]
        return df


def load_plans() -> pd.DataFrame:
    conn = sqlite3.connect(find_db().as_uri() + "?mode=ro", uri=True)
    try:
        return pd.read_sql("SELECT * FROM plans", conn).set_index("sku")
    finally:
        conn.close()


def enforce(df: pd.DataFrame, plans: pd.DataFrame) -> pd.DataFrame:
    """Logical constraints + derived columns."""
    i = lambda c: df[c].round().astype(int)  # noqa: E731
    # plan / lines
    lo = df["plan_sku"].map(plans["min_lines"]).astype(int)
    hi = df["plan_sku"].map(plans["max_lines"]).fillna(6).astype(int)
    df["n_lines"] = i("n_lines").clip(lower=lo, upper=hi).clip(1, 6)
    n = df["n_lines"]
    df["plan_family"] = df["plan_sku"].map(plans["family"])
    df["plan_tier"] = df["plan_sku"].map(plans["tier"])
    df["plan_data_cap_gb"] = df["plan_sku"].map(plans["data_cap_gb"])  # NaN = unlimited
    df["plan_is_unlimited"] = df["plan_data_cap_gb"].isna().astype(int)

    def price(row):
        p = plans.loc[row.plan_sku]
        pr = [int(x) for x in str(p["line_prices"]).split(",") if x]
        k = int(row.n_lines)
        return float(sum(pr[:k]) + max(0, k - len(pr)) * (p["extra_line_cents"] if pd.notna(p["extra_line_cents"]) else pr[-1]))
    df["plan_price_cents"] = [price(r) for r in df[["plan_sku", "n_lines"]].itertuples()]
    # lines / devices / financing
    df["n_byod_lines"] = i("n_byod_lines").clip(0, n)
    owned = n - df["n_byod_lines"]
    for c in ["n_financed_lines", "n_flagship_devices", "n_lines_device_36m_plus"]:
        df[c] = i(c).clip(lower=0).clip(upper=owned)
    df["n_tradein_eligible_lines"] = i("n_tradein_eligible_lines").clip(0, n)
    fin = df["n_financed_lines"] > 0
    for c in FIN_COLS:
        df[c] = np.where(fin, df[c].fillna(0), 0)
    df["max_financing_months_remaining"] = np.where(fin, df["max_financing_months_remaining"].clip(lower=1), 0)
    df["min_financing_months_left_financed"] = np.where(
        fin, np.minimum(df["min_financing_months_left_financed"].clip(lower=1), df["max_financing_months_remaining"]), 0)
    df["financing_ends_within_3m"] = df["min_financing_months_left_financed"].between(1, 3).astype(int)
    dated = owned > 0
    for c in DEV_COLS:
        df[c] = np.where(dated, df[c], np.nan)
    df["mean_device_age_months"] = np.minimum(df["mean_device_age_months"], df["max_device_age_months"])
    df.loc[~dated, "n_lines_device_36m_plus"] = 0
    # usage vs plan
    capped = df["plan_data_cap_gb"].notna()
    df["n_lines_over_cap_3m"] = np.where(capped, i("n_lines_over_cap_3m").clip(0, n), 0)
    df["n_lines_light_on_premium"] = np.where(df["plan_tier"] == "premium", i("n_lines_light_on_premium").clip(0, n), 0)
    df["n_lines_usage_up_30pct"] = i("n_lines_usage_up_30pct").clip(0, n)
    df["plan_misfit_share"] = (df["plan_misfit_share"].clip(0, 1) * n).round() / n
    # billing
    has_prior = df["prior_avg_bill_cents"].notna()
    df["bill_increase_pct"] = np.where(has_prior, df["bill_increase_pct"].clip(lower=0), 0.0)
    up = has_prior & (df["bill_increase_pct"] > 0)
    df.loc[up, "last_bill_cents"] = (df.loc[up, "prior_avg_bill_cents"] * (1 + df.loc[up, "bill_increase_pct"])).round()
    flat = has_prior & ~up
    df.loc[flat, "last_bill_cents"] = np.minimum(df.loc[flat, "last_bill_cents"], df.loc[flat, "prior_avg_bill_cents"])
    # support: topics partition the 90d contacts
    for c in TOPICS:
        df[c] = i(c).clip(lower=0)
    df["support_90d"] = df[TOPICS].sum(axis=1)
    s90 = df["support_90d"]
    df["support_270d"] = np.maximum(i("support_270d"), s90)
    df["unresolved_90d"] = i("unresolved_90d").clip(0, s90)
    df["negative_contacts_90d"] = i("negative_contacts_90d").clip(0, s90)
    df["unresolved_270d"] = np.minimum(np.maximum(i("unresolved_270d"), df["unresolved_90d"]), df["support_270d"])
    df["cancel_inquiries_270d"] = np.maximum(i("cancel_inquiries_270d"), df["cancellation_inquiry_contacts_90d"])
    any270, any90 = df["support_270d"] > 0, s90 > 0
    df["avg_sentiment"] = np.where(any270, df["avg_sentiment"].fillna(0).clip(-1, 1), 0.0)
    df["min_sentiment_270d"] = np.where(any270, np.minimum(df["min_sentiment_270d"].fillna(0), df["avg_sentiment"]), 0.0)
    df["avg_sentiment_90d"] = np.where(any90, df["avg_sentiment_90d"].fillna(0).clip(-1, 1), 0.0)
    d = df["days_since_last_contact"].fillna(999)
    d = np.where(any90, np.clip(d, 0, 90), np.where(any270, np.clip(d, 91, 270), 999))
    df["days_since_last_contact"] = d.astype(int)
    # add-ons / signals
    df["n_account_addons"] = np.maximum(i("n_account_addons"), df["has_home_internet"] + df["has_streaming_addon"])
    df["n_protection_addons"] = i("n_protection_addons").clip(0, owned)
    df["n_line_addons"] = np.maximum(i("n_line_addons"), df["n_protection_addons"] + i("n_connected_lines"))
    df["competitor_research_score"] = df["competitor_research_score"].clip(0, 1)
    return df


def generate(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    real = pd.read_csv(L.FEATURES)
    real = real[real["is_persona"] == 0].reset_index(drop=True)
    cols = list(real.columns)
    if ENRICH.exists():
        e = pd.read_csv(ENRICH)
        real = real.merge(e, on="account_id", how="left")
        cols += [c for c in e.columns if c != "account_id"]
    cop = Copula().fit(real, rng)
    syn = cop.sample(n, rng)
    syn = enforce(syn, load_plans())
    syn["account_id"] = [f"SYN-{k:06d}" for k in range(1, n + 1)]
    syn["is_persona"] = 0
    for c in cols:  # restore integer dtypes
        if pd.api.types.is_integer_dtype(real[c]) and c in syn:
            syn[c] = syn[c].round().astype(int)
    return syn[cols], real[cols], cop


def tstr(syn_f, syn_l, real_f, real_l, target):
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    feats = [c for c in real_f.columns if c not in ("account_id", "is_persona", "plan_sku")]

    def X(df, ref=None):
        d = pd.get_dummies(df[feats], columns=[c for c in feats if df[c].dtype == object or str(df[c].dtype) == "str"
                                               or c in CATEGORICAL + ["plan_family", "plan_tier"]], dtype=float)
        for c in [c for c in d.columns if d[c].isna().any()]:
            d[c + "__na"] = d[c].isna().astype(float)
            d[c] = d[c].fillna(0)
        if ref is not None:
            d = d.reindex(columns=ref, fill_value=0.0)
        return d
    Xs = X(syn_f); Xr = X(real_f, Xs.columns)
    mk = lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, C=0.5))  # noqa: E731
    m = mk().fit(Xs, syn_l[target])
    a_tstr = roc_auc_score(real_l[target], m.predict_proba(Xr)[:, 1])
    cv = StratifiedKFold(5, shuffle=True, random_state=0)
    oof = cross_val_predict(mk(), Xr, real_l[target], cv=cv, method="predict_proba")[:, 1]
    a_trtr = roc_auc_score(real_l[target], oof)
    pcol = "p_true_90d" if target == "churn_90d" else "p_upgrade_90d"
    a_oracle = roc_auc_score(real_l[target], real_l[pcol])
    return a_tstr, a_trtr, a_oracle


def fidelity(syn_f, real_f, syn_l, real_l, cop, n, seed) -> str:
    num = [c for c in real_f.columns if c not in DERIVED and c not in CATEGORICAL and c != "account_id"]
    ks = []
    for c in num + ["plan_price_cents", "support_90d"]:
        a, b = real_f[c].dropna(), syn_f[c].dropna()
        ks.append((c, stats.ks_2samp(a, b).statistic, real_f[c].isna().mean(), syn_f[c].isna().mean()))
    ks = pd.DataFrame(ks, columns=["column", "KS", "blank_real", "blank_syn"]).sort_values("KS", ascending=False)
    tv = []
    for c in CATEGORICAL + ["plan_tier", "plan_family"]:
        p, q = real_f[c].value_counts(normalize=True), syn_f[c].value_counts(normalize=True)
        tv.append((c, 0.5 * p.subtract(q, fill_value=0).abs().sum()))
    numc = [c for c in num + ["plan_price_cents", "support_90d"] if real_f[c].nunique() > 1]
    Cr = real_f[numc].corr(method="spearman").values
    Cs = syn_f[numc].corr(method="spearman").values
    D = np.abs(Cr - Cs)[np.triu_indices(len(numc), 1)]
    pairs = pd.DataFrame([(numc[a], numc[b], Cr[a, b], Cs[a, b]) for a, b in zip(*np.triu_indices(len(numc), 1))],
                         columns=["a", "b", "real", "syn"])
    pairs["diff"] = (pairs.real - pairs.syn).abs()
    worst = pairs.sort_values("diff", ascending=False).head(8)
    res = {t: tstr(syn_f, syn_l, real_f, real_l, t) for t in ["churn_90d", "upgrade_90d"]}
    md = [f"# FIDELITY: {n:,} synthetic accounts generated from the sandbox's distributions",
          "", "> **ALL ROWS, LABELS AND RATES ARE SYNTHETIC.** These are **N synthetic accounts generated from the sandbox's distributions** "
          "(a Gaussian copula fitted to the 5,000 regular sandbox accounts in features.csv). No row is a real or sandbox customer. "
          f"Seed {seed}. Labels: the same `labels.py` recipe (tuned churn + upgrade), with b0s re-solved on the synthetic rows.",
          "", "## Method",
          "- Empirical marginal per column (inverse empirical CDF, so only observed values are produced and integers stay integers). "
          "The dependence comes from the normal-score (rank) correlation matrix with random tie-breaking, projected to the nearest positive-definite matrix.",
          "- Categoricals are ordinal codes, ordered by the category's mean bill (credit tier in its natural order).",
          "- Blanks keep their meaning. Columns that only exist under a condition (financing given a financed line; device age given a non-BYOD line; sentiment and days-since-contact given a contact) are modelled on the rows where they apply and set to their fill value otherwise. Other blanks (prior bill, 3-month bill change) get a missingness indicator inside the copula.",
          "- Constraints: lines within the plan's min/max; BYOD, financed, flagship and 36m+ counts ≤ owned lines; no financing values without a financed line; min months left ≤ max; a blank cap means unlimited (no over-cap lines); 'light on premium' only on premium plans; the five topic counts sum to support_90d; 90d ≤ 270d counts; unresolved and negative ≤ contacts; days since last contact consistent with the contact windows; last bill = prior × (1 + bill_increase_pct). Plan family, tier, cap and price are derived from plan_sku and the sandbox plans table.",
          "", "## Base rates (synthetic)", "", "| | real sandbox 5,000 | scaled synthetic |", "|---|---|---|",
          f"| mean monthly churn hazard | {real_l.monthly_hazard.mean():.4%} | {syn_l.monthly_hazard.mean():.4%} |",
          f"| mean p_true_90d | {real_l.p_true_90d.mean():.3%} | {syn_l.p_true_90d.mean():.3%} |",
          f"| churn_90d drawn | {real_l.churn_90d.mean():.3%} ({real_l.churn_90d.sum()}) | {syn_l.churn_90d.mean():.3%} ({syn_l.churn_90d.sum():,}) |",
          f"| mean p_upgrade_90d | {real_l.p_upgrade_90d.mean():.3%} | {syn_l.p_upgrade_90d.mean():.3%} |",
          f"| upgrade_90d drawn | {real_l.upgrade_90d.mean():.3%} ({real_l.upgrade_90d.sum()}) | {syn_l.upgrade_90d.mean():.3%} ({syn_l.upgrade_90d.sum():,}) |",
          f"| toy_p mean (ranking checks only) | {real_l.toy_p.mean():.3%} | {syn_l.toy_p.mean():.3%} |",
          f"| b0 churn / upgrade | {real_l.attrs.get('b0', float('nan')):.4f} / {real_l.attrs.get('b0_upgrade', float('nan')):.4f} | {syn_l.attrs['b0']:.4f} / {syn_l.attrs['b0_upgrade']:.4f} |",
          "", "## Marginals: two-sample KS statistic (numeric; 0 = identical)",
          f"Median KS {ks.KS.median():.3f}, max {ks.KS.max():.3f} ({ks.iloc[0].column}). Columns with KS > 0.05:", ""]
    md += ["| column | KS | blank real | blank syn |", "|---|---|---|---|"]
    md += [f"| {r.column} | {r.KS:.3f} | {r.blank_real:.1%} | {r.blank_syn:.1%} |" for r in ks[ks.KS > 0.05].itertuples()] or ["| (none) | | | |"]
    md += ["", "Categoricals, total-variation distance: " + ", ".join(f"{c} {v:.3f}" for c, v in tv),
           "", "## Dependence: Spearman correlation matrix, real vs synthetic",
           f"{len(numc)} numeric columns, {len(D):,} pairs. Mean |Δρ| = {D.mean():.3f}, median {np.median(D):.3f}, 95th pct {np.quantile(D, 0.95):.3f}, max {D.max():.3f}. "
           f"Frobenius ‖ΔC‖ / ‖C_real‖ = {np.linalg.norm(Cr - Cs) / np.linalg.norm(Cr):.3f}.", "",
           "Largest pair gaps:", "", "| a | b | ρ real | ρ syn | |Δ| |", "|---|---|---|---|---|"]
    md += [f"| {r.a} | {r.b} | {r.real:+.2f} | {r.syn:+.2f} | {r.diff:.2f} |" for r in worst.itertuples()]
    md += ["", "## Utility: train on synthetic, test on the 5,000 real sandbox accounts (TSTR)",
           "The model is standardized logistic regression on all features.csv columns (one-hot categoricals; blank → 0 plus indicator). "
           "TRTR = 5-fold out-of-fold AUC on the real 5,000. Oracle = AUC of the true synthetic probability on the real labels (ceiling).", "",
           "| target | TSTR AUC (train 50k syn → test 5k real) | TRTR AUC (5-fold on real) | oracle |", "|---|---|---|---|"]
    md += [f"| {t} | {a:.3f} | {b:.3f} | {o:.3f} |" for t, (a, b, o) in res.items()]
    md += ["", "## Caveats",
           "- A Gaussian copula keeps marginals and pairwise rank dependence. It does not keep higher-order interactions or tails conditional on several variables, and it can't create combinations that are rare in the 5,000.",
           "- Labels are recomputed from the synthetic features with the same synthetic recipe, so a TSTR AUC close to TRTR shows the scaled data carries the same feature-label structure. It says nothing about real-world accuracy.",
           "- Personas aren't in the scaled data. Use the real out/labels.csv for persona checks.",
           ]
    return "\n".join(md) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Gaussian-copula scaled synthetic accounts")
    ap.add_argument("--n", type=int, default=50000)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--no-fidelity", action="store_true")
    a = ap.parse_args()
    syn_f, real_f, cop = generate(a.n, a.seed)
    syn_l = L.label_frame(syn_f, "tuned")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    syn_f.to_csv(OUT_DIR / "features_scaled.csv", index=False)
    lab_cols = list(pd.read_csv(L.OUT, nrows=0).columns) if L.OUT.exists() else list(syn_l.columns)
    syn_l[[c for c in lab_cols if c in syn_l]].to_csv(OUT_DIR / "labels_scaled.csv", index=False)
    print(f"wrote {OUT_DIR}/features_scaled.csv + labels_scaled.csv  n={a.n}  "
          f"churn h={syn_l.monthly_hazard.mean():.4%} p90={syn_l.p_true_90d.mean():.3%} upgrade={syn_l.p_upgrade_90d.mean():.3%} [SYNTHETIC]")
    if not a.no_fidelity:
        real_all = pd.read_csv(L.OUT)
        real_l = real_all[real_all["is_persona"] == 0].reset_index(drop=True)
        full = pd.read_csv(L.FEATURES)
        real_l.attrs.update(L.label_frame(full, "tuned").attrs)
        (OUT_DIR / "FIDELITY.md").write_text(fidelity(syn_f, real_f, syn_l, real_l, cop, a.n, a.seed))
        print(f"wrote {OUT_DIR / 'FIDELITY.md'}")


if __name__ == "__main__":
    main()
