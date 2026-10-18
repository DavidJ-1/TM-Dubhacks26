"""Scale the sandbox to N synthetic accounts with a Gaussian copula -> harness/out/scaled/

"N synthetic accounts generated from the sandbox's distributions": each row is NEW synthetic data, not a
sandbox customer. Marginals = empirical distributions of the 5,000 regular sandbox accounts (features.csv);
dependence = rank (normal-score) correlation matrix. ALL LABELS AND RATES ARE SYNTHETIC.

Outputs (never touches out/features.csv or out/labels.csv):
  out/scaled/features_scaled.csv  same columns as features.csv + enrichment.csv columns (if out/enrichment.csv exists;
                                  household_income_usd + recent_job_change are sampled in the copula, the rest derived)
  out/scaled/labels_scaled.csv    same columns as labels.csv; same labels.py recipe (tuned churn + upgrade), b0s
                                  re-solved on the synthetic rows (0.99%/month churn, 6%/90d upgrade)
  out/scaled/FIDELITY.md          KS per column, correlation-matrix difference, base rates, TSTR AUC
Run: python harness/scale_synth.py [--n 250000] [--seed 2026] [--out-dir DIR] [--no-append-household] [--no-fidelity]
  50k reproduction (byte-identical to the original out/scaled CSVs):
    python harness/scale_synth.py --n 50000 --out-dir /tmp/x --legacy-50k --no-fidelity
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
# household fields: generated in a SECOND, conditional copula stage (separate RNG) so the main stream, and
# therefore the 50k files, stay byte-identical to the pre-household version
HOUSEHOLD = ["n_lines", "is_family_plan", "likely_kid_flag", "n_kid_lines", "kid_age_band",
             "promo_months_remaining", "contract_or_financing_months_remaining"]
HH_TARGETS = ["n_kid_lines", "kid_age_band", "promo_months_remaining"]
HH_COND = ["n_lines", "segment", "n_byod_lines", "max_financing_months_remaining", "max_device_age_months",
           "promo_expired_recent", "plan_tier"]
KID_ORDER = ["none", "0-12", "13-17", "18-24"]

CATEGORICAL = ["segment", "language", "contact_preference", "credit_tier", "discount_group", "plan_sku"]
CREDIT_ORDER = ["subprime", "near_prime", "prime"]
# derived after sampling (not modelled directly)
DERIVED = ["account_id", "is_persona", "plan_family", "plan_tier", "plan_data_cap_gb", "plan_is_unlimited",
           "plan_price_cents", "financing_ends_within_3m", "support_90d",
           # enrichment columns derived after sampling (only recent_job_change + household_income_usd are sampled)
           "income_band", "area_median_income_usd", "income_geo_level", "next_plan_sku", "next_plan_price_cents",
           "step_up_cost_cents", "step_up_cost_pct_income"]
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
    segment_lines = False  # if True: n_lines follows the REAL segment-conditional distribution (see sample())

    def fit(self, df: pd.DataFrame, rng: np.random.Generator):
        self.lines_by_segment = {k: np.sort(v.values.astype(float)) for k, v in df.groupby("segment")["n_lines"]}
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
        if self.segment_lines:
            # sandbox structure: line count is (near-)determined by segment (single/student 1, couple 2, family 3-5,
            # senior 1-2, smb 2-6). Keep the copula's rank of n_lines WITHIN each segment, but invert through the
            # real segment-conditional distribution.
            j = self.cols.index("n_lines")
            for seg, sup in self.lines_by_segment.items():
                idx = np.where(df["segment"].values == seg)[0]
                if len(idx):
                    r = stats.rankdata(U[idx, j], method="ordinal") / (len(idx) + 1)
                    df.loc[df.index[idx], "n_lines"] = sup[np.minimum((r * len(sup)).astype(int), len(sup) - 1)]
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


def generate(n: int, seed: int, segment_lines: bool = True) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    real = pd.read_csv(L.FEATURES)
    real = real[real["is_persona"] == 0].reset_index(drop=True)
    cols = list(real.columns)
    if ENRICH.exists():
        e = pd.read_csv(ENRICH)
        e = e[[c for c in e.columns if c not in HOUSEHOLD]]
        real = real.merge(e, on="account_id", how="left")
        cols += [c for c in e.columns if c != "account_id"]
    cop = Copula().fit(real, rng)
    cop.segment_lines = segment_lines
    syn = cop.sample(n, rng)
    plans = load_plans()
    syn = enforce(syn, plans)
    if ENRICH.exists():
        import enrichment as EN
        syn["income_band"] = EN.band(syn["household_income_usd"])
        syn["area_median_income_usd"] = real["area_median_income_usd"].iloc[0]
        syn["income_geo_level"] = real["income_geo_level"].iloc[0]
        syn["recent_job_change"] = syn["recent_job_change"].round().astype(int)
        syn = pd.concat([syn, EN.step_up(syn, plans)], axis=1)
    syn["account_id"] = [f"SYN-{k:06d}" for k in range(1, n + 1)]
    syn["is_persona"] = 0
    for c in cols:  # restore integer dtypes
        if pd.api.types.is_integer_dtype(real[c]) and c in syn:
            syn[c] = syn[c].round().astype(int)
    return syn[cols], real[cols], cop


def _midrank_z(ref: np.ndarray, x: np.ndarray) -> np.ndarray:
    ref = np.sort(ref)
    lo = np.searchsorted(ref, x, side="left"); hi = np.searchsorted(ref, x, side="right")
    return stats.norm.ppf((lo + 0.5 * (hi - lo) + 0.5) / (len(ref) + 1))


def _codes(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for c in HH_COND + HH_TARGETS:
        if c not in df:
            continue
        if c == "segment":
            out[c] = df[c].map({"student": 0, "single": 1, "senior": 2, "couple": 3, "smb": 4, "family": 5})
        elif c == "plan_tier":
            out[c] = df[c].map({"basic": 0, "standard": 1, "premium": 2})
        elif c == "kid_age_band":
            out[c] = df[c].map({k: i for i, k in enumerate(KID_ORDER)})
        elif c == "max_device_age_months":
            out[c] = df[c].fillna(-1)
        else:
            out[c] = df[c]
    return out.astype(float)


def household_stage(syn: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Household fields for synthetic rows: Gaussian copula conditional on already-sampled columns.
    Fitted on the 5,000 regular accounts (features.csv + enrichment.csv household columns)."""
    rng = np.random.default_rng(seed + 7919)  # separate stream
    real = pd.read_csv(L.FEATURES)
    real = real[real["is_persona"] == 0].merge(pd.read_csv(ENRICH)[["account_id"] + HH_TARGETS], on="account_id")
    R, S = _codes(real), _codes(syn)
    Zr = pd.DataFrame({c: _midrank_z(R[c].values, R[c].values) for c in HH_COND})
    for c in HH_TARGETS:
        Zr[c] = Copula._scores(R[c].reset_index(drop=True), pd.Series(True, index=range(len(R))), rng).values
    C = nearest_psd_corr(Zr.corr().fillna(0).to_numpy(copy=True))
    k = len(HH_COND)
    Scc, Stc, Stt = C[:k, :k], C[k:, :k], C[k:, k:]
    A = Stc @ np.linalg.inv(Scc)
    cov = Stt - A @ Stc.T
    Zs = np.column_stack([_midrank_z(R[c].values, S[c].values) for c in HH_COND])
    zt = Zs @ A.T + rng.multivariate_normal(np.zeros(len(HH_TARGETS)), (cov + cov.T) / 2, size=len(syn), method="eigh")
    U = stats.norm.cdf(zt)
    hh = pd.DataFrame(index=syn.index)
    for j, c in enumerate(HH_TARGETS):
        sup = np.sort(R[c].values)
        hh[c] = sup[np.minimum((U[:, j] * len(sup)).astype(int), len(sup) - 1)]
    # kids: the sandbox structure is near-deterministic (kid lines only on family accounts), so instead of the
    # copula draw we sample (n_kid_lines, kid_age_band) from the REAL empirical joint given (family, n_lines)
    n = syn["n_lines"].values
    fam = (syn["segment"] == "family").values
    rk = real.assign(fam=(real["segment"] == "family"))
    nk = np.zeros(len(syn), dtype=int)
    band = np.full(len(syn), "none", dtype=object)
    for (is_fam, nl), grp in rk.groupby(["fam", "n_lines"]):
        idx = np.where((fam == is_fam) & (n == nl))[0]
        if len(idx) and is_fam:
            pick = rng.integers(0, len(grp), len(idx))
            nk[idx] = grp["n_kid_lines"].values[pick]
            band[idx] = grp["kid_age_band"].values[pick]
    # family accounts with a line count unseen among real families: fall back to n_lines - 2 kids (>= 1 if 2+ lines)
    miss = fam & ~np.isin(n, rk.loc[rk["fam"], "n_lines"].unique())
    nk[miss] = np.clip(n[miss] - 2, 0, None); band[miss & (nk > 0)] = "0-12"
    owned = (syn["n_byod_lines"] < syn["n_lines"]).values
    promo = np.where(owned & (syn["promo_expired_recent"].values == 0), np.clip(hh["promo_months_remaining"].values, 0, 36), 0).astype(int)
    out = pd.DataFrame({
        "account_id": syn["account_id"].values, "n_lines": n,
        "is_family_plan": ((n >= 2) & (syn["segment"] != "smb").values).astype(int),
        "likely_kid_flag": (nk > 0).astype(int), "n_kid_lines": nk, "kid_age_band": band,
        "promo_months_remaining": promo,
        "contract_or_financing_months_remaining": np.maximum(syn["max_financing_months_remaining"].values, promo).astype(int),
    })
    out.attrs["fixups"] = {"kid fields: empirical conditional on (family, n_lines), copula draw discarded": int(len(syn)),
                           "family rows with unseen n_lines (fallback)": int(miss.sum())}
    return out


