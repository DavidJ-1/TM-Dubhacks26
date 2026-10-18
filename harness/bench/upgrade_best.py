"""Upgrade: capture at top 5/10/15/20%, and calibration of synthetic-trained models on the REAL 5k, before and
after a simple recalibration (5-fold CV Platt scaling fitted on the real 5k). ALL SYNTHETIC.
Also a lightweight churn calibration cross-check (logreg_core22 trained on 250k synthetic).

    OMP_NUM_THREADS=1 python3 -m harness.bench.upgrade_best
Outputs: out/upgrade_best.csv, out/upgrade_best.md
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score  # noqa: E402
from sklearn.model_selection import StratifiedKFold  # noqa: E402

from harness.bench import bench as B  # noqa: E402
from harness.bench import upgrade_improve as U  # noqa: E402
from harness.bench.compare import LogRegCore  # noqa: E402


def platt_cv(p, y, seed=B.SEED):
    """Out-of-fold Platt recalibration on the real rows: logistic regression of y on logit(p)."""
    z = B._logit(p).reshape(-1, 1); out = np.zeros(len(y))
    for tr, te in StratifiedKFold(5, shuffle=True, random_state=seed).split(z, y):
        out[te] = LogisticRegression(C=1e6, max_iter=1000).fit(z[tr], y[tr]).predict_proba(z[te])[:, 1]
    return out


def metrics(y, p):
    r = {"auc": roc_auc_score(y, p), "prauc": average_precision_score(y, p)}
    for k in (5, 10, 15, 20):
        r[f"top{k}_capture"] = B.capture(y, p, k / 100)
    r.update(mean_pred=float(p.mean()), actual_rate=float(y.mean()), ece10=B.ece(y, p), brier=brier_score_loss(y, p))
    return r


def main():
    B.OUT.mkdir(parents=True, exist_ok=True)
    fr = pd.read_csv(B.DEFAULT_FEATURES).merge(pd.read_csv(U.ENRICH).drop(columns=["n_lines"], errors="ignore"),
                                                on="account_id", validate="1:1")
    lab = pd.read_csv(B.DEFAULT_LABELS)
    frames, syn = [("real", fr)], {}
    for src, d in U.SCALED.items():
        F = pd.read_csv(d / "features_scaled.csv")
        hh = d / "household_scaled.csv"
        if not set(U.HOUSE[:3]) <= set(F.columns) and hh.exists():
            F = F.merge(pd.read_csv(hh).drop(columns=["n_lines"], errors="ignore"), on="account_id", validate="1:1")
        syn[src] = pd.read_csv(d / "labels_scaled.csv"); frames.append((src, F))
    Xs, base = U.build(frames)
    d = fr[["account_id", "is_persona"]].merge(lab.drop(columns=["is_persona"]), on="account_id", validate="1:1")
    reg = (d["is_persona"] == 0).values
    Xr = Xs["real"][reg].reset_index(drop=True)
    hi, lo = B.EXPECT[U.T]
    pm = d["account_id"].isin(hi + lo).values
    Xp = Xs["real"][pm].reset_index(drop=True); pid = d.loc[pm, "account_id"].tolist()
    prow = []
    TI = U.tiers(base)
    tn = {k.split(" ")[0]: k for k in TI}
    configs = [("b1", "lr_tuned", "real_5k"), ("b1", "hgb_sigmoid", "real_5k"), ("b2", "lr_tuned", "real_5k"),
               ("a", "lr_tuned", "synthetic_50k"), ("b1", "lr_tuned", "synthetic_50k"),
               ("a", "lr_tuned", "synthetic_250k"), ("b1", "lr_tuned", "synthetic_250k"),
               ("b1", "hgb_sigmoid", "synthetic_250k"), ("b2", "lr_tuned", "synthetic_250k"),
               ("c", "lr_tuned", "synthetic_250k")]
    rows = []
    y = d.loc[reg, U.T].values.astype(int)
    for t, mn, src in configs:
        cols = TI[tn[t]]
        if src == "real_5k":
            p, _, _ = U.oof_eval(Xr, y, cols, U.MODELS[mn])
        else:
            m = U.MODELS[mn](cols).fit(Xs[src][cols], syn[src][U.T].values.astype(int))
            p = m.predict_proba(Xr[cols])[:, 1]
            pp_ = m.predict_proba(Xp[cols])[:, 1]
            for i, a in enumerate(pid):
                pct = float((p < pp_[i]).mean() * 100 + (p == pp_[i]).mean() * 50)
                prow.append({"synthetic": 1, "tier": tn[t], "model": mn, "trained_on": src, "account_id": a,
                             "expect": "high" if a in hi else "low", "pct": round(pct, 1),
                             "pass": bool(pct >= 90 if a in hi else pct < 50)})
        for cal, pp in (("raw", p), ("platt_cv_on_real", platt_cv(p, y))):
            rows.append({"synthetic": 1, "target": U.T, "tier": tn[t], "model": mn, "trained_on": src,
                         "calibration": cal, **metrics(y, pp)})
        print(rows[-2]["tier"], mn, src, {k: round(v, 3) for k, v in rows[-2].items() if isinstance(v, float)},
              flush=True)
    # churn cross-check: core-22 LR on 250k synthetic -> real
    ds, Xsc, dr, Xtc, rreg, _ = B.load_tstr(U.SCALED["synthetic_250k"] / "features_scaled.csv",
                                            U.SCALED["synthetic_250k"] / "labels_scaled.csv")
    yc = dr.loc[rreg, "churn_90d"].values.astype(int)
    for mn, mk in (("logreg_core22", lambda: LogRegCore()), ("hgb_sigmoid", lambda: B.GBM("sigmoid"))):
        p = mk().fit(Xsc, ds["churn_90d"].values.astype(int)).predict_proba(Xtc[rreg].reset_index(drop=True))
        for cal, pp in (("raw", p), ("platt_cv_on_real", platt_cv(p, yc))):
            rows.append({"synthetic": 1, "target": "churn_90d", "tier": "prepare() (Model A inputs)", "model": mn,
                         "trained_on": "synthetic_250k", "calibration": cal, **metrics(yc, pp)})
    res = pd.DataFrame(rows)
    res.to_csv(B.OUT / "upgrade_best.csv", index=False, float_format="%.4f")
    md = ["# Upgrade capture + calibration on the real 5k (ALL SYNTHETIC)\n",
          "Capture = share of real upgrade_90d positives (322/5000) in the top k% by score. Platt = 5-fold CV logistic "
          "recalibration fitted on the real 5k (ranking unchanged, so AUC/capture are unchanged).\n",
          "| target | tier | model | trained on | calib | AUC | PR-AUC | top5 | top10 | top15 | top20 | mean pred | actual | ECE | Brier |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in res.iterrows():
        md.append(f"| {r.target} | {r.tier} | {r.model} | {r.trained_on} | {r.calibration} | {r.auc:.3f} | {r.prauc:.3f} | "
                  f"{r.top5_capture:.1%} | {r.top10_capture:.1%} | {r.top15_capture:.1%} | {r.top20_capture:.1%} | "
                  f"{r.mean_pred:.2%} | {r.actual_rate:.2%} | {r.ece10:.4f} | {r.brier:.4f} |")
    P = pd.DataFrame(prow)
    P.to_csv(B.OUT / "upgrade_best_personas.csv", index=False)
    pv = P.pivot_table(index=["tier", "model", "trained_on"], columns="account_id", values="pct").round(1)
    pv["n_pass"] = P.groupby(["tier", "model", "trained_on"])["pass"].sum()
    md += ["\nUpgrade personas for synthetic-trained models (percentile among the 5,000 real accounts; high 25/28 >= "
           "90, low 22/24/27 < 50):\n", "```", pv.to_string(), "```"]
    (B.OUT / "upgrade_best.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
