"""Model-agnostic churn + upgrade harness (Model A lane helpers, Model C hooks).  ALL DATA AND NUMBERS ARE SYNTHETIC / SIMULATED.

Public surface (everything is importable from this module):

    class ChurnModel                      name; fit(X, y) -> self; predict_proba(X) -> np.ndarray P(churn_90d), shape (n,)
                                          explain(X, k=3) -> DataFrame[account_id, risk_reason_1..k, stay_reason_1..k]
                                          (default explain = perturbation, so models may skip it)
    register_model(name, factory)         factory() -> ChurnModel; get_model(name); list_models()
    load_data(label=None)                 -> (X, y, meta); regular (non-persona) accounts only
    load_personas()                       -> (X, meta) for the 42 ACC-PERSONA-xx accounts (persona_check only)
    holdout_split(X, y, meta, test_size=0.25, seed=42)
                                          stratified ACCOUNT-LEVEL holdout (the data is ONE snapshot, as of 2026-10-01;
                                          there is no time dimension, so this is not a temporal split)
    cv_folds(X, y, k=5, seed=42)          stratified k-fold index pairs
    evaluate(model, label=None)           -> dict(auc, pr_auc, brier, calibration_bins, top10_recall, top10_lift, cv, ...)
    backtest(models=None, label=None)     -> DataFrame, every model side by side with the '3+ support calls in 90d'
                                          rule and the oracle (true synthetic probability)
    persona_check(model, label=None)      -> DataFrame pass/fail (PROVISIONAL)
    score_accounts(model, label=None)     -> DataFrame in the tm-churn contract columns
    near_or_over_data_cap(features=None) -> 'near or over data cap' upgrade baseline rule (features only)
    target='churn'|'upgrade'              on load_data/evaluate/backtest/persona_check/score_accounts
                                          (churn: churn_90d|toy_churn, rule_support3; upgrade: upgrade_90d,
                                          rule_near_or_over_data_cap, oracle p_upgrade_90d)
    Model C (uplift) hooks re-exported from uplift_eval.py: UpliftModel, TLearner, register_uplift_model,
    load_uplift, uplift_curve/qini_curve/auuc/qini_coefficient, action_curves, policy_value, compare_policies,
    simulate_uplift_frame, load_orange_belgium

CLI (from repo root):
    python harness/model_harness.py --all              # churn (churn_90d + toy_churn) + upgrade + uplift
    python harness/model_harness.py --target upgrade   # one target, every model registered for it
    python harness/model_harness.py --model logreg     # one model (churn by default)
    python harness/model_harness.py --uplift           # Model C only
    (python -m harness.model_harness ... also works, but imports the console package __init__.)
Outputs go to harness/out/ (gitignored): eval_<target>_<model>[_<label>].json, summary_<target>_<model>[...].txt,
harness_scores_<target>_<model>.csv, backtest_<target>_<label>.csv/.md, persona_check_<target>_<label>.csv,
harness_near_or_over_data_cap.csv, uplift_eval_summary.json/.md.

Stateless: features.csv and labels.csv are re-read on every call (labels may be regenerated). Nothing is cached.
Label column: CONFIG["label"] (default "churn_90d"); switch to "toy_churn" via --label, env MH_LABEL, or label=.

CAVEAT: churn_90d labels are drawn from a known logistic formula over these same features (harness/labels.py),
so high AUCs here test the PIPELINE, not real-world accuracy.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Single-threaded BLAS/OpenMP by default: the box is shared by several agents and HistGradientBoosting slows
# down badly when its OpenMP threads compete. Must be set before numpy/sklearn are imported. Override via env.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent


def _default_data_dir() -> str:
    """harness/out/ if the pipeline has been run here, else the tracked demo_data/ copies (fresh clone), else out/."""
    out, demo = HERE / "out", HERE.parent / "demo_data"
    if not (out / "features.csv").exists() and (demo / "features.csv").exists():
        return str(demo)
    return str(out)


CONFIG = {
    "data_dir": os.environ.get("MH_DATA_DIR") or _default_data_dir(),
    "out_dir": os.environ.get("MH_OUT_DIR", str(HERE / "out")),
    "label": os.environ.get("MH_LABEL", "churn_90d"),   # switch to "toy_churn" in one change
    "data": os.environ.get("MH_DATA", "real"),           # "real" (5,042 sandbox accounts) | "scaled" (50k SYN-*)
    "include_enrichment": False,     # enrichment columns (income, job change, next-plan price) kept OUT of X
    "test_size": 0.25,
    "seed": 42,
    "cv_k": 5,
    "top_frac": 0.10,
    "rule_threshold": 3,             # '3+ support calls in 90d'
    "persona_high_pct": 90.0,        # persona 'high' = top 10%: at/above the 90th percentile of regular accounts
                                     # (per David, 2026-10-17). Personas 21/22 are borderline by label design.
    "persona_low_pct": 50.0,         # persona 'low'  = scores at/below the median of regular accounts
}

CAVEAT = ("CAVEAT: all numbers are SYNTHETIC/SIMULATED. Labels are drawn from a known formula over these same "
          "features, so this tests the pipeline, not real-world accuracy.")

# label -> its oracle (true synthetic probability) column. The oracle column is optional at load time.
LABEL_CHOICES = {"churn_90d": "p_true_90d", "toy_churn": "toy_p", "upgrade_90d": "p_upgrade_90d"}
LABEL_TARGET = {"churn_90d": "churn", "toy_churn": "churn", "upgrade_90d": "upgrade"}
TARGETS = {
    "churn": {"default_label": "churn_90d", "labels": ["churn_90d", "toy_churn"], "rule": "rule_support3",
              "prob_col": "p_churn_90d", "rank_col": "risk_rank",
              "personas": {"ACC-PERSONA-04": "high", "ACC-PERSONA-21": "high", "ACC-PERSONA-22": "high",
                           "ACC-PERSONA-27": "high", "ACC-PERSONA-10": "low", "ACC-PERSONA-24": "low"}},
    "upgrade": {"default_label": "upgrade_90d", "labels": ["upgrade_90d"], "rule": "rule_near_or_over_data_cap",
                "prob_col": "p_upgrade_90d", "rank_col": "upgrade_rank",
                "personas": {"ACC-PERSONA-25": "high", "ACC-PERSONA-28": "high", "ACC-PERSONA-22": "low",
                             "ACC-PERSONA-24": "low", "ACC-PERSONA-27": "low"}},
}


def resolve_label(label: Optional[str] = None, target: Optional[str] = None) -> str:
    """label wins; else the target's default label; else CONFIG['label'] (env MH_LABEL)."""
    if label:
        return label
    if target:
        if target not in TARGETS:
            raise HarnessDataError(f"target must be one of {list(TARGETS)}, got {target!r}")
        return TARGETS[target]["default_label"]
    return CONFIG["label"]


def target_of(label: str) -> str:
    return LABEL_TARGET.get(label, "churn")
REQUIRED_FEATURE_COLS = ["account_id", "is_persona", "support_90d", "tenure_months", "competitor_research_score",
                         "port_out_inquiry", "app_sessions_30d", "bill_increase_pct"]
REQUIRED_LABEL_COLS = ["account_id"]   # + the chosen label column (checked at load time)
# Anything derived from the label pipeline must never reach X.
LEAKY_COLS = {"churn_90d", "p_true_90d", "monthly_hazard", "toy_p", "toy_churn",
              "label_driver_1", "label_driver_2", "label_driver_3", "churn_90d_x", "churn_90d_y",
              "upgrade_90d", "p_upgrade_90d", "upgrade_driver_1", "upgrade_driver_2", "upgrade_driver_3"}
CATEGORICAL = ["segment", "language", "contact_preference", "credit_tier", "discount_group",
               "plan_sku", "plan_family", "plan_tier"]
PERSONA_EXPECT = TARGETS["churn"]["personas"]   # back-compat alias (churn target)


# dataset -> (features file, labels file), relative to CONFIG["data_dir"]
DATASETS = {"real": ("features.csv", "labels.csv"),
            "scaled": ("scaled/features_scaled.csv", "scaled/labels_scaled.csv")}
# Enrichment columns (tm-data's out/enrichment.csv + the scaled set): excluded from X by default so inputs match
# Model A; include with include_enrichment=True / --include-enrichment.
ENRICHMENT_COLS = {"recent_job_change", "household_income_usd", "income_band", "area_median_income_usd",
                   "income_geo_level", "next_plan_sku", "next_plan_price_cents", "step_up_cost_cents",
                   "step_up_cost_pct_income"}


# Base features.csv columns that tm-data also repeats in enrichment.csv (as join context). They are ordinary
# sandbox features, NOT enrichment, so the enrichment exclusion must never drop them (dropping n_lines removed
# tm-churn's extra_lines and made harness model_a differ from churn_model.py, 2026-10-17).
ENRICHMENT_BASE_OVERLAP = {"n_lines", "is_persona"}


def enrichment_columns() -> set:
    cols = set(ENRICHMENT_COLS)
    p = Path(CONFIG["data_dir"]) / "enrichment.csv"
    if p.exists():
        cols |= set(pd.read_csv(p, nrows=0).columns) - {"account_id"}
    return cols - ENRICHMENT_BASE_OVERLAP


class HarnessDataError(ValueError):
    """Raised when inputs are missing or malformed (clear message, no silent fixes)."""


# --------------------------------------------------------------------------------------------- feature prep
def _fallback_prepare(f: pd.DataFrame) -> pd.DataFrame:
    """Minimal model-ready matrix, used only if harness/churn_features.py (tm-churn) is absent or fails.
    Same blank semantics as tm-churn: blank device age = BYOD, blank data cap = unlimited."""
    df = f.drop(columns=[c for c in ("account_id", "is_persona") if c in f.columns]).copy()
    if "max_device_age_months" in df:
        df["is_byod"] = df["max_device_age_months"].isna().astype(int)
    if "plan_data_cap_gb" in df:
        df["is_unlimited"] = df["plan_data_cap_gb"].isna().astype(int)
    if "bill_change_3m_pct" in df:
        df["short_history"] = df["bill_change_3m_pct"].isna().astype(int)
    return df


def _churn_features_prepare() -> Tuple[Callable[[pd.DataFrame], pd.DataFrame], str]:
    for mod in ("harness.churn_features", "churn_features"):
        try:
            m = __import__(mod, fromlist=["prepare"])
            if hasattr(m, "prepare"):
                return m.prepare, mod
        except Exception:  # noqa: BLE001  (missing or broken -> fallback, reported in outputs)
            continue
    return _fallback_prepare, "model_harness._fallback_prepare"


