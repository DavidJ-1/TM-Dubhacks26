# Same assumptions, different strategies (simulated)

**All customers and numbers are synthetic/simulated. We don't claim real lift until a holdout test.**

## Headline

- Ours makes 639 contacts to low-risk customers (no credits: fix-first callbacks, money-saving plan moves, check-ins and usage-based upsells) vs 4,523 for discounting everyone and 978 for the 3+ calls rule, and spends $6,725 on credits vs $126,050 for discounting everyone.
- Ours reaches 92 of the 138 customers who actually churned in the simulation (67%) with 1,123 contacts; the 3+ calls rule reaches 105 with 1,466, score-only 88 with 504.
- Depends on assumed save rates: ~42 expected saves at $957 per save, 73% cheaper per save than a $25 credit to everyone, net $38,528 vs -$75,835.
- Model A puts 62% of actual churners in its top 10% (out-of-fold), vs 54% for ranking by support calls and 10% at random (AUC 0.85 vs 0.83).

## 1. Assumption-free metrics (5,042 synthetic accounts)

These depend only on who each strategy contacts: no assumed save rates. Low risk = Model A risk < 5%. Churners reached = contacted accounts that churned in the simulated labels (138 total).

| strategy | contacted | unneeded contacts (low risk) | credit / discount spend | actual churners reached |
|---|---:|---:|---:|---:|
| 1. Do nothing | 0 | 0 (0%) | $0 | 0 (0%) |
| 2. Discount everyone | 5,042 | 4,523 (90%) | $126,050 | 138 (100%) |
| 3. 3+ support calls rule | 1,466 | 978 (67%) | $36,650 | 105 (76%) |
| 4. Top 10% risk score only | 504 | 0 (0%) | $12,600 | 88 (64%) |
| 5. Ours (Model A + EV engine) | 1,123 | 639 (57%) | $6,725 | 92 (67%) |

## 2. Simulated value (depends on assumed save rates)

Assumed save rates (engine CONFIG, illustrative): $25 care credit 25% if billing/service pain else 5% (+5 pts after bill shock); ours also uses fix-first 35%/4%, right-size/variant 30%/10%, check-in 12%/4% (on/off target); value = 24 mo x 50% margin. Same for every strategy.

| strategy | expected saves | offer cost | cost per save | net expected value |
|---|---:|---:|---:|---:|
| 1. Do nothing | 0.0 | $0 | n/a | $0 |
| 2. Discount everyone | 35.0 | $126,050 | $3,598 | -$75,835 |
| 3. 3+ support calls rule | 28.3 | $36,650 | $1,295 | $12,273 |
| 4. Top 10% risk score only | 23.7 | $12,600 | $532 | $30,245 |
| 5. Ours (Model A + EV engine) | 41.8 | $39,992 | $957 | $38,528 |

### Truth check (still depends on assumed save rates): same picks, saves re-scored with the hidden simulated churn probability

| strategy | expected saves (true p) | cost per save (true p) | net value (true p) |
|---|---:|---:|---:|
| 1. Do nothing | 0.0 | n/a | $0 |
| 2. Discount everyone | 34.8 | $3,622 | -$75,557 |
| 3. 3+ support calls rule | 27.8 | $1,316 | $11,954 |
| 4. Top 10% risk score only | 22.9 | $549 | $29,350 |
| 5. Ours (Model A + EV engine) | 40.8 | $981 | $37,480 |

Ours also carries $66,929 of non-retention EV (upsell margin, lock-in value and customer-savings trust value) that is **not** included in net value above, to keep the comparison like-for-like.

Ours' 639 low-risk contacts by action: fix_first 198, step_up 152, right_size 112, variant_switch 90, check_in 67, family_upgrade 17, home_internet_bundle 3. None are credits (the engine blocks credits below 5% risk); upsells (step_up/family_upgrade/home_internet_bundle) are the ones a judge could call unneeded.

## Churn model lift (out-of-fold, 5-fold CV)

5,000 regular accounts, 137 actual churners in 90 days (base rate 2.7%).

| method | AUC | share of churners in top 10% | lift |
|---|---:|---:|---:|
| Model A (out-of-fold) | 0.853 | 62% | 6.2x |
| Support-call count (naive rule) | 0.834 | 54% | 5.4x |
| Random | 0.500 | 10% | 1.0x |
| Oracle: hidden true probability (ceiling) | 0.864 | 64% | 6.4x |

The literal 3+ calls rule flags 1,462 accounts (29%) and catches 77% of churners. Existing holdout backtest (harness/out/backtest_churn_churn_90d.md) agrees: model_a CV top-10% recall 60.6% vs 26.2% for rule_support3.

## How it's computed

- Expected saves = sum over contacted accounts of p_churn_90d (Model A) x save rate. Save value = that x customer value (24 months x 50% service margin), exactly as in the engine.
- Credit baselines (2-4) give the $25 care credit regardless of eligibility, with the engine's care-credit save rate per account (25% on target for billing/service pain, 5% off target, +5 pts after bill shock) and $3 contact/annoyance cost. Save-rate source: engine drivers() on sandbox facts (read-only).
- Ours uses the chosen row in offer_candidates.csv (save rate, offer cost, annoyance) for each account.
- Net value = saved margin - offer cost - contact/annoyance cost.
- Unneeded contact = contacted while Model A risk < 5% (the engine's MIN_CREDIT_P_CHURN).

## Caveats

- We don't claim real lift until a holdout test. Synthetic data; save rates and costs are made-up but consistent across strategies.
- Ours' offer cost includes expected revenue given back on plan moves (right-size/variant) and $15 callbacks; credit spend counts only bill credits.
- Churners reached is in-sample for strategies 4-5 (Model A was fit on these labels); the out-of-fold lift table below is the honest model comparison.
- Partly circular: ours is scored with the same assumptions it optimizes. The truth-check table and harness/out/policy_eval.csv (simulated 50k randomized trial) are the less-circular views.
- Model A scores are in-sample for the strategy table; lift uses out-of-fold scores.

Source: offers.csv rows 5,042; regenerate with `python3 harness/compare_strategies.py`.

## Cross-check: simulated 50k randomized trial (tm-offers' policy_eval.csv, test split, DR estimate)

| policy | contacted | churners saved | offer cost | cost per save | net value (no upsell) |
|---|---:|---:|---:|---:|---:|
| do nothing | 0 | 0.0 | $0 | n/a | $0 |
| random (eligible arm) | 5,887 | 77.0 | $118,233 | $1,534 | $25,117 |
| 3+ calls rule -> $25 care credit | 841 | 32.7 | $21,025 | $643 | $17,230 |
| offer to everyone (best eligible offer) | 10,660 | 123.8 | $205,635 | $1,660 | $21,289 |
| Model B EV chooser | 3,309 | 113.5 | $118,266 | $1,042 | $108,364 |
| Model C uplift policy | 3,197 | 93.0 | $50,546 | $544 | $116,590 |
| oracle (true effects; reference only) | 3,209 | 130.0 | $53,936 | $415 | $200,980 |
