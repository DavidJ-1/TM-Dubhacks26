"""Model-agnostic churn harness (Model A lane helpers).  ALL DATA AND NUMBERS ARE SYNTHETIC / SIMULATED.

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
    near_or_over_data_cap(features=None)     -> "near or over data cap" upgrade baseline rule, features only

CLI (from repo root):
    python -m harness.model_harness --all            # every model, both labels, backtest + persona checks
    python -m harness.model_harness --model logreg   # one model
Outputs go to harness/out/ (gitignored): eval_<model>[_<label>].json, summary_<model>[_<label>].txt,
harness_scores_<model>.csv, backtest_<label>.csv/.md, persona_check_<label>.csv.

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

CONFIG = {
    "data_dir": os.environ.get("MH_DATA_DIR", str(HERE / "out")),
    "out_dir": os.environ.get("MH_OUT_DIR", str(HERE / "out")),
    "label": os.environ.get("MH_LABEL", "churn_90d"),   # switch to "toy_churn" in one change
    "test_size": 0.25,
    "seed": 42,
    "cv_k": 5,
    "top_frac": 0.10,
    "rule_threshold": 3,             # '3+ support calls in 90d'
    "persona_high_pct": 90.0,        # persona 'high' = top decile: at/above the 90th percentile of regular accounts
    "persona_low_pct": 50.0,         # persona 'low'  = scores at/below the median of regular accounts
}

CAVEAT = ("CAVEAT: all numbers are SYNTHETIC/SIMULATED. Labels are drawn from a known formula over these same "
          "features, so this tests the pipeline, not real-world accuracy.")

LABEL_CHOICES = {"churn_90d": "p_true_90d", "toy_churn": "toy_p"}   # label -> its oracle probability column
REQUIRED_FEATURE_COLS = ["account_id", "is_persona", "support_90d", "tenure_months", "competitor_research_score",
                         "port_out_inquiry", "app_sessions_30d", "bill_increase_pct"]
REQUIRED_LABEL_COLS = ["account_id", "churn_90d", "p_true_90d", "toy_p", "toy_churn"]
# Anything derived from the label pipeline must never reach X.
LEAKY_COLS = {"churn_90d", "p_true_90d", "monthly_hazard", "toy_p", "toy_churn",
              "label_driver_1", "label_driver_2", "label_driver_3", "churn_90d_x", "churn_90d_y"}
CATEGORICAL = ["segment", "language", "contact_preference", "credit_tier", "discount_group",
               "plan_sku", "plan_family", "plan_tier"]
PERSONA_EXPECT = {"ACC-PERSONA-04": "high", "ACC-PERSONA-21": "high", "ACC-PERSONA-22": "high",
                  "ACC-PERSONA-27": "high", "ACC-PERSONA-10": "low", "ACC-PERSONA-24": "low"}


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


def _load_joined(label: Optional[str] = None, data_dir: Optional[str] = None):
    label = label or CONFIG["label"]
    if label not in LABEL_CHOICES:
        raise HarnessDataError(f"label must be one of {list(LABEL_CHOICES)}, got {label!r}")
    d = Path(data_dir or CONFIG["data_dir"])
    f = _read_csv(d / "features.csv", REQUIRED_FEATURE_COLS, "features.csv")
    lab = _read_csv(d / "labels.csv", REQUIRED_LABEL_COLS, "labels.csv")   # always re-read, never cached
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
    meta = pd.DataFrame({
        "is_persona": f["is_persona"].astype(int).values,
        "support_90d": f["support_90d"].values,
        "oracle_p": lab[LABEL_CHOICES[label]].values,
        "p_true_90d": lab["p_true_90d"].values,
        "toy_p": lab["toy_p"].values,
        "label": label,
        "prep_source": src,
    }, index=X.index)
    y = lab[label].astype(float).rename(label)
    y.index = X.index
    return X, y, meta


def load_data(label: Optional[str] = None, data_dir: Optional[str] = None):
    """-> (X, y, meta) for the 5,000 regular accounts (personas excluded). X index = account_id.
    meta: is_persona, support_90d, oracle_p (true synthetic prob for the chosen label), p_true_90d, toy_p."""
    X, y, meta = _load_joined(label, data_dir)
    reg = meta["is_persona"] == 0
    X, y, meta = X[reg], y[reg], meta[reg]
    if y.isna().any():
        raise HarnessDataError(f"{int(y.isna().sum())} regular accounts have a blank label")
    return X, y.astype(int), meta


def load_personas(label: Optional[str] = None, data_dir: Optional[str] = None):
    X, _, meta = _load_joined(label, data_dir)
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
    if oracle_p is not None:
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
    path = Path(CONFIG["data_dir"]) / "features.csv"
    if not path.exists():
        return pd.DataFrame(index=pd.Index(ids, name="account_id"))
    f = pd.read_csv(path).set_index("account_id")
    return f.reindex(ids)


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


def contributions_to_reasons(contrib: pd.DataFrame, X: pd.DataFrame, k: int = 3, eps: float = 1e-6) -> pd.DataFrame:
    """contrib: rows = accounts, cols = feature groups (one-hot columns already merged); positive raises risk.
    Groups are merged again into tm-churn's reason groups (churn_features.REASON_GROUPS) when available, and
    worded with churn_features.phrase() so harness and Model A speak the same language; else REASONS above."""
    cf = _cf_text()
    if cf is not None:
        contrib = contrib.T.groupby(lambda g: g if g in REASONS and g not in cf._FEATURE_GROUP
                                    else cf.reason_group(g)).sum().T
    raw = _raw_features(X.index)
    raw = raw.combine_first(X) if len(raw.columns) else X
    cats = {g: [c for c in X.columns if _group_of(c) == g] for g in {_group_of(c) for c in X.columns if "=" in c}}

    def text(g, row, xr, risk):
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
    for aid, r in contrib.iterrows():
        row, xr = raw.loc[aid], X.loc[aid]
        s_ = r.sort_values()
        risk = [g for g, v in s_[::-1].items() if v > eps][:k]
        stay = [g for g, v in s_.items() if v < -eps][:k]
        rec = {"account_id": aid}
        for i in range(k):
            rec[f"risk_reason_{i + 1}"] = text(risk[i], row, xr, True) if i < len(risk) else ""
        for i in range(k):
            rec[f"stay_reason_{i + 1}"] = text(stay[i], row, xr, False) if i < len(stay) else ""
        rows.append(rec)
    cols = ["account_id"] + [f"risk_reason_{i + 1}" for i in range(k)] + [f"stay_reason_{i + 1}" for i in range(k)]
    return pd.DataFrame(rows, columns=cols)


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
        return contributions_to_reasons(self.contributions(X), X, k)


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
        return self.estimator.predict_proba(X[self.columns_].values)[:, 1]


class LogRegModel(SklearnChurnModel):
    """Standardised logistic regression. explain() is exact for a linear model: coef * (x - typical), in logit
    units, summed per feature group."""

    def __init__(self, C: float = 0.5):
        super().__init__("logreg", make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=5000)))

    def contributions(self, X):
        sc, lr = self.estimator[0], self.estimator[-1]
        ref = self.reference_.reindex(self.columns_).values
        w = lr.coef_[0] / np.where(sc.scale_ == 0, 1, sc.scale_)
        c = (X[self.columns_].values - ref) * w
        df = pd.DataFrame(c, index=X.index, columns=self.columns_)
        return df.T.groupby(lambda col: _group_of(col)).sum().T


_REGISTRY: Dict[str, Callable[[], ChurnModel]] = {}


def register_model(name: str, factory: Callable[[], ChurnModel]) -> None:
    """Register a factory (zero-arg callable returning a fresh ChurnModel). Re-registering replaces it."""
    if not callable(factory):
        raise TypeError("factory must be callable")
    _REGISTRY[name] = factory


def get_model(name: str) -> ChurnModel:
    if name not in _REGISTRY:
        raise KeyError(f"unknown model {name!r}; registered: {list_models()}")
    m = _REGISTRY[name]()
    m.name = name
    return m


def list_models() -> List[str]:
    return list(_REGISTRY)


register_model("rule_support3", SupportCallsRule)
register_model("logreg", LogRegModel)
register_model("hgb", lambda: SklearnChurnModel("hgb", HistGradientBoostingClassifier(
    max_iter=200, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=40, l2_regularization=1.0,
    random_state=42)))
register_model("rf", lambda: SklearnChurnModel("rf", RandomForestClassifier(
    n_estimators=400, min_samples_leaf=10, max_features="sqrt", n_jobs=-1, random_state=42)))


def _as_model(model) -> ChurnModel:
    return get_model(model) if isinstance(model, str) else model


def _fresh(model) -> ChurnModel:
    """New instance per fit (registry name -> factory; instance -> deep copy)."""
    if isinstance(model, str):
        return get_model(model)
    import copy
    return copy.deepcopy(model)


def _fit(model: ChurnModel, X, y) -> ChurnModel:
    model.fit(X, y)
    if getattr(model, "reference_", None) is None:
        model.set_reference(X)
    p = np.asarray(model.predict_proba(X.iloc[:5]))
    if p.shape != (min(5, len(X)),):
        raise HarnessDataError(f"{model.name}.predict_proba must return shape (n,), got {p.shape}")
    return model


# --------------------------------------------------------------------------------------------- evaluation
def _ids_hash(ids) -> str:
    import hashlib
    return hashlib.sha256(",".join(map(str, sorted(ids))).encode()).hexdigest()[:12]


def evaluate(model, label: Optional[str] = None, cv: bool = True, data=None) -> dict:
    """Fit on the stratified holdout's train side, score the test side; plus stratified k-fold CV summary."""
    X, y, meta = data if data is not None else load_data(label)
    label = meta["label"].iloc[0]
    name = model if isinstance(model, str) else model.name
    Xtr, Xte, ytr, yte, mtr, mte = holdout_split(X, y, meta)
    m = _fit(_fresh(model), Xtr, ytr)
    p = np.asarray(m.predict_proba(Xte), float)
    res = {"model": name, "label": label, "split": "stratified_account_holdout (single snapshot 2026-10-01; not temporal)",
           "test_size": CONFIG["test_size"], "seed": CONFIG["seed"], "n_train": int(len(Xtr)),
           "prep_source": meta["prep_source"].iloc[0], "caveat": CAVEAT}
    res.update(compute_metrics(yte, p, mte["oracle_p"].values))
    om = compute_metrics(yte, mte["oracle_p"].values)
    res["test_ids_hash"] = _ids_hash(Xte.index)
    res["oracle_same_rows"] = {k: om[k] for k in ("auc", "pr_auc", "brier", "top10_recall", "top10_lift")}
    res["auc_gap_to_oracle"] = res["auc"] - om["auc"]
    if cv:
        folds = []
        for tr, te in cv_folds(X, y):
            mm = _fit(_fresh(model), X.iloc[tr], y.iloc[tr])
            pp = mm.predict_proba(X.iloc[te])
            mt = compute_metrics(y.iloc[te], pp)
            row = {k: mt[k] for k in ("auc", "pr_auc", "brier", "top10_recall", "top10_lift")}
            row["oracle_auc"] = float(roc_auc_score(y.iloc[te], meta["oracle_p"].iloc[te]))
            folds.append(row)
        f = pd.DataFrame(folds)
        res["cv"] = {"k": CONFIG["cv_k"], **{f"{c}_mean": float(f[c].mean()) for c in f},
                     **{f"{c}_std": float(f[c].std()) for c in f}}
    return res