def prepare_features(features: pd.DataFrame) -> Tuple[pd.DataFrame, str]:
    """features.csv rows -> numeric model matrix indexed by account_id. Returns (X, prep_source)."""
    prep, src = _churn_features_prepare()
    ids = features["account_id"].values
    try:
        X = prep(features.copy())
    except Exception as e:  # noqa: BLE001
        print(f"[model_harness] {src}.prepare failed ({e}); using fallback", file=sys.stderr)
        X, src = _fallback_prepare(features.copy()), "model_harness._fallback_prepare"
    X = X.drop(columns=[c for c in ("account_id", "is_persona") if c in X.columns])
    obj = [c for c in X.columns if X[c].dtype == object or str(X[c].dtype) in ("category", "string", "str")]
    if obj:
        X = pd.get_dummies(X, columns=obj, prefix_sep="=", dtype=int)
    X = X.apply(pd.to_numeric, errors="coerce").astype(float)
    X = X.fillna(0.0)
    X.index = pd.Index(ids, name="account_id")
    bad = LEAKY_COLS.intersection(X.columns)
    if bad:
        raise HarnessDataError(f"label-derived columns leaked into features: {sorted(bad)}")
    return X, src


# --------------------------------------------------------------------------------------------- data loading
def _read_csv(path: Path, required: List[str], what: str) -> pd.DataFrame:
    if not path.exists():
        raise HarnessDataError(f"{what} not found at {path}. Run the tm-data lane first "
                               f"(python harness/features.py && python harness/labels.py).")
    df = pd.read_csv(path)
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise HarnessDataError(f"{what} at {path} is missing required columns {missing}; has {list(df.columns)}")
    if df["account_id"].duplicated().any():
        dup = df.loc[df["account_id"].duplicated(), "account_id"].head(5).tolist()
        raise HarnessDataError(f"{what} has duplicate account_id values, e.g. {dup}")
    return df


def _load_joined(label: Optional[str] = None, data_dir: Optional[str] = None, target: Optional[str] = None,
                 data: Optional[str] = None, include_enrichment: Optional[bool] = None):
    label = resolve_label(label, target)
    if label not in LABEL_CHOICES:
        raise HarnessDataError(f"label must be one of {list(LABEL_CHOICES)}, got {label!r}")
    data = data or CONFIG["data"]
    if data not in DATASETS:
        raise HarnessDataError(f"data must be one of {list(DATASETS)}, got {data!r}")
    d = Path(data_dir or CONFIG["data_dir"])
    ff, lf = DATASETS[data]
    f = _read_csv(d / ff, REQUIRED_FEATURE_COLS, ff)
    lab = _read_csv(d / lf, REQUIRED_LABEL_COLS + [label], lf)   # always re-read, never cached
    inc = CONFIG["include_enrichment"] if include_enrichment is None else include_enrichment
    if not inc:
        f = f.drop(columns=[c for c in enrichment_columns() if c in f.columns])
    only_f = set(f.account_id) - set(lab.account_id)
    only_l = set(lab.account_id) - set(f.account_id)
    if only_f or only_l:
        raise HarnessDataError(f"features/labels account_id mismatch: {len(only_f)} only in features "
                               f"(e.g. {sorted(only_f)[:3]}), {len(only_l)} only in labels (e.g. {sorted(only_l)[:3]})")
    vals = set(pd.unique(lab[label].dropna()))
    if not vals <= {0, 1}:
        raise HarnessDataError(f"label column {label!r} must be 0/1, found values {sorted(vals)[:10]}")
    # leak guard: EVERY labels.csv column (except account_id) is barred from the features, whatever tm-data adds
    barred = (set(lab.columns) | LEAKY_COLS) - {"account_id"}
    f = f.drop(columns=[c for c in f.columns if c in barred and c != "is_persona"])
    f = f.sort_values("account_id").reset_index(drop=True)
    lab = lab.set_index("account_id").loc[f["account_id"]]
    X, src = prepare_features(f)
    nan = np.full(len(f), np.nan)
    oc = LABEL_CHOICES[label]
    meta = pd.DataFrame({
        "is_persona": f["is_persona"].astype(int).values,
        "support_90d": f["support_90d"].values,
        "oracle_p": lab[oc].values if oc in lab.columns else nan,   # NaN -> oracle metrics reported as n/a
        "p_true_90d": lab["p_true_90d"].values if "p_true_90d" in lab.columns else nan,
        "toy_p": lab["toy_p"].values if "toy_p" in lab.columns else nan,
        "p_upgrade_90d": lab["p_upgrade_90d"].values if "p_upgrade_90d" in lab.columns else nan,
        "label": label,
        "target": target_of(label),
        "prep_source": src,
        "data": data,
    }, index=X.index)
    y = lab[label].astype(float).rename(label)
    y.index = X.index
    return X, y, meta


def load_data(label: Optional[str] = None, data_dir: Optional[str] = None, target: Optional[str] = None,
              data: Optional[str] = None, include_enrichment: Optional[bool] = None):
    """-> (X, y, meta) for the 5,000 regular accounts (personas excluded). X index = account_id.
    target='churn' (label churn_90d | toy_churn) or 'upgrade' (label upgrade_90d); label wins if both given.
    meta: is_persona, support_90d, oracle_p (true synthetic prob for the chosen label, NaN if absent), label, target."""
    X, y, meta = _load_joined(label, data_dir, target, data, include_enrichment)
    reg = meta["is_persona"] == 0
    X, y, meta = X[reg], y[reg], meta[reg]
    if y.isna().any():
        raise HarnessDataError(f"{int(y.isna().sum())} regular accounts have a blank label")
    return X, y.astype(int), meta


def load_personas(label: Optional[str] = None, data_dir: Optional[str] = None, target: Optional[str] = None):
    """Personas always come from the real sandbox file (the scaled set has none)."""
    X, _, meta = _load_joined(label, data_dir, target, data="real")
    p = meta["is_persona"] == 1
    return X[p], meta[p]


# --------------------------------------------------------------------------------------------- splits
def holdout_split(X, y, meta=None, test_size: Optional[float] = None, seed: Optional[int] = None):
    """Stratified ACCOUNT-LEVEL holdout. Every account lands in exactly one side; personas are rejected.
    NOTE: one snapshot (as of 2026-10-01), no time dimension, so this is NOT a temporal/out-of-time split."""
    test_size = CONFIG["test_size"] if test_size is None else test_size
    seed = CONFIG["seed"] if seed is None else seed
    if meta is not None and (meta.loc[X.index, "is_persona"] == 1).any():
        raise HarnessDataError("persona accounts must not be in train/test; use load_data()")
    tr, te = train_test_split(np.arange(len(X)), test_size=test_size, random_state=seed, stratify=y.values)
    out = [X.iloc[tr], X.iloc[te], y.iloc[tr], y.iloc[te]]
    if meta is not None:
        out += [meta.iloc[tr], meta.iloc[te]]
    return tuple(out)


def cv_folds(X, y, k: Optional[int] = None, seed: Optional[int] = None):
    """Stratified k-fold -> list of (train_idx, test_idx) positional arrays (few positives, so prefer CV)."""
    k = k or CONFIG["cv_k"]
    seed = CONFIG["seed"] if seed is None else seed
    return list(StratifiedKFold(n_splits=k, shuffle=True, random_state=seed).split(np.zeros(len(y)), y.values))


# --------------------------------------------------------------------------------------------- metrics
def top_frac_recall(y_true, score, frac: float = 0.10) -> float:
    """Share of positives caught in the top `frac` of scores. Ties at the cutoff are shared proportionally
    (expected value under random tie-breaking), so binary rules are not flattered or punished by sort order."""
    y_true, score = np.asarray(y_true, float), np.asarray(score, float)
    n, pos = len(y_true), y_true.sum()
    if pos == 0:
        return float("nan")
    k = int(round(frac * n))
    if k <= 0:
        return 0.0
    thr = np.sort(score)[::-1][k - 1]
    above = score > thr
    at = score == thr
    slots = k - above.sum()
    caught = y_true[above].sum() + (y_true[at].sum() * slots / at.sum() if at.sum() else 0.0)
    return float(caught / pos)


def calibration_bins(y_true, p, n_bins: int = 10) -> List[dict]:
    """Quantile reliability bins: mean predicted vs observed rate."""
    y_true, p = np.asarray(y_true, float), np.asarray(p, float)
    order = np.argsort(p, kind="mergesort")
    bins = []
    for i, idx in enumerate(np.array_split(order, n_bins)):
        if len(idx) == 0:
            continue
        bins.append({"bin": i + 1, "n": int(len(idx)), "mean_pred": float(p[idx].mean()),
                     "observed_rate": float(y_true[idx].mean()), "p_min": float(p[idx].min()),
                     "p_max": float(p[idx].max())})
    return bins


def compute_metrics(y_true, p, oracle_p=None, frac: Optional[float] = None) -> dict:
    frac = CONFIG["top_frac"] if frac is None else frac
    y_true, p = np.asarray(y_true, float), np.asarray(p, float)
    two = len(np.unique(y_true)) == 2
    bins = calibration_bins(y_true, p)
    ece = sum(b["n"] * abs(b["mean_pred"] - b["observed_rate"]) for b in bins) / len(y_true)
    rec = top_frac_recall(y_true, p, frac)
    m = {
        "n": int(len(y_true)), "positives": int(y_true.sum()), "base_rate": float(y_true.mean()),
        "auc": float(roc_auc_score(y_true, p)) if two else float("nan"),
        "pr_auc": float(average_precision_score(y_true, p)) if two else float("nan"),
        "brier": float(brier_score_loss(y_true, p)),
        "ece": float(ece), "mean_pred": float(p.mean()),
        "calibration_bins": bins,
        "top10_recall": rec, "top10_lift": float(rec / frac) if rec == rec else float("nan"),
    }
    if oracle_p is not None and not np.isnan(np.asarray(oracle_p, float)).all():
        o = np.asarray(oracle_p, float)
        m["mae_vs_true_p"] = float(np.abs(p - o).mean())      # calibration check against the true synthetic prob
        m["spearman_vs_true_p"] = float(pd.Series(p).corr(pd.Series(o), method="spearman"))
    return m


