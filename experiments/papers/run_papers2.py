"""Round 2: Firth/FLIC LR, spline-LR (GAM-like), bagged ModelA. Compliant core only. ALL SYNTHETIC."""
import os, sys, warnings, time
sys.dont_write_bytecode = True; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler, SplineTransformer
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegressionCV
from sklearn.model_selection import StratifiedKFold
from scipy.special import expit
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, "/workspace/tmobile/TM-Dubhacks26/harness")
import folds, metrics as M
from churn_features import CORE_FEATURES, leak_columns, prepare
from churn_model import ModelA
feats, y, labels = folds.load_raw()
barred = set(labels.columns) - {"account_id"}
feats_c = feats.drop(columns=[c for c in feats.columns if c != "account_id" and (c in barred or c in leak_columns([c]))])
X = prepare(feats_c).astype(float); yv = y.values; FOLDS = folds.get_folds(yv); fid = folds.fold_ids(yv)
core_ok = [c for c in CORE_FEATURES if c in X.columns and c not in ("port_out_inquiry", "competitor_research_score")]
Xc = X[core_ok]

class FirthFLIC:
    """Firth bias-reduced LR (Newton with hat-matrix-adjusted score) + FLIC intercept correction (Puhr et al. 2017)."""
    def fit(self, X, y):
        self.mu, self.sd = X.mean(), X.std(ddof=0).replace(0, 1)
        Z = np.c_[np.ones(len(y)), ((X - self.mu) / self.sd).values]; b = np.zeros(Z.shape[1])
        for _ in range(50):
            p = expit(Z @ b); W = p * (1 - p)
            I = Z.T @ (Z * W[:, None]); Ii = np.linalg.inv(I + 1e-8 * np.eye(len(b)))
            h = np.einsum("ij,jk,ik->i", Z * np.sqrt(W)[:, None], Ii, Z * np.sqrt(W)[:, None])
            step = Ii @ (Z.T @ (y - p + h * (0.5 - p)))
            b += np.clip(step, -1, 1)
            if np.abs(step).max() < 1e-6: break
        eta = Z[:, 1:] @ b[1:]; lo, hi = -15, 5   # FLIC: refit intercept so mean prediction == event rate
        for _ in range(60):
            m = (lo + hi) / 2; lo, hi = (m, hi) if expit(eta + m).mean() < y.mean() else (lo, m)
        b[0] = (lo + hi) / 2; self.b = b; return self
    def predict_proba(self, X):
        Z = np.c_[np.ones(len(X)), ((X - self.mu) / self.sd).values]; p = expit(Z @ self.b); return np.c_[1 - p, p]

def spline_lr():
    cont = [c for c in core_ok if Xc[c].nunique() > 6]
    ct = ColumnTransformer([("s", SplineTransformer(n_knots=4, degree=3, knots="quantile"), cont)], remainder="passthrough")
    return make_pipeline(ct, StandardScaler(), LogisticRegressionCV(Cs=[0.003, 0.01, 0.03, 0.1, 0.3, 1], cv=StratifiedKFold(3, shuffle=True, random_state=0), scoring="neg_log_loss", max_iter=5000))

class BagA:
    """Bootstrap-aggregated ModelA (20 bags): variance reduction for ~110 training positives."""
    def fit(self, X, y):
        rng = np.random.default_rng(0); self.ms = []
        for _ in range(20):
            i = rng.choice(len(y), len(y)); self.ms.append(ModelA(feature_set="core").fit(X.iloc[i], y[i]))
        return self
    def predict_proba(self, X): return np.mean([m.predict_proba(X) for m in self.ms], axis=0)

def oofp(mk, Xm):
    p = np.zeros(len(yv))
    for tr, te in FOLDS: p[te] = mk().fit(Xm.iloc[tr], yv[tr]).predict_proba(Xm.iloc[te])
    return p
B0 = oofp(lambda: ModelA(feature_set="core"), X); B1 = oofp(lambda: ModelA(feature_set="core"), Xc)
oof0 = pd.DataFrame({"account_id": feats.account_id.values, "fold": fid, "churn_90d": yv})
rows = []
for name, mk in [("R1 Firth+FLIC LR, compliant core", FirthFLIC), ("R2 spline-LR (GAM-like), compliant core", spline_lr), ("R3 bagged ModelA x20, compliant core", BagA)]:
    t0 = time.time(); p = np.zeros(len(yv))
    for tr, te in FOLDS:
        pr = mk().fit(Xc.iloc[tr], yv[tr]).predict_proba(Xc.iloc[te]); p[te] = pr if pr.ndim == 1 else pr[:, 1]
    a = M.all_metrics(yv, p); r = {"model": name, **a, **M.bootstrap_ci(yv, p, n_boot=300)}
    for ref, tag in ((B0, "vsB0"), (B1, "vsB1")):
        d, s = M.paired_fold_comparison(yv, p, ref, fid); pb = M.paired_bootstrap_delta(yv, p, ref, n_boot=300)
        r.update({f"{tag}_dauc_fold": f"{s.loc['auc','mean']:+.4f}±{s.loc['auc','sd']:.4f}", f"{tag}_dtop10_fold": f"{s.loc['top10','mean']:+.3f}±{s.loc['top10','sd']:.3f}",
                  f"{tag}_folds_better_top10": int(s.loc['top10', 'n_folds_better']), f"{tag}_dauc_boot": "%+.4f [%+.4f,%+.4f]" % pb["d_auc_boot"], f"{tag}_dtop10_boot": "%+.3f [%+.3f,%+.3f]" % pb["d_top10_boot"]})
    rows.append(r); oof0[name] = p; print(name, {k: round(v, 4) for k, v in a.items()}, f"({time.time()-t0:.0f}s)", flush=True)
pd.DataFrame(rows).to_csv(HERE / "results_round2.csv", index=False); oof0.to_csv(HERE / "oof_predictions_round2.csv", index=False)
pd.set_option("display.width", 300); pd.set_option("display.max_columns", 40); print(pd.DataFrame(rows).round(4).to_string())
