"""Model C hooks: uplift models + uplift / policy evaluation.  SYNTHETIC unless labeled 'public Orange Belgium'.

Reads tm-offers' long-format file natively (harness/out/uplift.csv; one row per account x eligible action,
including do nothing). Contract (tm-offers' columns, validated by load_uplift):
    account_id        str
    action            str     eligible action; the control arm is "do nothing" (also accepts do_nothing / none)
    split             str     train | test (evaluation uses test only)
    treated           0/1     exactly one treated row per account (the arm the account was randomized to)
    propensity        float   P(this arm) = 1 / n_eligible_arms
    outcome_stay_90d  0/1     only on the treated row; 1 = STAYED (higher = better)
    uplift_hat        float   P(stay|action) - P(stay|do nothing); 0 for do nothing
  optional:
    net_value_hat     float   expected net $ value of the action
    true_uplift       float   simulator ground truth (evaluation only, never for picking)
    pick_uplift/pick_ev 0/1   policy pick flags (one per account)
    synthetic         1
This module never writes uplift.csv or policy_eval.csv; it writes out/uplift_eval_summary.json/.md.

Public surface (re-exported by model_harness):
    class UpliftModel             fit(X, treatment, y) -> self; predict_uplift(X) -> (n,) array for one treatment
                                  arm, or DataFrame (n x non-control actions) for several
    TLearner(estimator_factory)   two-model / multi-model baseline (one classifier per arm)
    register_uplift_model(name, factory); get_uplift_model(name); list_uplift_models()
    load_uplift(path=None)        -> validated long frame
    uplift_curve / qini_curve / auuc / qini_coefficient     binary treatment-vs-control metrics
    action_curves(df)             per action vs do nothing + pooled 'best action' curve
    policy_value(df, picks, method='snipw'|'ipw'|'dm'|'dr')  off-policy value on split == 'test'
    compare_policies(df)          do nothing / treat everyone / top-k by churn risk / random / pick_* / oracle
    simulate_uplift_frame(...)    SYNTHETIC randomized multi-arm data with known true uplift (same schema)
    load_orange_belgium(path)     public Orange Belgium churn-uplift RCT (OpenML 45580, CC BY-NC-ND; read in
                                  place from <repo>/../raw or $MH_ORANGE_ARFF, never copied or committed)
    run_all(out_dir)              everything above -> out/uplift_eval_summary.json/.md
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

HERE = Path(__file__).resolve().parent
UPLIFT_CONFIG = {
    "uplift_path": os.environ.get("MH_UPLIFT_CSV", str(HERE / "out" / "uplift.csv")),
    "orange_path": os.environ.get("MH_ORANGE_ARFF",
                                  str(HERE.parent.parent / "raw" / "orange_belgium_churn_uplift_openml45580.arff")),
    "churn_scores_path": os.environ.get("MH_CHURN_SCORES", str(HERE / "out" / "churn_scores.csv")),
    "outcome_col": "outcome_stay_90d",
    "higher_is_better": True,
    "n_points": 101,
    "seed": 42,
    "topk_default_frac": 0.20,
}
CONTROL_NAMES = ("do nothing", "do_nothing", "none")
REQUIRED = ["account_id", "action", "split", "treated", "propensity", "uplift_hat"]
OPTIONAL = ["net_value_hat", "true_uplift", "pick_uplift", "pick_ev", "synthetic"]
CAVEAT = ("SYNTHETIC/SIMULATED unless labeled 'public Orange Belgium dataset'. Simulated treatment responses "
          "test the evaluation pipeline, not real-world offer performance.")


class UpliftDataError(ValueError):
    pass


# ============================================================================================ models
class UpliftModel:
    """fit(X, treatment, y): treatment = arm label per row (control = 0 or 'do nothing'); y = good outcome (1).
    predict_uplift(X): P(y=1 | arm) - P(y=1 | control). (n,) array if exactly one non-control arm was seen,
    else DataFrame with one column per non-control arm."""
    name = "base"

    def fit(self, X, treatment, y) -> "UpliftModel":
        raise NotImplementedError

    def predict_uplift(self, X):
        raise NotImplementedError


def _is_control(v) -> bool:
    return (isinstance(v, str) and v.strip().lower() in CONTROL_NAMES) or (not isinstance(v, str) and v == 0)


class TLearner(UpliftModel):
    """Two-model (T-learner) baseline: one classifier per arm, uplift = p_arm - p_control."""

    def __init__(self, estimator_factory: Callable = None, name: str = "t_learner_logreg"):
        self.factory = estimator_factory or (lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=3000)))
        self.name = name

    def fit(self, X, treatment, y):
        X = np.asarray(X, float)
        t = np.asarray(treatment, dtype=object)
        y = np.asarray(y).astype(int)
        ctrl = np.array([_is_control(v) for v in t])
        if ctrl.sum() == 0:
            raise UpliftDataError("TLearner needs control rows (treatment 0 or 'do nothing')")
        self.models_ = {"__control__": self._fit_one(X[ctrl], y[ctrl])}
        self.arms_ = [a for a in pd.unique(t[~ctrl])]
        for a in self.arms_:
            m = t == a
            self.models_[a] = self._fit_one(X[m], y[m])
        return self

    def _fit_one(self, X, y):
        if len(np.unique(y)) < 2:       # degenerate arm: constant rate
            return float(y.mean())
        return self.factory().fit(X, y)

    @staticmethod
    def _p(m, X):
        return np.full(len(X), m) if isinstance(m, float) else m.predict_proba(X)[:, 1]

    def predict_uplift(self, X):
        X = np.asarray(X, float)
        p0 = self._p(self.models_["__control__"], X)
        out = {a: self._p(self.models_[a], X) - p0 for a in self.arms_}
        if len(out) == 1:
            return next(iter(out.values()))
        return pd.DataFrame(out)


_UPLIFT_REGISTRY: Dict[str, Callable[[], UpliftModel]] = {}


def register_uplift_model(name: str, factory: Callable[[], UpliftModel]) -> None:
    if not callable(factory):
        raise TypeError("factory must be callable")
    _UPLIFT_REGISTRY[name] = factory


def get_uplift_model(name: str) -> UpliftModel:
    if name not in _UPLIFT_REGISTRY:
        raise KeyError(f"unknown uplift model {name!r}; registered: {list(_UPLIFT_REGISTRY)}")
    m = _UPLIFT_REGISTRY[name]()
    m.name = name
    return m


def list_uplift_models() -> List[str]:
    return list(_UPLIFT_REGISTRY)


register_uplift_model("t_learner_logreg", lambda: TLearner(name="t_learner_logreg"))
register_uplift_model("t_learner_hgb", lambda: TLearner(lambda: HistGradientBoostingClassifier(
    max_iter=150, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=50, random_state=42), "t_learner_hgb"))


# ============================================================================================ loading
def load_uplift(path=None, df: Optional[pd.DataFrame] = None, outcome_col: Optional[str] = None,
                higher_is_better: Optional[bool] = None) -> pd.DataFrame:
    """Read + validate tm-offers' long-format uplift file. Adds: is_control, y (outcome, flipped if lower is
    better). Clear errors on schema problems; never modifies the file."""
    outcome_col = outcome_col or UPLIFT_CONFIG["outcome_col"]
    hib = UPLIFT_CONFIG["higher_is_better"] if higher_is_better is None else higher_is_better
    if df is None:
        p = Path(path or UPLIFT_CONFIG["uplift_path"])
        if not p.exists():
            raise UpliftDataError(f"uplift file not found at {p}")
        df = pd.read_csv(p)
    df = df.copy()
    missing = [c for c in REQUIRED + [outcome_col] if c not in df.columns]
    if missing:
        raise UpliftDataError(f"uplift data is not in the Model C long format: missing {missing}; "
                              f"has {list(df.columns)[:20]}")
    if not set(pd.unique(df["treated"].dropna())) <= {0, 1}:
        raise UpliftDataError("treated must be 0/1")
    nt = df.groupby("account_id")["treated"].sum()
    if (nt != 1).any():
        bad = nt[nt != 1].index[:5].tolist()
        raise UpliftDataError(f"each account needs exactly one treated row; offenders e.g. {bad}")
    if df.duplicated(["account_id", "action"]).any():
        raise UpliftDataError("duplicate (account_id, action) rows")
    df["is_control"] = df["action"].astype(str).str.strip().str.lower().isin(CONTROL_NAMES)
    nc = df.groupby("account_id")["is_control"].sum()
    if (nc != 1).any():
        raise UpliftDataError(f"each account needs exactly one control ('do nothing') row; "
                              f"offenders e.g. {nc[nc != 1].index[:5].tolist()}")
    tr = df[df["treated"] == 1]
    if tr[outcome_col].isna().any():
        raise UpliftDataError(f"{outcome_col} must be present on every treated row")
    if ((tr["propensity"] <= 0) | (tr["propensity"] > 1)).any():
        raise UpliftDataError("propensity must be in (0, 1]")
    if not set(pd.unique(df["split"].dropna())) <= {"train", "test"}:
        raise UpliftDataError("split must be 'train' or 'test'")
    if df.groupby("account_id")["split"].nunique().max() > 1:
        raise UpliftDataError("split must be constant within an account")
    y = df[outcome_col].astype(float)
    df["y"] = y if hib else -y
    for c in ("pick_uplift", "pick_ev"):
        if c in df.columns:
            n = df.groupby("account_id")[c].sum()
            if (n > 1).any():
                raise UpliftDataError(f"{c} flags more than one action for some accounts")
    return df


def account_table(df: pd.DataFrame) -> pd.DataFrame:
    """One row per account: treated_action, propensity, y, split."""
    t = df[df["treated"] == 1].set_index("account_id")
    return pd.DataFrame({"treated_action": t["action"], "propensity": t["propensity"].astype(float),
                         "y": t["y"].astype(float), "split": t["split"],
                         "treated_is_control": t["is_control"]})


def wide(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """account x action matrix of `col` (NaN = not eligible)."""
    return df.pivot(index="account_id", columns="action", values=col)


def control_name(df: pd.DataFrame) -> str:
    return df.loc[df["is_control"], "action"].iloc[0]


# ============================================================================================ binary metrics
def uplift_curve(y, t, score, n_points: Optional[int] = None, seed: Optional[int] = None) -> pd.DataFrame:
    """Cumulative uplift by targeting the top-k by score. t = 1 treated / 0 control.
    gain(k) = (mean_y_treated(top k) - mean_y_control(top k)) * k   (incremental good outcomes)
    qini(k) = Y_t(k) - Y_c(k) * N_t(k) / N_c(k)
    Ties in score are broken at random (seeded)."""
    n_points = n_points or UPLIFT_CONFIG["n_points"]
    rng = np.random.default_rng(UPLIFT_CONFIG["seed"] if seed is None else seed)
    y, t, s = np.asarray(y, float), np.asarray(t, int), np.asarray(score, float)
    order = np.lexsort((rng.random(len(s)), -s))
    y, t = y[order], t[order]
    nt, nc = np.cumsum(t), np.cumsum(1 - t)
    yt, yc = np.cumsum(y * t), np.cumsum(y * (1 - t))
    with np.errstate(divide="ignore", invalid="ignore"):
        gain = np.where((nt > 0) & (nc > 0), (yt / nt - yc / nc) * np.arange(1, len(y) + 1), 0.0)
        qini = np.where(nc > 0, yt - yc * nt / nc, yt)
    n = len(y)
    idx = np.unique(np.clip(np.round(np.linspace(0, n, n_points)).astype(int) - 1, 0, n - 1))
    return pd.DataFrame({"frac": (idx + 1) / n, "k": idx + 1, "n_t": nt[idx], "n_c": nc[idx],
                         "gain": gain[idx], "qini": qini[idx]})


def qini_curve(y, t, score, **kw) -> pd.DataFrame:
    return uplift_curve(y, t, score, **kw)[["frac", "k", "qini"]]


def auuc(curve: pd.DataFrame, n: int) -> float:
    """Area under the uplift (gain) curve per account, minus the random-targeting line. ~0 for random scores."""
    rand = curve["frac"] * curve["gain"].iloc[-1]
    return float(np.trapezoid(curve["gain"] - rand, curve["frac"]) / n)


def qini_coefficient(curve: pd.DataFrame, n: int) -> float:
    """Area between the Qini curve and the random line, per account. ~0 for random, > 0 if the score ranks
    persuadable accounts first (units: incremental good outcomes per account)."""
    rand = curve["frac"] * curve["qini"].iloc[-1]
    return float(np.trapezoid(curve["qini"] - rand, curve["frac"]) / n)


def binary_uplift_metrics(y, t, score, **kw) -> dict:
    c = uplift_curve(y, t, score, **kw)
    n = len(np.asarray(y))
    t = np.asarray(t, int)
    y = np.asarray(y, float)
    ate = float(y[t == 1].mean() - y[t == 0].mean()) if t.any() and (1 - t).any() else float("nan")
    top = c.iloc[(c["frac"] - 0.2).abs().argmin()]
    return {"n": n, "n_treated": int(t.sum()), "n_control": int((1 - t).sum()), "ate": ate,
            "auuc": auuc(c, n), "qini_coefficient": qini_coefficient(c, n),
            "gain_at_top20pct_per_account": float(top["gain"] / n), "curve": c}


# ============================================================================================ multi-arm curves
def action_curves(df: pd.DataFrame, split: str = "test", score_col: str = "uplift_hat") -> Dict[str, dict]:
    """Per action vs do nothing: accounts eligible for the action whose treated arm is that action or do
    nothing (within those, assignment is 50/50 because propensities are equal), scored by that action's
    score_col. Plus a pooled 'best_action' curve: score = max score over non-control actions, treated = the
    account got its argmax action, control = got do nothing."""
    d = df if split is None else df[df["split"] == split]
    acc = account_table(d)
    S = wide(d, score_col)
    ctrl = control_name(d)
    res = {}
    for a in [c for c in S.columns if c != ctrl]:
        elig = S[a].notna()
        ids = acc.index[acc.index.isin(S.index[elig]) & acc["treated_action"].isin([a, ctrl])]
        if len(ids) < 20:
            continue
        sub = acc.loc[ids]
        t = (sub["treated_action"] == a).astype(int)
        if t.sum() == 0 or t.sum() == len(t):
            continue
        res[a] = binary_uplift_metrics(sub["y"], t, S.loc[ids, a])
    Sn = S.drop(columns=[ctrl])
    has = Sn.notna().any(axis=1)
    best = Sn[has].idxmax(axis=1)
    bscore = Sn[has].max(axis=1)
    a2 = acc.loc[best.index]
    keep = (a2["treated_action"] == best) | a2["treated_is_control"]
    if keep.sum() >= 20:
        t = (a2.loc[keep, "treated_action"] == best[keep]).astype(int)
        res["best_action"] = binary_uplift_metrics(a2.loc[keep, "y"], t, bscore[keep])
    return res


# ============================================================================================ policy value
def picks_from_flags(df: pd.DataFrame, col: str) -> pd.Series:
    """account -> action from a pick flag column; accounts with no flag get do nothing."""
    ctrl = control_name(df)
    p = df[df[col] == 1].set_index("account_id")["action"]
    return p.reindex(df["account_id"].unique()).fillna(ctrl)


def policy_value(df: pd.DataFrame, picks, method: str = "snipw", split: Optional[str] = "test",
                 score_col: str = "uplift_hat") -> dict:
    """Off-policy value of a deterministic policy (account -> action) from randomized data.
    ipw   = mean( 1[T=pi] * y / propensity )
    snipw = sum( 1[T=pi] * y / propensity ) / sum( 1[T=pi] / propensity )      (self-normalised)
    dm    = mu0 + mean( score_col[pi] ),  mu0 = SNIPW value of do nothing (direct method on uplift_hat)
    dr    = dm + mean( 1[T=pi] / propensity * (y - (mu0 + score_col[T])) )
    Also: share treated, gain vs do nothing (same estimator), and true expected gain vs do nothing
    (= mean true_uplift[pi]) when the simulator's true_uplift column exists."""
    d = df if split is None else df[df["split"] == split]
    acc = account_table(d)
    ctrl = control_name(d)
    if isinstance(picks, dict):
        picks = pd.Series(picks)
    picks = picks.reindex(acc.index).fillna(ctrl)
    S = wide(d, score_col).reindex(acc.index)
    elig = S.notna()
    # ineligible picks fall back to do nothing (can't take an action the account isn't eligible for)
    ok = np.array([bool(elig.at[i, a]) if a in elig.columns else False for i, a in picks.items()])
    picks = picks.where(ok, ctrl)
    match = (acc["treated_action"] == picks).astype(float)
    w = match / acc["propensity"]
    y = acc["y"]
    n = len(acc)

    def snipw_of(wv):
        return float((wv * y).sum() / wv.sum()) if wv.sum() > 0 else float("nan")

    ipw = float((w * y).sum() / n)
    ipw_se = float((w * y).std(ddof=1) / np.sqrt(n))
    snipw = snipw_of(w)
    w0 = (acc["treated_is_control"]).astype(float) / acc["propensity"]
    mu0 = snipw_of(w0)
    s_pick = np.array([S.at[i, a] for i, a in picks.items()], float)
    s_pick = np.nan_to_num(s_pick)
    s_treat = np.nan_to_num(np.array([S.at[i, a] for i, a in acc["treated_action"].items()], float))
    dm = float(mu0 + s_pick.mean())
    dr = float(dm + (w * (y - (mu0 + s_treat))).mean())
    val = {"ipw": ipw, "snipw": snipw, "dm": dm, "dr": dr}[method]
    out = {"method": method, "value": val, "ipw": ipw, "ipw_se": ipw_se, "snipw": snipw, "dm": dm, "dr": dr,
           "do_nothing_value_snipw": mu0, "gain_vs_do_nothing": (snipw - mu0) if method == "snipw" else val - mu0,
           "share_treated": float((picks != ctrl).mean()), "n_accounts": n, "n_matched": int(match.sum())}
    if "true_uplift" in d.columns:
        T = wide(d, "true_uplift").reindex(acc.index)
        tu = np.nan_to_num(np.array([T.at[i, a] for i, a in picks.items()], float))
        out["true_gain_vs_do_nothing"] = float(tu.mean())     # exact expected extra stays per account
    return out


