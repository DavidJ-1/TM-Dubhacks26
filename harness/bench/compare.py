"""'How we compare' panel + lift and synthetic dollars + calibration check. ALL NUMBERS SYNTHETIC.

All our rows are 5-fold stratified out-of-fold scores (seed 42) on the 5,000 regular sandbox accounts
(personas excluded), so every account is scored by a model that never saw its label.

    OMP_NUM_THREADS=1 python3 -m harness.bench.compare [--features F --labels L]

Outputs in harness/bench/out/: how_we_compare.csv/.md/.png, published_telco.csv, lift_catch.csv/.md,
calibration_check.png, compare_summary.json.

Dollars are deliberately NOT modelled here: the project's dollar numbers come from tm-offers' policy evaluation
(harness/model_c_artifacts/policy_eval.csv: simulated randomized trial, IPW + doubly-robust, assumptions partly
circular). This file reports lift and churners caught per k contacted only.
"""
from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score  # noqa: E402
from sklearn.model_selection import StratifiedKFold  # noqa: E402

from harness.bench import bench as B  # noqa: E402


# Published IBM Telco Customer Churn results (7,043 customers, 26.5% churn). DIFFERENT DATASET: context only.
PUBLISHED = [
    {"source": "Gaddamwar 2026, arXiv:2608.26151 (Table 1, test n=1,409; SMOTE)", "model": "Logistic regression",
     "auc": 0.8411, "url": "https://arxiv.org/abs/2608.26151"},
    {"source": "Gaddamwar 2026, arXiv:2608.26151 (Table 1)", "model": "XGBoost", "auc": 0.8369,
     "url": "https://arxiv.org/abs/2608.26151"},
    {"source": "Gaddamwar 2026, arXiv:2608.26151 (Table 1)", "model": "LightGBM", "auc": 0.8306,
     "url": "https://arxiv.org/abs/2608.26151"},
    {"source": "Ali, Ahmed & Attia 2026, arXiv:2607.10260 (Table VIII, tuned)", "model": "CatBoost", "auc": 0.8403,
     "url": "https://arxiv.org/abs/2607.10260"},
    {"source": "Ali, Ahmed & Attia 2026, arXiv:2607.10260 (Table VIII, tuned)", "model": "XGBoost", "auc": 0.8408,
     "url": "https://arxiv.org/abs/2607.10260"},
    {"source": "pablowilliams/churn-propensity-modelling report (Table 1, test 20%)", "model": "Logistic regression",
     "auc": 0.845, "url": "https://raw.githubusercontent.com/pablowilliams/churn-propensity-modelling/main/paper/report.pdf"},
    {"source": "pablowilliams/churn-propensity-modelling report (Table 1)", "model": "XGBoost", "auc": 0.847,
     "url": "https://raw.githubusercontent.com/pablowilliams/churn-propensity-modelling/main/paper/report.pdf"},
    {"source": "CCallahan308/signalforge README (test AUC, 20% holdout)", "model": "Logistic regression",
     "auc": 0.849, "url": "https://github.com/CCallahan308/signalforge"},
    {"source": "CCallahan308/signalforge README", "model": "Gradient boosting", "auc": 0.847,
     "url": "https://github.com/CCallahan308/signalforge"},
]
TELCO_DATASET_URL = "https://www.kaggle.com/datasets/blastchar/telco-customer-churn"


MODEL_A_OOF = B.REPO / "harness/out/churn_oof_pred.csv"


class LogRegCore(B.LogReg):
    """Unweighted LR on tm-churn's curated CORE_FEATURES only (Model A's feature set, without its calibration)."""
    def __init__(self):
        super().__init__(None); self.name = "logreg_core22"

    def _X(self, X):
        import churn_features  # type: ignore  (path set by bench.prepare_fn)
        return X[[c for c in churn_features.CORE_FEATURES if c in X.columns]]


