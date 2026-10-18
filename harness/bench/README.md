# Benchmark: cheap model candidates for churn + upgrade (ALL NUMBERS SYNTHETIC)

Every account here is a judge-sandbox stub account or a synthetic copy, and every label is simulated by
`harness/labels.py`. Nothing below is real-world accuracy: it is a pipeline check against a label recipe we wrote
ourselves. Python + scikit-learn only (no LightGBM/XGBoost, no LLMs).

## Headline: lift and churners caught (churn_90d, 5,000 sandbox accounts, 137 synthetic churners)

Out-of-fold scores (no account is scored by a model that saw its label). Binary-rule ties are broken at random
(expected values). Full table: `out/lift_catch.md`.

| contact | Model A (ours, OOF) | 3+ support-contacts rule | support_90d count ranking | random | oracle ceiling |
|---|---|---|---|---|---|
| top 250 (5%) | 62 caught, **9.1x lift** | 18, 2.6x | 54, 7.9x | 7 | 66, 9.6x |
| top 500 (10%) | **85 caught (62%)**, 6.2x | 36 (26%), 2.6x | 74 (54%), 5.4x | 14 | 88 (64%), 6.4x |
| top 1000 (20%) | 106 (77%), 3.9x | 72 (52%), 2.6x | 94 (69%), 3.4x | 27 | 108 (79%), 3.9x |
| 1,462 (all the rule flags) | 112 (82%) | 105 (77%) | 105 | 40 | 113 |

- **Per 500 contacted: Model A catches ~85 synthetic churners vs ~36 for the 3+ rule (2.4x) and ~14 at random.**
  Model A's top 500 finds 85 churners; the 3+ rule needs to contact all 1,462 accounts it flags (29% of the base) to
  find 105.
- The 3+ rule flags 29.2% of accounts, catches 76.6% of churners, at 7.2% precision (AUC 0.744, PR-AUC 0.061).
- Honest caveat: on these synthetic labels a plain ranking by `support_90d` count is close to the models on AUC
  (0.834 vs Model A 0.853, inside fold noise), although Model A still catches more at every k. The count ranking
  fails persona 24, the happy frequent caller (2/6 personas pass vs 5/6 for the LRs), and it gives no reasons.
  data prep is checking whether contact counts are too tied to the label drivers.

### Dollars (not modelled here)
Dollar figures live in the offer engine's [`harness/model_c_artifacts/policy_eval.csv`](../model_c_artifacts/policy_eval.csv).
They come from the simulated 50k randomized trial, use IPW and doubly-robust estimates, and rest on our own save-rate
assumptions, which are partly circular. They are simulated, not measured lift, and **may change as offer rules are
added**, so this README deliberately quotes no dollar values. The bench reports lift and churners caught only, so
the project has only one dollar model.

## The ceiling (read this before quoting AUCs)
Labels are drawn from a known probability (`p_true_90d`, `p_upgrade_90d`). Scoring with that probability is the best
any model can do given the coin-flip noise: **oracle AUC churn 0.864, upgrade 0.808** (`out/ceilings.csv`, recomputed
from labels.csv, not hardcoded). Model A's OOF AUC of 0.853 is ~99% of the reachable ceiling. The bench's
all-feature LR (0.822) is ~95%. With 137 churners, fold SD is ~0.03-0.07, so **every model within ~0.04 AUC is
tied**. Do not sell 0.85 vs 0.82 as a win.

## How we compare (`out/how_we_compare.md/.csv/.png`)
churn_90d, 5-fold stratified OOF (seed 42) on the 5,000 regular accounts:

