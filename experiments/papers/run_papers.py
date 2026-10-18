"""Paper-inspired cheap methods vs baseline LR on identical folds. ALL DATA/METRICS SYNTHETIC.
Run: .venv/bin/python run_papers.py   (reads demo_data read-only; writes only in this folder)"""
import os, sys, json, warnings, time
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"; sys.dont_write_bytecode = True
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegressionCV, LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from scipy.stats import rankdata
import lightgbm as lgb
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, "/workspace/tmobile/TM-Dubhacks26/harness")
import folds, metrics as M
from churn_features import CORE_FEATURES, leak_columns, prepare
from churn_model import ModelA

feats, y, labels = folds.load_raw()
barred = set(labels.columns) - {"account_id"}
feats_c = feats.drop(columns=[c for c in feats.columns if c != "account_id" and (c in barred or c in leak_columns([c]))])
X = prepare(feats_c).astype(float)
yv = y.values; FOLDS = folds.get_folds(yv); fid = folds.fold_ids(yv)
# CPNI compliance: no port-out/porting, competitor-contact, location, protected attrs/proxies (age, gender, race, ZIP, language)
CPNI_PAT = ("port", "competitor", "zip", "location", "geo", "lat", "lon", "state", "city", "age_", "gender", "race",
            "language", "senior", "55_plus", "segment=")
flag = [c for c in X.columns if any(t in c.lower() for t in CPNI_PAT) and "device_age" not in c and "usage" not in c]
core = [c for c in CORE_FEATURES if c in X.columns]
core_ok = [c for c in core if c not in flag]
print("[SYNTHETIC] n", len(yv), "pos", yv.sum(), "| CPNI-flagged prepared cols:", flag, "| core dropped:", sorted(set(core)-set(core_ok)), flush=True)

def inner(): return StratifiedKFold(3, shuffle=True, random_state=0)
def lr_cv(): return make_pipeline(StandardScaler(), LogisticRegressionCV(Cs=[0.003,0.01,0.03,0.1,0.3,1,3,10], cv=inner(), scoring="neg_log_loss", max_iter=5000))

class MonoHGB:
    """HGB with monotonic constraints whose signs come from training-fold univariate correlation (only for |r|>0.02)."""
    def __init__(self, **kw): self.kw = kw
    def fit(self, X, y):
        r = np.array([np.corrcoef(X.iloc[:, j], y)[0, 1] if X.iloc[:, j].std() > 0 else 0 for j in range(X.shape[1])])
        r = np.nan_to_num(r); cst = np.where(r > 0.02, 1, np.where(r < -0.02, -1, 0))
        self.m = HistGradientBoostingClassifier(monotonic_cst=cst, random_state=0, **self.kw).fit(X, y); return self
    def predict_proba(self, X): return self.m.predict_proba(X)

