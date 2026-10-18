# How we compare (our numbers SYNTHETIC; published numbers are a different dataset)

## churn_90d

| row | auc | auc_fold_sd | prauc | top10_capture | top10_lift | rule_flag_share | rule_recall | rule_precision |
|---|---|---|---|---|---|---|---|---|
| LR on all 58 prepare() features (unweighted) | 0.822 | 0.052 | 0.216 | 0.540 | 5.401 |  |  |  |
| LR on Model A's 22 core features (unweighted) | 0.841 | 0.071 | 0.238 | 0.577 | 5.766 |  |  |  |
| HGB + sigmoid calibration (challenger) | 0.824 | 0.030 | 0.188 | 0.584 | 5.839 |  |  |  |
| Untuned default sklearn GradientBoostingClassifier() | 0.809 | 0.038 | 0.140 | 0.533 | 5.328 |  |  |  |
| Untuned default sklearn HistGradientBoostingClassifier() | 0.784 | 0.051 | 0.140 | 0.467 | 4.672 |  |  |  |
| Rule: 3+ support contacts in 90d (binary) | 0.744 | 0.058 | 0.061 | 0.262 | 2.621 | 0.292 | 0.766 | 0.072 |
| Rule: rank by support_90d contact count | 0.834 | 0.043 | 0.158 | 0.537 | 5.369 |  |  |  |
| Ours: Model A (tm-churn LR, 22 core features; its OOF) | 0.853 | 0.059 | 0.255 | 0.620 | 6.204 |  |  |  |
| Oracle ceiling (label-generating probability) | 0.864 | 0.054 | 0.291 | 0.642 | 6.423 |  |  |  |

## upgrade_90d

| row | auc | auc_fold_sd | prauc | top10_capture | top10_lift | rule_flag_share | rule_recall | rule_precision |
|---|---|---|---|---|---|---|---|---|
| LR on all 58 prepare() features (unweighted) | 0.740 | 0.037 | 0.185 | 0.298 | 2.981 |  |  |  |
| HGB + sigmoid calibration (challenger) | 0.747 | 0.026 | 0.172 | 0.307 | 3.075 |  |  |  |
| Untuned default sklearn GradientBoostingClassifier() | 0.733 | 0.028 | 0.160 | 0.304 | 3.043 |  |  |  |
| Untuned default sklearn HistGradientBoostingClassifier() | 0.730 | 0.026 | 0.151 | 0.283 | 2.826 |  |  |  |
| Rule: near or over data cap (binary, tm-harness rule) | 0.544 | 0.008 | 0.081 | 0.177 | 1.766 | 0.039 | 0.121 | 0.198 |
| Rule: rank by lines over cap + usage/cap | 0.670 | 0.026 | 0.122 | 0.199 | 1.988 |  |  |  |
| Oracle ceiling (label-generating probability) | 0.808 | 0.018 | 0.266 | 0.376 | 3.758 |  |  |  |

## Published IBM Telco Customer Churn AUCs (context only, NOT head-to-head)

Different dataset: 7,043 customers, 26.5% churn (vs our 2.7% over 90 days), different features, real (not synthetic) labels. Dataset: https://www.kaggle.com/datasets/blastchar/telco-customer-churn

| model | auc | source | url |
|---|---|---|---|
| Logistic regression | 0.841 | Gaddamwar 2026, arXiv:2608.26151 (Table 1, test n=1,409; SMOTE) | https://arxiv.org/abs/2608.26151 |
| XGBoost | 0.837 | Gaddamwar 2026, arXiv:2608.26151 (Table 1) | https://arxiv.org/abs/2608.26151 |
| LightGBM | 0.831 | Gaddamwar 2026, arXiv:2608.26151 (Table 1) | https://arxiv.org/abs/2608.26151 |
| CatBoost | 0.840 | Ali, Ahmed & Attia 2026, arXiv:2607.10260 (Table VIII, tuned) | https://arxiv.org/abs/2607.10260 |
| XGBoost | 0.841 | Ali, Ahmed & Attia 2026, arXiv:2607.10260 (Table VIII, tuned) | https://arxiv.org/abs/2607.10260 |
| Logistic regression | 0.845 | pablowilliams/churn-propensity-modelling report (Table 1, test 20%) | https://raw.githubusercontent.com/pablowilliams/churn-propensity-modelling/main/paper/report.pdf |
| XGBoost | 0.847 | pablowilliams/churn-propensity-modelling report (Table 1) | https://raw.githubusercontent.com/pablowilliams/churn-propensity-modelling/main/paper/report.pdf |
| Logistic regression | 0.849 | CCallahan308/signalforge README (test AUC, 20% holdout) | https://github.com/CCallahan308/signalforge |
| Gradient boosting | 0.847 | CCallahan308/signalforge README | https://github.com/CCallahan308/signalforge |