| row | AUC | fold sd | PR-AUC | top-10% capture | top-10% lift |
|---|---|---|---|---|---|
| **Ours: Model A (the churn model LR, 22 core features; its own OOF, `harness/out/churn_oof_pred.csv`)** | **0.853** | 0.059 | 0.255 | **62.0%** | 6.2x |
| LR on Model A's 22 core features (bench refit, unweighted, uncalibrated) | 0.841 | 0.071 | 0.238 | 57.7% | 5.8x |
| LR on all 58 prepare() features (unweighted) | 0.822 | 0.052 | 0.216 | 54.0% | 5.4x |
| HGB + sigmoid calibration (challenger) | 0.824 | 0.030 | 0.188 | 58.4% | 5.8x |
| Untuned default `GradientBoostingClassifier()` | 0.809 | 0.038 | 0.140 | 53.3% | 5.3x |
| Untuned default `HistGradientBoostingClassifier()` | 0.784 | 0.051 | 0.140 | 46.7% | 4.7x |
| Rule: 3+ support contacts in 90d (binary) | 0.744 | 0.058 | 0.061 | 26.2% | 2.6x |
| Rule: rank by support_90d count | 0.834 | 0.043 | 0.158 | 53.7% | 5.4x |
| Oracle ceiling | 0.864 | 0.054 | 0.291 | 64.2% | 6.4x |

upgrade_90d (new affordability-based labels, 322/5000): LR all features 0.740, HGB+sigmoid 0.747, default GBC
0.733, default HGB 0.730, the binary near-or-over-cap rule 0.544 (flags 3.9%, catches 12%), near-cap ranking 0.670,
oracle 0.808. Model A's 22 churn features are the wrong set for upgrade (0.66-0.68), so upgrade uses all features.

