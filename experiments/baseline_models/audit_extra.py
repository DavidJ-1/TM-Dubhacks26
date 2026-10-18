"""Extra leakage/compliance audit (SYNTHETIC): ids/groups across folds, near-duplicate aggregates, oracle ceiling, cancel ablation."""
import sys, warnings; sys.dont_write_bytecode = True; warnings.filterwarnings("ignore")
sys.path.insert(0, "."); sys.path.insert(0, "/workspace/tmobile/TM-Dubhacks26/harness")
import numpy as np, pandas as pd, folds, metrics as M
from churn_features import leak_columns, prepare
from churn_model import ModelA
f, y, lab = folds.load_raw(); yv = y.values; fid = folds.fold_ids(yv)
print("dup account_id:", f.account_id.duplicated().sum(), "| group-like cols:", [c for c in f.columns if any(t in c.lower() for t in ("household", "hh_", "group_id", "customer_id", "line_id"))])
raw = f.drop(columns=["account_id"]).select_dtypes("number")
dup_rows = raw.duplicated(keep=False).sum(); print("exact duplicate feature rows:", dup_rows)
c = raw.corr().abs(); pairs = [(a, b, round(c.loc[a, b], 4)) for i, a in enumerate(c) for b in c.columns[i+1:] if c.loc[a, b] > 0.95]
print("raw feature pairs |r|>0.95:", pairs)
t = f.tenure_months * f.plan_price_cents
print("corr(tenure*plan_price, any raw col) max:", raw.corrwith(t).abs().drop(["tenure_months", "plan_price_cents"]).sort_values().tail(3).round(3).to_dict())
print("oracle p_true_90d:", {k: round(v, 4) for k, v in M.all_metrics(yv, lab.p_true_90d.values).items()})
barred = set(lab.columns) - {"account_id"}
X = prepare(f.drop(columns=[c for c in f.columns if c != "account_id" and (c in barred or c in leak_columns([c]))])).astype(float)
drop = ["port_out_inquiry", "competitor_research_score", "cancel_inquiries_270d"]
p = np.zeros(len(yv))
for tr, te in folds.get_folds(yv):
    p[te] = ModelA(feature_set="core").fit(X.drop(columns=drop).iloc[tr], yv[tr]).predict_proba(X.drop(columns=drop).iloc[te])
base = pd.read_csv("oof_predictions.csv")["baseline_modelA_LR (core, sign-drop, C by CV)"].values if __import__("os").path.exists("oof_predictions.csv") else None
print("baseline minus port_out+competitor+cancel_inquiries:", {k: round(v, 4) for k, v in M.all_metrics(yv, p).items()}, M.bootstrap_ci(yv, p, 500))
if base is not None:
    print(M.paired_fold_comparison(yv, p, base, fid)[1].round(4).to_string()); print(M.paired_bootstrap_delta(yv, p, base, 500))