# --------------------------------------------------------------------------------------------- reason codes
# feature -> (risk sentence, stay sentence); {v} = the account's value. Unknown features get a generic sentence.
REASONS: Dict[str, Tuple[str, str]] = {
    "support_90d": ("{v:.0f} support contacts in the last 90 days", "Few or no support contacts lately ({v:.0f} in 90 days)"),
    "unresolved_90d": ("{v:.0f} unresolved support issues in the last 90 days", "No unresolved support issues"),
    "unresolved_270d": ("{v:.0f} unresolved support issues in the last 9 months", "Support issues get resolved"),
    "negative_contacts_90d": ("{v:.0f} unhappy support conversations in the last 90 days", "No unhappy support conversations lately"),
    "avg_sentiment": ("Support conversations have been negative overall", "Support conversations have been positive"),
    "avg_sentiment_90d": ("Recent support conversations were negative", "Recent support conversations were positive"),
    "min_sentiment_270d": ("Had at least one very angry support contact", "No angry support contacts"),
    "support_270d": ("{v:.0f} support contacts in the last 9 months", "Rarely needs support"),
    "days_since_last_contact": ("Contacted support recently", "No recent support contact"),
    "competitor_research_score": ("Shopping around: competitor research score {v:.2f}", "Not shopping other carriers"),
    "port_out_inquiry": ("Asked about porting their number away", "Has not asked about leaving"),
    "cancel_inquiries_270d": ("Asked about cancelling ({v:.0f} times)", "Never asked about cancelling"),
    "cancellation_inquiry_contacts_90d": ("Asked about cancelling recently", "No recent cancellation questions"),
    "bill_increase_pct": ("Bill went up {v:.0%} vs their usual", "Bill is steady"),
    "bill_change_3m_pct": ("Bill rose over the last 3 months", "Bill has not risen recently"),
    "promo_expired_recent": ("A promotion just expired", "No promotion expired recently"),
    "billing_contacts_90d": ("{v:.0f} billing questions in the last 90 days", "No billing complaints"),
    "network_contacts_90d": ("{v:.0f} network complaints in the last 90 days", "No network complaints"),
    "device_contacts_90d": ("{v:.0f} device issues in the last 90 days", "No device issues"),
    "plan_change_contacts_90d": ("Asked about changing plans recently", "No plan-change requests"),
    "tenure_months": ("Fairly new customer ({v:.0f} months)", "Long-time customer ({v:.0f} months)"),
    "app_sessions_30d": ("Rarely uses the T-Life app ({v:.0f} sessions in 30 days)", "Active T-Life app user ({v:.0f} sessions in 30 days)"),
    "plan_misfit_share": ("Plan does not fit their usage", "Plan fits their usage"),
    "n_financed_lines": ("No phones on a payment plan (nothing ties them)", "{v:.0f} phones still on a payment plan"),
    "financing_balance_total_cents": ("Little left owed on phones", "Still paying off phones"),
    "max_financing_months_remaining": ("Phone payments ending soon", "Several months of phone payments left"),
    "n_lines": ("Single or few lines", "{v:.0f} lines on the account"),
    "autopay": ("Not on AutoPay", "On AutoPay"),
    "max_device_age_months": ("Oldest phone is {v:.0f} months old", "Phones are fairly new"),
    "mean_device_age_months": ("Phones are getting old", "Phones are fairly new"),
    "has_home_internet": ("No Home Internet bundle", "Has Home Internet bundled"),
    "last_bill_cents": ("High monthly bill", "Moderate monthly bill"),
}


def _raw_features(ids) -> pd.DataFrame:
    """Raw features.csv rows for these account_ids (re-read each call; empty frame if unavailable)."""
    path = Path(CONFIG["data_dir"]) / DATASETS["real"][0]
    if not path.exists():
        return pd.DataFrame(index=pd.Index(ids, name="account_id"))
    f = pd.read_csv(path).set_index("account_id")
    out = f.reindex(ids)
    miss = ~pd.Index(ids).isin(f.index)
    sp = Path(CONFIG["data_dir"]) / DATASETS["scaled"][0]
    if miss.any() and sp.exists():
        g = pd.read_csv(sp).set_index("account_id")
        out = out.combine_first(g.reindex(ids)[out.columns.intersection(g.columns)])
    return out


def raw_column(X: pd.DataFrame, col: str) -> np.ndarray:
    """A raw features.csv column aligned to X: from X if present (e.g. toy/test data), else looked up by
    account_id. Lets baselines like the support-calls rule use fields the model-ready prep drops."""
    if col in X.columns:
        return X[col].to_numpy(dtype=float)
    raw = _raw_features(X.index)
    if col not in raw.columns or raw[col].isna().all():
        raise HarnessDataError(f"column {col!r} not in X and not found in features.csv for these accounts")
    return raw[col].fillna(0).to_numpy(dtype=float)


def _cf_text():
    for mod in ("harness.churn_features", "churn_features"):
        try:
            m = __import__(mod, fromlist=["phrase"])
            if hasattr(m, "phrase") and hasattr(m, "reason_group"):
                return m
        except Exception:  # noqa: BLE001
            continue
    return None


def _group_of(col: str) -> str:
    return col.split("=", 1)[0]


def _sentence(group: str, direction: str, raw: dict) -> str:
    v = raw.get(group, np.nan)
    if group in REASONS:
        tpl = REASONS[group][0 if direction == "risk" else 1]
        try:
            return tpl.format(v=float(v)) if "{v" in tpl else tpl
        except (TypeError, ValueError):
            return tpl.split("{")[0].strip()
    label = group.replace("_", " ")
    cat = raw.get(group + "__cat")
    if cat is not None:
        return f"{label}: {cat} ({'raises' if direction == 'risk' else 'lowers'} risk)"
    return f"{label} {'raises' if direction == 'risk' else 'lowers'} risk"


def _reference_row(X: pd.DataFrame) -> pd.Series:
    """Typical account: median for numeric columns, the most common category for one-hot groups."""
    ref = X.median()
    for g in {_group_of(c) for c in X.columns if "=" in c}:
        cols = [c for c in X.columns if _group_of(c) == g]
        top = X[cols].sum().idxmax()
        ref[cols] = 0.0
        ref[top] = 1.0
    return ref


def _money(v) -> str:
    return f"${float(v) / 100:,.0f}"


def _n(v) -> int:
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return 0


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


# Upgrade-target phrases: feature -> f(value, up) -> short customer-card sentence. "up" = this pushes the
# upgrade likelihood UP (listed under reasons for), else DOWN (reasons against). Value-aware, never raw names.
_CATEGORY_TEXT = {
    "segment": {"family": "Family account", "couple": "Couple's account", "single": "Single-person account",
                "senior": "Senior account", "student": "Student account", "smb": "Small-business account"},
    "contact_preference": {"app": "Prefers the T-Life app", "sms": "Prefers texts", "email": "Prefers email",
                           "call": "Prefers phone calls"},
    "discount_group": {"none": "No special discount", "55_plus": "On a 55+ discount", "community": "On a community discount",
                       "partner": "On a partner (employer) discount", "student": "On a student discount"},
    "plan_family": {"essentials": "On an Essentials plan", "experience_more": "On an Experience More plan",
                    "experience_beyond": "On an Experience Beyond plan"},
    "plan_tier": {"basic": "On a basic-tier plan", "standard": "On a standard-tier plan", "premium": "On a premium plan"},
    "language": {"en": "English speaker", "es": "Spanish speaker", "other": "Prefers another language"},
    "credit_tier": {"prime": "Prime credit", "near_prime": "Near-prime credit", "subprime": "Subprime credit"},
    "income_band": {},
    "income_geo_level": {},
}

