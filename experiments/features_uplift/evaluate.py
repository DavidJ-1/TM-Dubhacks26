"""Evaluate variants vs baseline Model A LR on IDENTICAL OOF folds. SYNTHETIC labels."""
import sys, warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
R = "/workspace/tmobile/TM-Dubhacks26"
sys.path.insert(0, R + "/harness"); sys.dont_write_bytecode = True
from churn_features import prepare, CORE_FEATURES, leak_columns
from churn_model import ModelA
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
feats = pd.read_csv(R + "/demo_data/features.csv"); labels = pd.read_csv(R + "/demo_data/labels.csv")
folds = pd.read_csv(R + "/demo_data/churn_oof_pred.csv").set_index("account_id")
barred = set(labels.columns) - {"account_id"}
feats = feats.drop(columns=[c for c in feats.columns if c != "account_id" and (c in barred or c in leak_columns([c]))])
X = prepare(feats)
ids = folds.index; X = X.loc[ids]
y = labels.set_index("account_id").churn_90d.loc[ids].astype(int).values
fold = folds.fold.values
T = pd.read_csv("trend_features.csv", index_col=0).loc[ids]; H = pd.read_csv("household_features.csv", index_col=0).loc[ids]
base_cols = [c for c in CORE_FEATURES if c in X.columns]

def top10(y, s):
    k = int(round(0.10 * len(y))); return y[np.argsort(-s, kind="stable")[:k]].sum() / y.sum()
def ece(y, p, b=10):
    q = pd.qcut(p, b, labels=False, duplicates="drop"); d = pd.DataFrame({"y": y, "p": p, "q": q}).groupby("q")
    return float((d.size() / len(y) * (d.y.mean() - d.p.mean()).abs()).sum())
M = {"AUC": roc_auc_score, "PR_AUC": average_precision_score, "top10": top10,
     "Brier": brier_score_loss, "ECE": ece}

def oof(Xv):
    p = np.zeros(len(y))
    for f in range(5):
        tr, te = fold != f, fold == f
        p[te] = ModelA(feature_set="all").fit(Xv[tr], y[tr]).predict_proba(Xv[te])
    return p

D = pd.read_csv("device_features.csv", index_col=0).loc[ids]
H = H.drop(columns=["hh_n_roles"])  # member_role has child/teen/senior -> age proxy, dropped (CPNI/protected-attr rule)
S = pd.read_csv("signal_features.csv", index_col=0).loc[ids].drop(columns=["sg_went_quiet"])  # constant 0 in stub data
NONCOMPLIANT = ["port_out_inquiry", "competitor_research_score", "cancel_inquiries_270d"]
variants = {"baseline_LR": X[base_cols],
            "LR+signals": pd.concat([X[base_cols], S], axis=1),
            "baseline_compliant(no port-out/competitor/cancel)": X[[c for c in base_cols if c not in NONCOMPLIANT]],
            "LR+all_new+signals": pd.concat([X[base_cols], T, H, D, S], axis=1),
            "LR+device_fin": pd.concat([X[base_cols], D], axis=1),
            "LR+all_new": pd.concat([X[base_cols], T, H, D], axis=1),
            "LR+trend": pd.concat([X[base_cols], T], axis=1),
            "LR+household": pd.concat([X[base_cols], H], axis=1),
            "LR+trend+household": pd.concat([X[base_cols], T, H], axis=1)}
import os
if len(sys.argv) > 1 and sys.argv[1] == "oof":
    k = sys.argv[2]; np.save(f"oof_{k[:20]}.npy", oof(variants[k])); sys.exit()
P = {k: np.load(f"oof_{k[:20]}.npy") for k in variants}
ref = folds.p_churn_90d.values
print("repro check: baseline AUC", roc_auc_score(y, P["baseline_LR"]), "harness OOF AUC", roc_auc_score(y, ref),
      "max|diff|", np.abs(P["baseline_LR"] - ref).max())
rng = np.random.default_rng(2026); B = 400
boots = [rng.integers(0, len(y), len(y)) for _ in range(B)]
rows = []
for k, p in P.items():
    r = {"variant": k}
    for m, fn in M.items():
        r[m] = fn(y, p)
        pf = np.array([fn(y[fold == f], p[fold == f]) for f in range(5)])
        bf = np.array([fn(y[fold == f], P["baseline_LR"][fold == f]) for f in range(5)])
        r[m + "_fold_sd"] = pf.std(ddof=1)
        d = pf - bf; r[m + "_fold_delta"] = f"{d.mean():+.4f}±{d.std(ddof=1):.4f}"
        if k != "baseline_LR":
            bd = np.array([fn(y[i], p[i]) - fn(y[i], P["baseline_LR"][i]) for i in boots]) if m in ("AUC","PR_AUC","top10","Brier") else np.array([0.0])
            lo, hi = np.percentile(bd, [2.5, 97.5]); r[m + "_delta_CI"] = f"[{lo:+.4f},{hi:+.4f}]"
            r[m + "_real"] = "REAL" if (lo > 0 or hi < 0) else "noise"
        else:
            bb = np.array([fn(y[i], p[i]) for i in boots]) if m in ("AUC","PR_AUC","top10","Brier") else np.array([np.nan]); lo, hi = np.percentile(bb, [2.5, 97.5])
            r[m + "_delta_CI"] = f"CI95 [{lo:.4f},{hi:.4f}]"; r[m + "_real"] = "-"
    rows.append(r)
res = pd.DataFrame(rows); res.to_csv("results.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 100)
for m in M:
    print(res[["variant", m, m + "_fold_sd", m + "_fold_delta", m + "_delta_CI", m + "_real"]].to_string(index=False))
# leakage audit: single-feature AUC (direction-free) for every new feature
la = []
for c in list(T.columns) + list(H.columns) + list(D.columns) + list(S.columns):
    v = pd.concat([T, H, D, S], axis=1)[c].values
    a = roc_auc_score(y, v) if np.std(v) > 0 else 0.5
    la.append({"feature": c, "single_AUC": max(a, 1 - a), "corr_with_label": np.corrcoef(v, y)[0, 1],
               "max_abs_corr_w_core": X[base_cols].corrwith(pd.Series(v, index=ids)).abs().max(),
               "FLAG_gt_0.95": max(a, 1 - a) > 0.95})
la = pd.DataFrame(la).sort_values("single_AUC", ascending=False); la.to_csv("leakage_audit.csv", index=False)
print(la.to_string(index=False))
pd.DataFrame({"account_id": ids, "fold": fold, "y": y, **{k: v for k, v in P.items()}}).to_csv("oof_preds.csv", index=False)
# secondary view: rank by expected $ loss (p x last bill x 3 months) vs probability. ARPA proxy = last_bill_cents.
bill = feats.set_index("account_id").last_bill_cents.loc[ids].values / 100
k = int(round(0.1 * len(y))); dv = []
for name, p in P.items():
    for how, s in (("prob", p), ("exp_$loss", p * bill * 3)):
        top = np.argsort(-s, kind="stable")[:k]
        dv.append({"variant": name, "rank_by": how, "top10_capture_churners": y[top].sum() / y.sum(),
                   "top10_capture_churn_$": (y[top] * bill[top]).sum() / (y * bill).sum()})
dv = pd.DataFrame(dv); dv.to_csv("dollar_view.csv", index=False); print(dv.to_string(index=False))
