"""Scaling comparison (ALL SYNTHETIC): does training on more synthetic accounts help on the REAL 5k?

Train on: real 5k (5-fold stratified OOF, seed 42), synthetic 50k (harness/out/scaled/), synthetic 250k
(harness/out/scaled_250k/). ALWAYS test on the 5,000 real non-persona sandbox accounts. Synthetic inputs are cut to
the features.csv columns (enrichment/household columns dropped) and prepared in ONE prepare() call with the real
rows. Models: logreg_core22 (churn only), logreg_unweighted (all prepare() features), hgb_sigmoid.
Every row carries the oracle AUC on the same real rows and a paired stratified bootstrap 95% CI of
(model AUC - oracle AUC); `above_ceiling` flags point estimates over the oracle.

    OMP_NUM_THREADS=1 python3 -m harness.bench.scaling
Outputs: out/scaling.csv, out/scaling.md, out/scaling_check.png
"""
from __future__ import annotations

import os
import sys
import time

os.environ.setdefault("OMP_NUM_THREADS", "1")
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import average_precision_score  # noqa: E402

from harness.bench import bench as B  # noqa: E402
from harness.bench.compare import LogRegCore  # noqa: E402
from harness.bench.learning_curve import same_rows_vs_oracle  # noqa: E402

SOURCES = {"synthetic_50k": B.REPO / "harness/out/scaled", "synthetic_250k": B.REPO / "harness/out/scaled_250k"}
MODELS = {"logreg_core22": lambda: LogRegCore(), "logreg_unweighted": lambda: B.LogReg(None),
          "hgb_sigmoid": lambda: B.GBM("sigmoid")}


def models_for(t):
    return {k: v for k, v in MODELS.items() if not (t == "upgrade_90d" and k == "logreg_core22")}


def rec(t, model, src, n, y, p, orc, secs):
    s = same_rows_vs_oracle(t, model, n, y, p, orc)
    return {"synthetic": 1, "target": t, "model": model, "train_source": src, "n_train": n, "test": "real 5k",
            "auc": s["auc_model"], "prauc": average_precision_score(y, p), "top10_capture": B.capture(y, p, 0.10),
            "oracle_auc_same_rows": s["auc_oracle_same_rows"], "oracle_prauc_same_rows": average_precision_score(y, orc),
            "oracle_top10_same_rows": B.capture(y, orc, 0.10), "auc_minus_oracle": s["diff"],
            "diff_ci95_lo": s["diff_ci95"][0], "diff_ci95_hi": s["diff_ci95"][1],
            "above_ceiling": bool(s["diff"] > 0), "fit_secs": round(secs, 1)}


def main():
    a = B.cli("Scaling comparison.").parse_args()
    B.OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    df, X_all, reg, _ = B.load(a.features, a.labels)
    Xr = X_all[reg].reset_index(drop=True)
    for t in a.targets:
        y = df.loc[reg, t].values.astype(int); orc = df.loc[reg, B.ORACLE[t]].values
        for mn, mk in models_for(t).items():
            t0 = time.time(); p, fa, _, _ = B.oof(mk(), Xr, y)
            r = rec(t, mn, "real_5k (5-fold OOF)", int(len(y) * 0.8), y, p, orc, time.time() - t0)
            r["auc_fold_sd"] = float(np.std(fa, ddof=1)); rows.append(r)
            print(t, mn, "real", round(r["auc"], 4), flush=True)
    for src, d in SOURCES.items():
        fs, ls = d / "features_scaled.csv", d / "labels_scaled.csv"
        if not (fs.exists() and ls.exists()):
            print("missing", src); continue
        ds, Xs, dr, Xt, rreg, rep = B.load_tstr(fs, ls, a.features, a.labels)
        Xt = Xt[rreg].reset_index(drop=True)
        for t in a.targets:
            y = dr.loc[rreg, t].values.astype(int); orc = dr.loc[rreg, B.ORACLE[t]].values
            ys = ds[t].values.astype(int)
            for mn, mk in models_for(t).items():
                t0 = time.time(); m = mk().fit(Xs, ys); p = m.predict_proba(Xt)
                r = rec(t, mn, src, len(ys), y, p, orc, time.time() - t0)
                r["n_dropped_synthetic_cols"] = len(rep["synthetic_extra_columns_dropped"]); rows.append(r)
                print(t, mn, src, round(r["auc"], 4), f"{r['fit_secs']}s", flush=True)
    res = pd.DataFrame(rows)
    res.to_csv(B.OUT / "scaling.csv", index=False, float_format="%.4f")
    md = ["# Scaling comparison: train on real 5k vs synthetic 50k vs synthetic 250k; test on the REAL 5k (ALL "
          "SYNTHETIC LABELS)\n",
          "AUC minus oracle uses the oracle on exactly the same real rows; CI = paired stratified bootstrap 95% "
          "(2,000 resamples). A point above the ceiling with a CI that straddles 0 is noise (137 real churners).\n",
          "| target | model | trained on | n train | AUC | fold sd | PR-AUC | top-10% | oracle AUC | AUC - oracle [95% CI] |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in res.iterrows():
        sd = r.get("auc_fold_sd"); sd = "" if pd.isna(sd) else f"{sd:.3f}"
        flag = " **above ceiling (noise if CI spans 0)**" if r.above_ceiling else ""
        md.append(f"| {r.target} | {r.model} | {r.train_source} | {r.n_train:,} | {r.auc:.3f} | {sd} | {r.prauc:.3f} | "
                  f"{r.top10_capture:.3f} | {r.oracle_auc_same_rows:.3f} | {r.auc_minus_oracle:+.3f} "
                  f"[{r.diff_ci95_lo:+.3f}, {r.diff_ci95_hi:+.3f}]{flag} |")
    (B.OUT / "scaling.md").write_text("\n".join(md))
    plot(res, B.OUT / "scaling_check.png")
    print("\n".join(md))


def plot(res, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    tg = list(dict.fromkeys(res.target))
    fig, axes = plt.subplots(1, len(tg), figsize=B.FIG_IN, dpi=B.FIG_DPI, squeeze=False)
    order = ["real_5k (5-fold OOF)", "synthetic_50k", "synthetic_250k"]
    for ax, t in zip(axes[0], tg):
        g = res[res.target == t]
        ms = list(dict.fromkeys(g.model)); w = 0.8 / len(ms)
        for j, m in enumerate(ms):
            h = g[g.model == m].set_index("train_source").reindex(order)
            ax.bar(np.arange(3) + j * w, h.auc, w, label=m)
        ax.axhline(g.oracle_auc_same_rows.iloc[0], ls="--", c="k", label=f"oracle {g.oracle_auc_same_rows.iloc[0]:.3f}")
        ax.set_xticks(np.arange(3) + 0.4 - w / 2); ax.set_xticklabels(order)
        ax.set_ylim(0.65, 0.9); ax.set_title(f"{t}: AUC on the real 5k"); ax.legend(fontsize=9)
    fig.suptitle("Scaling: more synthetic training rows, always tested on the real sandbox accounts")
    B.save_fig(fig, path); plt.close(fig)


if __name__ == "__main__":
    main()