UPGRADE_PHRASES: Dict[str, Callable[[float, bool], str]] = {
    # data use vs cap
    "data_cap_use": lambda v, up: "Uses most of their data cap each month" if up else "Has plenty of data headroom",
    "n_lines_over_cap_3m": lambda v, up: ("A line went over its data cap recently" if _n(v) else "No line has hit its data cap"),
    "plan_misfit_share": lambda v, up: ("Current plan does not match how they use it" if float(v) > 0 else "Current plan matches their usage"),
    "data_gb_3m_avg": lambda v, up: (f"Heavy data user (about {_n(v)} GB a month)" if up else f"Light data user (about {_n(v)} GB a month)"),
    "data_growth_pct": lambda v, up: ("Data use is growing fast" if float(v) > 0.1 else ("Data use is flat" if float(v) > -0.1 else "Data use is falling")),
    "n_lines_usage_up_30pct": lambda v, up: (f"{_plural(_n(v), 'line')} using 30% more data than before" if _n(v) else "No line's usage is growing fast"),
    "hotspot_gb_3m_avg": lambda v, up: ("Relies on hotspot data" if float(v) >= 1 else "Rarely uses hotspot"),
    "streaming_hours_3m_avg": lambda v, up: ("Streams a lot of video" if up else "Streams little video"),
    "voice_min_3m_avg": lambda v, up: ("Talks a lot on the phone" if up else "Makes few calls"),
    "n_lines_light_on_premium": lambda v, up: ("Pays for a premium plan they barely use" if _n(v) else "Not overpaying for a premium plan"),
    "is_unlimited": lambda v, up: ("Already on an unlimited plan" if _n(v) else "On a plan with a data cap"),
    "plan_is_unlimited": lambda v, up: ("Already on an unlimited plan" if _n(v) else "On a plan with a data cap"),
    "plan_data_cap_gb": lambda v, up: "Plan has a data cap",
    "plan_price_cents": lambda v, up: (f"Plan costs {_money(v)} a month"),
    # devices / financing / trade-in
    "max_device_age_months": lambda v, up: (f"Oldest phone is {_n(v) // 12} years old" if _n(v) >= 24 else
                                            (f"Oldest phone is {_n(v)} months old" if _n(v) else "Phones are new")),
    "mean_device_age_months": lambda v, up: ("Phones are getting old" if _n(v) >= 24 else "Phones are fairly new"),
    "n_lines_device_36m_plus": lambda v, up: (f"{_plural(_n(v), 'phone')} over 3 years old" if _n(v) else "No phones over 3 years old"),
    "n_tradein_eligible_lines": lambda v, up: (f"{_plural(_n(v), 'phone')} eligible for trade-in" if _n(v) else "No phones eligible for trade-in"),
    "n_flagship_devices": lambda v, up: (f"Owns {_plural(_n(v), 'flagship phone')}" if _n(v) else "No flagship phones"),
    "is_byod": lambda v, up: ("Brought their own phone" if _n(v) else "Bought their phone from T-Mobile"),
    "n_byod_lines": lambda v, up: (f"{_plural(_n(v), 'line')} on their own phone" if _n(v) else "All phones bought from T-Mobile"),
    "no_financing": lambda v, up: ("No phone payments left" if _n(v) else "Still paying off a phone"),
    "n_financed_lines": lambda v, up: (f"Paying off {_plural(_n(v), 'phone')}" if _n(v) else "No phones on a payment plan"),
    "financing_balance_total_cents": lambda v, up: (f"Still owes {_money(v)} on phones" if float(v) > 0 else "Phones fully paid off"),
    "monthly_installment_total_cents": lambda v, up: (f"Pays {_money(v)} a month for phones" if float(v) > 0 else "No monthly phone payments"),
    "max_financing_months_remaining": lambda v, up: (f"Phone payments run {_n(v)} more months" if _n(v) else "No phone payments left"),
    "min_financing_months_left_financed": lambda v, up: (f"Next phone payoff in {_n(v)} months" if _n(v) else "No phone payoff coming up"),
    "financing_ends_within_3m": lambda v, up: ("Phone will be paid off within 3 months" if _n(v) else "No phone payoff in the next 3 months"),
    "installment_ended_recent": lambda v, up: ("Just paid off a phone" if _n(v) else "No phone paid off recently"),
    "new_installment_recent": lambda v, up: ("Just started paying for a new phone" if _n(v) else "No new phone recently"),
    # bill / affordability
    "bill_increase_pct": lambda v, up: (("Recent bill jump makes an upgrade unlikely" if not up else "Bill jumped recently")
                                        if float(v) >= 0.10 else
                                        ("Bill crept up recently" if float(v) > 0.02 else "Bill has been steady")),
    "bill_change_3m_pct": lambda v, up: ("Bill rose over the last 3 months" if float(v) > 0.02 else "Bill has not risen lately"),
    "promo_expired_recent": lambda v, up: ("A promotion just ended" if _n(v) else "No promotion ended recently"),
    "bill_changes_12m": lambda v, up: (f"Bill changed {_plural(_n(v), 'time')} this year" if _n(v) else "Bill has not changed this year"),
    "last_bill_cents": lambda v, up: (f"Pays {_money(v)} a month"),
    "prior_avg_bill_cents": lambda v, up: (f"Usually pays about {_money(v)} a month"),
    "step_up_cost_pct_income": lambda v, up: ("Next plan up is affordable for their income" if up else "Next plan up would be a stretch on their income"),
    "step_up_cost_cents": lambda v, up: (f"Next plan up costs {_money(v)} more a month"),
    "next_plan_price_cents": lambda v, up: (f"Next plan up costs {_money(v)} a month"),
    "household_income_usd": lambda v, up: ("Higher household income" if up else "Lower household income"),
    "area_median_income_usd": lambda v, up: ("Lives in a higher-income area" if up else "Lives in a lower-income area"),
    "recent_job_change": lambda v, up: ("Recently changed jobs" if _n(v) else "No recent job change"),
    # tenure / account
    "tenure_months": lambda v, up: (f"Customer for {_n(v) // 12} years" if _n(v) >= 24 else f"Customer for {_n(v)} months"),
    "tenure_capped60": lambda v, up: ("Customer for 5+ years" if _n(v) >= 60 else
                                      (f"Customer for {_n(v) // 12} years" if _n(v) >= 24 else f"Customer for {_n(v)} months")),
    "early_tenure": lambda v, up: ("New customer (under a year)" if _n(v) else "Customer for over a year"),
    "short_history": lambda v, up: ("Too new for a full billing history" if _n(v) else "Has a full billing history"),
    "extra_lines": lambda v, up: (f"{_plural(_n(v) + 1, 'line')} on the account" if _n(v) else "Single-line account"),
    "n_lines": lambda v, up: (f"{_plural(_n(v), 'line')} on the account" if _n(v) > 1 else "Single-line account"),
    "no_autopay": lambda v, up: ("Not on AutoPay" if _n(v) else "On AutoPay"),
    "autopay": lambda v, up: ("On AutoPay" if _n(v) else "Not on AutoPay"),
    "has_home_internet": lambda v, up: ("Has T-Mobile Home Internet" if _n(v) else "No Home Internet"),
    "has_streaming_addon": lambda v, up: ("Has a streaming add-on" if _n(v) else "No streaming add-on"),
    "n_account_addons": lambda v, up: (f"Has {_plural(_n(v), 'add-on')}" if _n(v) else "No add-ons"),
    "n_line_addons": lambda v, up: (f"Has {_plural(_n(v), 'line add-on')}" if _n(v) else "No line add-ons"),
    "n_protection_addons": lambda v, up: (f"Has device protection on {_plural(_n(v), 'phone')}" if _n(v) else "No device protection"),
    "n_connected_lines": lambda v, up: (f"Has {_plural(_n(v), 'connected device')}" if _n(v) else "No connected devices"),
    # engagement / service experience
    "app_sessions_30d": lambda v, up: (f"Active in the T-Life app ({_n(v)} visits a month)" if _n(v) >= 8 else "Rarely opens the T-Life app"),
    "low_app_use": lambda v, up: ("Rarely opens the T-Life app" if _n(v) else "Uses the T-Life app regularly"),
    "competitor_research_score": lambda v, up: ("Shopping other carriers" if float(v) >= 0.4 else "Not shopping other carriers"),
    "port_out_inquiry": lambda v, up: ("Asked about switching carriers" if _n(v) else "Has not asked about switching"),
    "cancel_inquiries_270d": lambda v, up: ("Asked about cancelling" if _n(v) else "Never asked about cancelling"),
    "cancellation_inquiry_contacts_90d": lambda v, up: ("Asked about cancelling recently" if _n(v) else "No recent cancellation questions"),
    "unresolved_90d": lambda v, up: (f"{_plural(_n(v), 'unresolved support issue')} lately" if _n(v) else "No unresolved support issues"),
    "unresolved_270d": lambda v, up: ("Has had unresolved support issues" if _n(v) else "Support issues get resolved"),
    "negative_contacts_90d": lambda v, up: ("Recent unhappy support calls" if _n(v) else "No unhappy support calls"),
    "troubled_4plus": lambda v, up: ("Many recent support problems" if _n(v) else "No pile-up of support problems"),
    "neg_sentiment": lambda v, up: ("Unhappy tone in support contacts" if float(v) > 0 else "No unhappy support contacts"),
    "avg_sentiment": lambda v, up: ("Positive support experiences" if float(v) > 0 else "Mixed or negative support experiences"),
    "avg_sentiment_90d": lambda v, up: ("Recent support went well" if float(v) > 0 else "Recent support went poorly"),
    "min_sentiment_270d": lambda v, up: ("Had at least one angry support call" if float(v) < -0.5 else "No angry support calls"),
    "support_90d": lambda v, up: (f"{_plural(_n(v), 'support contact')} in 90 days" if _n(v) else "No recent support contacts"),
    "support_270d": lambda v, up: (f"{_plural(_n(v), 'support contact')} this year" if _n(v) else "No support contacts this year"),
    "days_since_last_contact": lambda v, up: ("Contacted support recently" if _n(v) < 30 else "No recent support contact"),
    "billing_contacts_90d": lambda v, up: ("Recent billing questions" if _n(v) else "No billing questions"),
    "network_contacts_90d": lambda v, up: ("Recent network complaints" if _n(v) else "No network complaints"),
    "device_contacts_90d": lambda v, up: ("Recent device problems" if _n(v) else "No device problems"),
    "plan_change_contacts_90d": lambda v, up: ("Asked about changing plans" if _n(v) else "Has not asked about changing plans"),
}


# Upgrade reason-direction guard (same idea as tm-churn's SIGN_PRIOR guard). feature group -> (sign, mode).
# sign +1 = more of it makes an upgrade MORE likely, -1 = LESS likely. mode "presence": the account either has
# the condition (value > 0) or not, and the reason wording says which; "vs_typical": compared with the typical
# account (the model's reference row). A group is shown as a reason FOR upgrading only when the account sits on
# the side that its sign says helps, and AGAINST only on the side that hurts; otherwise it is skipped and the
# next group is used. So e.g. unresolved support issues, money still owed on phones, a bill jump or an unhappy
# support tone can only ever be reasons against (their absence may be a reason for: "Phones fully paid off").
UPGRADE_DIRECTION: Dict[str, Tuple[int, str]] = {
    # hurts an upgrade when present
    "unresolved_90d": (-1, "presence"), "unresolved_270d": (-1, "presence"),
    "financing_balance_total_cents": (-1, "presence"), "n_financed_lines": (-1, "presence"),
    "monthly_installment_total_cents": (-1, "presence"), "max_financing_months_remaining": (-1, "presence"),
    "new_installment_recent": (-1, "presence"),
    "bill_increase_pct": (-1, "presence"), "bill_change_3m_pct": (-1, "presence"),
    "promo_expired_recent": (-1, "presence"),
    "neg_sentiment": (-1, "presence"), "negative_contacts_90d": (-1, "presence"), "troubled_4plus": (-1, "presence"),
    "cancel_inquiries_270d": (-1, "presence"), "cancellation_inquiry_contacts_90d": (-1, "presence"),
    "port_out_inquiry": (-1, "presence"),
    # hurts an upgrade when above the typical account (shopping around is a churn sign, not an upgrade sign)
    "competitor_research_score": (-1, "vs_typical"),
    # helps an upgrade when present
    "n_lines_over_cap_3m": (1, "presence"), "n_lines_usage_up_30pct": (1, "presence"),
    "plan_misfit_share": (1, "presence"), "n_tradein_eligible_lines": (1, "presence"),
    "n_lines_device_36m_plus": (1, "presence"), "financing_ends_within_3m": (1, "presence"),
    "installment_ended_recent": (1, "presence"), "no_financing": (1, "presence"),
    # helps an upgrade when above the typical account
    "max_device_age_months": (1, "vs_typical"), "data_gb_3m_avg": (1, "vs_typical"),
    "data_growth_pct": (1, "vs_typical"), "hotspot_gb_3m_avg": (1, "vs_typical"),
}


