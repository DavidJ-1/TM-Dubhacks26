# Upgrade capture + calibration on the real 5k (ALL SYNTHETIC)

Capture = share of real upgrade_90d positives (322/5000) in the top k% by score. Platt = 5-fold CV logistic recalibration fitted on the real 5k (ranking unchanged, so AUC/capture are unchanged).

| target | tier | model | trained on | calib | AUC | PR-AUC | top5 | top10 | top15 | top20 | mean pred | actual | ECE | Brier |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| upgrade_90d | b1 a + job change | lr_tuned | real_5k | raw | 0.746 | 0.202 | 21.7% | 34.5% | 41.9% | 47.2% | 6.48% | 6.44% | 0.0066 | 0.0561 |
| upgrade_90d | b1 a + job change | lr_tuned | real_5k | platt_cv_on_real | 0.742 | 0.198 | 21.1% | 34.5% | 41.6% | 47.5% | 6.47% | 6.44% | 0.0061 | 0.0563 |
| upgrade_90d | b1 a + job change | hgb_sigmoid | real_5k | raw | 0.753 | 0.185 | 19.6% | 33.2% | 41.6% | 48.4% | 6.47% | 6.44% | 0.0037 | 0.0566 |
| upgrade_90d | b1 a + job change | hgb_sigmoid | real_5k | platt_cv_on_real | 0.752 | 0.182 | 18.9% | 32.6% | 41.6% | 48.8% | 6.45% | 6.44% | 0.0045 | 0.0566 |
| upgrade_90d | b2 b1 + income band | lr_tuned | real_5k | raw | 0.771 | 0.226 | 22.4% | 35.7% | 47.5% | 55.9% | 6.47% | 6.44% | 0.0025 | 0.0552 |
| upgrade_90d | b2 b1 + income band | lr_tuned | real_5k | platt_cv_on_real | 0.768 | 0.222 | 22.7% | 36.0% | 47.2% | 56.2% | 6.47% | 6.44% | 0.0032 | 0.0554 |
| upgrade_90d | a features.csv + domain | lr_tuned | synthetic_50k | raw | 0.771 | 0.231 | 24.8% | 36.0% | 43.8% | 51.9% | 6.05% | 6.44% | 0.0100 | 0.0551 |
| upgrade_90d | a features.csv + domain | lr_tuned | synthetic_50k | platt_cv_on_real | 0.770 | 0.230 | 24.5% | 36.0% | 43.8% | 51.9% | 6.44% | 6.44% | 0.0067 | 0.0551 |
| upgrade_90d | b1 a + job change | lr_tuned | synthetic_50k | raw | 0.771 | 0.232 | 24.8% | 36.0% | 43.8% | 51.9% | 6.05% | 6.44% | 0.0098 | 0.0551 |
| upgrade_90d | b1 a + job change | lr_tuned | synthetic_50k | platt_cv_on_real | 0.770 | 0.230 | 24.5% | 36.3% | 43.8% | 51.9% | 6.44% | 6.44% | 0.0071 | 0.0551 |
| upgrade_90d | a features.csv + domain | lr_tuned | synthetic_250k | raw | 0.774 | 0.237 | 23.6% | 36.3% | 44.1% | 51.9% | 6.09% | 6.44% | 0.0094 | 0.0549 |
| upgrade_90d | a features.csv + domain | lr_tuned | synthetic_250k | platt_cv_on_real | 0.774 | 0.234 | 23.3% | 36.3% | 44.1% | 52.2% | 6.44% | 6.44% | 0.0069 | 0.0549 |
| upgrade_90d | b1 a + job change | lr_tuned | synthetic_250k | raw | 0.775 | 0.237 | 23.6% | 36.3% | 44.4% | 51.9% | 6.09% | 6.44% | 0.0101 | 0.0549 |
| upgrade_90d | b1 a + job change | lr_tuned | synthetic_250k | platt_cv_on_real | 0.774 | 0.234 | 23.3% | 36.3% | 44.1% | 52.2% | 6.44% | 6.44% | 0.0065 | 0.0549 |
| upgrade_90d | b1 a + job change | hgb_sigmoid | synthetic_250k | raw | 0.776 | 0.243 | 24.8% | 36.3% | 44.4% | 52.8% | 6.01% | 6.44% | 0.0103 | 0.0547 |
| upgrade_90d | b1 a + job change | hgb_sigmoid | synthetic_250k | platt_cv_on_real | 0.775 | 0.241 | 24.2% | 36.3% | 44.7% | 52.8% | 6.44% | 6.44% | 0.0057 | 0.0547 |
| upgrade_90d | b2 b1 + income band | lr_tuned | synthetic_250k | raw | 0.799 | 0.255 | 26.4% | 38.5% | 50.0% | 58.1% | 6.02% | 6.44% | 0.0061 | 0.0539 |
| upgrade_90d | b2 b1 + income band | lr_tuned | synthetic_250k | platt_cv_on_real | 0.799 | 0.253 | 26.1% | 38.5% | 49.7% | 58.1% | 6.44% | 6.44% | 0.0032 | 0.0539 |
| upgrade_90d | c b3 + recipe drivers (RECIPE-REVEALING) | lr_tuned | synthetic_250k | raw | 0.805 | 0.262 | 27.3% | 39.4% | 50.9% | 58.1% | 6.01% | 6.44% | 0.0075 | 0.0536 |
| upgrade_90d | c b3 + recipe drivers (RECIPE-REVEALING) | lr_tuned | synthetic_250k | platt_cv_on_real | 0.804 | 0.261 | 27.0% | 39.8% | 51.2% | 59.0% | 6.44% | 6.44% | 0.0042 | 0.0536 |
| churn_90d | prepare() (Model A inputs) | logreg_core22 | synthetic_250k | raw | 0.863 | 0.286 | 48.2% | 63.5% | 73.0% | 78.8% | 3.91% | 2.74% | 0.0117 | 0.0230 |
| churn_90d | prepare() (Model A inputs) | logreg_core22 | synthetic_250k | platt_cv_on_real | 0.861 | 0.287 | 48.2% | 63.5% | 73.7% | 78.8% | 2.74% | 2.74% | 0.0032 | 0.0227 |
| churn_90d | prepare() (Model A inputs) | hgb_sigmoid | synthetic_250k | raw | 0.864 | 0.266 | 46.7% | 61.3% | 71.5% | 78.8% | 3.92% | 2.74% | 0.0118 | 0.0232 |
| churn_90d | prepare() (Model A inputs) | hgb_sigmoid | synthetic_250k | platt_cv_on_real | 0.863 | 0.267 | 46.0% | 61.3% | 71.5% | 78.8% | 2.74% | 2.74% | 0.0037 | 0.0229 |

Upgrade personas for synthetic-trained models (percentile among the 5,000 real accounts; high 25/28 >= 90, low 22/24/27 < 50):

```
account_id                                                           ACC-PERSONA-22  ACC-PERSONA-24  ACC-PERSONA-25  ACC-PERSONA-27  ACC-PERSONA-28  n_pass
tier                                     model       trained_on                                                                                            
a features.csv + domain                  lr_tuned    synthetic_250k             2.9            50.7            95.2             3.3            94.9       4
                                                     synthetic_50k              2.7            49.8            92.7             3.3            93.3       5
b1 a + job change                        hgb_sigmoid synthetic_250k             1.1            47.5            97.9             2.5            93.8       5
                                         lr_tuned    synthetic_250k             3.0            50.6            95.2             3.3            94.8       4
                                                     synthetic_50k              2.7            49.9            92.8             3.3            93.4       5
b2 b1 + income band                      lr_tuned    synthetic_250k             5.5            47.3            96.6             1.1            97.6       5
c b3 + recipe drivers (RECIPE-REVEALING) lr_tuned    synthetic_250k             7.8            55.2            96.5             1.2            97.1       4
```