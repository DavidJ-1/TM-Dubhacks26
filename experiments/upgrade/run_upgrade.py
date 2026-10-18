"""Upgrade propensity on SIMULATED label labels.csv:upgrade_90d. ALL SYNTHETIC. Reads demo_data read-only."""
import sys, json, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "/workspace/tmobile/scratch_models")
import numpy as np, pandas as pd
from folds import load_raw, fold_ids, DATA
import metrics as M
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import roc_auc_score

f, ychurn, lab = load_raw()
fid = fold_ids(ychurn)  # EXACT churn folds (stratified on churn, seed 2026)
y = lab["upgrade_90d"].astype(int).values
assert (lab["account_id"].values == f["account_id"].values).all()
EXCL = ["account_id", "is_persona", "port_out_inquiry", "competitor_research_score",  # port-out / competitor
        "language", "segment", "discount_group"]  # protected-attribute proxies (age: senior/55_plus/student; language->ethnicity)
X = f.drop(columns=[c for c in EXCL if c in f]).copy()
cat = [c for c in X.columns if not pd.api.types.is_numeric_dtype(X[c])]
X = pd.get_dummies(X, columns=cat, dummy_na=False).astype(float)
X["plan_data_cap_gb_missing"] = X["plan_data_cap_gb"].isna().astype(float)
X = X.fillna(X.median())
# domain ratios (pre-cutoff, from existing features only)
X["util_per_line"] = (f["data_gb_3m_avg"] / f["n_lines"] / f["plan_data_cap_gb"]).fillna(0).clip(0, 5)
X["over_cap_share"] = f["n_lines_over_cap_3m"] / f["n_lines"]
X["hotspot_per_line"] = f["hotspot_gb_3m_avg"] / f["n_lines"]
print("n", len(y), "pos", y.sum(), "rate", y.mean().round(4), "features", X.shape[1])
print("upgrade positives per churn fold:", [int(y[fid == k].sum()) for k in range(5)])

def oof(make):
    p = np.zeros(len(y))
    for k in range(5):
        tr, te = fid != k, fid == k
        p[te] = make().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    return p

models = {
 "LR (C=0.1, std)": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=3000)),
 "LR balanced": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.1, class_weight="balanced", max_iter=3000)),
 "HGB (shallow, regularized)": lambda: HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, l2_regularization=1.0, min_samples_leaf=40, random_state=0),
}
P = {n: oof(m) for n, m in models.items()}
P["oracle p_upgrade_90d (generator truth, ceiling)"] = lab["p_upgrade_90d"].values
rows, base = [], P["LR (C=0.1, std)"]
for n, p in P.items():
    pf = M.per_fold(y, p, fid); a = M.all_metrics(y, p); ci = M.bootstrap_ci(y, p, n_boot=200)
    r = {"model": n, **{k: round(v, 4) for k, v in a.items()},
         "auc_fold": f"{pf.auc.mean():.3f}±{pf.auc.std():.3f}", "prauc_fold": f"{pf.pr_auc.mean():.3f}±{pf.pr_auc.std():.3f}",
         "top10_fold": f"{pf.top10.mean():.3f}±{pf.top10.std():.3f}",
         "auc_ci": "[%.3f, %.3f]" % ci["auc_ci"], "top10_ci": "[%.3f, %.3f]" % ci["top10_ci"], "mean_pred": round(float(p.mean()), 4)}
    if n != "LR (C=0.1, std)":
        d = M.paired_bootstrap_delta(y, p, base, n_boot=200); _, s = M.paired_fold_comparison(y, p, base, fid)
        r["dAUC_vs_LR [95%CI]"] = "%+.3f [%+.3f, %+.3f]" % d["d_auc_boot"]; r["dTop10_vs_LR [95%CI]"] = "%+.3f [%+.3f, %+.3f]" % d["d_top10_boot"]
        r["folds_better_auc"] = int(s.loc["auc", "n_folds_better"])
    rows.append(r)
res = pd.DataFrame(rows); res.to_csv("results.csv", index=False); print(res.T.to_string())
# leakage audit
sf = {c: max(roc_auc_score(y, X[c]), 1 - roc_auc_score(y, X[c])) for c in X.columns if X[c].nunique() > 1}
sf = pd.Series(sf).sort_values(ascending=False); sf.to_csv("single_feature_auc.csv"); print("top single-feature AUC\n", sf.head(10).round(3))
# overlap with churn top-10%
best = "HGB (shallow, regularized)" if res.set_index("model").loc["HGB (shallow, regularized)", "auc"] > res.set_index("model").loc["LR (C=0.1, std)", "auc"] else "LR (C=0.1, std)"
pu = P[best]; churn = pd.read_csv(DATA / "churn_oof_pred.csv").set_index("account_id").loc[f["account_id"], "p_churn_90d"].values
k = round(0.1 * len(y)); tu = set(np.argsort(-pu)[:k]); tc = set(np.argsort(-churn)[:k]); ov = tu & tc
ovl = {"model_for_overlap": best, "k": k, "overlap": len(ov), "overlap_share": len(ov) / k, "expected_if_independent": k * k / len(y),
       "spearman_upgrade_vs_churn": float(pd.Series(pu).corr(pd.Series(churn), method="spearman")),
       "churners_in_upgrade_top10": int(ychurn.values[list(tu)].sum()), "upgraders_in_churn_top10": int(y[list(tc)].sum())}
print(ovl); json.dump(ovl, open("overlap.json", "w"), indent=1)
pd.DataFrame({"account_id": f["account_id"], "fold": fid, "upgrade_90d": y, **{n: P[n].round(6) for n in models}}).to_csv("upgrade_oof_pred.csv", index=False)
