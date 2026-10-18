# Scaling comparison: train on real 5k vs synthetic 50k vs synthetic 250k; test on the REAL 5k (ALL SYNTHETIC LABELS)

AUC minus oracle uses the oracle on exactly the same real rows; CI = paired stratified bootstrap 95% (2,000 resamples). A point above the ceiling with a CI that straddles 0 is noise (137 real churners).

| target | model | trained on | n train | AUC | fold sd | PR-AUC | top-10% | oracle AUC | AUC - oracle [95% CI] |
|---|---|---|---|---|---|---|---|---|---|
| churn_90d | logreg_core22 | real_5k (5-fold OOF) | 4,000 | 0.841 | 0.071 | 0.238 | 0.577 | 0.864 | -0.023 [-0.037, -0.010] |
| churn_90d | logreg_unweighted | real_5k (5-fold OOF) | 4,000 | 0.822 | 0.052 | 0.216 | 0.540 | 0.864 | -0.042 [-0.068, -0.017] |
| churn_90d | hgb_sigmoid | real_5k (5-fold OOF) | 4,000 | 0.824 | 0.030 | 0.188 | 0.584 | 0.864 | -0.040 [-0.062, -0.020] |
| upgrade_90d | logreg_unweighted | real_5k (5-fold OOF) | 4,000 | 0.740 | 0.037 | 0.185 | 0.298 | 0.808 | -0.068 [-0.085, -0.050] |
| upgrade_90d | hgb_sigmoid | real_5k (5-fold OOF) | 4,000 | 0.747 | 0.026 | 0.172 | 0.307 | 0.808 | -0.061 [-0.078, -0.044] |
| churn_90d | logreg_core22 | synthetic_50k | 50,000 | 0.865 |  | 0.290 | 0.620 | 0.864 | +0.001 [-0.003, +0.006] **above ceiling (noise if CI spans 0)** |
| churn_90d | logreg_unweighted | synthetic_50k | 50,000 | 0.869 |  | 0.292 | 0.620 | 0.864 | +0.005 [-0.003, +0.015] **above ceiling (noise if CI spans 0)** |
| churn_90d | hgb_sigmoid | synthetic_50k | 50,000 | 0.861 |  | 0.258 | 0.606 | 0.864 | -0.003 [-0.012, +0.005] |
| upgrade_90d | logreg_unweighted | synthetic_50k | 50,000 | 0.762 |  | 0.193 | 0.326 | 0.808 | -0.045 [-0.060, -0.031] |
| upgrade_90d | hgb_sigmoid | synthetic_50k | 50,000 | 0.769 |  | 0.210 | 0.323 | 0.808 | -0.039 [-0.053, -0.026] |
| churn_90d | logreg_core22 | synthetic_250k | 250,000 | 0.863 |  | 0.286 | 0.635 | 0.864 | -0.001 [-0.004, +0.001] |
| churn_90d | logreg_unweighted | synthetic_250k | 250,000 | 0.864 |  | 0.291 | 0.635 | 0.864 | +0.000 [-0.004, +0.005] **above ceiling (noise if CI spans 0)** |
| churn_90d | hgb_sigmoid | synthetic_250k | 250,000 | 0.864 |  | 0.266 | 0.613 | 0.864 | +0.000 [-0.007, +0.008] **above ceiling (noise if CI spans 0)** |
| upgrade_90d | logreg_unweighted | synthetic_250k | 250,000 | 0.765 |  | 0.197 | 0.317 | 0.808 | -0.043 [-0.057, -0.029] |
| upgrade_90d | hgb_sigmoid | synthetic_250k | 250,000 | 0.770 |  | 0.227 | 0.317 | 0.808 | -0.038 [-0.051, -0.025] |