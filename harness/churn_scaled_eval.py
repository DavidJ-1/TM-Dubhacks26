"""Train Model A on tm-data's synthetic scaled set, test on the real 5k sandbox accounts (SYNTHETIC labels).

Compares core features vs core + household fields (promo/contract months remaining, family plan, kid flag),
and reports the oracle (p_true_90d) on the same real rows. Writes out/churn_scaled_eval.csv.
Run: python harness/churn_scaled_eval.py [--scaled out/scaled_250k] [--sizes 5000 50000 250000]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import churn_features as cf  # noqa: E402
from churn_features import leak_columns, prepare  # noqa: E402
from churn_model import OUT, PERSONA_PREFIX, SEED, ModelA  # noqa: E402

HOUSEHOLD = ["promo_months_remaining", "contract_or_financing_months_remaining", "is_family_plan", "likely_kid_flag"]


def load(feat, lab, extra=None):
    f, l = pd.read_csv(feat), pd.read_csv(lab)
    if extra is not None:
        f = f.merge(extra, on="account_id", how="left", suffixes=("", "_enr"))
    barred = set(l.columns) - {"account_id"}
    f = f.drop(columns=[c for c in f.columns if c != "account_id" and (c in barred or c in leak_columns([c]))])
    hh = f.set_index("account_id")[[c for c in HOUSEHOLD if c in f.columns]].astype(float)
    X = prepare(f)
    X = X.join(hh.reindex(X.index).fillna(hh.median()), rsuffix="_hh")
    y = l.set_index("account_id").reindex(X.index)
    return X, y


def top10(y, p):
    k = int(np.ceil(0.1 * len(y)))
    return y.values[np.argsort(-p)[:k]].sum() / y.sum()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scaled", default=str(OUT / "scaled_250k"))
    ap.add_argument("--sizes", type=int, nargs="+", default=[5000, 50000, 250000])
    a = ap.parse_args(argv)
    sd = Path(a.scaled)
    Xs, ys = load(sd / "features_scaled.csv", sd / "labels_scaled.csv")
    Xr, yr = load(OUT / "features.csv", OUT / "labels.csv", pd.read_csv(OUT / "enrichment.csv"))
    reg = ~Xr.index.str.startswith(PERSONA_PREFIX)
    Xr, yr = Xr[reg], yr[reg]
    y_real = yr["churn_90d"].astype(int)
    rows = [{"model": "oracle p_true_90d", "train_rows": 0, "auc": roc_auc_score(y_real, yr["p_true_90d"]),
             "pr_auc": average_precision_score(y_real, yr["p_true_90d"]), "top10_capture": top10(y_real, yr["p_true_90d"].values)}]
    rng = np.random.default_rng(SEED)
    hh_cols = [c for c in HOUSEHOLD if c in Xs.columns]
    for n in a.sizes:
        idx = rng.choice(len(Xs), min(n, len(Xs)), replace=False)
        Xn, yn = Xs.iloc[idx], ys["churn_90d"].iloc[idx].astype(int)
        for name, extra in (("model_a core", []), ("model_a core+household", hh_cols)):
            saved = list(cf.CORE_FEATURES)
            cf.CORE_FEATURES[:] = saved + extra
            try:
                m = ModelA().fit(Xn, yn)
                p = m.predict_proba(Xr.reindex(columns=Xn.columns))
            finally:
                cf.CORE_FEATURES[:] = saved
            rows.append({"model": name, "train_rows": len(yn), "auc": roc_auc_score(y_real, p),
                         "pr_auc": average_precision_score(y_real, p), "top10_capture": top10(y_real, p),
                         "mean_p": p.mean(), "n_features": len(getattr(m, "cols_", []))})
            print(rows[-1], flush=True)
    df = pd.DataFrame(rows)
    df.insert(0, "note", "SYNTHETIC: train on tm-data scaled set, test on real 5k sandbox accounts (simulated labels)")
    df.to_csv(OUT / "churn_scaled_eval.csv", index=False)
    print(df.drop(columns="note").round(3).to_string(index=False))


if __name__ == "__main__":
    main()
