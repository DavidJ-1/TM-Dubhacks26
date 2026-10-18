# Churn model experiments (scratch). ALL DATA, LABELS AND METRICS ARE SYNTHETIC.

Written 2026-10-17 ~8:57 PM PT. Nothing in the repo was changed (no edits to demo_data/, harness/out, app, or sandbox.db; no git commands that change anything).

**Synthetic-generator caveat.** `labels.csv` churn_90d is a draw from a known formula (`p_true_90d`) over these same features. AUC 0.85 / top-10% lift ~6x is higher than public real benchmarks (e.g. Orange KDD Cup 2009 churn, best AUC ~0.765). The model is recovering the generator's rules. It is not evidence of real-world accuracy.

## Rerun
```
cd /workspace/tmobile/scratch_models
/workspace/tmobile/TM-Dubhacks26/.venv/bin/python folds.py            # checks the folds against demo_data/churn_oof_pred.csv
/workspace/tmobile/TM-Dubhacks26/.venv/bin/python run_experiments.py  # all models (slow on a loaded box; the HGB grid there did not finish tonight) -> results.csv, oof_predictions.csv, leakage_*.csv
/workspace/tmobile/TM-Dubhacks26/.venv/bin/python audit_extra.py
OMP_NUM_THREADS=1 /workspace/tmobile/TM-Dubhacks26/.venv/bin/python quick_hgb.py   # fast HGB + ensemble (paired vs baseline)      # duplicates/groups, correlated pairs, oracle, cancel ablation
```
Shared modules for other workers: `folds.py` (`load_raw()`, `get_folds()`, `fold_ids()`) and `metrics.py` (`all_metrics`, `per_fold`, `bootstrap_ci`, `paired_fold_comparison`, `paired_bootstrap_delta`, `single_feature_auc` with leak flag at AUC > 0.95, `top_capture`, which matches `harness/compare_strategies.topk_capture`).

## Fold definition (from harness/churn_model.py)
- Rows: the 5,000 regular accounts. That is 5,042 minus 42 `ACC-PERSONA-*` accounts. There are 137 churners (2.74%). So the n is 5,000, not 5,042.
- `StratifiedKFold(n_splits=5, shuffle=True, random_state=2026)` on churn_90d, in features.csv file order. No grouping is used. Each row is its own account/household, there are no duplicate account_ids, and there is no household/customer id column, so GroupKFold is not needed.
- The fold ids match the `fold` column of `demo_data/churn_oof_pred.csv` exactly.
- Baseline = `ModelA(feature_set="core")`: 22 core features, standardized L2 LR, C picked by an inner `LogisticRegressionCV` (5-fold, log loss) inside each training fold, plus sign-prior feature dropping.

## Baseline reproduction (synthetic)
The refit OOF matches the stored demo OOF to 6 decimals: **AUC 0.8531, top-10% capture 62.04% (85/137), PR-AUC 0.255, Brier 0.0230, ECE 0.0040** (10 equal-count bins). **It matches** the expected ~0.85 / ~62%.
- Spread across folds: AUC 0.820-0.895 (sd 0.036). Top-10% 51.9%-67.9% (sd 0.061).
- Bootstrap 95% CI (stratified, n=300-500): AUC [0.816, 0.887], top-10% [54.0%, 68.6%].
- Reliability: the bottom 9 deciles predict 0.4-3.4% vs observed 0.2-4.2%. The top decile predicts 16.3% vs observed 17.0%. Calibration is good.
- **Ceiling:** the generator's true probability `p_true_90d` scores AUC 0.864, top-10% 64.2%. So no model can beat the baseline by more than about 0.011 AUC / 2.2 pp (about 3 churners). Even the oracle's top-10% gain over the baseline has a paired-bootstrap CI that includes 0: +1.9 pp [-0.7, +5.1].

## Results (same 5 folds; synthetic)
| model | AUC | PR-AUC | top-10% | Brier | ECE |
|---|---:|---:|---:|---:|---:|
| **Baseline Model A LR (core)** | 0.853 | 0.255 | 62.0% | 0.0230 | 0.0040 |
| LR core, nested C sweep (no sign drop) | 0.852 | 0.253 | 62.8% | 0.0232 | 0.0035 |
| LR all 58 prepared features, nested C | 0.855 | 0.253 | 56.9% | 0.0232 | 0.0043 |
| LR core, class_weight=balanced | 0.855 | 0.239 | 58.4% | 0.128 | 0.264 |
| LR core + log1p + 21 pairwise interactions, nested C | 0.852 | 0.247 | 61.3% | 0.0234 | 0.0039 |
| LR core + log/interactions, balanced | 0.842 | 0.209 | 60.6% | 0.126 | 0.257 |
| HGB, fixed params (lr .05, 150 iter, 7 leaves, min_leaf 100, l2 1), all features | 0.828 | 0.157 | 53.3% | 0.0252 | 0.0074 |
| Rank-average baseline LR + HGB | 0.848 | 0.202 | 60.6% | n/a (ranks) | n/a |
| Oracle p_true_90d (ceiling, not a model) | 0.864 | 0.291 | 64.2% | 0.0226 | 0.0044 |

