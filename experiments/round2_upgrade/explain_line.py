from common import *
src = open("/workspace/tmobile/scratch_models/upgrade/real/backtest.py").read().split("def run(cut)")[0]; g = {}; exec(src, g)
lines = g["lines"].copy(); lines["pm"] = lines.device_purchase_date.str[:7]
a, X, win = g["build"](pd.Period("2026-06", "M"))
a["n_eligible"] = (a.n_device_lines - a.n_fin_starts_pre).clip(lower=0); X["n_eligible"] = a.n_eligible.values
X["eligible_share"] = (a.n_eligible / a.n_device_lines.replace(0, np.nan)).fillna(0).values
L = lines[lines.account_id.isin(a.account_id) & (lines.byod == 0)].reset_index(drop=True); yl = L.pm.isin(win).astype(int).values
XL = X.copy(); XL["account_id"] = a.account_id.values; XL = L[["account_id"]].merge(XL, on="account_id", how="left").drop(columns="account_id")
m = lr().fit(XL, yl); c = pd.Series(m[-1].coef_[0], index=XL.columns).sort_values(key=abs, ascending=False); print(c.head(12).round(3).to_string())
# tenure effect on per-line rate
t = pd.cut(XL.tenure_at_cut, [0, 6, 12, 24, 48, 200]); print(pd.Series(yl).groupby(t.values).agg(["mean", "size"]).round(3))
