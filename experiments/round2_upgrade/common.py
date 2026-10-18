"""Shared model zoo + evaluation. ALL SYNTHETIC."""
import os, sys, warnings; warnings.filterwarnings("ignore")
os.environ.setdefault("OMP_NUM_THREADS", "1")
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, ".pylib")); sys.path.insert(0, "/workspace/tmobile/scratch_models")
import numpy as np, pandas as pd
import metrics as M
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler, SplineTransformer
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import StratifiedKFold, StratifiedGroupKFold
from sklearn.metrics import roc_auc_score, average_precision_score
from interpret.glassbox import ExplainableBoostingClassifier

def lr(): return make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=3000))

def spline_lr(X):
    cont = [c for c in X.columns if X[c].nunique() > 6]; rest = [c for c in X.columns if c not in cont]
    def f():
        ct = ColumnTransformer([("s", make_pipeline(StandardScaler(), SplineTransformer(n_knots=5, degree=3, knots="quantile")), cont),
                                ("p", StandardScaler(), rest)])
        return make_pipeline(ct, LogisticRegression(C=0.1, max_iter=5000))
    return f

def ebm(): return ExplainableBoostingClassifier(interactions=5, outer_bags=4, max_rounds=2000, n_jobs=1, random_state=2026)

HGB_GRID = [dict(max_depth=2, learning_rate=0.05, max_iter=300, min_samples_leaf=50, l2_regularization=1.0),
            dict(max_depth=3, learning_rate=0.03, max_iter=300, min_samples_leaf=80, l2_regularization=3.0),
            dict(max_depth=None, max_leaf_nodes=8, learning_rate=0.05, max_iter=200, min_samples_leaf=100, l2_regularization=1.0),
            dict(max_depth=4, learning_rate=0.02, max_iter=400, min_samples_leaf=150, l2_regularization=5.0)]

class TunedHGB:
    """Picks a config by 3-fold inner CV log-loss on the training fold only (nested; no test leakage)."""
    def fit(self, X, y):
        from sklearn.model_selection import cross_val_score
        sc = [cross_val_score(HistGradientBoostingClassifier(random_state=0, **g), X, y, cv=StratifiedKFold(3, shuffle=True, random_state=1), scoring="neg_log_loss").mean() for g in HGB_GRID]
        self.cfg = int(np.argmax(sc)); self.m = HistGradientBoostingClassifier(random_state=0, **HGB_GRID[self.cfg]).fit(X, y); return self
    def predict_proba(self, X): return self.m.predict_proba(X)

def oof(make, X, y, folds):
    p = np.zeros(len(y))
    for tr, te in folds: p[te] = make().fit(X.iloc[tr], y[tr]).predict_proba(X.iloc[te])[:, 1]
    return p

def fold_ids(folds, n):
    f = np.zeros(n, int)
    for k, (_, te) in enumerate(folds): f[te] = k
    return f

def evaluate(P, y, fid, ref_name, prob_models, n_boot=200):
    rows = []
    for n, p in P.items():
        pf = M.per_fold(y, np.clip(p, 0, 1) if n in prob_models else (p - p.min()) / (p.max() - p.min() + 1e-12), fid)
        ci = M.bootstrap_ci(y, p, n_boot=n_boot); t10 = M.top_capture(y, p)
        r = {"model": n, "auc": roc_auc_score(y, p), "auc_ci": "[%.3f, %.3f]" % ci["auc_ci"], "auc_fold": f"{pf.auc.mean():.3f}±{pf.auc.std():.3f}",
             "pr_auc": average_precision_score(y, p), "pr_auc_ci": "[%.3f, %.3f]" % ci["pr_auc_ci"],
             "top10": t10, "top10_ci": "[%.3f, %.3f]" % ci["top10_ci"], "lift10": t10 / 0.10,
             "precision10": y[np.argsort(-p)[:round(0.1 * len(y))]].mean()}
        if n in prob_models:
            r.update(brier=M.brier_score_loss(y, np.clip(p, 0, 1)), ece=M.ece(y, np.clip(p, 0, 1))[0], mean_pred=p.mean())
        if n != ref_name:
            d = M.paired_bootstrap_delta(y, p, P[ref_name], n_boot=n_boot)
            r["dAUC_vs_ref"] = "%+.3f [%+.3f, %+.3f]" % d["d_auc_boot"]; r["dTop10_vs_ref"] = "%+.3f [%+.3f, %+.3f]" % d["d_top10_boot"]
            r["beats_ref_beyond_noise"] = bool(d["d_auc_boot"][1] > 0)
        rows.append(r)
    return pd.DataFrame(rows).round(4)
