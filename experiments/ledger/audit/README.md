# Audit files behind the headline (all numbers synthetic)

Same 184-account policy and conservative costing as ledger_summary.json at 27c2870 (+$3,938).
Copied from scratch_models/adversary/out_final/; scripts alongside for reference.

| Claim | File | Row / key |
|---|---|---|
| Random accounts, same offers: mean -$2,311, best -$1,229, never beats us on average, 7.6% of single quarters | t2_falsification.csv | "random accounts, same offers" |
| Random top-10%-risk accounts: mean -$366, best +$582, 18.8% of single quarters | t2_falsification.csv | "random top-10%-risk accounts" |
| Shuffled churn labels (200 refits): ~10 contacts, +$50, never beats us | t2_falsification.csv | "label permutation" |
| Cross-fit (fit 4 folds, score 5th): 179 contacts, +$3,856 | t2_falsification.csv | "cross-fit LR" |
| Break-even 5.17%; CVaR bound -$7,099 | adversary_summary.json | breakeven.central, dro_cvar10 |
| Worst case in the reasonable box at 10%: -$4,793 | t1_worst_case.csv | |
| Robust A: 139 contacts, +$3,785 | t3_robust_policy.csv | |
| Do saves stick (own risk kept): -$1,307 at 10%, 36 of 184, break-even 14.5% (Q&A only) | saves_stick.json | |