**Published IBM Telco Customer Churn AUCs: context only, NOT head-to-head.** That is a different dataset (7,043 real
customers, 26.5% churn vs our 2.7% per 90 days, different features, real labels;
https://www.kaggle.com/datasets/blastchar/telco-customer-churn). Published test AUCs cluster at 0.83-0.85:
- Gaddamwar 2026, arXiv:2608.26151, Table 1: LR 0.841, XGBoost 0.837, LightGBM 0.831 (5-fold CV LR 0.845 +/- 0.013). https://arxiv.org/abs/2608.26151
- Ali, Ahmed & Attia 2026, arXiv:2607.10260, Table VIII (tuned): XGBoost 0.841, LightGBM 0.840, CatBoost 0.840. https://arxiv.org/abs/2607.10260
- pablowilliams/churn-propensity-modelling report, Table 1: XGBoost 0.847, RF 0.847, LR 0.845. https://raw.githubusercontent.com/pablowilliams/churn-propensity-modelling/main/paper/report.pdf
- CCallahan308/signalforge README: LR 0.849, gradient boosting 0.847, RF 0.846. https://github.com/CCallahan308/signalforge
The shared lesson, which also holds in our data: tuned boosting does not beat a regularized LR on account-level
tabular churn features. All published figures were read from the pages above on 2026-10-17. None comes from IBM
itself, and the two GitHub sources are not peer reviewed.

## Learning curve (`out/learning_curve.csv`, `out/learning_curve_long.csv`, `out/learning_curve_check.png`)
- **real_5k**: train on n sandbox accounts, score a stratified 25% holdout, 10 seeds (holdout and subsample both vary).
- **synthetic_50k**: train on n of data prep's 50k Gaussian-copula synthetic accounts
  (`harness/out/scaled/`; enrichment columns dropped so the inputs match Model A), test on **all 5,000 real sandbox
  accounts**. 10 seeds up to 5k, 5 at 10k-25k, 3 at 50k (LR at 50k is deterministic, so sd = 0).

churn_90d AUC (mean +/- sd):

| n train | LR core-22, real_5k | LR core-22, synthetic | LR all-58, real_5k | LR all-58, synthetic | HGB+sig, real_5k | HGB+sig, synthetic |
|---|---|---|---|---|---|---|
| 250 | 0.771 +/- 0.059 | | 0.750 +/- 0.072 | | 0.739 +/- 0.122 | |
| 1,000 | 0.807 +/- 0.040 | 0.770 +/- 0.099 | 0.755 +/- 0.044 | 0.727 +/- 0.090 | 0.805 +/- 0.037 | 0.752 +/- 0.119 |
| 2,000 / 2,500 | 0.814 +/- 0.032 | 0.847 +/- 0.011 | 0.782 +/- 0.049 | 0.823 +/- 0.015 | 0.820 +/- 0.034 | 0.822 +/- 0.012 |
| 3,750 / 5,000 | 0.844 +/- 0.032 | 0.856 +/- 0.007 | 0.811 +/- 0.031 | 0.844 +/- 0.012 | 0.822 +/- 0.034 | 0.841 +/- 0.010 |
| 10,000 | | 0.857 +/- 0.003 | | 0.854 +/- 0.005 | | 0.845 +/- 0.009 |
| 25,000 | | 0.862 +/- 0.002 | | 0.863 +/- 0.004 | | 0.857 +/- 0.005 |
| 50,000 | | 0.865 | | 0.869 | | 0.863 |

Top-10% capture at 50k synthetic: LR all-58 62.0%, core-22 62.0%, HGB 61.6% (oracle on the same 5,000 rows: 64.2%).
Upgrade at 50k synthetic: LR all-58 0.762, HGB 0.767 vs oracle 0.808. The gap is expected, because the new upgrade
recipe uses household income / step-up cost, which are not model inputs.

**Train-on-synthetic caveat.** Training on synthetic data looks strong because 50k rows let a model learn our own
label recipe almost exactly. That is a property of synthetic labels, not of real customer behaviour. Same-rows check
(`out/tstr_leak_check_synthetic_50k.json`): on the identical 5,000 real rows, the oracle AUC is 0.8639 and LR
all-58 trained on 50k synthetic gets 0.8690 (diff +0.005, paired stratified bootstrap 95% CI [-0.003, +0.015]). Core-22
gets 0.8652 (CI [-0.003, +0.006]) and HGB 0.8623. The small excess over the oracle is noise (~137 real churners), not
a leak. Leak checks passed: no synthetic column matches a labels.csv column or the leak pattern, there is no
account-id overlap, and the 9 enrichment columns (`recent_job_change`, `household_income_usd`, `income_band`,
`area_median_income_usd`, `income_geo_level`, `next_plan_sku`, `next_plan_price_cents`, `step_up_cost_cents`,
`step_up_cost_pct_income`) were dropped. data prep confirms the copula sampled only feature columns, and the labels were
drawn afterwards with the same recipe.

What the curve says: on 5k real accounts the LRs are still climbing at 3,750 (data-limited: ~100 churners in
training), and the curated 22-feature LR beats the 58-feature LR at every size. With more (synthetic) data both LRs
saturate at the ceiling by ~10-25k rows. HGB gains nothing over LR at any size.

## Scaling: real 5k vs synthetic 50k vs synthetic 250k, always tested on the real 5k (`out/scaling.md/.csv`, `out/scaling_check.png`)
Synthetic inputs are cut to the features.csv columns and prepared in one `prepare()` call with the real rows. The
oracle is computed on the same 5,000 real rows, and every row carries a paired stratified bootstrap 95% CI of
(AUC minus oracle).

| target | model | real 5k (5-fold OOF) | synthetic 50k | synthetic 250k | oracle |
|---|---|---|---|---|---|
| churn_90d | logreg_core22 | 0.841 (sd 0.071) | 0.865 [+0.001, CI -0.003/+0.006] | 0.863 | 0.864 |
| churn_90d | logreg all-58 | 0.822 (sd 0.052) | 0.869 [+0.005, CI -0.003/+0.015] | 0.864 [+0.000, CI -0.004/+0.005] | 0.864 |
| churn_90d | hgb_sigmoid | 0.824 (sd 0.030) | 0.861 | 0.864 [+0.000, CI -0.007/+0.008] | 0.864 |
| upgrade_90d | logreg all-58 | 0.740 (sd 0.037) | 0.762 | 0.765 | 0.808 |
| upgrade_90d | hgb_sigmoid | 0.747 (sd 0.026) | 0.769 | 0.770 | 0.808 |

- Churn: every point above the ceiling has a CI that spans 0, so it is noise. Churn saturates at the ceiling by 50k,
  and 250k only cuts variance. This matches the churn model's Model A scaling run (`harness/out/churn_scaled_eval.csv`,
  0473c4f: 0.853 / 0.863 / 0.863 at 5k / 50k / 250k) and data prep's TSTR table (0.820 / 0.860 / 0.863).
- Synthetic-trained churn models rank well but are miscalibrated on the real 5k: mean predicted 3.9% vs actual
  2.74%. A 5-fold CV Platt recalibration fitted on the real 5k fixes it (mean 2.74%, ECE 0.012 -> 0.003; see
  `out/upgrade_best.md`).