def rows_for(target):
    if target == "churn_90d":
        return [("LR on all 58 prepare() features (unweighted)", "model", lambda: B.LogReg(None)),
                ("LR on Model A's 22 core features (unweighted)", "model", lambda: LogRegCore()),
                ("HGB + sigmoid calibration (challenger)", "model", lambda: B.GBM("sigmoid")),
                ("Untuned default sklearn GradientBoostingClassifier()", "model", lambda: B.SkGBDefault()),
                ("Untuned default sklearn HistGradientBoostingClassifier()", "model", lambda: B.GBM(None, default=True)),
                ("Rule: 3+ support contacts in 90d (binary)", "score", B.support_3plus_score),
                ("Rule: rank by support_90d contact count", "score", B.support_count_score)]
    return [("LR on all 58 prepare() features (unweighted)", "model", lambda: B.LogReg(None)),
            ("HGB + sigmoid calibration (challenger)", "model", lambda: B.GBM("sigmoid")),
            ("Untuned default sklearn GradientBoostingClassifier()", "model", lambda: B.SkGBDefault()),
            ("Untuned default sklearn HistGradientBoostingClassifier()", "model", lambda: B.GBM(None, default=True)),
            ("Rule: near or over data cap (binary, tm-harness rule)", "score", B.near_cap_binary_score),
            ("Rule: rank by lines over cap + usage/cap", "score", B.near_cap_score)]


def score_all(target, df, Xr, reg):
    y = df.loc[reg, target].values.astype(int)
    skf = list(StratifiedKFold(B.N_FOLDS, shuffle=True, random_state=B.SEED).split(Xr, y))
    out, scores = [], {}
    for label, kind, obj in rows_for(target):
        if kind == "model":
            p = np.zeros(len(y))
            for tr, te in skf:
                m = obj().fit(Xr.iloc[tr], y[tr]); p[te] = m.predict_proba(Xr.iloc[te])
        else:
            p = obj(Xr)
        scores[label] = p
    if target == "churn_90d" and MODEL_A_OOF.exists():  # tm-churn's own out-of-fold predictions, scored as-is
        oo = pd.read_csv(MODEL_A_OOF).set_index("account_id")["p_churn_90d"].reindex(df.loc[reg, "account_id"])
        if oo.notna().all():
            scores["Ours: Model A (tm-churn LR, 22 core features; its OOF)"] = oo.values
    scores["Oracle ceiling (label-generating probability)"] = df.loc[reg, B.ORACLE[target]].values
    prev = y.mean()
    for label, p in scores.items():
        fa = [roc_auc_score(y[te], p[te]) for _, te in skf]
        r = {"target": target, "row": label, "auc": roc_auc_score(y, p), "auc_fold_sd": float(np.std(fa, ddof=1)),
             "prauc": average_precision_score(y, p), "top10_capture": B.capture(y, p, 0.10)}
        r["top10_lift"] = r["top10_capture"] / 0.10
        r["top10_precision"] = r["top10_capture"] * y.sum() / np.ceil(0.10 * len(y))
        if label.startswith("Rule") and "binary" in label:
            flag = p > 0
            r["rule_flag_share"] = float(flag.mean()); r["rule_recall"] = float(y[flag].sum() / y.sum())
            r["rule_precision"] = float(y[flag].mean())
        r["prevalence"] = prev
        out.append(r)
    return pd.DataFrame(out), scores, y


def expected_sum(vals, score, k):
    """Expected sum of vals over the top-k by score with random tie-breaking."""
    vals, s = np.asarray(vals, float), np.asarray(score, float)
    k = min(int(k), len(s))
    thr = np.sort(s)[::-1][k - 1]
    above, tie = s > thr, s == thr
    return float(vals[above].sum() + vals[tie].mean() * (k - above.sum()))


