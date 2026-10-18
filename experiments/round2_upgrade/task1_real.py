"""Task 1: real sandbox purchase backtest, account- and line-level. ALL SYNTHETIC (stub sandbox, read-only)."""
from common import *
import json, time
src = open("/workspace/tmobile/scratch_models/upgrade/real/backtest.py").read().split("def run(cut)")[0]; g = {}; exec(src, g)
lines = g["lines"].copy(); lines["pm"] = lines.device_purchase_date.str[:7]
out = []; t0 = time.time()
for cut in [pd.Period("2026-06", "M"), pd.Period("2026-03", "M")]:
    a, X, win = g["build"](cut)
    a["n_eligible"] = (a.n_device_lines - a.n_fin_starts_pre).clip(lower=0)
    X["n_eligible"] = a.n_eligible.values; X["eligible_share"] = (a.n_eligible / a.n_device_lines.replace(0, np.nan)).fillna(0).values
    # ---------------- account level
    y = a.y.values; folds = list(StratifiedKFold(5, shuffle=True, random_state=2026).split(X, y)); fid = fold_ids(folds, len(y))
    P = {"Rule: n_device_lines": a.n_device_lines.values + 1e-6 * a.months_since_fin_start.values,
         "Rule: eligible lines (device lines - pre-cutoff financing starts)": a.n_eligible.values + 1e-6 * a.months_since_fin_start.values,
         "Rule (calibrated): 1-(1-q)^eligible, q fit in-fold": None}
    pe = np.zeros(len(y))
    for tr, te in folds:  # one-parameter prior: per-eligible-line window purchase rate q
        from scipy.optimize import minimize_scalar
        k = a.n_eligible.values
        nll = lambda q: -np.sum(y[tr] * np.log(1 - (1 - q) ** k[tr] + 1e-12) + (1 - y[tr]) * k[tr] * np.log(1 - q))
        q = minimize_scalar(nll, bounds=(1e-4, 0.9), method="bounded").x; pe[te] = 1 - (1 - q) ** k[te]
    P["Rule (calibrated): 1-(1-q)^eligible, q fit in-fold"] = pe
    for n, m in [("LR", lr), ("Spline LR", spline_lr(X)), ("EBM", ebm), ("Tuned HGB (nested)", TunedHGB)]:
        P[n] = oof(m, X, y, folds); print(cut, "acct", n, round(roc_auc_score(y, P[n]), 3), f"{time.time()-t0:.0f}s", flush=True)
    r = evaluate(P, y, fid, "Rule (calibrated): 1-(1-q)^eligible, q fit in-fold", {"LR", "Spline LR", "EBM", "Tuned HGB (nested)", "Rule (calibrated): 1-(1-q)^eligible, q fit in-fold"})
    r.insert(0, "level", "account"); r.insert(0, "cutoff", str(cut)); r.insert(2, "n", len(y)); r.insert(3, "base_rate", y.mean().round(4)); out.append(r)
    # ---------------- line level: non-BYOD lines of the same accounts (BYOD lines never buy: trivially 0)
    L = lines[lines.account_id.isin(a.account_id) & (lines.byod == 0)].reset_index(drop=True)
    yl = L.pm.isin(win).astype(int).values
    XL = X.copy(); XL["account_id"] = a.account_id.values; XL = L[["account_id"]].merge(XL, on="account_id", how="left")
    groups = XL.pop("account_id").values
    lf = list(StratifiedGroupKFold(5, shuffle=True, random_state=2026).split(XL, yl, groups)); fl = fold_ids(lf, len(yl))
    PL = {"Rule: account n_device_lines": XL.n_device_lines.values + 1e-6 * XL.months_since_fin_start.values,
          "Rule: account eligible_share": XL.eligible_share.values + 1e-6 * XL.months_since_fin_start.values}
    for n, m in [("LR", lr), ("Spline LR", spline_lr(XL)), ("EBM", ebm), ("Tuned HGB (nested)", TunedHGB)]:
        PL[n] = oof(m, XL, yl, lf); print(cut, "line", n, round(roc_auc_score(yl, PL[n]), 3), f"{time.time()-t0:.0f}s", flush=True)
    r = evaluate(PL, yl, fl, "Rule: account eligible_share", {"LR", "Spline LR", "EBM", "Tuned HGB (nested)"})
    r.insert(0, "level", "line (non-BYOD)"); r.insert(0, "cutoff", str(cut)); r.insert(2, "n", len(yl)); r.insert(3, "base_rate", yl.mean().round(4)); out.append(r)
    sf = pd.Series({c: max(roc_auc_score(yl, XL[c]), 1 - roc_auc_score(yl, XL[c])) for c in XL.columns if XL[c].nunique() > 1}).sort_values(ascending=False)
    sf.to_csv(f"task1_single_feature_auc_line_{cut}.csv")
    print(r[["model", "auc", "auc_ci", "top10", "dAUC_vs_ref"]].to_string(), "\nline top single-feature AUC:", sf.head(5).round(3).to_dict(), flush=True)
res = pd.concat(out); res.to_csv("task1_results.csv", index=False); print(res.to_string())