def _argmax_rows(S: pd.DataFrame, ctrl: str):
    """Row-wise (argmax column, max value); rows with no eligible (all-NaN) column -> (ctrl, NaN)."""
    has = S.notna().any(axis=1)
    best = pd.Series(ctrl, index=S.index, dtype=object)
    val = pd.Series(np.nan, index=S.index)
    if has.any():
        best[has] = S[has].idxmax(axis=1)
        val[has] = S[has].max(axis=1)
    return best, val


def _risk_scores(ids) -> Optional[pd.Series]:
    p = Path(UPLIFT_CONFIG["churn_scores_path"])
    if not p.exists():
        return None
    s = pd.read_csv(p)
    if "account_id" not in s or "p_churn_90d" not in s:
        return None
    return s.set_index("account_id")["p_churn_90d"].reindex(ids)


def compare_policies(df: pd.DataFrame, split: str = "test", risk: Optional[pd.Series] = None,
                     extra: Optional[Dict[str, pd.Series]] = None, seed: Optional[int] = None) -> pd.DataFrame:
    """Policies: do_nothing; treat_everyone (random eligible non-control action for every account);
    random (random eligible arm incl. do nothing); top_k_by_churn_risk (top-k accounts by p_churn_90d get
    their best uplift_hat action, k = number treated by pick_uplift, else 20%); uplift_hat_positive
    (argmax uplift_hat if > 0); pick_uplift / pick_ev flags if present; oracle_true_uplift if true_uplift
    exists. Values are SNIPW (with IPW, its SE, DM and DR alongside)."""
    rng = np.random.default_rng(UPLIFT_CONFIG["seed"] if seed is None else seed)
    d = df[df["split"] == split] if split else df
    ctrl = control_name(d)
    S = wide(d, "uplift_hat")
    ids = S.index
    elig_non = S.drop(columns=[ctrl]).notna()
    pol: Dict[str, pd.Series] = {"do_nothing": pd.Series(ctrl, index=ids)}

    def rand_choice(row_mask, include_ctrl):
        opts = list(row_mask.index[row_mask.values]) + ([ctrl] if include_ctrl else [])
        return opts[rng.integers(len(opts))] if opts else ctrl

    pol["treat_everyone"] = pd.Series([rand_choice(elig_non.loc[i], False) for i in ids], index=ids)
    pol["random"] = pd.Series([rand_choice(elig_non.loc[i], True) for i in ids], index=ids)
    Sn = S.drop(columns=[ctrl])
    best, bval = _argmax_rows(Sn, ctrl)
    pol["uplift_hat_positive"] = best.where(bval > 0, ctrl)
    for c in ("pick_uplift", "pick_ev"):
        if c in d.columns:
            pol[c] = picks_from_flags(d, c)
    k_ref = pol.get("pick_uplift", pol["uplift_hat_positive"])
    k = int((k_ref != ctrl).sum()) or int(round(UPLIFT_CONFIG["topk_default_frac"] * len(ids)))
    r = risk if risk is not None else _risk_scores(ids)
    if r is not None and r.notna().any():
        top = r.reindex(ids).fillna(-1).sort_values(ascending=False).index[:k]
        tk = pd.Series(ctrl, index=ids, dtype=object)
        tk.loc[top] = best.loc[top]
        pol["top_k_by_churn_risk"] = tk
    if "true_uplift" in d.columns:
        T = wide(d, "true_uplift").drop(columns=[ctrl])
        tb, tv = _argmax_rows(T, ctrl)
        pol["oracle_true_uplift"] = tb.where(tv > 0, ctrl)
    for name, s in (extra or {}).items():
        pol[name] = s
    rows = []
    for name, s in pol.items():
        v = policy_value(d, s, "snipw", split=None)
        rows.append({"policy": name, **{k2: v[k2] for k2 in v if k2 != "method"}})
    out = pd.DataFrame(rows)
    out.attrs["k_top"] = k
    return out


