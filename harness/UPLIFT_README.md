# Model C: simulated randomized trial, T-learner uplift, offline policy evaluation

> **SYNTHETIC.** The customers come from the judge sandbox, and the trial, outcomes and "true" effects are our own
> simulation. **Circularity caveat:** the hidden true effects are built from our save-rate assumptions and the
> sandbox promo rules, so this validates the method end to end, not real-world lift. No real offer outcomes exist.

## Run
```bash
python harness/uplift.py              # rebuilds offers.csv, offer_candidates.csv, uplift.csv, policy_eval.csv,
                                      # uplift_curve.csv, uplift_auuc.csv, out/charts/*.png, model_c_artifacts/
TM_TRIAL_REPLICATES=1 python harness/uplift.py   # a single trial cohort (underpowered; see caveats)
```
A run takes about 40 s. If `out/churn_scores.csv` changes during the run, the script rebuilds once more.
`out/offers_pipeline_run.json` records the churn_scores mtime used.
**Dependency:** the PNGs need `matplotlib`, which is not in the shared `requirements.txt` (that file isn't owned by
this lane). Add `matplotlib>=3.8` there or use `/workspace/tmobile/harness/.venv`. Without it the script still
writes every CSV and skips the PNGs.

## Method
1. **Arms and eligibility.** There are 9 arms: do nothing plus Model B's 8 actions, including the combined
   credit + fix. Eligibility comes from Model B's sandbox promo rules.
2. **Randomized trial.** `assign_arms` picks one eligible arm per account uniformly at random, so propensity =
   1 / number of eligible arms. The trial runs `TRIAL_REPLICATES` = 20 times: independent re-randomized cohorts of
   the same 5,042 accounts, with fresh assignments and outcome draws. Estimates are reported per test split.
3. **Hidden truth** (`true_effects`, deliberately not Model B's EV formula). Each arm saves a share of would-be
   churners. The share depends on:
   - problem match (network, unresolved, billing or bill shock, usage or life event, device, overpay)
   - tenure (×0.8–1.2) and value (credits work less well for high-value households)
   - backfires (an upsell within the bill-shock window)
   - lognormal multiplicative noise plus additive noise
   - a "sleeping dog" penalty for contacting low-risk customers who have no matching problem

   The effect is `true_uplift = p_churn_90d × share`, clipped. The outcome is
   `outcome_stay_90d ~ Bernoulli(1 − p_churn_90d + true_uplift)`.
4. **T-learner.** One `StandardScaler + LogisticRegression(C=0.3)` per arm, trained on the 70% train split
   (seeded) with the features.csv numeric and one-hot features plus `p_churn_90d`. Arms with fewer than 40 treated
   train rows fall back to the do-nothing model plus a shrunk mean shift; with K=20 no arm needs the fallback.
   `uplift_hat = P(stay|arm) − P(stay|do nothing)` and
   `net_value_hat = uplift_hat × value + upsell − cost − annoyance`, using Model B's value, cost and annoyance terms.
5. **Policies** are evaluated on the test split:
   - Model B EV
   - Model C uplift (argmax of net_value_hat, do nothing if ≤ 0)
   - offer to everyone (best eligible offer by Model B EV)
   - the 3+ calls rule (care credit)
   - random eligible arm
   - do nothing
   - the true-effect oracle (reference only)

   Estimators are self-normalized IPW and doubly robust (DR, with the T-learner as the outcome model). Metrics are
   churners saved, net value with and without upsell revenue, and cost per save. The `true_*` columns use the
   hidden effects.
6. **Qini** on the test split. Each model ranks accounts and names one arm per account. The curve is the IPW
   estimate of incremental saves from treating the top k,
   `Σ [1(A=do nothing)·churn/e − 1(A=arm)·churn/e]`, with the same ranking valued on the hidden truth in extra
   columns. AUUC is the mean gap between each curve and its random baseline (`uplift_auuc.csv`).

## Schemas
**`out/uplift.csv`** has one row per account × eligible action, in this column order:
`account_id, action, split, treated, propensity, outcome_stay_90d, uplift_hat, net_value_hat, true_uplift,
pick_uplift, pick_ev, synthetic`
- `treated` and `outcome_stay_90d` come from the first trial cohort; the outcome is filled only on the treated row.
- `uplift_hat` and `net_value_hat` are filled for all rows. Only `split = test` rows are out-of-sample.
- `pick_uplift` is the Model C pick (it may be do nothing); `pick_ev` is the Model B pick from offers.csv.

**`out/policy_eval.csv`** columns: `policy, n_test_accounts, trial_replicates, n_contacted, offer_cost_usd,`
`churners_saved_{ipw,dr}, net_value_no_upsell_{ipw,dr}_usd, net_value_with_upsell_{ipw,dr}_usd,
cost_per_save_{ipw,dr}_usd, true_churners_saved, true_net_value_{no,with}_upsell_usd, true_cost_per_save_usd,
data_note`. Net value is 24-month margin minus offer cost, versus do nothing, with annoyance excluded.

**`out/uplift_curve.csv`** columns: `policy_or_model, frac_targeted, cum_incremental_saves, random_baseline`, then
the extras `cum_true_incremental_saves, true_random_baseline, data_note`.

**Charts:** `out/charts/uplift_curve.png` and `out/charts/policy_value.png`, each with the synthetic +
circularity footnote. Committed deck copies of the PNGs and CSVs are in `harness/model_c_artifacts/`.

## Pure functions (`harness/uplift.py`)
```python
eligible_arms(details) -> dict[account_id, list[arm]]
assign_arms(elig, seed) -> DataFrame[account_id, arm, propensity]
true_save_share(arm, drivers, tenure, value_z) -> float
true_effects(details, p_churn, tenure, seed) -> DataFrame[account_id, arm, true_uplift]
simulate_outcomes(assign, truth, p_churn, seed) -> DataFrame[..., outcome_stay_90d]
split_accounts(ids, train_frac, seed) -> Series[account_id -> 'train'|'test']
build_X(features, p_churn) -> DataFrame
fit_t_learner(X, trial, train_ids) -> dict[arm -> model info]
predict_stay(models, X, arm) -> ndarray
make_policies(long, offers, facts) -> dict[name -> Series(account_id -> arm)]
ope(policy, test, long_test, reps) -> dict          # IPW (self-normalized) + DR
policy_table(policies, test, long_test, reps) -> DataFrame
qini_curves(test, long_test, offers, facts, reps) -> DataFrame
auuc_table(curve) -> DataFrame
```