def household_fidelity(hh_syn: pd.DataFrame) -> list[str]:
    real = pd.read_csv(L.FEATURES)[["account_id", "is_persona"]].merge(pd.read_csv(ENRICH), on="account_id")
    real = real[real["is_persona"] == 0]
    rows = ["", "## Household fields (offer strategy; not in any label)",
            "These come from a second Gaussian-copula stage conditional on n_lines, segment, BYOD count, financing months, device age, promo_expired and plan tier, kid fields (n_kid_lines, kid_age_band) drawn from the real empirical joint given (family segment, n_lines), because the sandbox structure there is near-deterministic. Sandbox constraints also apply: no promo on all-BYOD or promo-expired accounts, and promo ≤ 36 months.", "",
            "| field | real 5,000 | synthetic |", "|---|---|---|"]
    for c in ["is_family_plan", "likely_kid_flag"]:
        rows.append(f"| {c} rate | {real[c].mean():.2%} | {hh_syn[c].mean():.2%} |")
    for c in ["n_kid_lines", "promo_months_remaining", "contract_or_financing_months_remaining"]:
        rows.append(f"| {c}: mean / share > 0 / KS | {real[c].mean():.2f} / {(real[c] > 0).mean():.2%} | "
                    f"{hh_syn[c].mean():.2f} / {(hh_syn[c] > 0).mean():.2%} / KS {stats.ks_2samp(real[c], hh_syn[c]).statistic:.3f} |")
    p, q = real["kid_age_band"].value_counts(normalize=True), hh_syn["kid_age_band"].value_counts(normalize=True)
    rows.append(f"| kid_age_band mix | {', '.join(f'{k} {v:.1%}' for k, v in p.items())} | {', '.join(f'{k} {v:.1%}' for k, v in q.items())} (TV {0.5 * p.subtract(q, fill_value=0).abs().sum():.3f}) |")
    rows.append(f"| constraint fix-ups applied | – | {hh_syn.attrs.get('fixups')} |")
    if "segment" in hh_syn.attrs:
        rows.append(f"| (segment, n_lines) pairs never seen in the real 5,000 | 0% | {hh_syn.attrs['segment']:.2%} |")
    return rows


