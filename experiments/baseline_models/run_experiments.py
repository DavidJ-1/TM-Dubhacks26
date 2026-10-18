"""One command: python run_experiments.py   (uses repo .venv python; reads demo_data read-only; writes only here)
ALL DATA, LABELS AND METRICS ARE SYNTHETIC."""
import os, sys, json, warnings, time
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"; sys.dont_write_bytecode = True
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler, FunctionTransformer
from sklearn.linear_model import LogisticRegression, LogisticRegressionCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GridSearchCV, StratifiedKFold
from scipy.stats import rankdata
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, "/workspace/tmobile/TM-Dubhacks26/harness")
import folds, metrics as M
from churn_features import CORE_FEATURES, leak_columns, prepare
from churn_model import ModelA

feats, y, labels = folds.load_raw()
barred = set(labels.columns) - {"account_id"}
feats_c = feats.drop(columns=[c for c in feats.columns if c != "account_id" and (c in barred or c in leak_columns([c]))])
X = prepare(feats_c).astype(float)
yv = y.values; FOLDS = folds.get_folds(yv); fid = folds.fold_ids(yv)
core = [c for c in CORE_FEATURES if c in X.columns]
print(f"[SYNTHETIC] n={len(yv)} pos={yv.sum()} prepared features={X.shape[1]} core={len(core)}", flush=True)

def inner(): return StratifiedKFold(3, shuffle=True, random_state=0)

# interaction / log features built row-wise (no fitted state -> no leakage); scaling fit inside fold by pipeline
TOP = ["unresolved_90d", "neg_sentiment", "bill_increase_pct", "competitor_research_score", "port_out_inquiry", "early_tenure", "cancel_inquiries_270d"]
def add_inter(df):
    d = df[core].copy()
    for c in core:
        v = df[c]
        if v.min() >= 0 and v.nunique() > 5 and v.skew() > 2: d[f"log1p_{c}"] = np.log1p(v)
    t = [c for c in TOP if c in df.columns]
    for i, a in enumerate(t):
        for b in t[i+1:]: d[f"{a}*{b}"] = df[a] * df[b]
    return d

def lr_cv(cw=None):
    return make_pipeline(StandardScaler(), LogisticRegressionCV(Cs=[0.003, 0.01, 0.03, 0.1, 0.3, 1, 3, 10], cv=inner(),
                         scoring="neg_log_loss", max_iter=5000, class_weight=cw))

def hgb(cw=None):
    base = HistGradientBoostingClassifier(learning_rate=0.05, max_iter=150, early_stopping=False, random_state=0, class_weight=cw)
    grid = {"max_leaf_nodes": [7, 15], "min_samples_leaf": [40, 100]}  # small grid: box was CPU-contended tonight
    return GridSearchCV(base, grid, scoring="roc_auc", cv=inner(), n_jobs=-1)

MODELS = {
    "baseline_modelA_LR (core, sign-drop, C by CV)": (lambda: ModelA(feature_set="core"), lambda d: d),
    "COMPLIANCE ablation: baseline minus port_out_inquiry": (lambda: ModelA(feature_set="core"), lambda d: d.drop(columns=["port_out_inquiry"])),
    "COMPLIANCE ablation: baseline minus port_out + competitor_research": (lambda: ModelA(feature_set="core"), lambda d: d.drop(columns=["port_out_inquiry", "competitor_research_score"])),
    "COMPLIANCE ablation: LR all feats minus port/competitor/segment(age proxy)": (lambda: lr_cv(), lambda d: d.drop(columns=["port_out_inquiry", "competitor_research_score"] + [c for c in d.columns if c.startswith("segment=")])),
    "LR core, nested C sweep (no sign-drop)": (lambda: lr_cv(), lambda d: d[core]),
    "LR all prepared feats, nested C": (lambda: lr_cv(), lambda d: d),
    "LR core, class_weight=balanced": (lambda: lr_cv("balanced"), lambda d: d[core]),
    "LR core + log/interactions, nested C": (lambda: lr_cv(), add_inter),
    "LR core + log/interactions, balanced": (lambda: lr_cv("balanced"), add_inter),
    "HGB all feats, inner-CV grid": (lambda: hgb(), lambda d: d),
}
oof = {}; info = {}
for name, (mk, fx) in MODELS.items():
    t0 = time.time(); p = np.zeros(len(yv)); chosen = []
    Xm = fx(X)
    for tr, te in FOLDS:
        m = mk().fit(Xm.iloc[tr], yv[tr])
        p[te] = m.predict_proba(Xm.iloc[te])[:, 1] if not isinstance(m, ModelA) else m.predict_proba(Xm.iloc[te])
        if isinstance(m, ModelA): chosen.append(f"C={m.C_:g}, dropped={m.dropped_for_sign_}")
        elif hasattr(m, "best_params_"): chosen.append(m.best_params_)
        else: chosen.append(f"C={m[-1].C_[0]:g}")
    oof[name] = p; info[name] = chosen
    print(f"{name}: {M.all_metrics(yv, p)}  ({time.time()-t0:.0f}s)", flush=True)

