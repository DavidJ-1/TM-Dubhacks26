# 5-fold CV bench (SYNTHETIC data, SYNTHETIC labels)

- harness/churn_features.prepare() (imported at run time); features=/workspace/tmobile/TM-Dubhacks26/harness/out/features.csv; labels=/workspace/tmobile/TM-Dubhacks26/harness/out/labels.csv
- regular accounts: 5000; personas held out: 42
- model features from prepare(): 58

## churn_90d (positives 137/5000, synthetic)

| model | roc_auc | auc_frac_of_oracle | fold_auc_sd | pr_auc | brier | ece10 | top10_capture | top10_lift | fit_s_median | infer_ms_per_1k_median |
|---|---|---|---|---|---|---|---|---|---|---|
| rule_support_90d_count | 0.8169 | 0.9456 | 0.0413 | 0.1552 | 0.0246 | 0.0014 | 0.5320 | 5.3201 | 0.002 | 0.135 |
| logreg_none | 0.8218 | 0.9513 | 0.0517 | 0.2165 | 0.0244 | 0.0083 | 0.5401 | 5.4015 | 0.028 | 1.862 |
| logreg_balanced | 0.8161 | 0.9447 | 0.0375 | 0.2213 | 0.1282 | 0.2284 | 0.5401 | 5.4015 | 0.034 | 1.774 |
| hgb | 0.8318 | 0.9629 | 0.0400 | 0.1798 | 0.0244 | 0.0060 | 0.5547 | 5.5474 | 0.102 | 3.194 |
| hgb_isotonic | 0.8292 | 0.9598 | 0.0267 | 0.1805 | 0.0242 | 0.0031 | 0.5839 | 5.8394 | 0.213 | 8.908 |
| hgb_sigmoid | 0.8241 | 0.9540 | 0.0295 | 0.1884 | 0.0241 | 0.0006 | 0.5839 | 5.8394 | 0.205 | 8.727 |
| logreg_none_rawcontacts | 0.8334 | 0.9647 | 0.0453 | 0.2074 | 0.0245 | 0.0091 | 0.5401 | 5.4015 | 0.030 | 1.841 |
| hgb_rawcontacts | 0.8241 | 0.9540 | 0.0460 | 0.1849 | 0.0245 | 0.0060 | 0.5766 | 5.7664 | 0.120 | 3.568 |
| oracle | 0.8639 | 1.0000 |  | 0.2909 | 0.0226 | 0.0030 | 0.6423 | 6.4234 | 0.000 | 0.000 |

Persona check (PROVISIONAL; high = >=90th pct, low = <50th): rule_support_90d_count 2/6, logreg_none 5/6, logreg_balanced 5/6, hgb 5/6, hgb_isotonic 5/6, hgb_sigmoid 5/6, logreg_none_rawcontacts 4/6, hgb_rawcontacts 5/6

## upgrade_90d (positives 322/5000, synthetic)

| model | roc_auc | auc_frac_of_oracle | fold_auc_sd | pr_auc | brier | ece10 | top10_capture | top10_lift | fit_s_median | infer_ms_per_1k_median |
|---|---|---|---|---|---|---|---|---|---|---|
| rule_near_cap | 0.6609 | 0.8183 | 0.0196 | 0.1177 | 0.0582 | 0.0047 | 0.1935 | 1.9354 | 0.002 | 0.262 |
| logreg_none | 0.7400 | 0.9162 | 0.0367 | 0.1845 | 0.0572 | 0.0139 | 0.2981 | 2.9814 | 0.025 | 1.742 |
| logreg_balanced | 0.7373 | 0.9128 | 0.0346 | 0.1766 | 0.1992 | 0.3190 | 0.2950 | 2.9503 | 0.029 | 1.754 |
| hgb | 0.7439 | 0.9210 | 0.0212 | 0.1718 | 0.0570 | 0.0019 | 0.3043 | 3.0435 | 0.095 | 3.071 |
| hgb_isotonic | 0.7422 | 0.9190 | 0.0277 | 0.1691 | 0.0572 | 0.0026 | 0.3137 | 3.1366 | 0.208 | 9.019 |
| hgb_sigmoid | 0.7471 | 0.9250 | 0.0263 | 0.1725 | 0.0570 | 0.0054 | 0.3075 | 3.0745 | 0.214 | 9.116 |
| logreg_none_rawcontacts | 0.7356 | 0.9107 | 0.0318 | 0.1797 | 0.0574 | 0.0157 | 0.2981 | 2.9814 | 0.029 | 1.901 |
| hgb_rawcontacts | 0.7429 | 0.9198 | 0.0210 | 0.1718 | 0.0570 | 0.0030 | 0.2981 | 2.9814 | 0.100 | 3.026 |
| oracle | 0.8077 | 1.0000 |  | 0.2662 | 0.0535 | 0.0051 | 0.3758 | 3.7578 | 0.000 | 0.000 |

Persona check (PROVISIONAL; high = >=90th pct, low = <50th): rule_near_cap 4/5, logreg_none 5/5, logreg_balanced 4/5, hgb 4/5, hgb_isotonic 5/5, hgb_sigmoid 4/5, logreg_none_rawcontacts 5/5, hgb_rawcontacts 4/5