def oracle_metrics(label: Optional[str] = None, data=None) -> dict:
    """Ceiling: the true synthetic probability scored on the same holdout test side."""
    X, y, meta = data if data is not None else load_data(label)
    _, _, _, yte, _, mte = holdout_split(X, y, meta)
    res = {"model": "oracle_true_p", "label": meta["label"].iloc[0], "caveat": CAVEAT}
    res.update(compute_metrics(yte, mte["oracle_p"].values))
    return res


def backtest(models: Optional[Iterable] = None, label: Optional[str] = None, cv: bool = True) -> pd.DataFrame:
    """Every model side by side with the '3+ support calls in 90d' rule and the oracle ceiling."""
    data = load_data(label)
    models = list(models) if models is not None else list_models()
    names = [m if isinstance(m, str) else m.name for m in models]
    if "rule_support3" not in names:
        models = ["rule_support3"] + models
    rows, evals = [], {}
    for mdl in models:
        r = evaluate(mdl, cv=cv, data=data)
        evals[r["model"]] = r
        rows.append({k: r.get(k) for k in ("model", "label", "auc", "pr_auc", "brier", "ece", "top10_recall",
                                           "top10_lift", "mean_pred", "base_rate", "positives", "n")}
                    | {"oracle_auc_same_rows": r["oracle_same_rows"]["auc"], "auc_gap_to_oracle": r["auc_gap_to_oracle"]}
                    | ({"cv_auc_mean": r["cv"]["auc_mean"], "cv_auc_std": r["cv"]["auc_std"],
                        "cv_oracle_auc_mean": r["cv"]["oracle_auc_mean"],
                        "cv_pr_auc_mean": r["cv"]["pr_auc_mean"], "cv_top10_recall_mean": r["cv"]["top10_recall_mean"]}
                       if cv else {}))
    o = oracle_metrics(data=data)
    orow = {k: o.get(k) for k in ("model", "label", "auc", "pr_auc", "brier", "ece", "top10_recall",
                                  "top10_lift", "mean_pred", "base_rate", "positives", "n")}
    orow.update({"oracle_auc_same_rows": o["auc"], "auc_gap_to_oracle": 0.0})
    if cv:
        oa = [roc_auc_score(data[1].iloc[te], data[2]["oracle_p"].iloc[te]) for _, te in cv_folds(data[0], data[1])]
        orow.update({"cv_auc_mean": float(np.mean(oa)), "cv_auc_std": float(np.std(oa, ddof=1)),
                     "cv_oracle_auc_mean": float(np.mean(oa))})
    orow["oracle_auc_all_regular"] = float(roc_auc_score(data[1], data[2]["oracle_p"]))
    rows.append(orow)
    df = pd.DataFrame(rows)
    rule = df.loc[df.model == "rule_support3"].iloc[0]
    df["auc_vs_rule"] = df["auc"] - rule["auc"]
    df["top10_recall_vs_rule"] = df["top10_recall"] - rule["top10_recall"]
    df.attrs["caveat"] = CAVEAT
    df.attrs["evals"] = evals
    return df