class LGBRank:
    """LightGBM lambdarank (pairwise/listwise ranking objective, NDCG truncated at top-10%) on training-fold chunks."""
    def __init__(self, n=300): self.n = n
    def fit(self, X, y):
        rng = np.random.default_rng(0); idx = rng.permutation(len(y)); q = 500
        idx = idx[: len(idx)//q*q]
        self.m = lgb.LGBMRanker(objective="lambdarank", n_estimators=self.n, learning_rate=0.03, num_leaves=7, min_child_samples=40,
                                colsample_bytree=0.8, reg_lambda=1.0, lambdarank_truncation_level=50, n_jobs=1,
                                verbose=-1, random_state=0)
        self.m.fit(X.iloc[idx], y[idx], group=[q]*(len(idx)//q), eval_at=[50]); return self
    def predict_proba(self, X): s = self.m.predict(X); return np.c_[-s, s]

class LGBFocal:
    """LightGBM binary with focal loss (Lin et al. 2017), gamma=2, alpha=0.25; scores used for ranking."""
    def __init__(self, gamma=2.0, alpha=0.25, n=300): self.g, self.a, self.n = gamma, alpha, n
    def fit(self, X, y):
        g, a = self.g, self.a
        def focal(y_true, raw):
            # numeric grad/hess of focal loss wrt raw score
            def loss(z):
                p = 1/(1+np.exp(-z)); p = np.clip(p, 1e-9, 1-1e-9)
                return -(a*y_true*(1-p)**g*np.log(p) + (1-a)*(1-y_true)*p**g*np.log(1-p))
            e = 1e-4; l0, lp, lm = loss(raw), loss(raw+e), loss(raw-e)
            return (lp-lm)/(2*e), np.maximum((lp-2*l0+lm)/e**2, 1e-6)
        self.m = lgb.LGBMClassifier(objective=focal, n_estimators=self.n, learning_rate=0.03, num_leaves=7, min_child_samples=40,
                                    subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, verbose=-1, random_state=0, n_jobs=1).fit(X, y)
        return self
    def predict_proba(self, X): s = self.m.predict(X, raw_score=True); p = 1/(1+np.exp(-s)); return np.c_[1-p, p]

class LGBBin:
    def fit(self, X, y):
        self.m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.03, num_leaves=7, min_child_samples=40, subsample=0.8, subsample_freq=1,
                                    colsample_bytree=0.8, reg_lambda=1.0, verbose=-1, random_state=0, n_jobs=1).fit(X, y); return self
    def predict_proba(self, X): return self.m.predict_proba(X)

class OverLR:
    """Random oversampling of positives to 1:3 before LR (SMOTE-family stand-in; Elor & Averbuch-Elor 2022 predict no gain)."""
    def fit(self, X, y):
        rng = np.random.default_rng(0); pos = np.where(y == 1)[0]; neg = np.where(y == 0)[0]
        extra = rng.choice(pos, len(neg)//3 - len(pos)); i = np.r_[neg, pos, extra]
        self.m = lr_cv().fit(X.iloc[i], y[i]); return self
    def predict_proba(self, X): return self.m.predict_proba(X)

class IsoCal:
    """Baseline ModelA + isotonic calibration fit on inner-CV OOF scores of the training fold."""
    def fit(self, X, y):
        s = np.zeros(len(y))
        for tr, te in inner().split(X, y): s[te] = ModelA(feature_set="core").fit(X.iloc[tr], y[tr]).predict_proba(X.iloc[te])
        self.iso = IsotonicRegression(out_of_bounds="clip", y_min=1e-4).fit(s, y)
        self.m = ModelA(feature_set="core").fit(X, y); return self
    def predict_proba(self, X): p = self.m.predict_proba(X); return np.c_[1-self.iso.predict(p), self.iso.predict(p)][:, ::-1][:, ::-1]

Xok_all = X.drop(columns=flag)
MODELS = {
 "B0 baseline ModelA LR (core, incl. port/competitor)": (lambda: ModelA(feature_set="core"), X),
 "B1 ModelA LR CPNI-compliant core": (lambda: ModelA(feature_set="core"), X.drop(columns=flag)),
 "P1 HGB monotone-constrained, compliant core": (lambda: MonoHGB(learning_rate=0.05, max_iter=200, max_leaf_nodes=7, min_samples_leaf=60, l2_regularization=1.0), X[core_ok]),
 "P1b HGB monotone, all compliant feats": (lambda: MonoHGB(learning_rate=0.05, max_iter=200, max_leaf_nodes=7, min_samples_leaf=60, l2_regularization=1.0), Xok_all),
 "P2 LightGBM lambdarank (top-k objective), compliant core": (lambda: LGBRank(), X[core_ok]),
 "P3 LightGBM focal loss, compliant core": (lambda: LGBFocal(), X[core_ok]),
 "P3b LightGBM binary logloss, compliant core": (lambda: LGBBin(), X[core_ok]),
 "P4 LR + random oversampling 1:3, compliant core": (lambda: OverLR(), X[core_ok]),
 "P5 ModelA + isotonic calibration (compliant)": (lambda: IsoCal(), X.drop(columns=flag)),
}
oof = {}
for name, (mk, Xm) in MODELS.items():
    t0 = time.time(); p = np.zeros(len(yv))
    for tr, te in FOLDS:
        m = mk().fit(Xm.iloc[tr], yv[tr]); pr = m.predict_proba(Xm.iloc[te])
        p[te] = pr if pr.ndim == 1 else pr[:, 1]
    oof[name] = p; print(f"{name}: {M.all_metrics(yv, np.clip(p,0,1) if 'rank' not in name else rankdata(p)/len(p))} ({time.time()-t0:.0f}s)", flush=True)

rk = lambda a: rankdata(a)/len(a)
oof["P6 rank-avg ensemble B1 LR + P1 mono-HGB (compliant)"] = (rk(oof["B1 ModelA LR CPNI-compliant core"]) + rk(oof["P1 HGB monotone-constrained, compliant core"]))/2
oof["P6b rank-avg B1 LR + P1 mono-HGB + P2 lambdarank (compliant)"] = (rk(oof["B1 ModelA LR CPNI-compliant core"]) + rk(oof["P1 HGB monotone-constrained, compliant core"]) + rk(oof["P2 LightGBM lambdarank (top-k objective), compliant core"]))/3
RANK_ONLY = {k for k in oof if k.startswith(("P2 ", "P3 ", "P6"))}

B0, B1 = "B0 baseline ModelA LR (core, incl. port/competitor)", "B1 ModelA LR CPNI-compliant core"
stored = pd.read_csv(folds.DATA / "churn_oof_pred.csv").set_index("account_id").loc[feats.account_id, "p_churn_90d"].values
rows = []
for name, p in oof.items():
    ps = rk(p) if name in RANK_ONLY else np.clip(p, 0, 1)
    a = M.all_metrics(yv, ps); pf = M.per_fold(yv, ps, fid); ci = M.bootstrap_ci(yv, ps, n_boot=500)
    r = {"model": name, **a, "auc_fold_sd": pf.auc.std(), "top10_fold_sd": pf.top10.std(), **ci}
    for ref, tag in ((B0, "vsB0"), (B1, "vsB1")):
        if name == ref: continue
        d, s = M.paired_fold_comparison(yv, ps, oof[ref], fid); pb = M.paired_bootstrap_delta(yv, ps, oof[ref], n_boot=500)
        r.update({f"{tag}_dauc_fold": f"{s.loc['auc','mean']:+.4f}±{s.loc['auc','sd']:.4f}", f"{tag}_dtop10_fold": f"{s.loc['top10','mean']:+.3f}±{s.loc['top10','sd']:.3f}",
                  f"{tag}_folds_better_top10": int(s.loc["top10", "n_folds_better"]),
                  f"{tag}_dauc_boot": "%+.4f [%+.4f,%+.4f]" % pb["d_auc_boot"], f"{tag}_dtop10_boot": "%+.3f [%+.3f,%+.3f]" % pb["d_top10_boot"]})
    if name in RANK_ONLY: r["brier"] = r["ece"] = np.nan
    rows.append(r)
res = pd.DataFrame(rows); res.to_csv(HERE / "results.csv", index=False)
pd.DataFrame(oof).assign(account_id=feats.account_id.values, fold=fid, churn_90d=yv).to_csv(HERE / "oof_predictions.csv", index=False)
print("stored demo OOF:", M.all_metrics(yv, stored), "corr w/ B0:", np.corrcoef(stored, oof[B0])[0, 1])
pd.set_option("display.width", 300); pd.set_option("display.max_columns", 40); pd.set_option("display.max_colwidth", 60)
print(res.round(4).to_string())

# repeated CV noise (3 seeds x 5-fold) for B0 vs B1 vs best tree: noise estimate only, NOT the canonical folds
rep = []
for seed in range(3):
    sk = StratifiedKFold(5, shuffle=True, random_state=100+seed)
    for name, (mk, Xm) in [(B0, MODELS[B0]), (B1, MODELS[B1]), ("P1", MODELS["P1 HGB monotone-constrained, compliant core"])]:
        p = np.zeros(len(yv))
        for tr, te in sk.split(Xm, yv): pr = mk().fit(Xm.iloc[tr], yv[tr]).predict_proba(Xm.iloc[te]); p[te] = pr if pr.ndim == 1 else pr[:, 1]
        rep.append({"seed": seed, "model": name, **M.all_metrics(yv, np.clip(p, 0, 1))})
    print("repcv seed", seed, "done", flush=True)
rep = pd.DataFrame(rep); rep.to_csv(HERE / "repeated_cv.csv", index=False)
print(rep.groupby("model")[["auc", "pr_auc", "top10", "brier"]].agg(["mean", "std"]).round(4).to_string())
