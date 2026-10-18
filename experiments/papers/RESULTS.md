# Paper-driven modeling tricks vs baseline LR — ALL DATA AND NUMBERS SYNTHETIC
Folds: the repo's own folds (`../folds.py`: StratifiedKFold(5, shuffle, seed 2026), 5,000 non-persona accounts, 137 churners).
B0 reproduces the stored demo OOF exactly (AUC 0.8531, top-10% capture 0.620; correlation with demo_data/churn_oof_pred.csv = 1.000000).
Scripts: `run_papers.py` (P*), `run_papers2.py` (R*), `fast_paired.py`. Logs: run.log, run2.log. Tables: results.csv, results_round2.csv, repeated_cv.csv. OOF scores: oof_predictions*.csv.
Nothing was written outside this folder. No git operations were run.

## CPNI compliance flags (per the parent's steer)
- In the baseline CORE_FEATURES today: **`port_out_inquiry`** (a porting signal) and **`competitor_research_score`** (competitor-contact/research). Both are used by the shipped Model A (B0).
- Protected-attribute proxies in the prepared feature matrix: **`segment=senior` / `segment=student`** (age proxies; segment is not in core, but it is in the "all features" sets). `discount_group=55_plus` is already dropped by prepare() as redundant. `language` and `credit_tier` are already dropped by prepare() (FAIRNESS_DROP).
- No ZIP, location, gender or race columns exist.
- All P*/R* variants exclude these. **B1 = the baseline Model A without port/competitor** is the fair compliant reference.

## Results (OOF on the identical folds; 1 churner = 0.73 pp of top-10% capture)
| Variant | AUC | PR-AUC | Top-10% | Brier | ECE | Δtop10 vs B0, fold mean±sd (folds better) | Δtop10 vs B0, paired bootstrap 95% CI | Δtop10 vs B1, fold | Δtop10 vs B1, bootstrap |
|---|---|---|---|---|---|---|---|---|---|
| B0 baseline Model A (incl. port/competitor) | .853 | .255 | .620 | .0230 | .0040 | — | — | +.029±.047 | +.033 [.000,+.073] |
| B1 Model A, CPNI-compliant | .851 | .249 | .591 | .0232 | .0043 | −.029±.047 (0/5) | −.033 [−.073,.000] | — | — |
| **R2 spline-LR (GAM-like), compliant** | **.854** | .239 | **.628** | .0233 | .0037 | +.000±.044 (2/5) | +.002 [−.040,+.051] | **+.029±.016 (4/5)** | **+.033 [.000,+.066]** |
| R1 Firth + FLIC LR, compliant | .849 | .238 | .599 | .0236 | .0057 | −.021±.060 | −.029 [−.073,+.015] | +.008±.031 | +.003 [−.029,+.036] |
| R3 bagged Model A ×20, compliant | .851 | .245 | .599 | .0233 | .0035 | −.022±.032 | −.028 [−.073,+.007] | +.007±.016 | +.003 [−.022,+.033] |
| P1 HGB, monotone constraints, compliant core | .836 | .180 | .547 | .0249 | .0081 | −.065±.046 (0/5) | −.075 [−.139,−.011] | −.036±.025 | −.041 [−.102,+.015] |
| P1b HGB, monotone, all compliant features | .828 | .184 | .577 | .0250 | .0053 | −.051±.055 | −.043 [−.117,+.022] | −.022±.042 | −.010 |
| P2 LightGBM lambdarank (top-k ranking loss) | .840 | .182 | .584 | n/a | n/a | −.028±.070 | −.038 [−.102,+.022] | +.001±.058 | −.005 |
| P3 LightGBM focal loss (γ=2) | .841 | .202 | .584 | n/a | n/a | −.029±.047 | −.041 [−.102,+.022] | .000±.044 | −.007 |
| P3b LightGBM, plain logloss | .833 | .201 | .577 | .0242 | .0044 | −.043±.079 | −.049 | −.014±.066 | −.016 |
| P4 LR + random oversampling 1:3 (SMOTE-family) | .854 | .232 | .555 | .0600 | .1297 | −.058±.031 (0/5) | −.065 [−.117,−.015] | −.029±.030 | −.032 |
| P5 Model A + isotonic calibration | .839 | .221 | .591 | .0236 | .0046 | −.029±.039 | −.036 | .000±.044 | −.002 |
| P6 rank-average of B1 LR + P1 HGB | .850 | .211 | .562 | n/a | n/a | −.051±.040 | −.058 [−.113,−.007] | −.022±.032 | −.025 |
| P6b rank-average of B1 + P1 + P2 | .849 | .207 | .577 | n/a | n/a | −.028±.059 | −.042 | +.001±.044 | −.009 |

