"""Task 2: simulated upgrade_90d (labels.csv) on the exact churn folds. ALL SYNTHETIC.
Generator-matched transforms from harness/labels.py upgrade_terms(), minus student (age proxy) and the two income terms."""
from common import *
from folds import load_raw, fold_ids as churn_fold_ids, DATA
f, ychurn, lab = load_raw(); fid = churn_fold_ids(ychurn); y = lab.upgrade_90d.astype(int).values
folds = [(np.where(fid != k)[0], np.where(fid == k)[0]) for k in range(5)]
EXCL = ["account_id", "is_persona", "port_out_inquiry", "competitor_research_score", "language", "segment", "discount_group"]
B = f.drop(columns=EXCL); B = pd.get_dummies(B, columns=[c for c in B.columns if not pd.api.types.is_numeric_dtype(B[c])]).astype(float)
B["cap_missing"] = B.plan_data_cap_gb.isna().astype(float); B = B.fillna(B.median())
B["util_per_line"] = (f.data_gb_3m_avg / f.n_lines / f.plan_data_cap_gb).fillna(0).clip(0, 5)
B["over_cap_share"] = f.n_lines_over_cap_3m / f.n_lines; B["hotspot_per_line"] = f.hotspot_gb_3m_avg / f.n_lines
churn = pd.read_csv(DATA / "churn_oof_pred.csv").set_index("account_id").loc[f.account_id, "p_churn_90d"].values
T = pd.DataFrame(index=f.index)
T["tier_basic"] = (f.plan_tier == "basic").astype(float); T["tier_standard"] = (f.plan_tier == "standard").astype(float)
T["capped_plan"] = f.plan_data_cap_gb.notna().astype(float); T["top_tier"] = (f.plan_family == "experience_beyond").astype(float)
T["premium_nontop"] = (f.plan_family == "experience_more").astype(float); T["over_cap_share"] = f.n_lines_over_cap_3m / f.n_lines
T["near_cap"] = (((f.data_gb_3m_avg / f.n_lines) / f.plan_data_cap_gb) >= 0.8).astype(float)
T["usage_growth"] = f.data_growth_pct.fillna(0).clip(-0.5, 1.0); T["hotspot_heavy"] = ((f.hotspot_gb_3m_avg / f.n_lines) >= 5).astype(float)
T["device_age_years"] = (f.max_device_age_months.fillna(0) - 12).clip(lower=0) / 12; T["old_device_36m"] = (f.n_lines_device_36m_plus > 0).astype(float)
T["installment_ended_recent"] = f.installment_ended_recent.astype(float); T["tenure_years_capped5"] = f.tenure_months.clip(upper=60) / 12
T["bill_increase_pct"] = f.bill_increase_pct.fillna(0).clip(lower=0); T["promo_expired_recent"] = f.promo_expired_recent.astype(float)
z = np.log(churn / (1 - churn)); T["churn_risk_z"] = ((z - z.mean()) / z.std()).clip(min=0)  # from OOF churn score (legit, OOF)
GEN = dict(tier_basic=1.0, tier_standard=0.5, capped_plan=0.5, top_tier=-1.0, premium_nontop=-0.4, over_cap_share=1.5, near_cap=0.6, usage_growth=0.8,
           hotspot_heavy=0.4, device_age_years=0.45, old_device_36m=0.3, installment_ended_recent=0.5, tenure_years_capped5=0.1,
           bill_increase_pct=-4.0, promo_expired_recent=-1.0, churn_risk_z=-0.25)
BT = pd.concat([B, T.add_prefix("g_")], axis=1)
P = {}
P["LR baseline (round 1 features)"] = oof(lr, B, y, folds)
P["Spline LR"] = oof(spline_lr(B), B, y, folds)
P["EBM"] = oof(ebm, B, y, folds)
P["LR generator-matched transforms only (16)"] = oof(lambda: make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=3000)), T, y, folds)
P["LR features + generator transforms"] = oof(lr, BT, y, folds)
P["EBM features + generator transforms"] = oof(ebm, BT, y, folds)
P["Reference: known recipe coefs, no income/student (not learned)"] = (T * pd.Series(GEN)).sum(axis=1).values
P["Reference: oracle p_upgrade_90d (incl. income/student)"] = lab.p_upgrade_90d.values
prob = {k for k in P if not k.startswith("Reference: known")}
r = evaluate(P, y, fid, "LR baseline (round 1 features)", prob); r.to_csv("task2_results.csv", index=False); print(r.to_string(), flush=True)
best = r[~r.model.str.startswith("Reference")].sort_values("auc", ascending=False).model.iloc[0]
pd.DataFrame({"account_id": f.account_id, "fold": fid, "upgrade_90d": y, "churn_90d": ychurn.values, "p_churn_oof": churn,
              "support_90d": f.support_90d, **{k: P[k] for k in P}}).to_csv("task2_oof.csv", index=False)
open("task2_best.txt", "w").write(best); print("best:", best)