- Top-10% capture at 250k: churn LR 63.5%, upgrade 31.7% (features.csv only; the oracle is 37.6%).
- `learning_curve*.csv` now also has `train_source=synthetic_250k` (1k ... 50k subsamples of the 250k set, plus the
  full 250k), with the same schema. Same-rows check: `out/tstr_leak_check_synthetic_250k.json`.
- **Known data issue:** in the 50k set, ~36% of single-segment accounts have 2+ lines (a segment/line-count
  mismatch). data prep fixed it in the 250k set, so prefer the 250k rows.
- data prep's upgrade TSTR (0.778 / 0.799 / 0.801) is higher than our features.csv-only 0.765. Our tier b2/c numbers
  reproduce it (0.799 / 0.805 at 250k), which suggests their run included the enrichment columns (income).

## Upgrade improvement (`out/upgrade_improve.md/.csv`, `out/upgrade_improve_check.png`, `out/upgrade_best.md`)
The upgrade recipe (`harness/labels.py` UPGRADE_COEFS) is a logistic function of these terms:
- plan tier, capped plan, top/premium family
- over-cap share, near cap (utilisation >= 80%), usage growth, heavy hotspot use
- device age, a phone paid off recently, tenure, student
- bill shock
- **step-up cost as a share of income** and **log(income / national median)**, both from enrichment.csv
- churn risk

Three of the inputs exist only in enrichment.csv, so tiers matter:

| tier | what is added | real 5k OOF: best AUC (fold sd) | trained on 250k synthetic -> real 5k |
|---|---|---|---|
| a0 | prepare() only (old baseline) | 0.747 HGB+sig (0.026); LR 0.736 | LR 0.765, HGB 0.767 |
| a | + domain features from features.csv (per-line cap utilisation, over-cap share, hotspot/line, tier dummies, device age past 12 months) | 0.753 HGB+sig (0.025); LR 0.747 | **LR 0.775**, HGB 0.772 |
| b1 | + recent_job_change (in no label) | 0.753 HGB+sig; LR 0.746 | LR 0.775, HGB 0.776 |
| b2 | + income_band (a coarsened version of the income driver) | 0.772 HGB+sig; LR 0.771 | LR 0.800 |
| b3 | + household (family, kids, promo months; in no label) | 0.773; LR 0.770 | LR 0.799 |
| c | + RECIPE-REVEALING drivers (step_up_cost_pct_income, log income ratio, on_top_plan) | 0.777 LR (0.034) | LR 0.805 |
| | oracle (same rows) | 0.808 | 0.808 |

- **Interactions** (degree-2 `interaction_only` on 10-13 usage/plan/device/bill/affordability terms, C tuned by inner
  CV) gain nothing: 0.749 vs 0.747 on tier a. **Tuned HGB** (RandomizedSearchCV over learning_rate, max_leaf_nodes,
  min_samples_leaf, l2, max_iter, nested in the outer folds) is no better than the bench HGB, at 0.740-0.766 vs
  0.747-0.775. The search overfits with ~260 positives per training fold.
- **Recipe-revealing columns.** `step_up_cost_pct_income` is the recipe's affordability term itself (the label
  clips it to [0, 10]). `log(household_income_usd / area_median_income_usd)` is the recipe's income term exactly.
  `on_top_plan` duplicates the recipe's top-tier term, which is also already in features.csv via plan_family.
  `income_band` is a coarsened copy of the income driver and accounts for most of the enrichment gain (b1 -> b2:
  +0.025). `area_median_income_usd` is a constant. `recent_job_change` and the household fields are in no label and
  add nothing (b1 ~ a, b3 ~ b2), which is a useful negative control. None of these columns is a label-derived
  probability or a label: they are inputs to the formula, generated before the labels, so they are not leaks. But
  the gain from b2/c means the model is **recovering our own synthetic upgrade formula**, not learning real
  customer behaviour. The honest "what a model learns" numbers are tiers a/b1: **0.753 on the real 5k and 0.775
  trained on 250k synthetic**, vs the old 0.740.
