# Features + uplift experiments (trend, household, device, signals): SYNTHETIC DATA AND LABELS
Run Sat 2026-10-17, about 8:36–8:42 PM PDT. Everything is in this folder. The repo, demo_data, harness/out and sandbox.db were opened read-only (sqlite `mode=ro`).

**Setup.** 5,000 regular accounts with 137 positives (2.74%). The folds are the exact harness folds (the `fold` column of
demo_data/churn_oof_pred.csv, i.e. StratifiedKFold(5, shuffle, seed 2026); they match ../folds.py). The model is the harness `ModelA`
(standardized L2 LR with C picked by CV and sign-prior pruning) fitted on CORE_FEATURES plus the new columns.
**The baseline reproduces exactly:** OOF AUC 0.8531, max |p diff| vs the harness OOF is 5e-7.
Bootstrap: 400 paired resamples of accounts. "Fold Δ" is the mean±sd of the per-fold paired (variant − baseline) deltas.

| Variant | AUC | ΔAUC 95% CI | PR-AUC | ΔPR CI | Top-10% capture | Δtop10 CI | fold Δtop10 | Brier | ECE | Call |
|---|---|---|---|---|---|---|---|---|---|---|
| **baseline LR** | 0.853 (CI 0.814–0.891, fold sd .036) | – | 0.255 | – | **62.0%** (54.5–70.2) | – | – | 0.0230 | 0.0040 | – |
| + trend (usage/bill/support deltas, slopes) | 0.860 | [−.002,+.015] | 0.271 | [−.007,+.032] | 62.8% | [−2.9,+3.3]pp | +0.0±2.6pp | 0.0229 | 0.0036 | noise |
| + household aggregates | 0.852 | [−.004,+.003] | 0.247 | **[−.016,−.003]** | 62.8% | [−3.1,+2.4]pp | 0.0±2.5pp | 0.0232 | 0.0027 | noise; PR-AUC slightly *worse* |
| + device/financing (payoff, paid-off share, promo months, single-product) | 0.853 | [−.006,+.005] | 0.255 | [−.019,+.016] | 61.3% | [−3.9,+1.5]pp | −1.4±2.0pp | 0.0231 | 0.0043 | noise |
| + signals (last mo vs prior 3, support 30d vs prior 60, tenure bucket, interactions) | 0.853 | [−.005,+.004] | 0.261 | [−.012,+.017] | 60.6% | [−5.0,+1.4]pp | −0.7±3.0pp | 0.0230 | 0.0036 | noise |
| + trend + household | 0.860 | [−.002,+.015] | 0.266 | [−.013,+.028] | 62.8% | [−3.8,+3.7]pp | +0.8±4.0pp | 0.0230 | 0.0043 | noise |
| + all new (trend+hh+device) | 0.861 | [−.001,+.017] | 0.264 | [−.016,+.027] | 61.3% | [−4.6,+2.7]pp | 0.0±2.6pp | 0.0230 | 0.0051 | noise |
| + all new + signals | 0.863 | **[+.0005,+.019]** | 0.269 | [−.011,+.030] | 61.3% | [−6.1,+2.3]pp | −0.7±3.1pp | 0.0230 | 0.0051 | AUC borderline (the CI barely clears 0 across 8 comparisons, so treat it as noise); top-10 noise |
| baseline minus port-out / competitor-research / cancel-inquiry (compliance) | 0.851 | [−.012,+.008] | 0.251 | [−.028,+.012] | **58.4%** | **[−7.8,−0.7]pp** | −2.9±5.3pp | 0.0233 | 0.0042 | **real loss** of ~3.6pp top-10 |

A 1-account change in top-10 capture is 0.73pp. Every top-10 difference here is within ±2 accounts (±1.5pp), except the compliance variant at −5 accounts.
ECE uses 10 equal-count bins, and all ECE deltas are inside per-fold sd (~0.002–0.003). Brier deltas are ≤0.0002, so calibration is unchanged.
Raw numbers: results.csv, oof_*.npy. Leakage: leakage_audit.csv. $ view: dollar_view.csv.

## Secondary view: rank by expected $ loss (p × last bill × 3) vs by probability (top 10%)
Baseline: by probability it captures 62.0% of churners and 65.2% of churner $; by expected $ loss it captures 57.7% of churners and 64.2% of churner $.
Ranking by $ trades about 4pp of churner count for no gain in $ captured. The noise band applies again, so don't switch on this evidence.

## Leakage audit (every new feature)
- **Time windows:** every source row is strictly before as_of 2026-10-01 (asserted in the code). Usage and billing run 2025-10..2026-09 and support runs 2026-01-04..2026-09-30.
  The 90-day label window is after as_of, so there is no label-window activity.
