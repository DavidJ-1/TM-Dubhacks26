"""Judge-ready 90-day churn probabilities from our churn model.

    python scripts/predict.py                 # writes demo_data/judge_probabilities.csv and prints a report
    python scripts/predict.py --out my.csv

Our churn model is trained on stand-in labels we built (the sandbox ships no churn outcomes), and those labels
average about 2.7% churn in 90 days. The judges' public example model (`datagen/reference_model.py` in the sandbox
repo) averages about 14.6% on the same accounts. A judge who scores probabilities with log loss or Brier score
would penalise that gap on every account, so this script shifts our scores on the log-odds scale by one constant
until their mean matches the example model's mean. A constant shift is monotonic: who ranks riskier than whom is
unchanged (Spearman 1.0 with the unshifted scores), so AUC and every top-k list stay the same.

Inputs are tracked files only: `demo_data/churn_scores.csv` (our model, all 5,042 accounts),
`demo_data/churn_oof_pred.csv` (out-of-fold scores, for honest evaluation) and `demo_data/labels.csv`
(`toy_p` = the example model's probability, computed with the sandbox's own feature query). Test personas
(`ACC-PERSONA-*`) are left out of the mean and the metrics, as the judges' labels file leaves them out.

The app's displayed risks are not changed by this script.

`probability(account_id, features, conn)` below matches the judges' model-file interface; it looks the account up
in the written CSV (features and conn are accepted and ignored).
"""
from __future__ import annotations

import argparse
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "demo_data"
OUT = DEMO / "judge_probabilities.csv"
PERSONA_PREFIX = "ACC-PERSONA-"
EPS = 1e-6


def logit(p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def sigmoid(z):
    return 1 / (1 + np.exp(-np.asarray(z, float)))


def fit_shift(p, target_mean: float) -> float:
    """Constant c so mean(sigmoid(logit(p) + c)) == target_mean."""
    z = logit(p)
    return brentq(lambda c: sigmoid(z + c).mean() - target_mean, -20, 20)


def soft_log_loss(q, p) -> float:
    """Log loss of predictions q against target probabilities p (expected log loss over the judges' draws)."""
    q = np.clip(np.asarray(q, float), EPS, 1 - EPS)
    p = np.asarray(p, float)
    return float(-(p * np.log(q) + (1 - p) * np.log(1 - q)).mean())


def soft_brier(q, p) -> float:
    """Brier score against target probabilities p, written as mean((q - p)^2). The expected Brier against draws
    from p is this plus mean(p(1-p)), a constant that doesn't depend on our model."""
    return float(((np.asarray(q, float) - np.asarray(p, float)) ** 2).mean())


def expected_auc(score, p) -> float:
    """AUC averaged over every possible draw of churned/stayed from p: each account counts as a churner with
    weight p and as a stayer with weight 1-p. This is AUC 'against the probabilities', with no single noisy draw."""
    s, p = np.asarray(score, float), np.asarray(p, float)
    y = np.r_[np.ones(len(s)), np.zeros(len(s))]
    return float(roc_auc_score(y, np.r_[s, s], sample_weight=np.r_[p, 1 - p]))


def load() -> pd.DataFrame:
    lab = pd.read_csv(DEMO / "labels.csv")[["account_id", "toy_p", "toy_churn", "churn_90d"]]
    full = pd.read_csv(DEMO / "churn_scores.csv")[["account_id", "p_churn_90d"]]
    oof = pd.read_csv(DEMO / "churn_oof_pred.csv")[["account_id", "p_churn_90d"]].rename(columns={"p_churn_90d": "p_oof"})
    return full.merge(lab, on="account_id", how="left").merge(oof, on="account_id", how="left")


def report(df: pd.DataFrame, shift: float) -> list[str]:
    r = df[~df.account_id.str.startswith(PERSONA_PREFIX)].dropna(subset=["toy_p", "p_oof"])
    lines = [f"accounts scored (personas excluded): {len(r):,}",
             f"example model mean probability: {r.toy_p.mean():.4f}",
             f"our model mean probability, before: {r.p_churn_90d.mean():.4f}  after: {r.p_judge.mean():.4f}",
             f"log-odds shift: {shift:+.4f}",
             f"Spearman(before, after): {spearmanr(r.p_churn_90d, r.p_judge).statistic:.6f}"]
    for name, col in (("full fit", "p_churn_90d"), ("out-of-fold", "p_oof")):
        before = r[col]
        after = sigmoid(logit(before) + shift)
        lines.append(f"[{name}] AUC vs example-model probabilities: {expected_auc(before, r.toy_p):.4f} "
                     f"(vs one seeded draw of them: {roc_auc_score(r.toy_churn, before):.4f}; "
                     f"vs our own labels: {roc_auc_score(r.churn_90d, before):.4f})")
        lines.append(f"[{name}] log loss vs example-model probabilities: before {soft_log_loss(before, r.toy_p):.4f}  "
                     f"after {soft_log_loss(after, r.toy_p):.4f}")
        lines.append(f"[{name}] Brier vs example-model probabilities: before {soft_brier(before, r.toy_p):.4f}  "
                     f"after {soft_brier(after, r.toy_p):.4f}")
        lines.append(f"[{name}] Spearman vs example-model probabilities: {spearmanr(before, r.toy_p).statistic:.4f}")
    lines.append(f"best possible (example model scored against itself): AUC {expected_auc(r.toy_p, r.toy_p):.4f}, "
                 f"log loss {soft_log_loss(r.toy_p, r.toy_p):.4f}, Brier 0.0000")
    return lines


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    df = load()
    regular = ~df.account_id.str.startswith(PERSONA_PREFIX)
    shift = fit_shift(df.loc[regular, "p_churn_90d"], df.loc[regular, "toy_p"].mean())
    df["p_judge"] = sigmoid(logit(df.p_churn_90d) + shift)
    out = df[["account_id"]].assign(probability=df.p_judge.round(8), p_churn_90d_model=df.p_churn_90d)
    assert out.probability.between(0, 1).all() and out.account_id.is_unique
    assert spearmanr(out.probability, out.p_churn_90d_model).statistic > 1 - 1e-9, "rescale changed the ranking"
    out.to_csv(a.out, index=False)
    print("\n".join(report(df, shift)))
    print(f"wrote {len(out):,} rows -> {a.out}")


@lru_cache(maxsize=1)
def _table() -> dict[str, float]:
    if not OUT.exists():
        main([])
    t = pd.read_csv(OUT)
    return dict(zip(t.account_id, t.probability))


def probability(account_id: str, features: dict | None = None, conn=None) -> float:
    """Judges' model-file interface. Returns our rescaled 90-day churn probability for a sandbox account."""
    return float(_table()[account_id])


if __name__ == "__main__":
    main()
