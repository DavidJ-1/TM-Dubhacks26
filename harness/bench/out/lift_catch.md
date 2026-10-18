# Lift and churners caught, churn_90d (ALL SYNTHETIC)

Out-of-fold scores on 5,000 regular sandbox accounts (137 synthetic churners). Binary-rule ties broken at random (expected values). Dollars: see harness/model_c_artifacts/policy_eval.csv.

| k_label | targeting | churners_caught | share_of_churners | lift_vs_random | precision |
|---|---|---|---|---|---|
| top 250 | LR, all prepare() features | 58.0 | 42.3% | 8.47x | 23.2% |
| top 250 | LR on Model A core-22 | 63.0 | 46.0% | 9.20x | 25.2% |
| top 250 | Ours: Model A OOF (the churn model) | 62.0 | 45.3% | 9.05x | 24.8% |
| top 250 | 3+ contacts rule | 18.0 | 13.1% | 2.62x | 7.2% |
| top 250 | support_90d count ranking | 53.8 | 39.2% | 7.85x | 21.5% |
| top 250 | Random | 6.9 | 5.0% | 1.00x | 2.7% |
| top 250 | Oracle | 66.0 | 48.2% | 9.64x | 26.4% |
| top 500 | LR, all prepare() features | 74.0 | 54.0% | 5.40x | 14.8% |
| top 500 | LR on Model A core-22 | 79.0 | 57.7% | 5.77x | 15.8% |
| top 500 | Ours: Model A OOF (the churn model) | 85.0 | 62.0% | 6.20x | 17.0% |
| top 500 | 3+ contacts rule | 35.9 | 26.2% | 2.62x | 7.2% |
| top 500 | support_90d count ranking | 73.5 | 53.7% | 5.37x | 14.7% |
| top 500 | Random | 13.7 | 10.0% | 1.00x | 2.7% |
| top 500 | Oracle | 88.0 | 64.2% | 6.42x | 17.6% |
| top 1000 | LR, all prepare() features | 93.0 | 67.9% | 3.39x | 9.3% |
| top 1000 | LR on Model A core-22 | 107.0 | 78.1% | 3.91x | 10.7% |
| top 1000 | Ours: Model A OOF (the churn model) | 106.0 | 77.4% | 3.87x | 10.6% |
| top 1000 | 3+ contacts rule | 71.8 | 52.4% | 2.62x | 7.2% |
| top 1000 | support_90d count ranking | 94.4 | 68.9% | 3.45x | 9.4% |
| top 1000 | Random | 27.4 | 20.0% | 1.00x | 2.7% |
| top 1000 | Oracle | 108.0 | 78.8% | 3.94x | 10.8% |
| rule flags all (1462) | LR, all prepare() features | 108.0 | 78.8% | 2.70x | 7.4% |
| rule flags all (1462) | LR on Model A core-22 | 112.0 | 81.8% | 2.80x | 7.7% |
| rule flags all (1462) | Ours: Model A OOF (the churn model) | 112.0 | 81.8% | 2.80x | 7.7% |
| rule flags all (1462) | 3+ contacts rule | 105.0 | 76.6% | 2.62x | 7.2% |
| rule flags all (1462) | support_90d count ranking | 105.0 | 76.6% | 2.62x | 7.2% |
| rule flags all (1462) | Random | 40.1 | 29.2% | 1.00x | 2.7% |
| rule flags all (1462) | Oracle | 113.0 | 82.5% | 2.82x | 7.7% |


meta: {"n_accounts": 5000, "n_churners": 137, "rule_flag_count": 1462, "dollars": "not modelled here; see harness/model_c_artifacts/policy_eval.csv (the offer engine)"}
