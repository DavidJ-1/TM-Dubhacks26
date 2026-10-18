# Upgrade model improvement (ALL SYNTHETIC)

Target upgrade_90d, 322/5000 positives on the real sandbox accounts; oracle AUC on the same rows 0.808, PR-AUC 0.266, top-10% 0.376.

| tier | model | trained on | AUC | fold sd | PR-AUC | top-10% | gap to oracle | personas (5) |
|---|---|---|---|---|---|---|---|---|
| a0 prepare() only (baseline) | lr_tuned | real_5k (5-fold OOF) | 0.736 | 0.032 | 0.181 | 0.301 | +0.071 | 5/5 |
| a0 prepare() only (baseline) | hgb_sigmoid | real_5k (5-fold OOF) | 0.747 | 0.026 | 0.172 | 0.307 | +0.061 |  |
| a0 prepare() only (baseline) | hgb_tuned | real_5k (5-fold OOF) | 0.740 | 0.025 | 0.179 | 0.292 | +0.068 | 4/5 |
| a0 prepare() only (baseline) | lr_tuned | synthetic_50k -> real 5k | 0.762 |  | 0.194 | 0.317 | +0.046 |  |
| a0 prepare() only (baseline) | hgb_tuned | synthetic_50k -> real 5k | 0.763 |  | 0.209 | 0.320 | +0.045 |  |
| a0 prepare() only (baseline) | lr_tuned | synthetic_250k -> real 5k | 0.765 |  | 0.196 | 0.307 | +0.043 |  |
| a0 prepare() only (baseline) | hgb_tuned | synthetic_250k -> real 5k | 0.767 |  | 0.215 | 0.321 | +0.041 |  |
| a features.csv + domain | lr_tuned | real_5k (5-fold OOF) | 0.747 | 0.032 | 0.203 | 0.345 | +0.061 | 5/5 |
| a features.csv + domain | lr_interactions | real_5k (5-fold OOF) | 0.749 | 0.021 | 0.206 | 0.357 | +0.059 |  |
| a features.csv + domain | hgb_sigmoid | real_5k (5-fold OOF) | 0.753 | 0.025 | 0.185 | 0.329 | +0.055 |  |
| a features.csv + domain | hgb_tuned | real_5k (5-fold OOF) | 0.744 | 0.029 | 0.178 | 0.314 | +0.063 | 4/5 |
| a features.csv + domain | lr_tuned | synthetic_50k -> real 5k | 0.771 |  | 0.231 | 0.360 | +0.037 |  |
| a features.csv + domain | hgb_tuned | synthetic_50k -> real 5k | 0.769 |  | 0.231 | 0.360 | +0.039 |  |
| a features.csv + domain | lr_tuned | synthetic_250k -> real 5k | 0.775 |  | 0.236 | 0.363 | +0.033 |  |
| a features.csv + domain | hgb_tuned | synthetic_250k -> real 5k | 0.772 |  | 0.234 | 0.363 | +0.035 |  |
| b1 a + job change | lr_tuned | real_5k (5-fold OOF) | 0.746 | 0.033 | 0.202 | 0.345 | +0.062 | 5/5 |
| b1 a + job change | lr_interactions | real_5k (5-fold OOF) | 0.748 | 0.022 | 0.206 | 0.357 | +0.060 |  |
| b1 a + job change | hgb_sigmoid | real_5k (5-fold OOF) | 0.753 | 0.025 | 0.185 | 0.332 | +0.055 |  |
| b1 a + job change | hgb_tuned | real_5k (5-fold OOF) | 0.747 | 0.029 | 0.179 | 0.317 | +0.061 | 4/5 |
| b1 a + job change | lr_tuned | synthetic_50k -> real 5k | 0.771 |  | 0.232 | 0.360 | +0.037 |  |
| b1 a + job change | hgb_tuned | synthetic_50k -> real 5k | 0.773 |  | 0.249 | 0.357 | +0.034 |  |
| b1 a + job change | lr_tuned | synthetic_250k -> real 5k | 0.775 |  | 0.236 | 0.363 | +0.033 |  |
| b1 a + job change | hgb_tuned | synthetic_250k -> real 5k | 0.776 |  | 0.242 | 0.370 | +0.032 |  |
| b2 b1 + income band | lr_tuned | real_5k (5-fold OOF) | 0.771 | 0.035 | 0.226 | 0.357 | +0.037 | 5/5 |
| b2 b1 + income band | lr_interactions | real_5k (5-fold OOF) | 0.766 | 0.025 | 0.218 | 0.357 | +0.042 |  |
| b2 b1 + income band | hgb_sigmoid | real_5k (5-fold OOF) | 0.772 | 0.029 | 0.210 | 0.363 | +0.035 |  |
| b2 b1 + income band | hgb_tuned | real_5k (5-fold OOF) | 0.766 | 0.027 | 0.194 | 0.357 | +0.041 | 4/5 |
| b2 b1 + income band | lr_tuned | synthetic_50k -> real 5k | 0.796 |  | 0.250 | 0.391 | +0.011 |  |
| b2 b1 + income band | hgb_tuned | synthetic_50k -> real 5k | 0.785 |  | 0.249 | 0.385 | +0.023 |  |
| b2 b1 + income band | lr_tuned | synthetic_250k -> real 5k | 0.800 |  | 0.255 | 0.379 | +0.008 |  |
| b2 b1 + income band | hgb_tuned | synthetic_250k -> real 5k | 0.791 |  | 0.257 | 0.391 | +0.017 |  |
| b3 b2 + household (family/kids/promo) | lr_tuned | real_5k (5-fold OOF) | 0.770 | 0.036 | 0.227 | 0.357 | +0.037 | 5/5 |
| b3 b2 + household (family/kids/promo) | lr_interactions | real_5k (5-fold OOF) | 0.765 | 0.026 | 0.218 | 0.366 | +0.043 |  |
| b3 b2 + household (family/kids/promo) | hgb_sigmoid | real_5k (5-fold OOF) | 0.773 | 0.030 | 0.206 | 0.373 | +0.035 |  |
| b3 b2 + household (family/kids/promo) | hgb_tuned | real_5k (5-fold OOF) | 0.762 | 0.031 | 0.194 | 0.373 | +0.046 | 4/5 |
| b3 b2 + household (family/kids/promo) | lr_tuned | synthetic_50k -> real 5k | 0.795 |  | 0.249 | 0.398 | +0.013 |  |
| b3 b2 + household (family/kids/promo) | hgb_tuned | synthetic_50k -> real 5k | 0.785 |  | 0.247 | 0.385 | +0.023 |  |
| b3 b2 + household (family/kids/promo) | lr_tuned | synthetic_250k -> real 5k | 0.799 |  | 0.255 | 0.385 | +0.008 |  |
| b3 b2 + household (family/kids/promo) | hgb_tuned | synthetic_250k -> real 5k | 0.791 |  | 0.257 | 0.391 | +0.017 |  |
| c b3 + recipe drivers (RECIPE-REVEALING) | lr_tuned | real_5k (5-fold OOF) | 0.777 | 0.034 | 0.231 | 0.357 | +0.030 | 5/5 |
| c b3 + recipe drivers (RECIPE-REVEALING) | lr_interactions | real_5k (5-fold OOF) | 0.772 | 0.022 | 0.226 | 0.373 | +0.035 |  |
| c b3 + recipe drivers (RECIPE-REVEALING) | hgb_sigmoid | real_5k (5-fold OOF) | 0.775 | 0.027 | 0.212 | 0.363 | +0.032 |  |
| c b3 + recipe drivers (RECIPE-REVEALING) | hgb_tuned | real_5k (5-fold OOF) | 0.764 | 0.024 | 0.203 | 0.348 | +0.044 | 4/5 |
| c b3 + recipe drivers (RECIPE-REVEALING) | lr_tuned | synthetic_50k -> real 5k | 0.802 |  | 0.255 | 0.407 | +0.006 |  |
| c b3 + recipe drivers (RECIPE-REVEALING) | hgb_tuned | synthetic_50k -> real 5k | 0.787 |  | 0.251 | 0.385 | +0.021 |  |
| c b3 + recipe drivers (RECIPE-REVEALING) | lr_tuned | synthetic_250k -> real 5k | 0.805 |  | 0.260 | 0.388 | +0.003 |  |
| c b3 + recipe drivers (RECIPE-REVEALING) | hgb_tuned | synthetic_250k -> real 5k | 0.792 |  | 0.260 | 0.413 | +0.015 |  |