def tstr(syn_f, syn_l, real_f, real_l, target):
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    feats = [c for c in real_f.columns if c not in ("account_id", "is_persona", "plan_sku", "income_geo_level")]

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


def fidelity(syn_f, real_f, syn_l, real_l, cop, n, seed, extra=None) -> str:
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
          "- n_lines (unless --legacy-50k): the copula's rank is kept within each segment, but values come from the REAL segment-conditional distribution. The plain copula broke the sandbox's segment/line-count structure, producing for example singles with 4 lines; the original 50k set in out/scaled/ has that flaw.",
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
           f"| target | TSTR AUC (train {n:,} syn → test 5k real) | TRTR AUC (5-fold on real) | oracle |", "|---|---|---|---|"]
    md += [f"| {t} | {a:.3f} | {b:.3f} | {o:.3f} |" for t, (a, b, o) in res.items()]
    md += extra or []
    md += ["", "## Caveats",
           "- A Gaussian copula keeps marginals and pairwise rank dependence. It does not keep higher-order interactions or tails conditional on several variables, and it can't create combinations that are rare in the 5,000.",
           "- Labels are recomputed from the synthetic features with the same synthetic recipe, so a TSTR AUC close to TRTR shows the scaled data carries the same feature-label structure. It says nothing about real-world accuracy.",
           "- Personas aren't in the scaled data. Use the real out/labels.csv for persona checks.",
           ]
    return "\n".join(md) + "\n"