def upgrade_direction_ok(g: str, up: bool, row, xr=None, reference=None) -> bool:
    """True if group g may be shown as an upgrade reason in this direction (up=True -> FOR, False -> AGAINST)."""
    if g not in UPGRADE_DIRECTION:
        return True
    sign, mode = UPGRADE_DIRECTION[g]
    try:
        if mode == "presence":
            v = row.get(g, np.nan) if hasattr(row, "get") else np.nan
            if v is None or (isinstance(v, float) and v != v):
                v = xr.get(g, np.nan) if xr is not None and hasattr(xr, "get") else np.nan
            v = float(v)
            if v != v:
                return False
            side = 1 if v > 0 else -1                       # has the condition / doesn't
        else:
            if xr is None or reference is None or g not in getattr(xr, "index", []) or g not in reference.index:
                return True
            d = float(xr[g]) - float(reference[g])
            if d == 0:
                return False
            side = 1 if d > 0 else -1
    except (TypeError, ValueError):
        return False
    return (side * sign > 0) == bool(up)


def _upgrade_sentence(g: str, row, up: bool, cat: Optional[str] = None) -> str:
    """Short customer-card sentence for the upgrade target. Never returns raw column names or underscores."""
    if cat is not None or g in _CATEGORY_TEXT:
        table = _CATEGORY_TEXT.get(g, {})
        if cat in table:
            return table[cat]
        if cat and cat != "none":
            return cat.replace("_", " ").capitalize()
        return "Other account details"
    v = row.get(g, np.nan) if hasattr(row, "get") else np.nan
    f = UPGRADE_PHRASES.get(g)
    if f is not None:
        try:
            vv = 0.0 if v is None or (isinstance(v, float) and v != v) else v
            return f(float(vv), up)
        except (TypeError, ValueError):
            pass
    return "Other account details" if up else "Other account details"


def contributions_to_reasons(contrib: pd.DataFrame, X: pd.DataFrame, k: int = 3, eps: float = 1e-6,
                             target: str = "churn", reference: Optional[pd.Series] = None) -> pd.DataFrame:
    """contrib: rows = accounts, cols = feature groups (one-hot columns already merged); positive raises risk.
    Groups are merged again into tm-churn's reason groups (churn_features.REASON_GROUPS) when available, and
    worded with churn_features.phrase() so harness and Model A speak the same language; else REASONS above."""
    cf = _cf_text() if target == "churn" else None
    if cf is not None:
        contrib = contrib.T.groupby(lambda g: g if g in REASONS and g not in cf._FEATURE_GROUP
                                    else cf.reason_group(g)).sum().T
    raw = _raw_features(X.index)
    raw = raw.combine_first(X) if len(raw.columns) else X
    cats = {g: [c for c in X.columns if _group_of(c) == g] for g in {_group_of(c) for c in X.columns if "=" in c}}

    def text(g, row, xr, risk):
        if target == "upgrade":
            cat = None
            if g in cats:
                rv = row.get(g) if hasattr(row, "get") else None
                if isinstance(rv, str):          # raw category (covers levels prepare() dropped)
                    cat = rv
                else:
                    on = [c for c in cats[g] if xr.get(c, 0) > 0.5]
                    cat = on[0].split("=", 1)[1] if on else "none"
            return _upgrade_sentence(g, row, risk, cat)
        if g in REASONS and (cf is None or g not in cf._FEATURE_GROUP):
            d = row.to_dict()
            for cg, cols in cats.items():
                on = [c for c in cols if xr.get(c, 0) > 0.5]
                d[cg + "__cat"] = on[0].split("=", 1)[1] if on else "none"
            return _sentence(g, "risk" if risk else "stay", d)
        if cf is not None:
            try:
                return cf.phrase(g, row, risk)
            except Exception:  # noqa: BLE001
                pass
        d = row.to_dict()
        for cg, cols in cats.items():
            on = [c for c in cols if xr.get(c, 0) > 0.5]
            d[cg + "__cat"] = on[0].split("=", 1)[1] if on else "none"
        return _sentence(g, "risk" if risk else "stay", d)

    rows = []
    ref = None
    if target == "upgrade":
        ref = reference if reference is not None else _reference_row(X)
    blocked = 0
    for aid, r in contrib.iterrows():
        row, xr = raw.loc[aid], X.loc[aid]
        s_ = r.sort_values()
        def pick(groups, up):
            nonlocal blocked
            seen, out_ = set(), []
            for g_ in groups:
                if target == "upgrade" and not upgrade_direction_ok(g_, up, row, xr, ref):
                    blocked += 1
                    continue
                t_ = text(g_, row, xr, up)
                if t_ and t_ not in seen:
                    seen.add(t_)
                    out_.append(t_)
                if len(out_) == k:
                    break
            return out_ + [""] * (k - len(out_))

        risk = pick([g for g, v in s_[::-1].items() if v > eps], True)
        stay = pick([g for g, v in s_.items() if v < -eps], False)
        rec = {"account_id": aid}
        for i in range(k):
            rec[f"risk_reason_{i + 1}"] = risk[i]
        for i in range(k):
            rec[f"stay_reason_{i + 1}"] = stay[i]
        rows.append(rec)
    cols = ["account_id"] + [f"risk_reason_{i + 1}" for i in range(k)] + [f"stay_reason_{i + 1}" for i in range(k)]
    out = pd.DataFrame(rows, columns=cols)
    out.attrs["direction_blocked"] = blocked
    return out


# --------------------------------------------------------------------------------------------- model interface
class ChurnModel:
    """Base class. Subclasses implement fit + predict_proba; explain() works for any model via perturbation:
    contribution(feature group) = p(x) - p(x with that group set to the typical account's value)."""
    name: str = "base"

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "ChurnModel":
        raise NotImplementedError

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        raise NotImplementedError

    # harness calls this after fit so explain() has a baseline; models may also call it themselves
    def set_reference(self, X: pd.DataFrame) -> "ChurnModel":
        self.reference_ = _reference_row(X)
        return self

    def contributions(self, X: pd.DataFrame) -> pd.DataFrame:
        ref = getattr(self, "reference_", None)
        if ref is None:
            ref = _reference_row(X)
        ref = ref.reindex(X.columns).fillna(0.0)
        base = self.predict_proba(X)
        groups: Dict[str, List[str]] = {}
        for c in X.columns:
            groups.setdefault(_group_of(c), []).append(c)
        out = {}
        for g, cols in groups.items():
            Xp = X.copy()
            Xp[cols] = np.broadcast_to(ref[cols].values, (len(X), len(cols)))
            out[g] = base - self.predict_proba(Xp)
        return pd.DataFrame(out, index=X.index)

    def explain(self, X: pd.DataFrame, k: int = 3) -> pd.DataFrame:
        """risk_reason_* = pushes the probability UP (churn risk / upgrade likelihood); stay_reason_* = DOWN."""
        return contributions_to_reasons(self.contributions(X), X, k, target=getattr(self, "target_", "churn"),
                                        reference=getattr(self, "reference_", None))


class SupportCallsRule(ChurnModel):
    """Baseline business rule: flag accounts with 3+ support contacts in 90 days. predict_proba returns the
    training churn rate of the flagged / unflagged group (so Brier is meaningful); the ranking is the rule."""
    name = "rule_support3"

    def __init__(self, threshold: int = None):
        self.threshold = CONFIG["rule_threshold"] if threshold is None else threshold

    def _flag(self, X):
        return raw_column(X, "support_90d") >= self.threshold

    def fit(self, X, y):
        f, yv = self._flag(X), np.asarray(y, float)
        prior = yv.mean()
        self.rate_flag_ = yv[f].mean() if f.any() else prior
        self.rate_noflag_ = yv[~f].mean() if (~f).any() else prior
        return self

    def predict_proba(self, X):
        return np.where(self._flag(X), self.rate_flag_, self.rate_noflag_).astype(float)

    def contributions(self, X):
        f = self._flag(X)
        gap = max(self.rate_flag_ - self.rate_noflag_, 1e-3)
        return pd.DataFrame({"support_90d": np.where(f, gap, -gap)}, index=X.index)


class SklearnChurnModel(ChurnModel):
    """Wraps any sklearn classifier with predict_proba."""

    def __init__(self, name: str, estimator):
        self.name, self.estimator = name, estimator

    def fit(self, X, y):
        self.columns_ = list(X.columns)
        self.estimator.fit(X[self.columns_].values, np.asarray(y).astype(int))
        self.set_reference(X)
        return self

    def predict_proba(self, X):
        return self.estimator.predict_proba(X.reindex(columns=self.columns_, fill_value=0.0).values)[:, 1]


class LogRegModel(SklearnChurnModel):
    """Standardised logistic regression. explain() is exact for a linear model: coef * (x - typical), in logit
    units, summed per feature group."""

    def __init__(self, C: float = 0.5):
        super().__init__("logreg", make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=5000)))

    def contributions(self, X):
        sc, lr = self.estimator[0], self.estimator[-1]
        ref = self.reference_.reindex(self.columns_).values
        w = lr.coef_[0] / np.where(sc.scale_ == 0, 1, sc.scale_)
        c = (X.reindex(columns=self.columns_, fill_value=0.0).values - ref) * w
        df = pd.DataFrame(c, index=X.index, columns=self.columns_)
        return df.T.groupby(lambda col: _group_of(col)).sum().T


class NearOrOverDataCapRule(ChurnModel):
    """Baseline UPGRADE rule 'near or over data cap' (see near_or_over_data_cap()). predict_proba returns the
    training upgrade rate of the flagged / unflagged group; the ranking is the rule."""
    name = "rule_near_or_over_data_cap"

    def __init__(self, ratio: float = 0.9, basis: str = "per_line"):
        self.ratio, self.basis = ratio, basis

    def _flag(self, X):
        cols = ["n_lines_over_cap_3m", "data_gb_3m_avg", "plan_data_cap_gb", "n_lines"]
        f = pd.DataFrame({"account_id": X.index})
        for c in cols:
            if c in X.columns:
                f[c] = X[c].values
            else:
                raw = _raw_features(X.index)
                if c not in raw.columns:
                    raise HarnessDataError(f"rule_near_or_over_data_cap needs {c!r} (features.csv)")
                f[c] = raw[c].values          # keep NaN cap = unlimited
        return near_or_over_data_cap(f, self.ratio, self.basis)["near_or_over_data_cap"].to_numpy() == 1

    fit = SupportCallsRule.fit
    predict_proba = SupportCallsRule.predict_proba

    def contributions(self, X):
        f = self._flag(X)
        gap = max(self.rate_flag_ - self.rate_noflag_, 1e-3)
        return pd.DataFrame({"data_cap_use": np.where(f, gap, -gap)}, index=X.index)


_REGISTRY: Dict[str, Callable[[], ChurnModel]] = {}
_TARGETS_OF: Dict[str, Tuple[str, ...]] = {}