def uplift_sanity(df: pd.DataFrame, split: str = "test") -> dict:
    """Correlation of uplift_hat with true_uplift on non-control rows (simulator ground truth)."""
    if "true_uplift" not in df.columns:
        return {}
    d = df[(~df["is_control"]) & ((df["split"] == split) if split else True)]
    return {"pearson_uplift_hat_vs_true": float(d["uplift_hat"].corr(d["true_uplift"])),
            "spearman_uplift_hat_vs_true": float(d["uplift_hat"].corr(d["true_uplift"], method="spearman")),
            "n_rows": int(len(d))}


# ============================================================================================ simulator
def simulate_uplift_frame(n: int = 6000, actions: Iterable[str] = ("do nothing", "$25 care credit",
                          "fix-first callback", "step-up plan"), noise: float = 0.03, seed: int = 0,
                          test_frac: float = 0.5, eligible_p: float = 0.75, score: str = "noisy_truth"):
    """SYNTHETIC randomized multi-arm data in tm-offers' schema, with known true uplift.
    score: 'noisy_truth' (uplift_hat = true + N(0, noise)), 'perfect' (= true), 'random' (pure noise).
    Returns (long_df, X) where X has the account features (index = account_id)."""
    rng = np.random.default_rng(seed)
    actions = list(actions)
    ctrl, arms = actions[0], actions[1:]
    ids = np.array([f"SIM-{i:05d}" for i in range(n)])
    X = pd.DataFrame({"billing_pain": rng.random(n), "network_pain": rng.random(n),
                      "heavy_use": rng.random(n), "risk": rng.beta(1.3, 6.0, n)}, index=pd.Index(ids, name="account_id"))
    p_stay0 = 1 - X["risk"].values
    tu = {}
    for j, a in enumerate(arms):
        driver = X.iloc[:, j % 3].values
        # helps when the action matches the account's pain (scaled by risk); sleeping dogs: small harm otherwise
        tu[a] = np.clip(0.6 * X["risk"].values * (driver - 0.55) * 2, -0.08, 0.5)
    rows = []
    split = np.where(rng.random(n) < test_frac, "test", "train")
    for i in range(n):
        el = [ctrl] + [a for a in arms if rng.random() < eligible_p]
        pick = el[rng.integers(len(el))]
        p_true = np.clip(p_stay0[i] + (tu[pick][i] if pick != ctrl else 0.0), 0, 1)
        y = int(rng.random() < p_true)
        for a in el:
            t_u = 0.0 if a == ctrl else float(tu[a][i])
            if score == "perfect":
                u_hat = t_u
            elif score == "random":
                u_hat = 0.0 if a == ctrl else float(rng.normal(0, 0.1))
            else:
                u_hat = 0.0 if a == ctrl else float(t_u + rng.normal(0, noise))
            rows.append({"account_id": ids[i], "action": a, "split": split[i], "treated": int(a == pick),
                         "propensity": 1.0 / len(el), "outcome_stay_90d": float(y) if a == pick else np.nan,
                         "uplift_hat": u_hat, "net_value_hat": u_hat * 1500 - (0 if a == ctrl else 40),
                         "true_uplift": t_u, "synthetic": 1})
    df = pd.DataFrame(rows)
    up = df.loc[df.groupby("account_id")["uplift_hat"].idxmax()]
    df["pick_uplift"] = 0
    sel = up[(up["uplift_hat"] > 0)].index
    df.loc[sel, "pick_uplift"] = 1
    ev = df.loc[df.groupby("account_id")["net_value_hat"].idxmax()]
    df["pick_ev"] = 0
    df.loc[ev[ev["net_value_hat"] > 0].index, "pick_ev"] = 1
    return df, X


