"""Shared data/feature construction for round 2. ALL DATA SYNTHETIC. Reads demo_data read-only."""
import sys, warnings
sys.dont_write_bytecode = True; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
sys.path.insert(0, "/workspace/tmobile/scratch_models"); sys.path.insert(0, "/workspace/tmobile/TM-Dubhacks26/harness")
import folds, metrics as M
from churn_features import CORE_FEATURES, leak_columns, prepare

feats, y, labels = folds.load_raw()
yv = y.values; FOLDS = folds.get_folds(yv); fid = folds.fold_ids(yv)
barred = set(labels.columns) - {"account_id"}
feats_c = feats.drop(columns=[c for c in feats.columns if c != "account_id" and (c in barred or c in leak_columns([c]))])
X = prepare(feats_c).astype(float).reset_index(drop=True)
CPNI = {"port_out_inquiry", "competitor_research_score", "competitor_research_x", "port_out_inquiry_x"}
AGE_PROXY = [c for c in X.columns if c.startswith("segment=")]
core = [c for c in CORE_FEATURES if c in X.columns]
core_ok = [c for c in core if c not in CPNI]
# raw contact counts that prepare() drops (legit pre-cutoff features in features.csv)
RAW_CONTACTS = ["support_90d", "billing_contacts_90d", "device_contacts_90d"]
for c in RAW_CONTACTS: X["raw_" + c] = feats[c].fillna(0).astype(float).values
plus = core + ["raw_" + c for c in RAW_CONTACTS]; plus_ok = [c for c in plus if c not in CPNI]

def recipe_terms(f):
    """Same functional form as harness/labels.py terms() (tuned recipe) -- FITS THE SYNTHETIC RECIPE. Only pre-cutoff feature columns."""
    t = pd.DataFrame(index=f.index)
    for c in ["support_90d", "unresolved_90d", "negative_contacts_90d", "bill_increase_pct", "plan_misfit_share",
              "app_sessions_30d", "billing_contacts_90d", "device_contacts_90d", "cancel_inquiries_270d"]:
        t[c] = f[c].fillna(0).astype(float)
    t["neg_sentiment"] = (-f["avg_sentiment"].fillna(0)).clip(lower=0)
    t["competitor_research_x"] = f["competitor_research_score"].astype(float)
    t["port_out_inquiry_x"] = f["port_out_inquiry"].astype(float)
    t["tenure_capped60"] = f["tenure_months"].clip(upper=60).astype(float)
    t["early_tenure"] = (f["tenure_months"] < 12).astype(float)
    t["no_financing"] = (f["n_financed_lines"] == 0).astype(float)
    t["no_autopay"] = (f["autopay"] == 0).astype(float)
    t["troubled_4plus"] = ((f["support_90d"] >= 4) & ((f["unresolved_90d"] > 0) | (f["negative_contacts_90d"] > 0))).astype(float)
    t["max_device_age_months_f"] = f["max_device_age_months"].fillna(0).astype(float)
    t["extra_lines"] = (f["n_lines"] - 1).astype(float)
    t["low_app_use"] = (f["app_sessions_30d"] <= 3).astype(float)
    t["promo_expired_recent"] = f["promo_expired_recent"].astype(float)
    return t.reset_index(drop=True).astype(float)
T = recipe_terms(feats); T_ok = T.drop(columns=[c for c in T.columns if c in CPNI])
p_true = labels["p_true_90d"].values  # EVAL-ONLY ceiling reference, never a feature
