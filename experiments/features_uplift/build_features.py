"""Build trend/delta + household features from sandbox.db (READ-ONLY). SYNTHETIC data. as_of 2026-10-01."""
import sqlite3, numpy as np, pandas as pd
DB = "/workspace/tmobile/TM-Dubhacks26/vendor/dubhacks/data/sandbox.db"
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
acc = pd.read_sql("select account_id from accounts", c).set_index("account_id")
lines = pd.read_sql("select * from lines", c)
use = pd.read_sql("select * from usage_monthly", c).merge(lines[["line_id", "account_id"]], on="line_id")
bill = pd.read_sql("select * from billing_history", c)
sup = pd.read_sql("select * from support_interactions", c)
AS_OF = pd.Timestamp("2026-10-01")
# every source row is strictly before as_of (label window = 90d after as_of) -> assert
assert use.month.max() <= "2026-09" and bill.month.max() <= "2026-09" and sup.interaction_date.max() < "2026-10-01"
months = sorted(use.month.unique()); midx = {m: i for i, m in enumerate(months)}
T = pd.DataFrame(index=acc.index)

def slope(df, val, key="account_id"):
    d = df.copy(); d["t"] = d.month.map(midx)
    g = d.groupby(key)
    cov = g.apply(lambda x: np.polyfit(x.t, x[val], 1)[0] if len(x) > 2 else 0.0, include_groups=False)
    return cov

# --- usage trends (account totals)
ua = use.groupby(["account_id", "month"])[["data_gb", "voice_minutes", "streaming_hours", "hotspot_gb"]].sum().reset_index()
last3, prev3 = months[-3:], months[-6:-3]
for v in ["data_gb", "voice_minutes", "streaming_hours"]:
    l = ua[ua.month.isin(last3)].groupby("account_id")[v].mean()
    p = ua[ua.month.isin(prev3)].groupby("account_id")[v].mean()
    T[f"tr_{v}_delta3v3"] = ((l - p) / (p + 1e-6)).clip(-1, 3)
    T[f"tr_{v}_slope12"] = slope(ua, v) / (ua.groupby("account_id")[v].mean() + 1e-6)
T["tr_usage_drop30"] = (T["tr_data_gb_delta3v3"] < -0.3).astype(float)
# --- billing trends
T["tr_bill_slope12"] = slope(bill, "total_cents") / (bill.groupby("account_id").total_cents.mean() + 1)
T["tr_bill_cv12"] = bill.groupby("account_id").total_cents.std() / (bill.groupby("account_id").total_cents.mean() + 1)
# --- support trends (monthly counts Jan-Sep 2026)
sup["d"] = pd.to_datetime(sup.interaction_date); sup["days_ago"] = (AS_OF - sup.d).dt.days
s90 = sup[sup.days_ago <= 90].groupby("account_id").size()
s90_180 = sup[(sup.days_ago > 90) & (sup.days_ago <= 180)].groupby("account_id").size()
T["tr_support_delta_90v90"] = s90.reindex(T.index, fill_value=0) - s90_180.reindex(T.index, fill_value=0)
sm = sup.assign(month=sup.d.dt.strftime("%Y-%m")).groupby(["account_id", "month"]).size().rename("n").reset_index()
grid = pd.MultiIndex.from_product([T.index, [m for m in months if m >= "2026-01"]], names=["account_id", "month"])
sm = sm.set_index(["account_id", "month"]).reindex(grid, fill_value=0).reset_index()
T["tr_support_slope9"] = slope(sm, "n")
sent90 = sup[sup.days_ago <= 90].groupby("account_id").sentiment.mean()
sentold = sup[sup.days_ago > 90].groupby("account_id").sentiment.mean()
T["tr_sentiment_delta"] = (sent90 - sentold).fillna(0)
# --- household (account = household; lines are members)
lines["dpd"] = pd.to_datetime(lines.device_purchase_date)
lines["dev_age"] = (AS_OF - lines.dpd).dt.days / 30.4
g = lines.groupby("account_id")
H = pd.DataFrame(index=acc.index)
H["hh_n_lines"] = g.size()
H["hh_n_roles"] = g.member_role.nunique()
H["hh_dev_age_spread"] = (g.dev_age.max() - g.dev_age.min()).fillna(0)
H["hh_dev_age_mean"] = g.dev_age.mean().fillna(0)
H["hh_byod_share"] = g.byod.mean()
H["hh_fin_balance_max"] = g.financing_balance_cents.max() / 100
H["hh_fin_months_spread"] = g.financing_months_remaining.max() - g.financing_months_remaining.min()
H["hh_tradein_share"] = g.tradein_eligible.mean()
lu = use[use.month.isin(last3)].groupby("line_id").data_gb.mean(); lp = use[use.month.isin(prev3)].groupby("line_id").data_gb.mean()
ldrop = ((lu - lp) / (lp + 1e-6) < -0.3).astype(float).rename("drop").to_frame().join(lines.set_index("line_id").account_id)
H["hh_share_lines_usage_drop"] = ldrop.groupby("account_id")["drop"].mean()
lu_a = lu.to_frame().join(lines.set_index("line_id").account_id).groupby("account_id").data_gb
H["hh_line_data_max_over_mean"] = (lu_a.max() / (lu_a.mean() + 1e-6))
T.fillna(0).to_csv("trend_features.csv"); H.fillna(0).to_csv("household_features.csv")
print(T.describe().T[["mean", "std"]]); print(H.describe().T[["mean", "std"]])
# grouping check: any shared ids across accounts?
print("lines per account max", H.hh_n_lines.max(), "| line_id unique:", lines.line_id.is_unique)