Persona percentiles (refit on all 5,000; high = 25/28 must be >= 90th pct, low = 22/24/27 < 50th):

account_id                                          ACC-PERSONA-22  ACC-PERSONA-24  ACC-PERSONA-25  ACC-PERSONA-27  ACC-PERSONA-28
tier                                     model                                                                                    
a features.csv + domain                  hgb_tuned             0.9            52.9            94.7             3.4            98.3
                                         lr_tuned              1.5            47.4            97.6             5.6            96.2
a0 prepare() only (baseline)             hgb_tuned             2.8            52.3            94.9             3.5            92.1
                                         lr_tuned              1.6            48.7            93.5             5.7            93.0
b1 a + job change                        hgb_tuned             0.9            52.9            94.7             3.4            98.3
                                         lr_tuned              1.5            47.6            97.6             5.9            96.3
b2 b1 + income band                      hgb_tuned             0.3            62.6            90.6             2.3            98.9
                                         lr_tuned              3.1            38.0            98.2             2.4            98.4
b3 b2 + household (family/kids/promo)    hgb_tuned             2.6            56.5            91.4             5.2            97.5
                                         lr_tuned              3.2            38.0            98.2             2.4            98.4
c b3 + recipe drivers (RECIPE-REVEALING) hgb_tuned             4.0            60.9            96.0             2.5            98.8
                                         lr_tuned              5.2            46.7            98.4             1.7            98.1