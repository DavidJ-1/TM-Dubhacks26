"""Extra pre-cutoff signals (sandbox read-only). SYNTHETIC."""
import sqlite3, pandas as pd, numpy as np
R="/workspace/tmobile/TM-Dubhacks26"; c = sqlite3.connect(f"file:{R}/vendor/dubhacks/data/sandbox.db?mode=ro", uri=True)
use = pd.read_sql("select u.*, l.account_id from usage_monthly u join lines l using(line_id)", c)
ua = use.groupby(["account_id","month"]).data_gb.sum().unstack()
sup = pd.read_sql("select * from support_interactions", c); sup["days_ago"]=(pd.Timestamp("2026-10-01")-pd.to_datetime(sup.interaction_date)).dt.days
D = pd.read_csv("device_features.csv", index_col=0); f = pd.read_csv(R+"/demo_data/features.csv").set_index("account_id")
S = pd.DataFrame(index=D.index)
S["sg_data_last_vs_prior3"] = ((ua["2026-09"] - ua[["2026-06","2026-07","2026-08"]].mean(1)) / (ua[["2026-06","2026-07","2026-08"]].mean(1)+1e-6)).clip(-1,3)
S["sg_went_quiet"] = (S.sg_data_last_vs_prior3 < -0.5).astype(float)
s30 = sup[sup.days_ago<=30].groupby("account_id").size(); s31_90 = sup[(sup.days_ago>30)&(sup.days_ago<=90)].groupby("account_id").size()
S["sg_support_30_vs_prior60"] = s30.reindex(S.index, fill_value=0) - s31_90.reindex(S.index, fill_value=0)/2
tb = pd.cut(f.tenure_months, [-1,12,24,60,1e9], labels=False).reindex(S.index)
S["sg_tenure_bucket"] = tb
S["sg_x_early_tenure_payoff"] = (f.tenure_months.reindex(S.index) < 24).astype(float) * D.dv_months_to_payoff_min
S["sg_x_support_trend_usage_drop"] = S.sg_support_30_vs_prior60 * (-S.sg_data_last_vs_prior3).clip(lower=0)
S.fillna(0).to_csv("signal_features.csv"); print(S.describe().T[["mean","std"]])
