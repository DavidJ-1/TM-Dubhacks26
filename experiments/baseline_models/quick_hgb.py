"""Fast fallback HGB (fixed params, no grid) + rank-average ensemble with baseline. SYNTHETIC.
Run: OMP_NUM_THREADS=1 /workspace/tmobile/TM-Dubhacks26/.venv/bin/python quick_hgb.py"""
import sys, warnings; sys.dont_write_bytecode = True; warnings.filterwarnings("ignore")
sys.path.insert(0, "."); sys.path.insert(0, "/workspace/tmobile/TM-Dubhacks26/harness")
import numpy as np, pandas as pd, folds, metrics as M
from scipy.stats import rankdata
from sklearn.ensemble import HistGradientBoostingClassifier
from churn_features import leak_columns, prepare
f, y, lab = folds.load_raw(); yv = y.values; fid = folds.fold_ids(yv)
barred = set(lab.columns) - {"account_id"}
X = prepare(f.drop(columns=[c for c in f.columns if c != "account_id" and (c in barred or c in leak_columns([c]))])).astype(float)
base = pd.read_csv(folds.DATA / "churn_oof_pred.csv").set_index("account_id").loc[f.account_id, "p_churn_90d"].values  # == refit baseline
p = np.zeros(len(yv))
for tr, te in folds.get_folds(yv):
    p[te] = HistGradientBoostingClassifier(learning_rate=0.05, max_iter=150, max_leaf_nodes=7, min_samples_leaf=100,
                                           l2_regularization=1.0, random_state=0).fit(X.iloc[tr], yv[tr]).predict_proba(X.iloc[te])[:, 1]
ens = (rankdata(base) + rankdata(p)) / 2
pd.DataFrame({"account_id": f.account_id, "fold": fid, "hgb": p, "ens_rank": ens, "baseline": base}).to_csv("oof_quick_hgb.csv", index=False)
for name, s in [("HGB fixed", p), ("rank-avg baseline+HGB", ens)]:
    print(name, {k: round(v, 4) for k, v in M.all_metrics(yv, s).items()}, M.bootstrap_ci(yv, s, 300))
    print(M.paired_fold_comparison(yv, s, base, fid)[1].round(4).to_string()); print(M.paired_bootstrap_delta(yv, s, base, 300))