def register_model(name: str, factory: Callable[[], ChurnModel], targets: Iterable[str] = ("churn",)) -> None:
    """Register a factory (zero-arg callable returning a fresh ChurnModel). Re-registering replaces it.
    targets: which targets the model is run on by default ('churn', 'upgrade'). Default churn only, so a
    churn-specific model (e.g. sign priors) is not silently run on upgrade; pass targets=("churn", "upgrade")."""
    if not callable(factory):
        raise TypeError("factory must be callable")
    bad = set(targets) - set(TARGETS)
    if bad:
        raise ValueError(f"unknown targets {bad}; use {list(TARGETS)}")
    _REGISTRY[name] = factory
    _TARGETS_OF[name] = tuple(targets)


def get_model(name: str) -> ChurnModel:
    if name not in _REGISTRY:
        raise KeyError(f"unknown model {name!r}; registered: {list_models()}")
    m = _REGISTRY[name]()
    m.name = name
    return m


def list_models(target: Optional[str] = None) -> List[str]:
    """All registered names, or those registered for `target`."""
    return [n for n in _REGISTRY if target is None or target in _TARGETS_OF.get(n, ("churn",))]


BOTH = ("churn", "upgrade")
register_model("rule_support3", SupportCallsRule, targets=("churn",))
register_model("rule_near_or_over_data_cap", NearOrOverDataCapRule, targets=("upgrade",))
register_model("logreg", LogRegModel, targets=BOTH)
register_model("hgb", lambda: SklearnChurnModel("hgb", HistGradientBoostingClassifier(
    max_iter=200, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=40, l2_regularization=1.0,
    random_state=42)), targets=BOTH)
register_model("rf", lambda: SklearnChurnModel("rf", RandomForestClassifier(
    n_estimators=300, min_samples_leaf=10, max_features="sqrt", n_jobs=1, random_state=42)), targets=BOTH)


def load_plugins() -> List[str]:
    """Import other lanes' model modules so they self-register (currently churn_model.py -> 'model_a').
    They import this module by name ('model_harness'), so the CLI runs from that same module object."""
    loaded = []
    for mod in ("churn_model",):
        try:
            if str(HERE) not in sys.path:
                sys.path.insert(0, str(HERE))
            __import__(mod)
            loaded.append(mod)
        except Exception as e:  # noqa: BLE001
            print(f"[model_harness] plugin {mod} not loaded: {e}", file=sys.stderr)
    return loaded


def _as_model(model) -> ChurnModel:
    return get_model(model) if isinstance(model, str) else model


def _fresh(model) -> ChurnModel:
    """New instance per fit (registry name -> factory; instance -> deep copy)."""
    if isinstance(model, str):
        return get_model(model)
    import copy
    return copy.deepcopy(model)


def _fit(model: ChurnModel, X, y, target: str = "churn") -> ChurnModel:
    model.fit(X, y)
    if getattr(model, "reference_", None) is None:
        model.set_reference(X)
    try:
        model.target_ = target          # explain() wording (churn vs upgrade)
    except AttributeError:
        pass
    p = np.asarray(model.predict_proba(X.iloc[:5]))
    if p.shape != (min(5, len(X)),):
        raise HarnessDataError(f"{model.name}.predict_proba must return shape (n,), got {p.shape}")
    return model


# --------------------------------------------------------------------------------------------- evaluation
def _ids_hash(ids) -> str:
    import hashlib
    return hashlib.sha256(",".join(map(str, sorted(ids))).encode()).hexdigest()[:12]


def _safe_auc(y, p) -> float:
    p = np.asarray(p, float)
    if np.isnan(p).any() or len(np.unique(y)) < 2:
        return float("nan")
    return float(roc_auc_score(y, p))


def evaluate(model, label: Optional[str] = None, cv: bool = True, data=None, target: Optional[str] = None) -> dict:
    """Fit on the stratified holdout's train side, score the test side; plus stratified k-fold CV summary.
    Always reports the oracle (true synthetic probability) AUC on the SAME test rows / folds."""
    X, y, meta = data if data is not None else load_data(label, target=target)
    label = meta["label"].iloc[0]
    tgt = target_of(label)
    name = model if isinstance(model, str) else model.name
    Xtr, Xte, ytr, yte, mtr, mte = holdout_split(X, y, meta)
    m = _fit(_fresh(model), Xtr, ytr, tgt)
    p = np.asarray(m.predict_proba(Xte), float)
    res = {"model": name, "target": tgt, "label": label,
           "split": "stratified_account_holdout (single snapshot 2026-10-01; not temporal)",
           "test_size": CONFIG["test_size"], "seed": CONFIG["seed"], "n_train": int(len(Xtr)),
           "prep_source": meta["prep_source"].iloc[0], "caveat": CAVEAT}
    res.update(compute_metrics(yte, p, mte["oracle_p"].values))
    if mte["oracle_p"].notna().all():
        om = compute_metrics(yte, mte["oracle_p"].values)
        res["oracle_same_rows"] = {k: om[k] for k in ("auc", "pr_auc", "brier", "top10_recall", "top10_lift")}
    else:
        res["oracle_same_rows"] = {k: float("nan") for k in ("auc", "pr_auc", "brier", "top10_recall", "top10_lift")}
    res["test_ids_hash"] = _ids_hash(Xte.index)
    res["auc_gap_to_oracle"] = res["auc"] - res["oracle_same_rows"]["auc"]
    if cv:
        folds = []
        for tr, te in cv_folds(X, y):
            mm = _fit(_fresh(model), X.iloc[tr], y.iloc[tr], tgt)
            pp = mm.predict_proba(X.iloc[te])
            mt = compute_metrics(y.iloc[te], pp)
            row = {k: mt[k] for k in ("auc", "pr_auc", "brier", "top10_recall", "top10_lift")}
            row["oracle_auc"] = _safe_auc(y.iloc[te], meta["oracle_p"].iloc[te])
            folds.append(row)
        f = pd.DataFrame(folds)
        res["cv"] = {"k": CONFIG["cv_k"], **{f"{c}_mean": float(f[c].mean()) for c in f},
                     **{f"{c}_std": float(f[c].std()) for c in f}}
    return res


def oracle_metrics(label: Optional[str] = None, data=None, target: Optional[str] = None) -> dict:
    """Ceiling: the true synthetic probability scored on the same holdout test side."""
    X, y, meta = data if data is not None else load_data(label, target=target)
    _, _, _, yte, _, mte = holdout_split(X, y, meta)
    res = {"model": "oracle_true_p", "label": meta["label"].iloc[0], "target": meta["target"].iloc[0],
           "caveat": CAVEAT}
    if mte["oracle_p"].isna().any():
        res.update({"auc": float("nan"), "pr_auc": float("nan"), "brier": float("nan"), "ece": float("nan"),
                    "top10_recall": float("nan"), "top10_lift": float("nan"), "mean_pred": float("nan"),
                    "base_rate": float(yte.mean()), "positives": int(yte.sum()), "n": int(len(yte))})
    else:
        res.update(compute_metrics(yte, mte["oracle_p"].values))
    return res


_ROW_KEYS = ("model", "target", "label", "auc", "pr_auc", "brier", "ece", "top10_recall", "top10_lift",
             "mean_pred", "base_rate", "positives", "n")


def backtest(models: Optional[Iterable] = None, label: Optional[str] = None, cv: bool = True,
             target: Optional[str] = None) -> pd.DataFrame:
    """Every model side by side with the target's baseline rule ('3+ support calls in 90d' for churn,
    'near or over data cap' for upgrade) and the oracle ceiling (true synthetic probability)."""
    data = load_data(label, target=target)
    tgt = data[2]["target"].iloc[0]
    rule_name = TARGETS[tgt]["rule"]
    models = list(models) if models is not None else list_models(tgt)
    names = [m if isinstance(m, str) else m.name for m in models]
    if rule_name not in names:
        models = [rule_name] + models
    rows, evals = [], {}
    for mdl in models:
        r = evaluate(mdl, cv=cv, data=data)
        evals[r["model"]] = r
        rows.append({k: r.get(k) for k in _ROW_KEYS}
                    | {"oracle_auc_same_rows": r["oracle_same_rows"]["auc"], "auc_gap_to_oracle": r["auc_gap_to_oracle"]}
                    | ({"cv_auc_mean": r["cv"]["auc_mean"], "cv_auc_std": r["cv"]["auc_std"],
                        "cv_oracle_auc_mean": r["cv"]["oracle_auc_mean"],
                        "cv_pr_auc_mean": r["cv"]["pr_auc_mean"], "cv_pr_auc_std": r["cv"]["pr_auc_std"],
                        "cv_top10_recall_mean": r["cv"]["top10_recall_mean"],
                        "cv_top10_recall_std": r["cv"]["top10_recall_std"]}
                       if cv else {}))
    o = oracle_metrics(data=data)
    orow = {k: o.get(k) for k in _ROW_KEYS}
    orow.update({"oracle_auc_same_rows": o["auc"], "auc_gap_to_oracle": 0.0})
    X, y, meta = data
    if cv:
        oa = [_safe_auc(y.iloc[te], meta["oracle_p"].iloc[te]) for _, te in cv_folds(X, y)]
        orow.update({"cv_auc_mean": float(np.mean(oa)), "cv_auc_std": float(np.std(oa, ddof=1)),
                     "cv_oracle_auc_mean": float(np.mean(oa))})
    orow["oracle_auc_all_regular"] = _safe_auc(y, meta["oracle_p"])
    rows.append(orow)
    df = pd.DataFrame(rows)
    rule = df.loc[df.model == rule_name].iloc[0]
    df["auc_vs_rule"] = df["auc"] - rule["auc"]
    df["top10_recall_vs_rule"] = df["top10_recall"] - rule["top10_recall"]
    if cv:
        df["cv_auc_vs_rule"] = df["cv_auc_mean"] - rule["cv_auc_mean"]
    df.attrs["caveat"] = CAVEAT
    df.attrs["evals"] = evals
    df.attrs["rule"] = rule_name
    return df


