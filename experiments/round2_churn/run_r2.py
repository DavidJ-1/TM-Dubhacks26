"""Round 2 experiments, both tracks, identical folds. ALL SYNTHETIC. Run: OMP_NUM_THREADS=1 .venv/bin/python run_r2.py"""
import os, sys, time, json
sys.dont_write_bytecode = True
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from common import *
from joblib import Parallel, delayed
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler, SplineTransformer
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegressionCV, LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold, GridSearchCV, cross_val_predict
from churn_model import ModelA
import lightgbm as lgb
from interpret.glassbox import ExplainableBoostingClassifier

def inner(k=3): return StratifiedKFold(k, shuffle=True, random_state=0)
CS = [0.003, 0.01, 0.03, 0.1, 0.3, 1, 3]
def lr_cv(): return make_pipeline(StandardScaler(), LogisticRegressionCV(Cs=CS, cv=inner(), scoring="neg_log_loss", max_iter=5000))

class SplineTuned:
    """Spline-LR with knots and C tuned by inner 3-fold CV (log loss); binary cols pass through."""
    def fit(self, X, y):
        cont = [c for c in X.columns if X[c].nunique() > 6]
        ct = ColumnTransformer([("s", SplineTransformer(n_knots=4, degree=3, knots="quantile"), cont)], remainder="passthrough")
        pipe = make_pipeline(ct, StandardScaler(), LogisticRegression(max_iter=5000))
        self.m = GridSearchCV(pipe, {"columntransformer__s__n_knots": [3, 4, 6], "logisticregression__C": [0.01, 0.03, 0.1, 0.3, 1]},
                              scoring="neg_log_loss", cv=inner()).fit(X, y)
        self.best = self.m.best_params_; return self
    def predict_proba(self, X): return self.m.predict_proba(X)

def Spline():  # fixed-config spline LR (sklearn estimator; used in stack)
    from sklearn.compose import make_column_selector
    ct = ColumnTransformer([("s", SplineTransformer(n_knots=4, degree=3, knots="quantile"), lambda d: [c for c in d.columns if d[c].nunique() > 6])], remainder="passthrough")
    return make_pipeline(ct, StandardScaler(), LogisticRegressionCV(Cs=[0.01, 0.03, 0.1, 0.3, 1], cv=inner(), scoring="neg_log_loss", max_iter=5000))

def ebm(): return ExplainableBoostingClassifier(interactions=10, outer_bags=8, learning_rate=0.015, min_samples_leaf=20, max_bins=64, n_jobs=1, random_state=0)
def hgb():
    base = HistGradientBoostingClassifier(learning_rate=0.03, early_stopping=False, random_state=0)
    return GridSearchCV(base, {"max_iter": [150, 400], "max_leaf_nodes": [4, 8], "min_samples_leaf": [50, 150], "l2_regularization": [1.0, 10.0]},
                        scoring="neg_log_loss", cv=inner())
def lgbm():
    base = lgb.LGBMClassifier(learning_rate=0.02, subsample=0.8, subsample_freq=1, colsample_bytree=0.7, verbose=-1, n_jobs=1, random_state=0)
    return GridSearchCV(base, {"n_estimators": [200, 500], "num_leaves": [3, 7], "min_child_samples": [50, 150], "reg_lambda": [1.0, 20.0]},
                        scoring="neg_log_loss", cv=inner())

class Stack:
    """LR meta-learner on inner 4-fold OOF logits of recipe-LR, spline-LR, EBM (each on its own feature view)."""
    def __init__(self, views): self.views = views  # list of (factory, cols)
    def fit(self, Xall, y):
        Z = np.column_stack([cross_val_predict(mk(), Xall[c], y, cv=inner(4), method="predict_proba")[:, 1] for mk, c in self.views])
        self.meta = LogisticRegression(C=1.0, max_iter=2000).fit(self._lg(Z), y)
        self.base = [mk().fit(Xall[c], y) for mk, c in self.views]; return self
    @staticmethod
    def _lg(Z): Z = np.clip(Z, 1e-6, 1 - 1e-6); return np.log(Z / (1 - Z))
    def predict_proba(self, Xall):
        Z = np.column_stack([m.predict_proba(Xall[c])[:, 1] for m, (_, c) in zip(self.base, self.views)]); return self.meta.predict_proba(self._lg(Z))

XA = pd.concat([X, T.add_prefix("T_")], axis=1)
Tc, Tc_ok = ["T_" + c for c in T.columns], ["T_" + c for c in T_ok.columns]
def specs(track):
    ok = track == "compliant"
    base_cols = [c for c in X.columns if not (ok and (c in CPNI))]
    pc = plus_ok if ok else plus; tc = Tc_ok if ok else Tc
    return {
        f"baseline ModelA LR": (lambda: ModelA(feature_set="core"), [c for c in base_cols if not c.startswith("raw_")]),
        f"spline-LR tuned (core)": (SplineTuned, core_ok if ok else core),
        f"spline-LR tuned (core+raw contacts)": (SplineTuned, pc),
        f"EBM interactions=10 (core+raw contacts)": (ebm, pc),
        f"HGB tuned inner-CV (core+raw contacts)": (hgb, pc),
        f"LightGBM tuned inner-CV (core+raw contacts)": (lgbm, pc),
        f"RECIPE-LR: generator terms (fits synthetic recipe)": (lr_cv, tc),
        f"RECIPE-spline-LR (fits synthetic recipe)": (Spline, tc),
        f"stack LR-meta[recipe-LR, spline, EBM]": (lambda tc=tc, pc=pc: Stack([(lr_cv, tc), (Spline, pc), (ebm, pc)]), tc + [c for c in pc if c not in tc]),
    }

def run_one(track, name, mk, cols, folds_=None, seed=None):
    t0 = time.time(); fl = folds_ if folds_ is not None else FOLDS; p = np.zeros(len(yv)); info = []
    for tr, te in fl:
        m = mk().fit(XA.iloc[tr][cols], yv[tr]); pr = m.predict_proba(XA.iloc[te][cols]); p[te] = pr if pr.ndim == 1 else pr[:, 1]
        info.append(str(getattr(m, "best", getattr(getattr(m, "m", None), "best_params_", getattr(m, "best_params_", "")))))
    return track, name, p, info, time.time() - t0

if __name__ == "__main__":
    jobs = [(tr, n, mk, c) for tr in ("full", "compliant") for n, (mk, c) in specs(tr).items()]
    out = Parallel(n_jobs=int(os.environ.get("NJ", 8)), verbose=0)(delayed(run_one)(*j) for j in jobs)
    oof = {}; hp = {}
    for tr, n, p, info, dt in out:
        oof[f"[{tr}] {n}"] = p; hp[f"[{tr}] {n}"] = info; print(f"[{tr}] {n}: {({k: round(v, 4) for k, v in M.all_metrics(yv, p).items()})} ({dt:.0f}s)", flush=True)
    pd.DataFrame(oof).assign(account_id=feats.account_id.values, fold=fid, churn_90d=yv).to_csv(HERE / "oof_r2.csv", index=False)
    json.dump(hp, open(HERE / "chosen_hparams.json", "w"), indent=1)
    print("ORACLE p_true_90d (eval-only):", M.all_metrics(yv, p_true))