Noise scale: 1 churner = 0.73 pp of top-10% capture. The fold sd of top-10% is about 6 pp, and the baseline CI is about ±7 pp. **Every difference in this table is within noise** except the calibration loss from class weighting. class_weight=balanced inflates probabilities (Brier 0.13, ECE 0.26) and does not help ranking. The top-10% "gain" from the C sweep is +1 churner.

**HGB note:** I killed the inner-CV-grid HGB run because the box was overloaded (load ~30). I replaced it with a fixed-parameter HGB (`quick_hgb.py`, OMP_NUM_THREADS=1). These parameters were chosen a priori, not tuned on the test folds.
- HGB is **worse than the baseline beyond noise**. Paired per-fold dAUC -0.024 ± 0.019 (0/5 folds better). dTop-10% -8.1 ± 6.0 pp (0/5 folds better). Paired bootstrap dAUC -0.025 [-0.048, -0.004], dTop-10% -9.2 pp [-15.7, -2.2].
- The rank-average ensemble is within noise of the baseline and slightly lower: dAUC -0.005 [-0.017, +0.006], dTop-10% -2.4 pp [-6.6, +2.2].
- This is expected because the generator is logistic (linear in logit). LightGBM/XGBoost are not installed in the repo venv and were not tried.

## Leakage audit (synthetic)
- No single feature has AUC > 0.95. Highest raw: support_90d 0.834, negative_contacts_90d 0.827, support_270d 0.822, min_sentiment_270d 0.79 (inverted), unresolved_90d 0.789, competitor_research_score 0.775. These are high but plausible, because they are the generator's inputs.
- The harness already bars every labels.csv column from the features (p_true_90d, monthly_hazard, toy_p, drivers, upgrade_*) and applies a leak-name regex. These label-file columns would leak (p_true AUC 0.864) but are not used.
- No date columns and no ID used as a feature. No exact duplicate rows. No `total_charges`-style aggregate (tenure x price) exists.
- Near-duplicate pairs (|r| > 0.95): n_line_addons ~ n_protection_addons (r = 1.00), last_bill ~ prior_avg_bill (0.98), cancel_inquiries_270d ~ cancellation_inquiry_contacts_90d (0.98), n_lines ~ voice_min (0.97), data_gb ~ streaming_hours (0.97). This is redundancy, not leakage. The baseline core uses only one feature from each pair.
- Snapshot caveat: these are single-snapshot (2026-10-01) features with no timestamps, so I cannot check that a feature predates the label window. `port_out_inquiry` and `cancel_inquiries_270d` are intent signals that in real data often sit right next to the churn event.

## Compliance flags (CPNI / protected attributes)
Baseline core features that are sensitive:
- **port_out_inquiry**: a port-out signal.
- **competitor_research_score**: a competitor-intent signal. Its source is unknown. If it comes from call/browsing records, it is CPNI-sensitive.
- **cancel_inquiries_270d**: a retention/cancel-intent field.

The baseline has no location, ZIP, age, gender, or race feature. In the wider prepared set (not the baseline), `segment=senior` / `segment=student` are **age proxies**. `language` exists in raw features (a national-origin proxy) but is not in the prepared features. `discount_group` (community/partner) may encode affiliation.

Ablations (synthetic, same folds):
| variant | AUC | top-10% | Brier |
|---|---:|---:|---:|
| baseline | 0.853 | 62.0% | 0.0230 |
| minus port_out_inquiry | 0.852 | 61.3% | 0.0231 |
| minus port_out + competitor_research | 0.851 | 59.1% | 0.0232 |
| minus port_out + competitor + cancel_inquiries | 0.851 | 58.4% (CI 50.4-66.1%) | 0.0233 |
| LR all features minus port/competitor/segment | 0.851 | 56.9% | 0.0233 |

Dropping all three sensitive fields costs about 0.002 AUC and about 3.6 pp top-10% (5 churners). That is within fold noise.

## Recommendation
Keep the current Model A LR. Nothing beats it beyond noise, and it is already within about 0.011 AUC of the generator's ceiling. Do not use class weighting, because it breaks calibration and the demo shows probabilities. If compliance matters, dropping port_out/competitor/cancel fields is cheap on synthetic data (within noise). Wording for the pitch: "recovers the synthetic generator's signal (AUC 0.85 vs 0.86 ceiling)", not a real-world accuracy claim.
