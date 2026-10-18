"""Value-aware ranking experiments. SYNTHETIC. Same folds as harness Model A."""
import sys, warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore"); sys.dont_write_bytecode = True
R = "/workspace/tmobile/TM-Dubhacks26"; sys.path.insert(0, R + "/harness")
from churn_features import prepare, CORE_FEATURES, leak_columns
from churn_model import ModelA
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, average_precision_score
feats = pd.read_csv(R + "/demo_data/features.csv"); labels = pd.read_csv(R + "/demo_data/labels.csv")
enr = pd.read_csv(R + "/demo_data/enrichment.csv").set_index("account_id")
folds = pd.read_csv(R + "/demo_data/churn_oof_pred.csv").set_index("account_id"); ids = folds.index; fold = folds.fold.values
barred = set(labels.columns) - {"account_id"}
F = feats.drop(columns=[c for c in feats.columns if c != "account_id" and (c in barred or c in leak_columns([c]))])
X = prepare(F).loc[ids]; base_cols = [c for c in CORE_FEATURES if c in X.columns]; X = X[base_cols]
y = labels.set_index("account_id").churn_90d.loc[ids].astype(int).values
fr = feats.set_index("account_id").loc[ids]
bill = fr.last_bill_cents.values / 100.0; value = bill / bill.mean()   # value = monthly bill / ARPA (sample mean)

def weighted_lr(w_fn):
    p = np.zeros(len(y))
    for f in range(5):
        tr, te = fold != f, fold == f
        m = ModelA(feature_set="all").fit(X[tr], y[tr])       # same sign-pruned cols + CV'd C as baseline
        Z = (X[m.cols_] - m.mu_) / m.sd_; w = w_fn(value[tr]); w = w / w.mean()
        lr = LogisticRegression(C=m.C_, max_iter=5000).fit(Z[tr], y[tr], sample_weight=w)
        p[te] = lr.predict_proba(Z[te])[:, 1]
    return p
def hgb(w_fn):
    p = np.zeros(len(y))
    for f in range(5):
        tr, te = fold != f, fold == f; w = w_fn(value[tr]); w = w / w.mean()
        m = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=40,
                                           l2_regularization=1.0, random_state=2026).fit(X[tr], y[tr], sample_weight=w)
        p[te] = m.predict_proba(X[te])[:, 1]
    return p
p_base = np.load("oof_baseline_LR.npy")
S = {"(a) baseline LR, rank by p": (p_base, p_base),
     "(b) baseline p x value": (p_base, p_base * value),
     "(c1) LR weighted by value": None, "(c2) LR weighted by sqrt(value)": None,
     "(d0) HGB unweighted": None, "(d1) HGB weighted by value": None}
JOBS = {"c1": lambda: weighted_lr(lambda v: v), "c2": lambda: weighted_lr(np.sqrt),
        "d0": lambda: hgb(lambda v: np.ones_like(v)), "d1": lambda: hgb(lambda v: v)}
if len(sys.argv) > 1:
    np.save(f"val_{sys.argv[1]}.npy", JOBS[sys.argv[1]]()); sys.exit()
pc1, pc2, pd0, pd1 = (np.load(f"val_{j}.npy") for j in ("c1", "c2", "d0", "d1"))
S["(c1) LR weighted by value"] = (pc1, pc1); S["(c2) LR weighted by sqrt(value)"] = (pc2, pc2)
S["(d0) HGB unweighted"] = (pd0, pd0); S["(d1) HGB weighted by value"] = (pd1, pd1)
S["(e) HGB-weighted p x value"] = (pd1, pd1 * value); S["(f) sqrt-weighted LR p x value"] = (pc2, pc2 * value)
k = int(round(0.1 * len(y)))
def caps(idx, s):
    yy, bb = y[idx], bill[idx]; top = np.argsort(-s[idx], kind="stable")[:k]
    return yy[top].sum() / yy.sum(), (yy[top] * bb[top]).sum() / (yy * bb).sum()
rng = np.random.default_rng(2026); boots = [rng.integers(0, len(y), len(y)) for _ in range(300)]
allidx = np.arange(len(y)); bc = np.array([caps(i, S["(a) baseline LR, rank by p"][1]) for i in boots])
senior = (fr.segment == "senior").values; d55 = (fr.discount_group == "55_plus").values
inc = enr.household_income_usd.reindex(ids).values; ainc = enr.area_median_income_usd.reindex(ids).values
rows = []
for name, (p, s) in S.items():
    c, d = caps(allidx, s); top = np.argsort(-s, kind="stable")[:k]
    bd = np.array([caps(i, s) for i in boots]) - bc
    fd = np.array([caps(np.where(fold == f)[0], s) for f in range(5)]) - np.array([caps(np.where(fold == f)[0], p_base) for f in range(5)])
    rows.append({"ranking": name, "AUC(p)": roc_auc_score(y, p), "PR_AUC(p)": average_precision_score(y, p),
                 "top10_churner_cap": c, "d_cnt_CI": "[%+.3f,%+.3f]" % tuple(np.percentile(bd[:, 0], [2.5, 97.5])),
                 "fold_d_cnt": "%+.3f±%.3f" % (fd[:, 0].mean(), fd[:, 0].std(ddof=1)),
                 "top10_churn$_cap": d, "d_$_CI": "[%+.3f,%+.3f]" % tuple(np.percentile(bd[:, 1], [2.5, 97.5])),
                 "fold_d_$": "%+.3f±%.3f" % (fd[:, 1].mean(), fd[:, 1].std(ddof=1)),
                 "n_churners_top10": int(y[top].sum()), "avg_bill_top10": bill[top].mean(), "avg_bill_all": bill.mean(),
                 "senior_share_top10": senior[top].mean(), "55plus_share_top10": d55[top].mean(),
                 "med_income_top10": np.nanmedian(inc[top]), "med_area_income_top10": np.nanmedian(ainc[top])})
res = pd.DataFrame(rows); res.to_csv("value_results.csv", index=False)
pd.set_option("display.width", 300); pd.set_option("display.max_columns", 30); print(res.to_string(index=False))
print("overall: senior %.3f 55plus %.3f med income %.0f med area income %.0f" % (senior.mean(), d55.mean(), np.nanmedian(inc), np.nanmedian(ainc)))
v = pd.Series(bill)
for nm, a in [("senior", senior.astype(float)), ("55_plus", d55.astype(float)), ("household_income", inc), ("area_median_income", ainc), ("n_lines", fr.n_lines.values)]:
    print(f"corr(bill,{nm}) = {v.corr(pd.Series(a), method='spearman'):+.3f}")
print("mean bill senior vs not: %.1f vs %.1f; 55plus vs not: %.1f vs %.1f" % (bill[senior].mean(), bill[~senior].mean(), bill[d55].mean(), bill[~d55].mean()))
print("churn rate senior %.4f, 55plus %.4f, all %.4f" % (y[senior].mean(), y[d55].mean(), y.mean()))
