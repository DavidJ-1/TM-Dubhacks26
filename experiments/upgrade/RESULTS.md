# Upgrade propensity model: results (ALL DATA SYNTHETIC / SIMULATED)

Run 2026-10-17 ~8:50 PM PT. Script: `run_upgrade.py`. Outputs: `results.csv`, `upgrade_oof_pred.csv`, `single_feature_auc.csv`, `overlap.json`, `run.log`.
Repo inputs were only read (demo_data via pandas, sandbox.db through `mode=ro`). Nothing in the repo was modified.

## 1. What upgrade signal exists
- **Label exists, but it's simulated.** `demo_data/labels.csv` has `upgrade_90d` (0/1), `p_upgrade_90d` and `upgrade_driver_1..3`.
  `harness/labels.py` (lines 153–278) generates it: a hand-set logistic recipe over features.csv plus enrichment.csv
  (tier, data cap, over-cap share, near-cap, usage growth, hotspot, device age, recent payoff, tenure, student, bill shock (negative),
  promo expired (negative), step-up cost/income, income, churn risk (negative)). It's calibrated to a 6.0%/90d target and drawn with a fixed seed.
  Definition: "would accept a plan step-up or device upgrade within 90 days." It's **not observed behaviour**: the model recovers the recipe.
  On the 5,000 regular accounts: 322 positives (6.44%).
- **Prior work already in the repo:** `harness/bench/upgrade_improve.py` and `upgrade_best.py` (OOF AUC ~0.75–0.80), and `demo_data/upgrade_scores.csv`
  (an LR trained on synthetic_250k). These results are consistent with that work.
- **Judge sandbox (read-only) has no plan-change, add-a-line or offer-acceptance history.** Each account has exactly one plan_sku, and
  `billing_history.change_reason` takes only stable, device_installment, installment_ended or promo_expired. Support has `plan_change` *contacts*
  (requests, not completed changes).
  There **is** device-purchase history: `lines.device_purchase_date` and `device_installment` billing events by month (2025-11..2026-09, rising to 310–358/month in Jul–Sep).
  That could support a **real-history device-upgrade backtest** (label = new device_installment in 2026-07..09, features from data before 2026-07). I did not build it:
  each line stores only its *current* device, so pre-cutoff device age is lost for lines that upgraded, and that is a direct leak unless it's rebuilt
  from billing events. About 1,669 accounts (33%) bought a device since 2026-07-01, far above the simulated 6%. So the stub's purchase dates are not consistent with the simulated label.

## 2. Models (exact churn folds: StratifiedKFold(5, shuffle, seed 2026) on churn_90d, from scratch_models/folds.py; 62–67 upgraders per fold)
Features: features.csv (85 columns after one-hot) plus 3 ratios (data utilisation per line vs cap, over-cap share, hotspot per line).
**Excluded:** port_out_inquiry, competitor_research_score, language, segment, discount_group (age/ethnicity proxies such as senior, 55_plus and student), and all enrichment income/job/kid fields (simulated and sensitive).

| model | AUC | fold mean±sd | PR-AUC | top-10% capture | Brier | ECE | ΔAUC vs LR [95% CI] | Δtop10 vs LR [95% CI] |
|---|---|---|---|---|---|---|---|---|
| **LR (C=0.1, standardized)** | 0.762 [0.736, 0.787] | 0.762±0.010 | 0.203 | 33.2% [28.9, 37.9] | 0.0562 | 0.010 | n/a | n/a |
| LR class_weight=balanced | 0.758 | 0.759±0.010 | 0.197 | 32.6% | 0.190 | 0.309 (miscalibrated, as expected) | −0.004 [−0.009, +0.002] | −0.009 [−0.028, +0.009] |
| HistGradientBoosting (depth 3) | 0.750 [0.724, 0.774] | 0.751±0.024 | 0.213 | 33.9% [28.9, 38.2] | 0.0559 | 0.011 | −0.013 [−0.029, +0.000] | +0.007 [−0.028, +0.050] |
| *Oracle: true p_upgrade_90d (ceiling)* | 0.808 | 0.807±0.017 | 0.266 | 37.6% | 0.0535 | 0.009 | +0.046 | +0.047 |

Base rate 6.44%, so a random 10% catches 10% (LR lift ≈ 3.3x). **No variant beats LR beyond fold or bootstrap noise.** HGB is slightly lower on AUC (better in 1/5 folds) and level on top-10%.
LR is well calibrated (mean prediction 6.46% vs 6.44% actual). The gap to the oracle is mostly the simulated income/affordability terms we chose to exclude, plus label noise.

## 3. Leakage audit
The best single-feature AUC is 0.670 (util_per_line), then plan tier/unlimited (0.66) and device age (0.63). **No feature exceeds 0.95; no red flags.**
Caveat: the label is a function of these same features, so "no leakage" means no post-outcome field. It does not mean the signal is real.

## 4. Overlap with churn risk (top 10% = 500 accounts each; churn = demo_data churn_oof_pred)
- Only **19 accounts (3.8%)** are in both top-10% lists, against 50 expected if the two scores were independent. Spearman(upgrade, churn) = **−0.27**.
- 5 churners fall in the upgrade top 10%, and 11 upgraders fall in the churn top 10%.
- Offer implication: the two lists are nearly disjoint, so step-up/upgrade offers and retention offers barely compete. The ~19 overlap accounts need the retention fix first (bill shock lowers upgrade propensity in the recipe).

## 5. Recommendation
Ship **LR** as the upgrade model (simple, calibrated, top-10% capture 33% ≈ 3.3x lift, AUC 0.76). HGB and class weights add nothing.
Label it on slides as "simulated upgrade-acceptance label; the model recovers our generator's rules."
Next step if wanted: build the real-history device-upgrade backtest from sandbox billing events (needs pre-cutoff device age reconstructed from billing, not from `lines`).

## Minimal data spec for a real upgrade model
Label: any of {plan tier step-up, device purchase/financing start, line added, premium add-on added} in a 90-day window after cutoff T.
Features: snapshot at T only (plan/tier history, device age at T, financing payoff date, 3/6-month usage vs cap, hotspot, bill trend, support topics before T).
Plus offer exposure logs (who was offered what, and when) to separate organic upgrades from offer-driven ones.