def fit_full(model, label: Optional[str] = None, data=None) -> ChurnModel:
    """Fit on ALL regular accounts (for scoring / personas; evaluation uses evaluate())."""
    X, y, _ = data if data is not None else load_data(label)
    return _fit(_fresh(model), X, y)


def persona_check(model, label: Optional[str] = None, fitted: Optional[ChurnModel] = None,
                  high_pct: Optional[float] = None, low_pct: Optional[float] = None) -> pd.DataFrame:
    """PROVISIONAL. Model fitted on all regular accounts; each persona's score is placed as a percentile of the
    regular accounts' scores. high = pct >= high_pct (default CONFIG persona_high_pct = 90, top decile);
    low = pct <= low_pct (default CONFIG persona_low_pct = 50, at/below median).
    Persona ids map 1:1 to accounts (sandbox personas.persona_id == account_id == ACC-PERSONA-xx)."""
    data = load_data(label)
    m = fitted or fit_full(model, data=data)
    reg_scores = np.asarray(m.predict_proba(data[0]), float)
    Xp, mp = load_personas(label)
    Xp = Xp.loc[[a for a in PERSONA_EXPECT if a in Xp.index]]
    missing = [a for a in PERSONA_EXPECT if a not in Xp.index]
    p = np.asarray(m.predict_proba(Xp), float)
    reasons = m.explain(Xp, k=3).set_index("account_id")
    rows = []
    for aid, s in zip(Xp.index, p):
        pct = float((reg_scores < s).mean() * 100 + (reg_scores == s).mean() * 50)
        exp = PERSONA_EXPECT[aid]
        hp = CONFIG["persona_high_pct"] if high_pct is None else high_pct
        lp = CONFIG["persona_low_pct"] if low_pct is None else low_pct
        ok = pct >= hp if exp == "high" else pct <= lp
        rows.append({"account_id": aid, "model": m.name, "label": data[2]["label"].iloc[0], "expected": exp,
                     "p_churn_90d": s, "percentile_vs_regular": round(pct, 1),
                     "support_90d": float(mp.loc[aid, "support_90d"]),
                     "true_p_90d": float(mp.loc[aid, "p_true_90d"]), "toy_p": float(mp.loc[aid, "toy_p"]),
                     "result": "PASS" if ok else "FAIL", "status": "provisional",
                     "rule": f"high: pct>={hp:g}; low: pct<={lp:g}",
                     "risk_reason_1": reasons.loc[aid, "risk_reason_1"],
                     "stay_reason_1": reasons.loc[aid, "stay_reason_1"]})
    for aid in missing:
        rows.append({"account_id": aid, "model": m.name, "expected": PERSONA_EXPECT[aid], "result": "MISSING",
                     "status": "provisional"})
    return pd.DataFrame(rows)