def lift_catch(df, reg, y, scores):
    ks = [250, 500, 1000]
    rule = scores["Rule: 3+ support contacts in 90d (binary)"]
    n_rule = int((rule > 0).sum())
    keep = {"LR, all prepare() features": scores["LR on all 58 prepare() features (unweighted)"],
            "LR on Model A core-22": scores["LR on Model A's 22 core features (unweighted)"],
            **({"Ours: Model A OOF (tm-churn)": scores[k] for k in scores if k.startswith("Ours: Model A")}),
            "3+ contacts rule": rule, "support_90d count ranking": scores["Rule: rank by support_90d contact count"],
            "Random": np.zeros(len(y)), "Oracle": scores["Oracle ceiling (label-generating probability)"]}
    rows = []
    for k in ks + [n_rule]:
        for name, s in keep.items():
            caught = expected_sum(y, s, k)
            rows.append({"k_contacted": k, "k_label": f"rule flags all ({n_rule})" if k == n_rule else f"top {k}",
                         "targeting": name, "churners_caught": caught, "share_of_churners": caught / y.sum(),
                         "lift_vs_random": (caught / k) / y.mean(), "precision": caught / k})
    d = pd.DataFrame(rows)
    meta = {"n_accounts": int(len(y)), "n_churners": int(y.sum()), "rule_flag_count": n_rule,
            "dollars": "not modelled here; see harness/model_c_artifacts/policy_eval.csv (tm-offers)"}
    return d, meta


