# Model B: offer chooser and upgrade moments (tm-offers lane)

> **Every customer and every number here is synthetic or simulated.** The accounts, usage, bills and promotions
> come from the judge sandbox (`mageshkumarj/dubhacks`, all rows `data_source = 'stub'`). Save rates, annoyance
> costs and the value horizon are our own assumptions, not fitted on real outcomes. Nothing here is a real
> T-Mobile offer.

## Run
```bash
python harness/offers.py                    # writes harness/out/offers.csv and offer_candidates.csv
TM_ENABLE_RIGHT_SIZE=0 python harness/offers.py   # same run with right-sizing turned off
```
The sandbox is found at `$TM_SANDBOX_DB`, then `/workspace/tmobile/dubhacks/data/sandbox.db`. It is opened
**read-only** (`file:...?mode=ro`). A full run takes about 20 s.

## Inputs
| File | From | Use |
|---|---|---|
| `out/churn_scores.csv` | tm-churn (Model A) | `p_churn_90d`, `risk_rank`. If the file is missing, `out/mock_churn_scores.csv` is generated with the same columns (switch: `CONFIG["CHURN_SOURCE"]`, default `auto`). The `churn_source` column in the output says which was used. |
| `out/features.csv` | tm-data | Account-level facts for detectors and eligibility (39 mapped columns, `FEATURES_MAP` in `offer_detectors.py`). |
| `sandbox.db` | judge | `promotions` (amounts and eligibility rules), `plans` (line-price tables, caps, eligibility), plus the per-line facts features.csv lacks: per-line usage peak and hotspot (`usage_monthly`), paid-off or upgrade-ready lines (`lines`), bill-shock month (`billing_history`) and unresolved network contacts (`support_interactions`). |

## The score
```
EV(action) = p_churn_90d x save_rate x customer_value  [+ p_accept x upsell_gain]  - expected_offer_cost - annoyance
customer_value = (last bill - device installments) x SERVICE_MARGIN (0.50) x VALUE_HORIZON_MONTHS (24)
```
**"do nothing" has EV 0. It wins whenever every eligible action scores below 0.** The upsell term applies only to
step-up (extra plan revenue x 0.8 margin x 24 months x P(accept)) and to device upgrade ($80 device margin x
P(accept)). A device credit or a right-size saving counts as a cost only if the customer accepts.

The save rate depends on whether the action addresses the account's churn driver (`on_target`) or not
(`off_target`). Drivers are computed from real fields: billing pain, service or network pain, unresolved contacts,
shopping around (competitor score, port-out, cancel inquiry), device pain, overpaying, outgrowing the plan, a
life event, and whether the customer is free to leave (no financing).