# ============================================================================================ Orange Belgium
def load_orange_belgium(path: Optional[str] = None):
    """Public Orange Belgium churn-uplift RCT (OpenML 45580; CC BY-NC-ND). Read in place; never copy/commit.
    Returns (X, t, y_stay) or None if the file is missing. y_stay = 1 - churn (higher = better)."""
    p = Path(path or UPLIFT_CONFIG["orange_path"])
    if not p.exists():
        return None
    names, types, data_line = [], [], None
    with open(p, "r", errors="replace") as fh:
        for i, line in enumerate(fh):
            s = line.strip()
            if s.lower().startswith("@attribute"):
                parts = s.split(None, 2)
                names.append(parts[1].strip("'\""))
                types.append(parts[2].strip().upper())
            elif s.lower().startswith("@data"):
                data_line = i
                break
    if data_line is None:
        raise UpliftDataError(f"{p}: no @DATA section")
    df = pd.read_csv(p, skiprows=data_line + 1, header=None, names=names, quotechar="'",
                     na_values=["?"], low_memory=False)
    if "t" not in df or "y" not in df:
        raise UpliftDataError(f"{p}: expected columns t (treatment) and y (churn)")
    t = df.pop("t").astype(int).values
    y_churn = df.pop("y").astype(int).values
    str_cols = [n for n, ty in zip(names, types) if ty.startswith("STRING") or ty.startswith("{")]
    str_cols = [c for c in str_cols if c in df.columns]
    num = df.drop(columns=str_cols).apply(pd.to_numeric, errors="coerce").fillna(0.0)
    cats = []
    for c in str_cols:
        if df[c].nunique() <= 30:
            cats.append(pd.get_dummies(df[c].astype(str), prefix=c, dtype=float))
    X = pd.concat([num] + cats, axis=1)
    return X, t, 1 - y_churn