def evaluate_scaled_to_real(model, label: Optional[str] = None, target: Optional[str] = None,
                            include_enrichment: Optional[bool] = None) -> dict:
    """Train on the 50k SYNTHETIC scaled accounts, test on the 5,000 regular sandbox accounts (all synthetic).
    The scaled rows come from a copula fitted to the real features (labels drawn independently with the same
    recipe), so there is no label leakage, but feature distributions are close by construction."""
    Xs, ys, ms = load_data(label, target=target, data="scaled", include_enrichment=include_enrichment)
    Xr, yr, mr = load_data(label, target=target, data="real", include_enrichment=include_enrichment)
    Xr = Xr.reindex(columns=Xs.columns, fill_value=0.0)
    lab = ms["label"].iloc[0]
    m = _fit(_fresh(model), Xs, ys, target_of(lab))
    p = np.asarray(m.predict_proba(Xr), float)
    res = {"model": m.name, "target": target_of(lab), "label": lab, "mode": "train scaled (50k SYN) -> test real 5k",
           "n_train": int(len(Xs)), "train_positives": int(ys.sum()), "caveat": CAVEAT}
    res.update(compute_metrics(yr, p, mr["oracle_p"].values))
    res["oracle_same_rows_auc"] = _safe_auc(yr, mr["oracle_p"])
    return res


def fit_full(model, label: Optional[str] = None, data=None, target: Optional[str] = None) -> ChurnModel:
    """Fit on ALL regular accounts (for scoring / personas; evaluation uses evaluate())."""
    X, y, meta = data if data is not None else load_data(label, target=target)
    return _fit(_fresh(model), X, y, meta["target"].iloc[0])


def persona_check(model, label: Optional[str] = None, fitted: Optional[ChurnModel] = None,
                  high_pct: Optional[float] = None, low_pct: Optional[float] = None,
                  target: Optional[str] = None) -> pd.DataFrame:
    """PROVISIONAL. Model fitted on all regular accounts; each persona's score is placed as a percentile of the
    regular accounts' scores. high = pct >= high_pct (default CONFIG persona_high_pct = 90, top 10%);
    low = pct <= low_pct (default CONFIG persona_low_pct = 50, at/below median).
    churn: 04/21/22/27 high, 10/24 low.  upgrade: 25/28 high, 22/24/27 low.
    Persona ids map 1:1 to accounts (sandbox personas.persona_id == account_id == ACC-PERSONA-xx)."""
    data = load_data(label, target=target)
    lab = data[2]["label"].iloc[0]
    tgt = target_of(lab)
    expect = TARGETS[tgt]["personas"]
    m = fitted or fit_full(model, data=data)
    reg_scores = np.asarray(m.predict_proba(data[0]), float)
    Xp, mp = load_personas(lab)
    Xp = Xp.reindex(columns=data[0].columns, fill_value=0.0)
    Xp = Xp.loc[[a for a in expect if a in Xp.index]]
    missing = [a for a in expect if a not in Xp.index]
    p = np.asarray(m.predict_proba(Xp), float)
    reasons = m.explain(Xp, k=3).set_index("account_id")
    hp = CONFIG["persona_high_pct"] if high_pct is None else high_pct
    lp = CONFIG["persona_low_pct"] if low_pct is None else low_pct
    rows = []
    for aid, s in zip(Xp.index, p):
        pct = float((reg_scores < s).mean() * 100 + (reg_scores == s).mean() * 50)
        exp = expect[aid]
        ok = pct >= hp if exp == "high" else pct <= lp
        rows.append({"account_id": aid, "model": m.name, "target": tgt, "label": lab, "expected": exp,
                     "score": s, "percentile_vs_regular": round(pct, 1),
                     "oracle_p": float(mp.loc[aid, "oracle_p"]),
                     "result": "PASS" if ok else "FAIL", "status": "provisional",
                     "rule": f"high: pct>={hp:g}; low: pct<={lp:g}",
                     "reason_up_1": reasons.loc[aid, "risk_reason_1"],
                     "reason_down_1": reasons.loc[aid, "stay_reason_1"]})
    for aid in missing:
        rows.append({"account_id": aid, "model": m.name, "target": tgt, "expected": expect[aid],
                     "result": "MISSING", "status": "provisional"})
    return pd.DataFrame(rows)


def score_accounts(model, label: Optional[str] = None, fitted: Optional[ChurnModel] = None,
                   target: Optional[str] = None) -> pd.DataFrame:
    """Scores for all accounts (regular + personas), fitted on all regular accounts. SYNTHETIC.
    churn:   tm-churn contract columns account_id, p_churn_90d, risk_rank, risk_reason_1..3, stay_reason_1..3
    upgrade: account_id, p_upgrade_90d, upgrade_rank, upgrade_reason_1..3, against_upgrade_reason_1..3
    rank 1 = highest probability."""
    data = load_data(label, target=target)
    lab = data[2]["label"].iloc[0]
    tgt = target_of(lab)
    m = fitted or fit_full(model, data=data)
    Xall, _, meta = _load_joined(lab, data="real")   # scores are always for the real sandbox accounts
    Xall = Xall.reindex(columns=data[0].columns, fill_value=0.0)
    p = np.asarray(m.predict_proba(Xall), float)
    pc, rc = TARGETS[tgt]["prob_col"], TARGETS[tgt]["rank_col"]
    df = pd.DataFrame({"account_id": Xall.index, pc: np.round(p, 6)})
    df[rc] = df[pc].rank(ascending=False, method="first").astype(int)
    ex = m.explain(Xall, k=3)
    if tgt == "upgrade":
        ex = ex.rename(columns={f"risk_reason_{i}": f"upgrade_reason_{i}" for i in (1, 2, 3)}
                       | {f"stay_reason_{i}": f"against_upgrade_reason_{i}" for i in (1, 2, 3)})
    df = df.merge(ex, on="account_id", how="left")
    df["is_persona"] = meta["is_persona"].values
    df["model"] = m.name
    df["label"] = lab
    df["synthetic"] = 1
    return df.sort_values(rc).reset_index(drop=True)


# --------------------------------------------------------------------------------------------- "near or over data cap" rule
def near_or_over_data_cap(features: Optional[pd.DataFrame] = None, ratio: float = 0.9,
                       basis: str = "per_line") -> pd.DataFrame:
    """'Near or over data cap': baseline UPGRADE (step-up) rule from features.csv only (never reads the sandbox). SYNTHETIC data.
    PROXY for 'near the data cap 2+ months': features.csv has no monthly near-cap count, so
      flag = n_lines_over_cap_3m > 0  OR  3-month avg usage >= ratio (0.9) * plan_data_cap_gb
    Unlimited plans (blank plan_data_cap_gb) always get 0.
    Usage column: data_gb_3m_avg = household total GB/month (sum over lines, averaged over the last 3 months).
    plan_data_cap_gb is a PER-LINE cap (features.py compares each line's GB to it), so basis="per_line" (default)
    divides by n_lines; basis="account" is the literal household-total / cap reading (flags multi-line homes
    whose combined use exceeds one line's cap)."""
    f = features if features is not None else _read_csv(Path(CONFIG["data_dir"]) / "features.csv",
                                                        ["account_id", "n_lines_over_cap_3m", "data_gb_3m_avg",
                                                         "plan_data_cap_gb", "n_lines"], "features.csv")
    if basis not in ("per_line", "account"):
        raise ValueError("basis must be 'per_line' or 'account'")
    cap = f["plan_data_cap_gb"].astype(float)
    use = f["data_gb_3m_avg"].astype(float)
    if basis == "per_line":
        use = use / f["n_lines"].clip(lower=1).astype(float)
    r = (use / cap).where(cap.notna() & (cap > 0))
    over = f["n_lines_over_cap_3m"].fillna(0) > 0
    near = r >= ratio
    flag = ((over | near) & cap.notna()).astype(int)
    reason = np.where(~cap.notna(), "",
                      np.where(over, "A line used more data than the plan includes (last 3 months)",
                               np.where(near, f"Using {ratio:.0%}+ of the plan's data on average (last 3 months)", "")))
    return pd.DataFrame({"account_id": f["account_id"].values, "near_or_over_data_cap": flag.values,
                         "n_lines_over_cap_3m": f["n_lines_over_cap_3m"].values,
                         "usage_to_cap_ratio": r.round(4).values, "basis": basis, "upgrade_reason": reason})


# --------------------------------------------------------------------------------------------- Model C (uplift) re-exports
_UPLIFT_NAMES = ["UpliftModel", "TLearner", "register_uplift_model", "get_uplift_model", "list_uplift_models",
                 "load_uplift", "uplift_curve", "qini_curve", "auuc", "qini_coefficient", "binary_uplift_metrics",
                 "action_curves", "policy_value", "compare_policies", "uplift_sanity", "simulate_uplift_frame",
                 "load_orange_belgium", "evaluate_orange_belgium", "UpliftDataError"]
try:
    try:
        import uplift_eval as _ue  # type: ignore
    except ImportError:
        from harness import uplift_eval as _ue  # type: ignore
    globals().update({n: getattr(_ue, n) for n in _UPLIFT_NAMES})
except Exception as _e:  # noqa: BLE001
    print(f"[model_harness] uplift_eval not available: {_e}", file=sys.stderr)


# --------------------------------------------------------------------------------------------- reporting / CLI
def _fmt(x, pct=False):
    if x is None or (isinstance(x, float) and x != x):
        return "n/a"
    return f"{x:.1%}" if pct else f"{x:.3f}"


def _pm(m, s, pct=False):
    if m is None or m != m:
        return "n/a"
    return f"{m:.1%} ± {s:.1%}" if pct else f"{m:.3f} ± {s:.3f}"