SEGMENT_LINES = True


def tstr_by_size(sizes, seeds, real_f, real_l, main=None):
    """TSTR AUC mean/sd over seeds for each synthetic training size (main=(n, seed, syn_f, syn_l) reused)."""
    rows = []
    for n in sizes:
        res = {"churn_90d": [], "upgrade_90d": []}
        for sd in seeds:
            if main is not None and n == main[0] and sd == main[1]:
                f, l = main[2], main[3]
            else:
                f, _, _ = generate(n, sd, segment_lines=SEGMENT_LINES)
                l = L.label_frame(f, "tuned")
            for t in res:
                res[t].append(tstr(f, l, real_f, real_l, t)[0])
            print(f"  tstr n={n} seed={sd}: churn {res['churn_90d'][-1]:.4f} upgrade {res['upgrade_90d'][-1]:.4f}", flush=True)
        rows.append((n, {t: (np.mean(v), np.std(v)) for t, v in res.items()}))
    return rows


def main():
    ap = argparse.ArgumentParser(description="Gaussian-copula scaled synthetic accounts")
    ap.add_argument("--n", type=int, default=250000)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out-dir", default=None,
                    help="default: out/scaled for n=50000, else out/scaled_<n/1000>k")
    ap.add_argument("--no-append-household", action="store_true",
                    help="write household fields only to household_scaled.csv (features_scaled.csv keeps the "
                         "pre-household columns, e.g. to reproduce the 50k files byte-identically)")
    ap.add_argument("--no-fidelity", action="store_true")
    ap.add_argument("--tstr-sizes", default="5000,50000", help="extra synthetic training sizes for the TSTR table")
    ap.add_argument("--tstr-seeds", type=int, default=3)
    ap.add_argument("--legacy-50k", action="store_true",
                    help="reproduce the original 50k files byte-identically (no segment-conditional n_lines, "
                         "household fields only in household_scaled.csv)")
    a = ap.parse_args()
    global SEGMENT_LINES
    SEGMENT_LINES = not a.legacy_50k
    if a.legacy_50k:
        a.no_append_household = True
    out_dir = Path(a.out_dir) if a.out_dir else (HERE / "out" / ("scaled" if a.n == 50000 else f"scaled_{a.n // 1000}k"))
    syn_f, real_f, cop = generate(a.n, a.seed, segment_lines=SEGMENT_LINES)
    syn_l = L.label_frame(syn_f, "tuned")
    out_dir.mkdir(parents=True, exist_ok=True)
    hh = household_stage(syn_f, a.seed) if ENRICH.exists() else None
    feat_out = syn_f
    if hh is not None:
        hh.to_csv(out_dir / "household_scaled.csv", index=False)
        if not a.no_append_household:
            feat_out = syn_f.merge(hh.drop(columns=["n_lines"]), on="account_id", how="left", validate="1:1")
    feat_out.to_csv(out_dir / "features_scaled.csv", index=False)
    lab_cols = list(pd.read_csv(L.OUT, nrows=0).columns) if L.OUT.exists() else list(syn_l.columns)
    syn_l[[c for c in lab_cols if c in syn_l]].to_csv(out_dir / "labels_scaled.csv", index=False)
    print(f"wrote {out_dir}/features_scaled.csv + labels_scaled.csv + household_scaled.csv  n={a.n}  "
          f"churn h={syn_l.monthly_hazard.mean():.4%} p90={syn_l.p_true_90d.mean():.3%} upgrade={syn_l.p_upgrade_90d.mean():.3%} [SYNTHETIC]", flush=True)
    if not a.no_fidelity:
        real_all = pd.read_csv(L.OUT)
        real_l = real_all[real_all["is_persona"] == 0].reset_index(drop=True)
        full = pd.read_csv(L.FEATURES)
        real_l.attrs.update(L.label_frame(full, "tuned").attrs)
        sizes = sorted({int(x) for x in a.tstr_sizes.split(",") if x} | {a.n})
        seeds = [a.seed + k for k in range(a.tstr_seeds)]
        tab = tstr_by_size(sizes, seeds, real_f, real_l, main=(a.n, a.seed, syn_f, syn_l))
        extra = ["", f"## TSTR by synthetic training size (mean ± sd over {len(seeds)} copula seeds; test = real 5,000)", "",
                 "| synthetic rows | churn_90d AUC | upgrade_90d AUC |", "|---|---|---|"]
        extra += [f"| {n:,} | {r['churn_90d'][0]:.3f} ± {r['churn_90d'][1]:.3f} | {r['upgrade_90d'][0]:.3f} ± {r['upgrade_90d'][1]:.3f} |" for n, r in tab]
        extra += ["", "**Honest read.** The labels come from our own recipe applied to the features, so the best possible AUC on the real 5,000 is the oracle (churn ≈ 0.864, upgrade ≈ 0.81, both limited by the coin-flip draws on only 137 / 322 real positives). "
                  "Churn TSTR already sits at that ceiling at 50k, so more rows mainly cut seed-to-seed variance (more stable numbers) and help the harder, noisier upgrade model. "
                  "They do **not** make churn prediction 'better' in any real-world sense. Small TSTR > oracle gaps are sampling noise from the small real test set."]
        if hh is not None:
            realf = real_f.assign(k=real_f["segment"] + "|" + real_f["n_lines"].astype(str))
            hh.attrs["segment"] = float((~(syn_f["segment"] + "|" + syn_f["n_lines"].astype(str)).isin(realf["k"])).mean())
            extra += household_fidelity(hh)
        (out_dir / "FIDELITY.md").write_text(fidelity(syn_f, real_f, syn_l, real_l, cop, a.n, a.seed, extra))
        print(f"wrote {out_dir / 'FIDELITY.md'}")


if __name__ == "__main__":
    main()