## Actions and eligibility
| Action | Eligibility (source) | Cost (source) |
|---|---|---|
| do nothing | always | 0 |
| $25 care credit | `PROMO-STUB-CARE-CREDIT`: tenure >= 6 months, >= 3 support contacts in 90 days | $25 x 1 month (promo) |
| loyalty credit | `PROMO-STUB-LOYALTY-CREDIT`: tenure >= 36 months | $5/mo x 12 months (promo; 12 matches the sandbox API's horizon for ongoing credits) |
| keep-your-phone credit | **Adapted.** The real `PROMO-STUB-KEEP-YOUR-PHONE` is only for a new ported-in BYOD line on Essentials Saver, which no existing customer meets. We reuse its $20/mo value as a retention credit for households with no financing and a paid-off or BYOD phone. Set `STRICT_PROMO_RULES=True` to make it ineligible for everyone. | $20/mo x 6 months (synthetic length) |
| right-size plan | **Behind `ENABLE_RIGHT_SIZE` (default ON; open scope question).** The cheapest allowed plan (sandbox `plans.eligibility` vs `discount_group`, plus line limits) that fits every line's 3-month peak usage within 70% of its cap and covers hotspot use, and saves at least $10/mo. Households that fail the sandbox misfit rule (every line < 5 GB on a premium plan) may only move to a cheaper variant in the same family and tier. | lost revenue x 12 months x P(accept 0.6) |
| step-up plan | Outgrowing the plan (near or over the cap, usage up 30%+, hotspot use on Essentials), or graduating (life event) | none; the upsell gain is added |
| device upgrade | A line that is paid off, trade-in eligible and owned 12+ months (sandbox stub upgrade rule). Credit is the best real promo the account meets: `OLD-PHONE-UPGRADE` ($150, phone owned 36+ months) or `TRADEIN-ANY` ($200). | credit x P(accept 0.15) |
| fix-first callback | Unresolved contacts in 90 days, or 2+ network complaints | $15 agent time (synthetic) |
| $25 care credit + fix-first | Eligible for both. Save = 1 - (1 - fix rate)(1 - credit increment). The credit adds its full on-target rate only when there is billing pain, because a credit doesn't fix coverage. This follows the plan doc's demo line "the $25 care credit plus a network fix". | $25 + $15 |

### Guardrails
- **No upsell after bill shock.** Step-up and device upgrade are *ineligible* for `UPSELL_BLOCK_DAYS_AFTER_BILL_SHOCK`
  (90) days after a `promo_expired` bill or a month-over-month rise of 15% or more that a new phone's installment
  didn't cause. This matches the "no upsell after bill shock" rule from the plan doc's nextbest ladder.
- **Bill-shock relief (policy override, not a sandbox rule; config `BILL_SHOCK_RELIEF`).** In that same window
  the care credit's 3-contact minimum is lowered to 1 (tenure >= 6 still applies), and credits get +5 points
  of save rate.
- Upsells after unresolved issues carry an extra $25 annoyance penalty.
- Fix-first is only on-target for issues a callback can fix (network or device). For billing-only complaints its
  save rate is 0.15: a callback can explain a price rise but can't undo it.

## Upgrade-moment detectors (booleans in offers.csv)
| Flag | Real field(s) |
|---|---|
| `um_device_paid_off` | `billing_history.change_reason = installment_ended` in the last 3 months |
| `um_payoff_soon` | features `financing_ends_within_3m` (`lines.financing_months_remaining`) |
| `um_old_device` | features `n_lines_device_36m_plus` (`lines.device_purchase_date`) |
| `um_near_plan_limit` | per-line 3-month average >= 80% of `plans.data_cap_gb`, or over the cap |
| `um_over_plan_cap` | features `n_lines_over_cap_3m` |
| `um_usage_growth` | features `n_lines_usage_up_30pct` |
| `um_plan_overpay` | sandbox misfit rule (every line < 5 GB on premium) or a qualifying right-size plan exists |
| `um_promo_expired` | `billing_history.change_reason = promo_expired`, last 3 months. No future promo-end date exists in the data. |
| `um_student_graduating` | **heuristic**: `discount_group = student` and tenure >= 36 months. The data has no graduation field. |

## Outputs
- `out/offers.csv`: one row per account with `account_id, action, expected_value, reason` (one plain-English
  sentence), the runner-up and its EV, the `upgrade_moment` and `um_*` flags, the EV of every action, and
  `also_fix_first`, `bill_shock_recent`, `churn_source` and `data_note`.
- `out/offer_candidates.csv`: one row per account x action (9 actions, including do nothing and every ineligible
  action), with `eligible, expected_value, offer_cost, save_rate, annoyance, reason, is_chosen`. Exactly one
  `is_chosen` per account. The script asserts that it matches offers.csv.

No persona is hand-pinned. Every decision comes from the general rules and the config block at the top of
`offers.py`.

## Model C: uplift score and policy simulation (`harness/uplift.py`)
**One command rebuilds everything:** `python harness/uplift.py` writes offers.csv, offer_candidates.csv,
uplift.csv, policy_eval.csv, uplift_curve.csv, uplift_curve.png and policy_value.png, plus
offers_pipeline_run.json, which records the churn_scores.csv mtime used. If churn_scores.csv changes during the
run, the script rebuilds once more. PNGs need matplotlib; without it the script skips them and still writes the CSVs.

- `uplift_score = p_churn_90d x save_rate(best eligible retention action)`: the expected incremental save from
  contacting the customer ("persuadable and at risk", not risk alone; see Ascarza 2018 in the plan doc).
- `policy_eval.csv` compares no outreach, a blanket $25 care credit, the 3+ support calls rule, Model A's top 20%
  by risk, Model C's top N by uplift, and the Model B EV chooser. It reports simulated incremental saves,
  retained value, upsell gain, cost, annoyance and net value.
- `uplift_curve.csv` holds the Qini-style points (`policy_or_model, frac_targeted, cum_incremental_saves,
  random_baseline`, plus `cum_net_value_usd`).

**Circularity caveat (also printed under both charts):** there are no real offer outcomes. Policies are scored
with tm-data's synthetic `p_true_90d` labels multiplied by Model B's *own* assumed save rates, costs and
annoyance, so the simulation partly grades Model B against its own assumptions. It shows how each rule spends
contacts under those assumptions. It is not measured lift.