Fold noise: B0's top-10% capture has a fold sd of .061, and its 95% CI is [.544,.701]. In repeated CV (3 seeds × 5 folds, a noise estimate only): B0 .611±.024, B1 .596±.018, P1 .574±.011.

## Verdict
- **Nothing beats the baseline beyond noise.** The best variant, spline-LR, ties B0 (+1 churner, CI centered on 0).
- **Complying with CPNI costs about 4 churners** (B0 → B1, −2.9 pp top-10%, borderline significant). **Spline-LR wins back all of that loss using only compliant features.** It beats B1 in 4/5 folds, and its bootstrap CI just touches 0, so the gain is borderline real. It also has the best ECE (.0037) and is still interpretable (per-feature shape curves).
- Trees (HGB/LightGBM), ranking losses (lambdarank), focal loss, ensembling with trees, oversampling and isotonic calibration all fail to help. Several are significantly worse. This matches the literature: with about 110 training positives and mostly monotone, additive signal, the low-variance additive model wins. Oversampling breaks calibration (ECE .13), as Elor & Averbuch-Elor predict.
- **Recommendation:** if the CPNI exclusions apply, replace Model A with spline-LR on the compliant core. It gives baseline-equal ranking without the porting/competitor features. Say "matches baseline", not "beats". Don't chase tree or ranking-loss variants tonight.

## Ideas and sources
1. Balancing/SMOTE rarely helps strong learners on proper metrics, and it hurts calibration — Elor & Averbuch-Elor, "To SMOTE, or not to SMOTE?" (2022) https://arxiv.org/abs/2201.08528 → P4 (confirmed).
2. Firth penalized LR plus FLIC intercept correction for rare events — Puhr et al., Stat Med 2017, https://onlinelibrary.wiley.com/doi/10.1002/sim.7273 (arXiv 2101.07620) → R1 (neutral).
3. LambdaRank / top-k ranking objective — LightGBM LGBMRanker docs, https://lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.LGBMRanker.html. Churn papers use LightGBM with tuned objectives (e.g. "Analysis of an Optimized LightGBM Based on Different Objective Functions for Customer Churn Prediction in Telecom", ICACR 2023, doi 10.1109/icacr59381.2023.10314612) → P2 (no gain).
4. Focal loss — Lin et al., "Focal Loss for Dense Object Detection" (2017), https://arxiv.org/abs/1708.02002 → P3 (no gain).
5. Monotonic constraints in GBMs (sklearn HistGradientBoosting `monotonic_cst`) → P1 (worse than LR).
6. GAM/spline additive models (the EBM/GA2M line of work: Lou, Caruana et al., "Accurate intelligible models with pairwise interactions", KDD 2013) → R2 (the best variant).
7. Bagging to reduce variance at small n (Breiman 1996) → R3 (neutral).
8. Isotonic/Platt calibration (sklearn calibration guide) → P5. The baseline is already well calibrated (ECE .004), and isotonic ties cost AUC.
9. TabPFN — Hollmann et al., Nature 2025, https://www.nature.com/articles/s41586-024-08328-6. **Not run.** It is not installed and needs torch plus gated model weights. The library's CPU limit is 1,000 rows for v2 and 5,000 for v3 (PriorLabs/TabPFN PR #1123), so 4,000 training rows × 5 folds on this overloaded 8-core box would not finish before the deadline. It's a worthwhile post-freeze try.
10. Repeated CV for noise estimation → repeated_cv.csv.
11. Target encoding: skipped. No high-cardinality categoricals remain after the compliance drops.

Ops note: under the box's load (~26), sklearn and LightGBM OpenMP thread oversubscription hung jobs. Run with OMP_NUM_THREADS=1. LightGBM's ranker with bagging (subsample) hung outright, so P2 runs without bagging.