def rk(a): return rankdata(a) / len(a)
B = "baseline_modelA_LR (core, sign-drop, C by CV)"
oof["Ensemble rank-avg baseline LR + HGB"] = (rk(oof[B]) + rk(oof["HGB all feats, inner-CV grid"])) / 2
oof["Ensemble rank-avg LR+inter + HGB"] = (rk(oof["LR core + log/interactions, nested C"]) + rk(oof["HGB all feats, inner-CV grid"])) / 2
RANK_ONLY = {k for k in oof if k.startswith("Ensemble")}

stored = pd.read_csv(folds.DATA / "churn_oof_pred.csv").set_index("account_id").loc[feats.account_id, "p_churn_90d"].values
rows = []
for name, p in oof.items():
    a = M.all_metrics(yv, p); pf = M.per_fold(yv, p, fid); ci = M.bootstrap_ci(yv, p, n_boot=500)
    r = {"model": name, **a, "auc_fold_sd": pf.auc.std(), "top10_fold_sd": pf.top10.std(), **ci}
    if name != B:
        d, s = M.paired_fold_comparison(yv, p, oof[B], fid); pb = M.paired_bootstrap_delta(yv, p, oof[B])
        r.update({"d_auc_fold_mean": s.loc["auc", "mean"], "d_auc_fold_sd": s.loc["auc", "sd"], "d_top10_fold_mean": s.loc["top10", "mean"],
                  "d_top10_fold_sd": s.loc["top10", "sd"], "folds_better_top10": int(s.loc["top10", "n_folds_better"]), **pb})
    if name in RANK_ONLY: r["brier"] = r["ece"] = np.nan
    rows.append(r)
res = pd.DataFrame(rows)
res.to_csv(HERE / "results.csv", index=False)
pd.DataFrame(oof).assign(account_id=feats.account_id.values, fold=fid, churn_90d=yv).to_csv(HERE / "oof_predictions.csv", index=False)
json.dump({k: [str(c) for c in v] for k, v in info.items()}, open(HERE / "chosen_hparams.json", "w"), indent=1)
_, bins = M.ece(yv, oof[B]); bins.to_csv(HERE / "baseline_reliability_bins.csv", index=False)

# leakage audit: prepared features + every raw feature column, and label-file columns for contrast
sfa = M.single_feature_auc(X, yv); sfa.to_csv(HERE / "leakage_single_feature_auc.csv", index=False)
raw_num = feats.drop(columns=["account_id"]).select_dtypes("number")
sfr = M.single_feature_auc(raw_num, yv); sfr.to_csv(HERE / "leakage_raw_feature_auc.csv", index=False)
lab_num = labels.drop(columns=["account_id", "churn_90d"]).select_dtypes("number")
sfl = M.single_feature_auc(lab_num, yv); sfl.to_csv(HERE / "leakage_labelfile_cols_auc.csv", index=False)
print("stored demo OOF:", M.all_metrics(yv, stored), "corr with refit baseline:", np.corrcoef(stored, oof[B])[0, 1])
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
print(res.round(4).to_string())
print("prepared top-10 single-feature AUC:\n", sfa.head(10).round(3).to_string())
print("raw top-10:\n", sfr.head(10).round(3).to_string())
print("labels.csv cols (NOT features, contrast):\n", sfl.head(8).round(3).to_string())
print("barred from features:", sorted(set(feats.columns) - set(feats_c.columns)))
print("raw cols with date/id-like names:", [c for c in feats.columns if any(t in c.lower() for t in ("date", "_id", "time", "churn", "cancel", "port"))])
