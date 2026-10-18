"""Learning curve (ALL SYNTHETIC): AUC, PR-AUC and top-10% capture vs training size, for unweighted logistic
regression on all prepare() features (logreg_unweighted), on Model A's 22 core features (logreg_core22, the
recommended model's feature set) and the sigmoid-calibrated HGB challenger, on churn_90d and upgrade_90d.

Protocol, per seed s (default 10 seeds):
  1. stratified 25% holdout of the regular (non-persona) accounts, split seed s;
  2. from the remaining 75% pool, a stratified subsample of n_train accounts (seed s); n_train = pool -> all of it;
  3. fit, score the holdout. Report mean and sd across seeds (sd covers holdout AND subsample variance).
Sizes: 250/500/1000/2000/3750 (more when the pool allows).
Train-on-synthetic mode (--train-features/--train-labels, train_source=synthetic_50k): n synthetic accounts in
1k/2.5k/5k/10k/25k/50k (10 seeds up to 5k, 5 at 10k-25k, 3 at 50k), tested on ALL real regular accounts; the oracle
is computed on exactly those real rows.

    OMP_NUM_THREADS=1 python3 -m harness.bench.learning_curve [--features F --labels L --n-max N]
        [--train-source real_5k|synthetic_50k] [--seeds 10]

Outputs (harness/bench/out/; rows for the other train_source are kept, so 5k and 50k runs coexist):
  learning_curve.csv       target, model, train_size, train_source, n_seeds, auc_mean, auc_sd, prauc_mean,
                           prauc_sd, top10_capture_mean, top10_capture_sd
  learning_curve_long.csv  target, train_source, model, n_train, metric, value, sd
  learning_curve_oracle.csv  oracle (label-generating p) on the same holdouts, per target/train_source
  ceilings.csv             target, oracle_auc (full regular population; written from the real_5k run)
  learning_curve_check.png
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402

from harness.bench import bench as B  # noqa: E402

SIZES = [250, 500, 1000, 2000, 3750, 5000, 10000, 20000, 37500]
def _core(s):
    from harness.bench.compare import LogRegCore
    return LogRegCore()


MODELS = {"logreg_unweighted": lambda s: B.LogReg(None), "logreg_core22": _core,
          "hgb_sigmoid": lambda s: B.GBM("sigmoid", seed=s)}
WIDE = ["target", "model", "train_size", "train_source", "n_seeds", "auc_mean", "auc_sd", "prauc_mean", "prauc_sd",
        "top10_capture_mean", "top10_capture_sd"]


def run(df, X_all, reg, targets, seeds):
    Xr = X_all[reg].reset_index(drop=True)
    rows, orows = [], []
    for t in targets:
        y = df.loc[reg, t].values.astype(int)
        orc = df.loc[reg, B.ORACLE[t]].values
        for s in range(seeds):
            pool, te = train_test_split(np.arange(len(y)), test_size=0.25, stratify=y, random_state=s)
            orows.append({"target": t, "seed": s, "auc": roc_auc_score(y[te], orc[te]),
                          "prauc": average_precision_score(y[te], orc[te]),
                          "top10_capture": B.capture(y[te], orc[te], 0.10)})
            sizes = [n for n in SIZES if n < len(pool)] + [len(pool)]
            for n in sorted(set(sizes)):
                tr = pool if n >= len(pool) else train_test_split(pool, train_size=n, stratify=y[pool],
                                                                   random_state=s)[0]
                for name, mk in MODELS.items():
                    try:
                        m = mk(s).fit(Xr.iloc[tr], y[tr])
                        p = m.predict_proba(Xr.iloc[te])
                        rows.append({"target": t, "model": name, "train_size": n, "seed": s,
                                     "n_pos_train": int(y[tr].sum()), "auc": roc_auc_score(y[te], p),
                                     "prauc": average_precision_score(y[te], p),
                                     "top10_capture": B.capture(y[te], p, 0.10)})
                    except Exception as e:  # noqa: BLE001  (e.g. too few positives for calibration folds)
                        print(f"  fail {t} {name} n={n} seed={s}: {e!r}", flush=True)
            print(f"  {t} seed {s} done", flush=True)
    return pd.DataFrame(rows), pd.DataFrame(orows)


TSTR_SIZES = [1000, 2500, 5000, 10000, 25000, 50000]


SAME_ROWS = []


def same_rows_vs_oracle(t, name, n, y, p, orc, B_=2000, seed=0):
    """Model vs oracle AUC on exactly the same real rows + paired bootstrap 95% CI of the difference."""
    rng = np.random.default_rng(seed)
    pos, neg = np.where(y == 1)[0], np.where(y == 0)[0]
    d = []
    for _ in range(B_):  # stratified resample keeps the positive count fixed
        ix = np.concatenate([rng.choice(pos, len(pos)), rng.choice(neg, len(neg))])
        d.append(roc_auc_score(y[ix], p[ix]) - roc_auc_score(y[ix], orc[ix]))
    a_m, a_o = roc_auc_score(y, p), roc_auc_score(y, orc)
    return {"target": t, "model": name, "train_size": n, "n_test_rows": int(len(y)), "n_test_pos": int(y.sum()),
            "auc_model": a_m, "auc_oracle_same_rows": a_o, "diff": a_m - a_o,
            "diff_ci95": [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]}


def tstr_seeds(n, seeds):
    return seeds if n <= 5000 else max(3, seeds // 2) if n < 50000 else 3


def run_tstr(ds, Xs, dr, Xr, rreg, targets, seeds):
    """Train on n synthetic accounts (stratified subsample, per seed), test on ALL real regular accounts."""
    Xt = Xr[rreg].reset_index(drop=True)
    rows, orows = [], []
    for t in targets:
        y = ds[t].values.astype(int)
        yt = dr.loc[rreg, t].values.astype(int)
        orc = dr.loc[rreg, B.ORACLE[t]].values
        orows.append({"target": t, "seed": 0, "auc": roc_auc_score(yt, orc), "prauc": average_precision_score(yt, orc),
                      "top10_capture": B.capture(yt, orc, 0.10)})
        for n in [m for m in TSTR_SIZES if m < len(y)] + [len(y)]:
            for s in range(tstr_seeds(n, seeds)):
                tr = (np.arange(len(y)) if n >= len(y) else
                      train_test_split(np.arange(len(y)), train_size=n, stratify=y, random_state=s)[0])
                for name, mk in MODELS.items():
                    m = mk(s).fit(Xs.iloc[tr], y[tr])
                    p = m.predict_proba(Xt)
                    rows.append({"target": t, "model": name, "train_size": n, "seed": s,
                                 "n_pos_train": int(y[tr].sum()), "auc": roc_auc_score(yt, p),
                                 "prauc": average_precision_score(yt, p), "top10_capture": B.capture(yt, p, 0.10)})
                    if n >= len(y) and s == 0:
                        SAME_ROWS.append(same_rows_vs_oracle(t, name, n, yt, p, orc))
            print(f"  tstr {t} n={n} done", flush=True)
    return pd.DataFrame(rows), pd.DataFrame(orows)


def summarize(raw, source):
    g = raw.groupby(["target", "model", "train_size"])
    w = g.agg(n_seeds=("seed", "nunique"), auc_mean=("auc", "mean"), auc_sd=("auc", "std"),
              prauc_mean=("prauc", "mean"), prauc_sd=("prauc", "std"),
              top10_capture_mean=("top10_capture", "mean"), top10_capture_sd=("top10_capture", "std"),
              n_pos_train_mean=("n_pos_train", "mean")).reset_index()
    w["train_source"] = source
    return w


def merge_write(path, new, source, cols):
    if path.exists():
        old = pd.read_csv(path)
        old = old[old["train_source"] != source]
        new = pd.concat([old, new], ignore_index=True)
    new[cols].to_csv(path, index=False, float_format="%.5f")
    return new[cols]


def to_long(w):
    rows = []
    for _, r in w.iterrows():
        for m, a, b in (("auc", "auc_mean", "auc_sd"), ("prauc", "prauc_mean", "prauc_sd"),
                        ("top10_capture", "top10_capture_mean", "top10_capture_sd")):
            rows.append({"target": r["target"], "train_source": r["train_source"], "model": r["model"],
                         "n_train": int(r["train_size"]), "metric": m, "value": r[a], "sd": r[b]})
    return pd.DataFrame(rows)


def plot(wide, orc, ceil, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    targets = list(dict.fromkeys(wide["target"]))
    mets = [("auc", "ROC AUC"), ("prauc", "PR-AUC"), ("top10_capture", "Share of positives in top 10%")]
    fig, axes = plt.subplots(len(targets), 3, figsize=B.FIG_IN, dpi=B.FIG_DPI, squeeze=False)
    for i, t in enumerate(targets):
        for j, (m, lab) in enumerate(mets):
            ax = axes[i][j]
            for (model, src), g in wide[wide.target == t].groupby(["model", "train_source"]):
                g = g.sort_values("train_size")
                ax.errorbar(g.train_size, g[f"{m}_mean"], yerr=g[f"{m}_sd"], marker="o", capsize=3,
                            label=f"{model} ({src})", ls="-" if src == "real_5k" else "--")
            o = orc[orc.target == t]
            ref = ceil.get(t) if m == "auc" else (o[m].mean() if len(o) else None)
            if ref is not None:
                ax.axhline(ref, ls="--", c="k", lw=1, label=f"oracle ceiling {ref:.3f}" + (" (full pop.)" if m ==
                           "auc" else " (same holdouts)"))
            ax.set_xscale("log"); ax.set_xlabel("training accounts (log scale)"); ax.set_title(f"{t}: {lab}")
            ax.grid(alpha=.3)
            if j == 0:
                ax.legend(fontsize=8, loc="lower right")
    fig.suptitle("Learning curve (mean +/- sd over seeds). real_5k: train on sandbox accounts, 25% stratified holdout; "
                 "synthetic_50k: train on scaled synthetic, test on all 5,000 sandbox accounts", fontsize=11)
    B.save_fig(fig, path); plt.close(fig)


def main():
    ap = B.cli("Learning curve.")
    ap.add_argument("--train-source", default=None, help="real_5k or synthetic_50k (default: by row count)")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--train-features", default=None, help="synthetic features (train-on-synthetic, test on ALL "
                    "real regular accounts from --features/--labels)")
    ap.add_argument("--train-labels", default=None)
    a = ap.parse_args()
    B.OUT.mkdir(parents=True, exist_ok=True)
    if a.train_features:
        ds, Xs, df, X_all, reg, rep = B.load_tstr(a.train_features, a.train_labels, a.features, a.labels)
        src = a.train_source or "synthetic_50k"
        print("TSTR leak report:", rep, flush=True)
        import json
        (B.OUT / f"tstr_leak_check_{src}.json").write_text(json.dumps(rep, indent=1))
        targets = [t for t in a.targets if t in ds and t in df]
        raw, orc = run_tstr(ds, Xs, df, X_all, reg, targets, a.seeds)
        rep["same_rows_vs_oracle"] = SAME_ROWS
        (B.OUT / f"tstr_leak_check_{src}.json").write_text(json.dumps(rep, indent=1, default=float))
        print(json.dumps(SAME_ROWS, indent=1, default=float))
    else:
        df, X_all, reg, note = B.load(a.features, a.labels, a.n_max)
        src = a.train_source or "real_5k"
        print(note, "| train_source:", src, flush=True)
        targets = [t for t in a.targets if t in df]
        raw, orc = run(df, X_all, reg, targets, a.seeds)
    raw.assign(train_source=src).to_csv(B.OUT / f"learning_curve_raw_{src}.csv", index=False, float_format="%.5f")
    wide = merge_write(B.OUT / "learning_curve.csv", summarize(raw, src), src, WIDE)
    merge_write(B.OUT / "learning_curve_long.csv", to_long(summarize(raw, src)), src,
                ["target", "train_source", "model", "n_train", "metric", "value", "sd"])
    orc = orc.assign(train_source=src)
    merge_write(B.OUT / "learning_curve_oracle.csv", orc, src, ["target", "train_source", "seed", "auc", "prauc",
                                                                 "top10_capture"])
    cpath = B.OUT / "ceilings.csv"
    if not a.train_features and (src == "real_5k" or not cpath.exists()):
        pd.DataFrame([{"target": t, "oracle_auc": roc_auc_score(df.loc[reg, t], df.loc[reg, B.ORACLE[t]])}
                      for t in targets]).to_csv(cpath, index=False, float_format="%.4f")
    ceil = pd.read_csv(cpath).set_index("target")["oracle_auc"].to_dict()
    allorc = pd.read_csv(B.OUT / "learning_curve_oracle.csv")
    plot(wide, allorc[allorc.train_source == "real_5k"] if (allorc.train_source == "real_5k").any() else allorc,
         ceil, B.OUT / "learning_curve_check.png")
    print(wide.to_string(index=False))
    print(allorc.groupby(["target", "train_source"])[["auc", "prauc", "top10_capture"]].agg(["mean", "std"]))


if __name__ == "__main__":
    main()