- **Best honest upgrade model:** tier-a/b1 LR (C tuned) trained on the 250k synthetic set, then Platt-recalibrated
  on the real 5k. AUC 0.775 (+0.035 vs 0.740). Top-10% capture 36.3%, top-15% 44.1-44.4%, top-20% 52%. Mean
  predicted 6.09% raw vs 6.44% actual; after Platt 6.44% (ECE 0.010 -> 0.007). Trained on the real 5k only, the
  best is HGB+sigmoid at 0.753 (top-10% 33.2%, top-15% 41.6%), within fold noise of LR at 0.746. With income band
  (b2, partly recipe-revealing), 250k LR reaches 0.799 (top-10% 38.5%, top-15% 50.0%).
- **Personas** (upgrade: 25/28 must be >= 90th pct, 22/24/27 below the median; `out/upgrade_persona_check.csv`,
  `out/upgrade_best_personas.csv`): LR passes 5/5 in every tier. Tuned HGB passes 4/5, failing persona 24 at the
  53rd-63rd pct. Synthetic-trained models do the same (`out/upgrade_best.md`): HGB+sig at 250k (b1) and LR at 50k pass 5/5. LR at 250k
  (a/b1) passes 4/5, with persona 24 at the 50.6th pct, just over the cut. Persona 24 sits right at the median for
  upgrade, so it is fragile for any model.

## Recommendation
**Unweighted logistic regression on Model A's curated features (that is Model A).** It is tied with HGB within noise,
reaches ~99% of the oracle ceiling OOF, is the most data-efficient at 5k, has exact additive reasons, and is
well calibrated without class weights (balanced weights inflate Brier from 0.024 to 0.128; see `out/cv_results.md`).
That calibration matters because the EV engine multiplies P(churn) by dollars. Keep sigmoid-calibrated HGB as the
challenger. For upgrade, use all-feature LR (0.740, tied with HGB at 0.747). Calibration check:
`out/calibration_check.png` (internal; the UI owns the presentation gain/calibration charts).

## Cross-check vs the harness (0e778bf) and notes
- the harness 5-fold: 3+ rule 0.743 / top-10% 26% (ours 0.744 / 26.2%); logreg 0.829 (ours 0.822 all-58, 0.841
  core-22); model_a 0.849 / 61% (Model A's own OOF file gives 0.853 / 62.0%); ceiling 0.863 (ours 0.864 on the full
  5,000, vs harness pooling). Upgrade: near-cap rule 0.544 (same), logreg 0.742 (ours 0.740), hgb 0.73 (our default
  HGB 0.730; our tuned HGB+sigmoid 0.747). The differences are fold seeds and feature subsets, and all are well
  inside fold sd.
- `harness/model_a.py` (the Retention Console's model) is a separate model trained on toy labels (~14.6% churn).
  It is **not** what we benchmark. "Model A" here means the churn model's `harness/churn_model.py`, scored from
  `harness/out/churn_oof_pred.csv`.
- Feature prep is imported at run time from `harness/churn_features.prepare()` (cleaned version, d9bcd76), never
  copied.
- No TinyJev/LLM rows (dropped by David).

## Run (all CPU, under 5 min total; `OMP_NUM_THREADS=1` is set inside)
```
python3 -m harness.bench.bench                 # 5-fold CV table + personas -> out/cv_results.*
python3 -m harness.bench.learning_curve        # real_5k curve, ceilings.csv
python3 -m harness.bench.learning_curve --train-features harness/out/scaled/features_scaled.csv \
        --train-labels harness/out/scaled/labels_scaled.csv          # synthetic_50k curve (test = real 5k)
python3 -m harness.bench.compare               # how_we_compare.*, lift_catch.*, calibration_check.png
python3 -m harness.bench.learning_curve --train-features harness/out/scaled_250k/features_scaled.csv \
        --train-labels harness/out/scaled_250k/labels_scaled.csv --train-source synthetic_250k
python3 -m harness.bench.scaling               # real 5k vs 50k vs 250k -> real 5k (~4 min)
python3 -m harness.bench.upgrade_improve       # upgrade feature tiers x models (~7 min)
python3 -m harness.bench.upgrade_best          # upgrade capture top5-20%, calibration + CV Platt, personas
```
`--features/--labels` (or `TM_BENCH_FEATURES`/`TM_BENCH_LABELS`) point at other data, and `--n-max N` caps the
regular accounts (stratified). Charts need matplotlib (in requirements.txt as of 5da5d78).