def evaluate_orange_belgium(path: Optional[str] = None, seed: int = 42) -> Optional[dict]:
    """T-learner uplift baselines on the public Orange Belgium RCT: 50/50 split stratified on (t, y), Qini/AUUC
    on the test half, and policy values (IPW with the empirical treatment share as propensity)."""
    data = load_orange_belgium(path)
    if data is None:
        return None
    X, t, y = data
    strat = t * 2 + y
    itr, ite = train_test_split(np.arange(len(t)), test_size=0.5, random_state=seed, stratify=strat)
    Xtr, Xte = X.values[itr], X.values[ite]
    res = {"dataset": "public Orange Belgium dataset (OpenML 45580, CC BY-NC-ND; read in place, not committed)",
           "n": int(len(t)), "n_test": int(len(ite)),
           "churn_treated": float(1 - y[t == 1].mean()), "churn_control": float(1 - y[t == 0].mean()),
           "outcome": "stay = 1 - churn (higher = better)", "models": {}}
    pt = t[ite].mean()
    # churn-risk model (ignores treatment) for the top-k-by-risk baseline
    risk_m = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=3000)).fit(Xtr, 1 - y[itr])
    risk = risk_m.predict_proba(Xte)[:, 1]
    yte, tte = y[ite], t[ite]

    def ipw_value(treat_mask):
        # deterministic binary policy: treat where mask; propensity = P(t=1) (randomized)
        m = np.where(treat_mask, tte == 1, tte == 0)
        w = m / np.where(treat_mask, pt, 1 - pt)
        v = float((w * yte).sum() / w.sum())
        se = float((w * yte).std(ddof=1) / np.sqrt(len(yte)))
        return v, se

    base, _ = ipw_value(np.zeros(len(yte), bool))
    for name in list_uplift_models():
        m = get_uplift_model(name).fit(Xtr, t[itr], y[itr])
        u = np.asarray(m.predict_uplift(Xte), float)
        mt = binary_uplift_metrics(yte, tte, u)
        k = max(int((u > 0).sum()), 1)
        pols = {"do_nothing": np.zeros(len(u), bool), "treat_everyone": np.ones(len(u), bool),
                "random_same_share": np.random.default_rng(seed).random(len(u)) < (u > 0).mean(),
                "top_k_by_churn_risk": np.isin(np.arange(len(u)), np.argsort(-risk)[:k]),
                "uplift_positive": u > 0}
        pv = {}
        for pn, mask in pols.items():
            v, se = ipw_value(mask)
            pv[pn] = {"snipw_stay_rate": v, "ipw_se_approx": se, "gain_vs_do_nothing": v - base,
                      "share_treated": float(mask.mean())}
        res["models"][name] = {"auuc": mt["auuc"], "qini_coefficient": mt["qini_coefficient"],
                               "ate_test": mt["ate"], "policies": pv}
    # random-score reference
    rq = binary_uplift_metrics(yte, tte, np.random.default_rng(seed).random(len(yte)))
    res["random_score_reference"] = {"auuc": rq["auuc"], "qini_coefficient": rq["qini_coefficient"]}
    return res


