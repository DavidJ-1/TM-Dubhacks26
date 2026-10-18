"""Device/financing + single-product household features (only from existing columns). SYNTHETIC."""
import sqlite3, pandas as pd, numpy as np
R="/workspace/tmobile/TM-Dubhacks26"
c = sqlite3.connect(f"file:{R}/vendor/dubhacks/data/sandbox.db?mode=ro", uri=True)
lines = pd.read_sql("select * from lines", c); f = pd.read_csv(R+"/demo_data/features.csv").set_index("account_id")
e = pd.read_csv(R+"/demo_data/enrichment.csv").set_index("account_id")
lines["fin"] = lines.financing_balance_cents > 0
lines["paid_off"] = (~lines.fin) & (lines.byod == 0)
g = lines.groupby("account_id")
D = pd.DataFrame(index=f.index)
D["dv_months_to_payoff_min"] = lines[lines.fin].groupby("account_id").financing_months_remaining.min().reindex(D.index).fillna(0)
D["dv_share_lines_paid_off"] = g.paid_off.mean().reindex(D.index).fillna(0)
D["dv_any_paid_off_device"] = (D.dv_share_lines_paid_off > 0).astype(float)
D["dv_promo_months_remaining"] = e.promo_months_remaining.reindex(D.index).fillna(0)
D["dv_contract_months_remaining"] = e.contract_or_financing_months_remaining.reindex(D.index).fillna(0)
D["hh_single_product"] = ((f.has_home_internet == 0) & (f.n_account_addons == 0) & (f.n_line_addons == 0)).astype(float)
D["hh_is_family_plan"] = e.is_family_plan.reindex(D.index).fillna(0).astype(float)
D.to_csv("device_features.csv"); print(D.describe().T[["mean","std"]])