def score_accounts(model, label: Optional[str] = None, fitted: Optional[ChurnModel] = None) -> pd.DataFrame:
    """tm-churn contract columns for all accounts (regular + personas), fitted on all regular accounts.
    risk_rank 1 = highest risk. Values are SYNTHETIC."""
    data = load_data(label)
    m = fitted or fit_full(model, data=data)
    Xall, _, meta = _load_joined(label)
    p = np.asarray(m.predict_proba(Xall), float)
    df = pd.DataFrame({"account_id": Xall.index, "p_churn_90d": np.round(p, 6)})
    df["risk_rank"] = df["p_churn_90d"].rank(ascending=False, method="first").astype(int)
    df = df.merge(m.explain(Xall, k=3), on="account_id", how="left")
    df["is_persona"] = meta["is_persona"].values
    df["model"] = m.name
    return df.sort_values("risk_rank").reset_index(drop=True)


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


# --------------------------------------------------------------------------------------------- reporting / CLI
def _fmt(x, pct=False):
    if x is None or (isinstance(x, float) and x != x):
        return "n/a"
    return f"{x:.1%}" if pct else f"{x:.3f}"


def backtest_markdown(bt: pd.DataFrame) -> str:
    lab = bt["label"].iloc[0]
    lines = [f"# Backtest ({lab}) - SYNTHETIC / SIMULATED", "", CAVEAT, "",
             "Stratified account-level holdout (25% test, seed 42); single snapshot as of 2026-10-01, not temporal.", "",
             "| model | AUC | oracle AUC (same test rows) | PR-AUC | Brier | top-10% recall | top-10% lift | "
             "CV AUC mean ± std (5-fold) | CV oracle AUC | AUC vs rule |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in bt.iterrows():
        cv = (f"{r['cv_auc_mean']:.3f} ± {r['cv_auc_std']:.3f}"
              if "cv_auc_mean" in r and r.get("cv_auc_mean") == r.get("cv_auc_mean") else "n/a")
        cvo = _fmt(r.get("cv_oracle_auc_mean")) if "cv_oracle_auc_mean" in r else "n/a"
        lines.append(f"| {r['model']} | {_fmt(r['auc'])} | {_fmt(r['oracle_auc_same_rows'])} | {_fmt(r['pr_auc'])} | "
                     f"{r['brier']:.4f} | {_fmt(r['top10_recall'], True)} | {r['top10_lift']:.2f}x | {cv} | {cvo} | "
                     f"{r['auc_vs_rule']:+.3f} |")
    lines += ["", f"Test positives: {int(bt['positives'].iloc[0])} of {int(bt['n'].iloc[0])} "
                  f"(base rate {bt['base_rate'].iloc[0]:.2%}, synthetic). oracle_true_p = the label's true synthetic "
                  "probability (ceiling). Oracle AUC on ALL regular accounts: "
                  f"{bt['oracle_auc_all_regular'].dropna().iloc[0]:.3f}. With ~35 test positives a single holdout is "
                  "noisy; compare each model to the oracle on the same rows and prefer the CV mean."]
    return "\n".join(lines)


def summary_text(ev: dict, personas: Optional[pd.DataFrame] = None) -> str:
    L = [f"Model harness summary: {ev['model']}  (label: {ev['label']})  [SYNTHETIC / SIMULATED]", CAVEAT,
         f"Split: {ev['split']}; train n={ev['n_train']}, test n={ev['n']}, test positives={ev['positives']} "
         f"(base rate {ev['base_rate']:.2%})",
         f"Feature prep: {ev['prep_source']}",
         f"ROC AUC {_fmt(ev['auc'])} (oracle true-p AUC on the same test rows: {_fmt(ev['oracle_same_rows']['auc'])}) | PR-AUC {_fmt(ev['pr_auc'])} | Brier {ev['brier']:.4f} | ECE {ev['ece']:.4f}",
         f"Top 10%: catches {_fmt(ev['top10_recall'], True)} of churners (lift {ev['top10_lift']:.2f}x)",
         f"Mean predicted {ev['mean_pred']:.2%} vs observed {ev['base_rate']:.2%}"]
    if "mae_vs_true_p" in ev:
        L.append(f"Vs true synthetic probability: MAE {ev['mae_vs_true_p']:.4f}, Spearman {ev['spearman_vs_true_p']:.3f}")
    if "cv" in ev:
        c = ev["cv"]
        L.append(f"{c['k']}-fold CV: AUC {c['auc_mean']:.3f} ± {c['auc_std']:.3f} (oracle {c['oracle_auc_mean']:.3f}), PR-AUC {c['pr_auc_mean']:.3f}, "
                 f"top-10% recall {c['top10_recall_mean']:.1%}")
    L.append("Reliability bins (mean predicted -> observed):")
    for b in ev["calibration_bins"]:
        L.append(f"  bin {b['bin']:>2} n={b['n']:>4}  {b['mean_pred']:.3%} -> {b['observed_rate']:.3%}")
    if personas is not None and len(personas):
        L.append("Persona check (PROVISIONAL; labels may be regenerated):")
        for _, r in personas.iterrows():
            L.append(f"  {r['account_id']} expect {r['expected']:<4} p={r.get('p_churn_90d', float('nan')):.3f} "
                     f"pct={r.get('percentile_vs_regular', float('nan'))} -> {r['result']}  ({r.get('risk_reason_1', '')})")
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


def run(models: List[str], labels: List[str], write_scores: bool = True, cv: bool = True) -> dict:
    out = Path(CONFIG["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    default = "churn_90d"
    result = {}
    for label in labels:
        suffix = "" if label == default else f"_{label}"
        data = load_data(label)
        bt = backtest(models, label=label, cv=cv)
        bt.to_csv(out / f"backtest_{label}.csv", index=False)
        md = backtest_markdown(bt)
        (out / f"backtest_{label}.md").write_text(md + "\n")
        print(md, "\n")
        pcs = []
        for name in models:
            ev = bt.attrs["evals"].get(name) or evaluate(name, cv=cv, data=data)
            fitted = fit_full(name, data=data)
            pc = persona_check(name, label=label, fitted=fitted)
            pcs.append(pc)
            ev["persona_check"] = {"status": "provisional", "rows": pc.to_dict("records")}
            (out / f"eval_{name}{suffix}.json").write_text(json.dumps(_jsonable(ev), indent=2))
            (out / f"summary_{name}{suffix}.txt").write_text(summary_text(ev, pc) + "\n")
            if write_scores and label == default:
                sc = score_accounts(name, label=label, fitted=fitted)
                sc.to_csv(out / f"harness_scores_{name}.csv", index=False)
        pc_all = pd.concat(pcs, ignore_index=True)
        pc_all.to_csv(out / f"persona_check_{label}.csv", index=False)
        print(f"Persona check ({label}, PROVISIONAL):")
        print(pc_all.pivot(index="account_id", columns="model", values="result").to_string(), "\n")
        result[label] = {"backtest": bt, "personas": pc_all}
    up = near_or_over_data_cap()
    up.to_csv(out / "harness_near_or_over_data_cap.csv", index=False)
    lit = near_or_over_data_cap(basis="account")["near_or_over_data_cap"].sum()
    print(f"'Near or over data cap' upgrade rule (proxy for 'near cap 2+ months'): {int(up.near_or_over_data_cap.sum())} accounts flagged "
          f"(per-line basis; literal household-total basis would flag {int(lit)}). No upgrade labels exist, so it is "
          "not backtested. SYNTHETIC.")
    print(CAVEAT)
    print(f"outputs written to {out}")
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="Model-agnostic churn harness (SYNTHETIC data).")
    ap.add_argument("--model", action="append", help=f"model name (repeatable); registered: {list_models()}")
    ap.add_argument("--all", action="store_true", help="every registered model, on churn_90d AND toy_churn")
    ap.add_argument("--label", choices=list(LABEL_CHOICES), help="label column (default CONFIG['label'])")
    ap.add_argument("--no-scores", action="store_true", help="skip harness_scores_<model>.csv")
    ap.add_argument("--no-cv", action="store_true", help="skip k-fold CV (faster)")
    a = ap.parse_args(argv)
    if not a.all and not a.model:
        ap.error("pass --all or --model NAME")
    models = list_models() if a.all else a.model
    if a.label:
        labels = [a.label]
    elif a.all:
        labels = ["churn_90d", "toy_churn"]
    else:
        labels = [CONFIG["label"]]
    run(models, labels, write_scores=not a.no_scores, cv=not a.no_cv)


if __name__ == "__main__":
    main()