# ============================================================================================ report
def _evaluate_frame(df: pd.DataFrame, label: str) -> dict:
    curves = action_curves(df)
    pol = compare_policies(df)
    return {"label": label,
            "curves": {a: {k: v for k, v in m.items() if k != "curve"} for a, m in curves.items()},
            "policies": pol.to_dict("records"), "k_top": pol.attrs.get("k_top"),
            "sanity": uplift_sanity(df)}


def simulator_validation(seed: int = 0) -> dict:
    """SYNTHETIC: same simulated world scored three ways; perfect > noisy > random (~0) is expected."""
    out = {}
    for sc in ("perfect", "noisy_truth", "random"):
        df, _ = simulate_uplift_frame(score=sc, seed=seed)
        out[sc] = _evaluate_frame(load_uplift(df=df), f"simulator ({sc} uplift_hat) - SYNTHETIC")
    # T-learner fitted on the simulator's train split (validates the UpliftModel interface end to end)
    df, X = simulate_uplift_frame(score="noisy_truth", seed=seed)
    acc = account_table(load_uplift(df=df))
    tr = acc[acc["split"] == "train"]
    m = get_uplift_model("t_learner_logreg").fit(X.loc[tr.index], tr["treated_action"].values, tr["y"].values)
    U = m.predict_uplift(X)
    U.index = X.index
    df2 = df.copy()
    nc = ~df2["action"].isin(CONTROL_NAMES)
    df2.loc[nc, "uplift_hat"] = [U.at[i, a] if a in U.columns else 0.0
                                 for i, a in zip(df2.loc[nc, "account_id"], df2.loc[nc, "action"])]
    up = df2.loc[df2.groupby("account_id")["uplift_hat"].idxmax()]
    df2["pick_uplift"] = 0
    df2.loc[up[up["uplift_hat"] > 0].index, "pick_uplift"] = 1
    out["t_learner_logreg"] = _evaluate_frame(load_uplift(df=df2), "simulator, T-learner (logreg) uplift_hat - SYNTHETIC")
    return out