- **Single-feature AUC:** none is above 0.95 (no red flag). The highest are tr_support_delta_90v90 at 0.83 and tr_support_slope9 at 0.83.
  Both correlate 0.77–0.79 with existing core support features. That isn't leakage, but there is a **circularity caveat**: the synthetic label formula
  (harness/labels.py) uses `support_90d`, which is *not* in CORE_FEATURES. The support-trend features mostly re-supply that term,
  and that is the likely source of the +0.006 AUC from trend. The gain is "real" only with respect to our own label recipe.
- **Near-duplicates:** hh_n_lines is the same as core n_lines/extra_lines (corr 1.0, which adds nothing), and sg_tenure_bucket has corr 0.94 with tenure. No total-charges-style
  (tenure × monthly) aggregate was built.
- **Constant or near-empty features in the stub data:** the usage "went quiet" flag is 0 for everyone (dropped), tr_usage_drop30 is set for 0.08% of accounts, and the line-level usage-drop share is 0.2%.
  **The sandbox usage is essentially flat, so usage-drop signals can't show value on this data.**

## Household grouping / fold leakage
The account is the household. Each account_id is one row, line_id is unique, and there is no cross-account household or family id in the sandbox.
The existing account-level StratifiedKFold is therefore already grouped by household, and GroupKFold(household) would give the same partition structure. No extra run was needed, and no cross-fold leakage was found.
Not buildable (no source data): other lines' churn before cutoff (no line-level churn history), OOF max line risk (no line-level labels),
share of new lines (no line activation date; device_purchase_date ≠ line add date).

## Compliance (CPNI / protected attributes)
- **Already in the baseline CORE_FEATURES and flagged:** `port_out_inquiry` (porting request), `competitor_research_score` (competitor-contact proxy),
  `cancel_inquiries_270d` (a cancellation / retention-call signal). Removing them costs about 3.6pp of top-10 capture (real, CI excludes 0). That is a product and legal decision for David.
- **Present in the data but not used by the churn model:** `segment` (has "senior"), `discount_group` ("55_plus"), `language`, line `member_role`
  (child/teen/senior, which are age proxies), and enrichment income / area-median-income (geo proxy). I dropped my `hh_n_roles` feature because it was built from member_role.
- None of my new features use porting, competitor, location, or protected fields.

## Uplift / persuadability (task 5): not built
The sandbox has **no real treatment signal.** `promotions` is a catalog of eligibility rules, and billing `promo_expired` / `installment_ended` are
bill events, not offers we made. There are no contact or offer logs and no outcomes. The repo's Model C uses a *simulated* trial, which is circular per its own README, so
following research guidance I did NOT build an uplift model as evidence. **Uplift-ready data spec:**
1. Log every offer decision per account: timestamp, model score and version, eligible arms, the chosen arm, channel, and whether it was delivered or opened.
2. A random holdout of 5–10% of eligible accounts gets no offer (our design choice), with propensity logged. Arm assignment within the treated group can also be randomized.
3. An outcome window of about 60 days post-offer (churn, port-out, accept/upgrade, and margin), with a pre-registered cutoff and no peeking.
4. Evaluate with Qini/AUUC plus bootstrap CIs and uplift at 10% against the plain risk ranking as benchmark. A plain churn model beat uplift models on
   Orange Belgium's randomized telecom data (arXiv, Dec 2023).
5. With a small holdout, prefer an X-learner. Class transformation assumes a 50/50 split, so it doesn't fit 5–10%.
Sizing: at 2.7% churn, a 10% holdout of 5k is about 14 churners, far too few. Uplift needs a much larger population or a pooled run over several months.

## Data gaps
No late or missed payment records. No overage charges (billing change_reason only has installment/promo/stable). No line activation dates,
no line-level churn history, no offer/contact logs. **Seasonality (Q4) is ignored:** there is a single as_of snapshot and one label window, so there is nothing to fit seasonality on.

## Recommendation
Keep the baseline LR for the demo. No new feature family moves top-10% capture beyond fold noise (all within about ±2 accounts). The AUC bumps from
support-trend features (+0.006–0.010) are borderline and mostly re-learn a term of our own synthetic label formula, so they're not worth claiming.
If one addition is wanted for the narrative, use the support-trend pair (tr_support_delta_90v90, tr_support_slope9). It's interpretable and leak-free,
but present it as "no significant change." The bigger open issue is compliance: three baseline features are porting, competitor, or cancel signals, and removing them is
a real ~3.6pp top-10 loss. Uplift waits on a logged randomized holdout as specified above.

Scripts: build_features.py, build_device.py, build_signals.py, evaluate.py (`python3 evaluate.py oof <variant>` then `python3 evaluate.py`).