def plot_compare(tab, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    pub = pd.DataFrame(PUBLISHED)
    fig, axes = plt.subplots(1, 2, figsize=B.FIG_IN, dpi=B.FIG_DPI, gridspec_kw={"width_ratios": [3, 2]})
    t = tab[tab.target == "churn_90d"].iloc[::-1]
    colors = ["#999" if r.startswith("Oracle") else "#e20074" if r.startswith("Ours") else "#c9c9c9" if r.startswith(
        "Rule") else "#7a7a7a" for r in t.row]
    ax = axes[0]
    ax.barh(t.row, t.auc, xerr=t.auc_fold_sd, color=colors, capsize=3)
    for i, (a, l) in enumerate(zip(t.auc, t.top10_lift)):
        ax.text(0.505, i, f"AUC {a:.3f}  |  top-10% lift {l:.1f}x", va="center", fontsize=9)
    ax.set_xlim(0.5, 0.92); ax.set_xlabel("ROC AUC (5-fold out-of-fold; error bar = fold sd)")
    ax.set_title("churn_90d on 5,000 sandbox accounts, SYNTHETIC labels (2.7% churn)")
    ax = axes[1]
    pp = pub.iloc[::-1]
    ax.barh([f"{m} - {s.split(' (')[0]}" for m, s in zip(pp.model, pp.source)], pp.auc, color="#bdbdbd", hatch="//")
    for i, a in enumerate(pp.auc):
        ax.text(0.505, i, f"{a:.3f}", va="center", fontsize=9, bbox=dict(fc="white", ec="none", pad=1))
    ax.set_xlim(0.5, 0.92); ax.set_xlabel("published ROC AUC")
    ax.set_title("Context only, NOT head-to-head:\npublished AUCs on IBM Telco\n(different dataset, 26.5% churn)", fontsize=10)
    ax.tick_params(axis="y", labelsize=7)
    fig.suptitle("How we compare (all our numbers SYNTHETIC)", fontsize=13)
    B.save_fig(fig, path); plt.close(fig)


def plot_calibration(cal, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, len(cal), figsize=B.FIG_IN, dpi=B.FIG_DPI, squeeze=False)
    for ax, (t, (y, preds)) in zip(axes[0], cal.items()):
        mx = 0
        for name, p in preds.items():
            q = pd.qcut(pd.Series(p).rank(method="first"), 10, labels=False)
            g = pd.DataFrame({"p": p, "y": y, "q": q}).groupby("q").mean()
            ax.plot(g.p, g.y, "o-", label=f"{name} (ECE {B.ece(y, p):.4f})"); mx = max(mx, g.p.max(), g.y.max())
        ax.plot([0, mx], [0, mx], "k--", lw=1, label="perfect")
        ax.set_xlabel("mean predicted P (decile)"); ax.set_ylabel("observed rate"); ax.set_title(f"{t} calibration")
        ax.legend(fontsize=8); ax.grid(alpha=.3)
    fig.suptitle("Calibration check, 5-fold out-of-fold, SYNTHETIC labels (internal check)")
    B.save_fig(fig, path); plt.close(fig)


def fmt_md(df, cols, f="{:.3f}"):
    h = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    for _, r in df.iterrows():
        h += "| " + " | ".join("" if pd.isna(r.get(c)) else (f.get(c, "{:.3f}") if isinstance(f, dict) else f).format(
            r[c]) if isinstance(r[c], (float, np.floating)) else str(r[c]) for c in cols) + " |\n"
    return h


def main():
    a = B.cli("How-we-compare + lift/dollars.").parse_args()
    df, X_all, reg, note = B.load(a.features, a.labels, a.n_max)
    Xr = X_all[reg].reset_index(drop=True)
    tabs, cal, summ = [], {}, {"SYNTHETIC": True, "prep": note}
    for t in [t for t in a.targets if t in df]:
        tab, scores, y = score_all(t, df, Xr, reg)
        tabs.append(tab)
        cal[t] = (y, {"logreg_unweighted": scores["LR on all 58 prepare() features (unweighted)"],
                      "hgb_sigmoid": scores["HGB + sigmoid calibration (challenger)"]})
        if t == "churn_90d":
            d, meta = lift_catch(df.reset_index(drop=True), reg, y, scores)
            d.insert(0, "synthetic", 1)
            d.to_csv(B.OUT / "lift_catch.csv", index=False, float_format="%.4f")
            summ["dollars_meta"] = meta
            md = ["# Lift and churners caught, churn_90d (ALL SYNTHETIC)\n",
                  "Out-of-fold scores on 5,000 regular sandbox accounts (137 synthetic churners). Binary-rule ties "
                  "broken at random (expected values). Dollars: see harness/model_c_artifacts/policy_eval.csv.\n",
                  fmt_md(d, ["k_label", "targeting", "churners_caught", "share_of_churners", "lift_vs_random",
                             "precision"],
                         {"churners_caught": "{:.1f}", "share_of_churners": "{:.1%}", "lift_vs_random": "{:.2f}x",
                          "precision": "{:.1%}"}),
                  f"\nmeta: {json.dumps(meta)}\n"]
            (B.OUT / "lift_catch.md").write_text("\n".join(md))
            print("\n".join(md))
    tab = pd.concat(tabs, ignore_index=True)
    tab.insert(0, "synthetic", 1)
    tab.to_csv(B.OUT / "how_we_compare.csv", index=False, float_format="%.4f")
    pub = pd.DataFrame(PUBLISHED).assign(dataset="IBM Telco Customer Churn (7,043 customers, 26.5% churn)",
                                         dataset_url=TELCO_DATASET_URL, comparable="no (different dataset)")
    pub.to_csv(B.OUT / "published_telco.csv", index=False)
    md = ["# How we compare (our numbers SYNTHETIC; published numbers are a different dataset)\n"]
    for t, g in tab.groupby("target", sort=False):
        md += [f"## {t}\n", fmt_md(g, ["row", "auc", "auc_fold_sd", "prauc", "top10_capture", "top10_lift",
                                        "rule_flag_share", "rule_recall", "rule_precision"])]
    md += ["## Published IBM Telco Customer Churn AUCs (context only, NOT head-to-head)\n",
           "Different dataset: 7,043 customers, 26.5% churn (vs our 2.7% over 90 days), different features, "
           f"real (not synthetic) labels. Dataset: {TELCO_DATASET_URL}\n",
           fmt_md(pub, ["model", "auc", "source", "url"])]
    (B.OUT / "how_we_compare.md").write_text("\n".join(md))
    print("\n".join(md))
    plot_compare(tab, B.OUT / "how_we_compare.png")
    plot_calibration(cal, B.OUT / "calibration_check.png")
    (B.OUT / "compare_summary.json").write_text(json.dumps(summ, indent=1, default=str))


if __name__ == "__main__":
    main()