def _md_policies(rows: List[dict]) -> List[str]:
    L = ["| policy | SNIPW stay rate | gain vs do nothing | IPW (± SE) | DR | share treated | true gain |",
         "|---|---|---|---|---|---|---|"]
    for r in rows:
        tg = r.get("true_gain_vs_do_nothing")
        L.append(f"| {r['policy']} | {r['snipw']:.4f} | {r['gain_vs_do_nothing']:+.4f} | {r['ipw']:.4f} ± "
                 f"{r['ipw_se']:.4f} | {r['dr']:.4f} | {r['share_treated']:.1%} | "
                 f"{'n/a' if tg is None else format(tg, '+.4f')} |")
    return L


def _md_frame(res: dict) -> List[str]:
    L = [f"### {res['label']}", "", "| curve | n | AUUC | Qini coef | gain@top20% /acct | ATE |", "|---|---|---|---|---|---|"]
    for a, m in res["curves"].items():
        L.append(f"| {a} | {m['n']} | {m['auuc']:+.4f} | {m['qini_coefficient']:+.4f} | "
                 f"{m['gain_at_top20pct_per_account']:+.4f} | {m['ate']:+.4f} |")
    L += [""] + _md_policies(res["policies"])
    if res.get("sanity"):
        s = res["sanity"]
        L.append(f"\nuplift_hat vs true_uplift: Pearson {s['pearson_uplift_hat_vs_true']:.3f}, "
                 f"Spearman {s['spearman_uplift_hat_vs_true']:.3f} (n={s['n_rows']} non-control test rows)")
    L.append(f"top_k_by_churn_risk k = {res.get('k_top')}")
    return L + [""]


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if o != o else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def run_all(out_dir: Optional[str] = None) -> dict:
    out = Path(out_dir or HERE / "out")
    out.mkdir(parents=True, exist_ok=True)
    summary = {"caveat": CAVEAT, "contract": {"required": REQUIRED + [UPLIFT_CONFIG["outcome_col"]],
                                              "optional": OPTIONAL, "control": "do nothing"}}
    md = ["# Model C uplift / policy evaluation", "", CAVEAT, ""]
    # 1. tm-offers' file
    try:
        df = load_uplift()
        summary["tm_offers"] = _evaluate_frame(df, "tm-offers out/uplift.csv (SYNTHETIC simulated responses)")
        md += ["## tm-offers uplift.csv (SYNTHETIC)", ""] + _md_frame(summary["tm_offers"])
    except UpliftDataError as e:
        summary["tm_offers"] = {"skipped": str(e)}
        md += ["## tm-offers uplift.csv", "", f"Skipped: {e}", ""]
    # 2. simulator validation
    sim = simulator_validation()
    summary["simulator"] = sim
    md += ["## Simulator validation (SYNTHETIC randomized multi-arm data, known true uplift)", ""]
    for r in sim.values():
        md += _md_frame(r)
    # 3. Orange Belgium
    ob = evaluate_orange_belgium()
    if ob is None:
        summary["orange_belgium"] = {"skipped": f"file not found at {UPLIFT_CONFIG['orange_path']}"}
        md += ["## public Orange Belgium dataset", "", "Skipped: file not found.", ""]
    else:
        summary["orange_belgium"] = ob
        md += ["## public Orange Belgium dataset (real RCT; OpenML 45580, CC BY-NC-ND, read in place)", "",
               f"n={ob['n']} (test half {ob['n_test']}); churn treated {ob['churn_treated']:.2%} vs control "
               f"{ob['churn_control']:.2%}. Outcome = stay.", "",
               "| model | AUUC | Qini coef | test ATE (stay) |", "|---|---|---|---|"]
        for name, m in ob["models"].items():
            md.append(f"| {name} | {m['auuc']:+.5f} | {m['qini_coefficient']:+.5f} | {m['ate_test']:+.4f} |")
        r = ob["random_score_reference"]
        md.append(f"| random score (reference) | {r['auuc']:+.5f} | {r['qini_coefficient']:+.5f} | |")
        for name, m in ob["models"].items():
            md += ["", f"Policies ({name}; SNIPW stay rate, approx IPW SE):", "",
                   "| policy | stay rate | gain vs do nothing | SE | share treated |", "|---|---|---|---|---|"]
            for pn, v in m["policies"].items():
                md.append(f"| {pn} | {v['snipw_stay_rate']:.4f} | {v['gain_vs_do_nothing']:+.4f} | "
                          f"{v['ipw_se_approx']:.4f} | {v['share_treated']:.1%} |")
        md.append("")
    (out / "uplift_eval_summary.json").write_text(json.dumps(_jsonable(summary), indent=2))
    (out / "uplift_eval_summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    print(f"wrote {out / 'uplift_eval_summary.json'} and .md")
    return summary


if __name__ == "__main__":
    run_all()
