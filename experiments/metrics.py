"""Shared metrics for churn experiments. ALL DATA SYNTHETIC.
top10_capture matches harness/compare_strategies.topk_capture (k=round(0.1*n), random tie-break seed 2026)."""
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss


def top_capture(y, s, frac=0.10, seed=2026):
    y = np.asarray(y); s = np.asarray(s, dtype=float)
    k = int(round(frac * len(y)))
    order = np.lexsort((np.random.default_rng(seed).random(len(y)), -s))
    return float(y[order[:k]].sum() / y.sum())


def ece(y, p, n_bins=10, strategy="quantile"):
    """Expected calibration error with equal-count (default) bins; returns (ece, bins DataFrame)."""
    y = np.asarray(y); p = np.asarray(p, dtype=float)
    if strategy == "quantile":
        b = pd.qcut(pd.Series(p).rank(method="first"), n_bins, labels=False).values
    else:
        b = np.minimum((p * n_bins).astype(int), n_bins - 1)
    df = pd.DataFrame({"y": y, "p": p, "b": b}).groupby("b").agg(n=("y", "size"), mean_pred=("p", "mean"), observed=("y", "mean"))
    e = float((df.n * (df.mean_pred - df.observed).abs()).sum() / len(y))
    return e, df.reset_index()


def all_metrics(y, p):
    y = np.asarray(y); p = np.asarray(p, dtype=float)
    return {"auc": roc_auc_score(y, p), "pr_auc": average_precision_score(y, p), "top10": top_capture(y, p),
            "brier": brier_score_loss(y, np.clip(p, 0, 1)), "ece": ece(y, np.clip(p, 0, 1))[0]}


def per_fold(y, p, fid):
    y = np.asarray(y); p = np.asarray(p, dtype=float); fid = np.asarray(fid)
    return pd.DataFrame([{"fold": k, **all_metrics(y[fid == k], p[fid == k])} for k in np.unique(fid)])


def bootstrap_ci(y, p, n_boot=1000, seed=0, stratified=True):
    """95% percentile CI for AUC, PR-AUC and top-10% capture (resampling accounts, stratified by label)."""
    y = np.asarray(y); p = np.asarray(p, dtype=float)
    rng = np.random.default_rng(seed)
    pos, neg = np.where(y == 1)[0], np.where(y == 0)[0]
    out = []
    for _ in range(n_boot):
        i = np.concatenate([rng.choice(pos, len(pos)), rng.choice(neg, len(neg))]) if stratified else rng.choice(len(y), len(y))
        out.append((roc_auc_score(y[i], p[i]), average_precision_score(y[i], p[i]), top_capture(y[i], p[i], seed=int(rng.integers(1e9)))))
    a = np.array(out)
    lo, hi = np.percentile(a, [2.5, 97.5], axis=0)
    return {f"{m}_ci": (float(l), float(h)) for m, l, h in zip(["auc", "pr_auc", "top10"], lo, hi)}


def paired_bootstrap_delta(y, p_new, p_base, n_boot=1000, seed=0):
    """Paired bootstrap of (new - base) for AUC and top-10% capture on the same resampled accounts. Returns mean + 95% CI."""
    y = np.asarray(y); a = np.asarray(p_new, float); b = np.asarray(p_base, float)
    rng = np.random.default_rng(seed)
    pos, neg = np.where(y == 1)[0], np.where(y == 0)[0]
    d = []
    for _ in range(n_boot):
        i = np.concatenate([rng.choice(pos, len(pos)), rng.choice(neg, len(neg))])
        s = int(rng.integers(1e9))
        d.append((roc_auc_score(y[i], a[i]) - roc_auc_score(y[i], b[i]), top_capture(y[i], a[i], seed=s) - top_capture(y[i], b[i], seed=s)))
    d = np.array(d)
    lo, hi = np.percentile(d, [2.5, 97.5], axis=0)
    return {"d_auc_boot": (float(d[:, 0].mean()), float(lo[0]), float(hi[0])),
            "d_top10_boot": (float(d[:, 1].mean()), float(lo[1]), float(hi[1]))}


def paired_fold_comparison(y, p_new, p_base, fid):
    """Per-fold deltas (new - base) on identical folds, plus mean and sd across folds."""
    a = per_fold(y, p_new, fid).set_index("fold"); b = per_fold(y, p_base, fid).set_index("fold")
    d = a - b
    summ = pd.DataFrame({"mean": d.mean(), "sd": d.std(ddof=1), "n_folds_better": (d > 0).sum()})
    return d, summ


LEAK_AUC = 0.95


def single_feature_auc(X, y):
    """|AUC-0.5|+0.5 for each numeric column alone; flag > LEAK_AUC as a leakage red flag."""
    y = np.asarray(y); rows = []
    for c in X.columns:
        v = pd.to_numeric(X[c], errors="coerce")
        if v.notna().sum() < 10 or v.nunique() < 2:
            continue
        a = roc_auc_score(y, v.fillna(v.median()))
        rows.append({"feature": c, "auc": a, "auc_abs": max(a, 1 - a), "leak_flag": max(a, 1 - a) > LEAK_AUC})
    return pd.DataFrame(rows).sort_values("auc_abs", ascending=False).reset_index(drop=True)