def backtest_markdown(bt: pd.DataFrame) -> str:
    lab, tgt = bt["label"].iloc[0], bt["target"].iloc[0]
    rule = bt.attrs.get("rule", TARGETS[tgt]["rule"])
    g = lambda r, k: r[k] if k in r and r[k] == r[k] else float("nan")  # noqa: E731
    lines = [f"# Backtest: target={tgt}, label={lab}  (SYNTHETIC / SIMULATED)", "", CAVEAT, "",
             "Stratified account-level holdout (25% test, seed 42) + 5-fold stratified CV; single snapshot as of "
             f"2026-10-01, not temporal. Baseline rule: {rule}.", "",
             "| model | CV AUC mean ± std | CV oracle AUC | CV PR-AUC | CV top-10% recall | holdout AUC | oracle AUC (same rows) "
             "| holdout PR-AUC | Brier | top-10% recall | top-10% lift | CV AUC vs rule |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in bt.iterrows():
        lines.append(f"| {r['model']} | {_pm(g(r, 'cv_auc_mean'), g(r, 'cv_auc_std'))} | {_fmt(g(r, 'cv_oracle_auc_mean'))} | "
                     f"{_pm(g(r, 'cv_pr_auc_mean'), g(r, 'cv_pr_auc_std'))} | "
                     f"{_pm(g(r, 'cv_top10_recall_mean'), g(r, 'cv_top10_recall_std'), True)} | "
                     f"{_fmt(r['auc'])} | {_fmt(r['oracle_auc_same_rows'])} | {_fmt(r['pr_auc'])} | "
                     f"{_fmt(r['brier'])} | {_fmt(r['top10_recall'], True)} | "
                     f"{'n/a' if r['top10_lift'] != r['top10_lift'] else format(r['top10_lift'], '.2f') + 'x'} | "
                     f"{'n/a' if g(r, 'cv_auc_vs_rule') != g(r, 'cv_auc_vs_rule') else format(g(r, 'cv_auc_vs_rule'), '+.3f')} |")
    oa = bt["oracle_auc_all_regular"].dropna() if "oracle_auc_all_regular" in bt else pd.Series(dtype=float)
    lines += ["", f"Holdout test positives: {int(bt['positives'].iloc[0])} of {int(bt['n'].iloc[0])} "
                  f"(base rate {bt['base_rate'].iloc[0]:.2%}, synthetic). oracle_true_p = the label's true synthetic "
                  f"probability (ceiling); oracle AUC on ALL regular accounts: {_fmt(oa.iloc[0]) if len(oa) else 'n/a'}. "
                  "A single holdout with few positives is noisy: compare each model to the oracle on the same rows "
                  "and prefer the CV mean."]
    return "\n".join(lines)


def summary_text(ev: dict, personas: Optional[pd.DataFrame] = None) -> str:
    what = "churners" if ev.get("target", "churn") == "churn" else "upgraders"
    L = [f"Model harness summary: {ev['model']}  (target: {ev.get('target')}, label: {ev['label']})  [SYNTHETIC / SIMULATED]",
         CAVEAT,
         f"Split: {ev['split']}; train n={ev['n_train']}, test n={ev['n']}, test positives={ev['positives']} "
         f"(base rate {ev['base_rate']:.2%})",
         f"Feature prep: {ev['prep_source']}",
         f"ROC AUC {_fmt(ev['auc'])} (oracle true-p AUC on the same test rows: {_fmt(ev['oracle_same_rows']['auc'])}) | "
         f"PR-AUC {_fmt(ev['pr_auc'])} | Brier {ev['brier']:.4f} | ECE {ev['ece']:.4f}",
         f"Top 10%: catches {_fmt(ev['top10_recall'], True)} of {what} (lift {ev['top10_lift']:.2f}x)",
         f"Mean predicted {ev['mean_pred']:.2%} vs observed {ev['base_rate']:.2%}"]
    if "mae_vs_true_p" in ev:
        L.append(f"Vs true synthetic probability: MAE {ev['mae_vs_true_p']:.4f}, Spearman {ev['spearman_vs_true_p']:.3f}")
    if "cv" in ev:
        c = ev["cv"]
        L.append(f"{c['k']}-fold CV: AUC {c['auc_mean']:.3f} ± {c['auc_std']:.3f} (oracle {_fmt(c['oracle_auc_mean'])}), "
                 f"PR-AUC {c['pr_auc_mean']:.3f} ± {c['pr_auc_std']:.3f}, top-10% recall {c['top10_recall_mean']:.1%}")
    L.append("Reliability bins (mean predicted -> observed):")
    for b in ev["calibration_bins"]:
        L.append(f"  bin {b['bin']:>2} n={b['n']:>4}  {b['mean_pred']:.3%} -> {b['observed_rate']:.3%}")
    if personas is not None and len(personas):
        L.append(f"Persona check (PROVISIONAL; labels may be regenerated; {personas['rule'].dropna().iloc[0] if 'rule' in personas else ''}):")
        for _, r in personas.iterrows():
            L.append(f"  {r['account_id']} expect {r['expected']:<4} p={r.get('score', float('nan')):.4f} "
                     f"pct={r.get('percentile_vs_regular', float('nan'))} -> {r['result']}  ({r.get('reason_up_1', '')})")
    return "\n".join(L)


def _jsonable(o):
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if o != o else float(o)
    if isinstance(o, np.integer):
        return int(o)
    return o


def run(models: Optional[List[str]], labels: List[str], write_scores: bool = True, cv: bool = True) -> dict:
    """models=None -> every model registered for each label's target (plus that target's baseline rule).
    Files: backtest_<target>_<label>.csv/.md, eval_<target>_<model>[_<label>].json, summary_<...>.txt,
    harness_scores_<target>_<model>.csv (default label only), persona_check_<target>_<label>.csv."""
    out = Path(CONFIG["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    result = {}
    for label in labels:
        tgt = target_of(label)
        default = TARGETS[tgt]["default_label"]
        suffix = "" if label == default else f"_{label}"
        mlist = [m for m in (models or list_models(tgt)) if models is None or tgt in _TARGETS_OF.get(m, ("churn",))
                 or m == TARGETS[tgt]["rule"]]
        if not mlist:
            print(f"[model_harness] no requested model is registered for target {tgt}; skipping {label}")
            continue
        data = load_data(label)
        bt = backtest(mlist, label=label, cv=cv)
        bt.to_csv(out / f"backtest_{tgt}_{label}.csv", index=False)
        md = backtest_markdown(bt)
        (out / f"backtest_{tgt}_{label}.md").write_text(md + "\n")
        print(md, "\n")
        pcs = []
        for name in bt["model"]:
            if name == "oracle_true_p":
                continue
            ev = bt.attrs["evals"].get(name) or evaluate(name, cv=cv, data=data)
            fitted = fit_full(name, data=data)
            pc = persona_check(name, label=label, fitted=fitted)
            pcs.append(pc)
            ev["persona_check"] = {"status": "provisional", "rows": pc.to_dict("records")}
            (out / f"eval_{tgt}_{name}{suffix}.json").write_text(json.dumps(_jsonable(ev), indent=2))
            (out / f"summary_{tgt}_{name}{suffix}.txt").write_text(summary_text(ev, pc) + "\n")
            if write_scores and label == default:
                sc = score_accounts(name, label=label, fitted=fitted)
                sc.to_csv(out / f"harness_scores_{tgt}_{name}.csv", index=False)
        pc_all = pd.concat(pcs, ignore_index=True)
        pc_all.to_csv(out / f"persona_check_{tgt}_{label}.csv", index=False)
        print(f"Persona check ({tgt}/{label}, PROVISIONAL, {pc_all['rule'].dropna().iloc[0]}): result (percentile)")
        pc_all["cell"] = pc_all["result"] + " (" + pc_all["percentile_vs_regular"].astype(str) + ")"
        print(pc_all.pivot(index="account_id", columns="model", values="cell").to_string(), "\n")
        result[label] = {"backtest": bt, "personas": pc_all}
    up = near_or_over_data_cap()
    up.to_csv(out / "harness_near_or_over_data_cap.csv", index=False)
    lit = near_or_over_data_cap(basis="account")["near_or_over_data_cap"].sum()
    print(f"'Near or over data cap' rule: {int(up.near_or_over_data_cap.sum())} accounts flagged (per-line basis, default); "
          f"household-total basis would flag {int(lit)}. SYNTHETIC.")
    print(CAVEAT)
    print(f"outputs written to {out}")
    return result


def main(argv=None):
    load_plugins()
    ap = argparse.ArgumentParser(description="Model-agnostic churn/upgrade harness (SYNTHETIC data).")
    ap.add_argument("--model", action="append", help=f"model name (repeatable); registered: {list_models()}")
    ap.add_argument("--all", action="store_true",
                    help="every registered model, churn (churn_90d + toy_churn) AND upgrade (upgrade_90d), + --uplift")
    ap.add_argument("--target", choices=list(TARGETS), help="churn | upgrade (default: churn, or both with --all)")
    ap.add_argument("--label", choices=list(LABEL_CHOICES), help="label column (overrides --target default)")
    ap.add_argument("--uplift", action="store_true", help="run Model C uplift / policy evaluation (uplift_eval.py)")
    ap.add_argument("--data", choices=list(DATASETS), help="training/eval dataset: real (default) | scaled (50k SYN)")
    ap.add_argument("--scaled-to-real", action="store_true",
                    help="extra eval: train on scaled 50k, test on the real 5k (writes eval_scaled_to_real_*.json)")
    ap.add_argument("--include-enrichment", action="store_true", help="keep enrichment columns in X (default: drop)")
    ap.add_argument("--no-scores", action="store_true", help="skip harness_scores_<target>_<model>.csv")
    ap.add_argument("--no-cv", action="store_true", help="skip k-fold CV (faster)")
    a = ap.parse_args(argv)
    if a.data:
        CONFIG["data"] = a.data
    if a.include_enrichment:
        CONFIG["include_enrichment"] = True
    if not (a.all or a.model or a.uplift or a.target or a.label or a.scaled_to_real):
        ap.error("pass --all, --target T, --model NAME and/or --uplift")
    if a.all or ((a.model or a.target or a.label) and not a.scaled_to_real):
        models = a.model or None   # None = every model registered for the target
        if a.label:
            labels = [a.label]
        elif a.target:
            labels = TARGETS[a.target]["labels"]
        elif a.all:
            labels = TARGETS["churn"]["labels"] + TARGETS["upgrade"]["labels"]
        else:
            labels = [CONFIG["label"]]
        run(models, labels, write_scores=not a.no_scores, cv=not a.no_cv)
    if a.scaled_to_real:
        out = Path(CONFIG["out_dir"])
        labels_s2r = [a.label] if a.label else (TARGETS[a.target]["labels"][:1] if a.target
                                                  else ["churn_90d", "upgrade_90d"])
        rows = []
        for lab in labels_s2r:
            for name in (a.model or list_models(target_of(lab))):
                r = evaluate_scaled_to_real(name, label=lab)
                (out / f"eval_scaled_to_real_{target_of(lab)}_{name}.json").write_text(json.dumps(_jsonable(r), indent=2))
                rows.append({k: r[k] for k in ("model", "label", "auc", "oracle_same_rows_auc", "pr_auc", "brier",
                                                "top10_recall", "top10_lift", "n_train", "n")})
        t = pd.DataFrame(rows)
        t.to_csv(out / "eval_scaled_to_real.csv", index=False)
        print("Train on scaled 50k SYN -> test on real 5k (SYNTHETIC):")
        print(t.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    if a.uplift or a.all:
        _ue.run_all(out_dir=CONFIG["out_dir"])


if __name__ == "__main__":
    # Run through the canonical module object ('model_harness') so plugins that `import model_harness`
    # (churn_model.py) register into the same registry the CLI uses.
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import model_harness as _canonical  # noqa: E402
    _canonical.main()
