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
The sandbox is found at `$DUBHACKS_DB` (the project-wide DB variable), then `vendor/dubhacks/data/sandbox.db`
(`make setup`), then a sibling `../dubhacks/data/sandbox.db` clone. It is opened
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

## SMS messages (`offer_messages.py`, columns `message_en`, `message_es`, `message_status`)
These are deterministic templates, not LLM output. Each message is under 300 characters (current maximum: about 250).
- It names the top risk reason in plain words with real values (for example "your promo ended and your bill
  went up 22%"), preferring the reason that the chosen action addresses.
- It offers **only the chosen action**. Every dollar amount comes from the sandbox: care credit $25
  (`PROMO-STUB-CARE-CREDIT`), loyalty $5/mo (`PROMO-STUB-LOYALTY-CREDIT`), device credits (`OLD-PHONE-UPGRADE` $150 or
  `TRADEIN-ANY` $200, with their payout months), and plan price differences computed from `plans.line_prices`.
- do nothing gets a blank message (`no_contact`). Fix-first gets a callback-to-fix note with no discount.
- **Keep-your-phone is never messaged.** The adapted credit is not a sandbox promo for existing customers, so it
  gets a blank message with `message_status = suppressed_adapted_promo`. Under `STRICT_PROMO_RULES=True` it is
  never chosen.
- Every message is synthetic: no names ("Hi there" / "Hola") and no phone numbers. Spanish uses *usted* throughout.
- **Validator:** `validate_messages()` re-derives every allowed amount from the sandbox tables and checks for
  length, phone-number-like text, and dollar amounts in fix-first messages. Results go to
  `out/message_validation.csv`, and the pass count is printed on every run.

## Model C
See `UPLIFT_README.md`. `python harness/uplift.py` is the single command that rebuilds Model B and Model C.

## Batch 4-6 additions (Sat 10/17 ~8:10 PM PDT; all numbers synthetic)

**New actions:** `variant_switch` (55+/partner/community discount variant or Essentials 4-Line Offer: same features,
cheaper; sandbox `plans.eligibility` == `accounts.discount_group`), `right_size` now = move DOWN only (sandbox misfit
<5 GB/line, or Beyond with every line <15 GB and <2 GB hotspot, no connected lines, no streaming add-on or Home
Internet -> More), `family_upgrade` (next plan + PROMO-STUB-TRADEIN-ANY $200/phone over 36 months; real fields only:
child/teen line roles, n_lines, phones with trade-in value after balance, a real moment), `bill_shock_price_lock`
(label "bill-shock relief": More/Beyond only, $25 care credit [+ $5/mo loyalty at 36+ mo], the 5-Year Price Guarantee
stated as a fact, no lock-in), `check_in` (no $; shopping / port-out / quiet app use, nothing open), `perk_reminder`
(no $, no brand names), `home_internet_bundle` (HINT Basic $50 + PROMO-STUB-BUNDLE-HINT $15).

**Customer-benefit term:** customer-first actions add `CUSTOMER_BENEFIT_WEIGHT x savings x 12 x p_accept` and count
lost margin x (1 - W) (W = 0.5). `SAME_COVERAGE_RULE`: an eligible same-features variant beats do-nothing, upsells,
check-ins and cross-sells (problem-solving actions still win).

**Lock-in value** (`lock_value()`): only from new promo-credit payout / financing months. Spec formula multiplied the
survival gap at month L by 24 months of margin; corrected to the sum of monthly survival gaps over the 24-month
horizon, cut active only beyond the lock the customer already has (`contract_or_financing_months_remaining`).
`action_if_lock_not_netted` shows the pick without netting. Model A already uses financing features, so no extra
switching-cost adjustment to p_churn.

**Guardrails:** no bill credits when p_churn_90d < 5%; upsells blocked within 90 days of bill shock, with an open
support issue, when a cheaper eligible variant exists, when the top driver is shopping/port-out (port-out inquiry or
risk >= 5%), or when the increase is > 25% of the current bill (40% if a line is already over its cap). Never income.
`ENRICHMENT_IN_DECISIONS` is permanently False (tm-strategy A/B): income / job change / kid age band / likely_kid_flag
appear only in `drivers` as `enrichment(simulated)[not used]`.

**Upgrade gate** (`upgrade_gate.py`): device / family upgrade only for accounts in the top 15% of tm-bench's NO-INCOME
upgrade model (tier "a features.csv + domain", lr_tuned, trained on synthetic 250k; bench top-15% capture 44%).
`TM_UPGRADE_GATE=0` drops it. `BILL_SHOCK_RELIEF_OVERRIDE` (default True, OPEN DECISION) is the one switch for the
care-credit 1-contact relief (`TM_BILL_SHOCK_RELIEF_OVERRIDE=0`).

**Texts:** no "We noticed"; upsells carry "Happy as is? No need to do anything."; downgrades list what you give up;
guarantee only as "covered by your 5-Year Price Guarantee" on a plan that has it; device credits as bill credits over
payout months; graduation is never a trigger or in text. Validator blocklist (word-prefix regex, en + es): school,
graduat, job, promot, income, kid, child, competitor, switch, port, AutoPay, public-only offers, "lock", "guaranteed
for N years", "we noticed".

**New outputs:** offers.csv adds `segment` (offer segment), `why_this_offer` (customer-facing), `lock_in_months`,
`drivers`, `promo_skus`, `upgrade_pct`, `upgrade_candidate`, `action_if_lock_not_netted`; offer_candidates.csv adds
`rank, action_code, save_value, upsell_gain, customer_benefit, lock_value, lock_in_months, promo_skus,
blocked_or_ineligible_reason`; `out/line_tradein.csv` (per-line now-vs-wait); `out/upgrade_scores.csv`.
Persona golden tests: `tests/test_persona_golden.py` (42 personas).

## Batch 7 (Sat 10/17 ~8:50 PM PDT; all numbers synthetic)
- **Upsells need a usage reason.** Step-up / family upgrade only when a line is near or over its data cap, or uses
  hotspot the plan lacks (Essentials: any; More: > 45 GB). Usage growth alone no longer triggers (removes the
  More -> Beyond "250 GB hotspot" pitches).
- **Family upgrade unbundled.** It is the plan move only (family plan + real child/teen line + usage need); the
  TRADEIN-ANY credit is never bundled. A phone trade-in stays a separate `device_upgrade` option. On those accounts
  the family upgrade replaces the generic step-up.
- **Savings ladder gaps closed** (`right_size` kinds in `action_detail`): `more_to_4line` (4+ lines on standard More,
  no hotspot / perks / connected lines / Home Internet, every line fits 50 GB -> Essentials 4 Line Offer, persona 37
  -$100/mo) and `essentials_saver` (1-2 light lines, every line's peak <= 10 GB -> Essentials Saver, persona 08
  -$10/mo). Texts list what the customer gives up (hotspot, 5-Year Price Guarantee, watch/tablet lines, line limit).
  No right-size while a support ticket or network issue is open (fix first; it is marketing).
- **Port-out floor.** A port-out inquiry never gets do nothing: check-in, or the fix-first callback when a ticket is
  open (`pick_override = port_out`). `PORT_OUT_ALWAYS_CONTACT` switch.
- **Honest do-nothing reasons** (`do_nothing_reason` code + `why_this_offer` sentence, real fields only): open_ticket
  ("Open ticket with support; no marketing until it's closed."), wait_payoff (only when a line has line_tradein's
  wait_until_payoff verdict and nothing stronger applies), low_risk ("Risk is low and nothing needs fixing"),
  bill_shock_low_risk, shopping_low_risk, recent_complaints, usage_need_held, happy (built from support / port-out /
  app fields, e.g. persona 24), nothing_helps.
- **offer_candidates.csv:** every allowed-but-losing option's `reason` now starts with a plain "Lost: ..." sentence;
  new `customer_monthly_delta` ($/mo change for the customer if accepted; negative = saves; persona 38 = -40).
  Existing columns unchanged.
- **offers.csv:** `segment` renamed `offer_segment`; new `do_nothing_reason`, `pick_override`, `customer_monthly_delta`.
- `upgrade_gate.load()` falls back to `$TM_OUT_DIR` then `demo_data/upgrade_scores.csv` (refresh.py copies it).
- `offers.prepare()` builds the scored frame (main() uses it); `offer_api._engine()` mirrors it (adds `n_wait_lines`).
- Tests: golden pins (exact action + SKU) for personas 04, 06, 10, 19, 21, 24, 28, 37, 38; persona 38's -$40/mo;
  persona 24's reason; wait personas 29/31/33; open-ticket wording; offer_api toggles for persona 21. Golden tests read
  `demo_data/` when `harness/out/` is missing.

## v2 #3: honest acceptance + upsell guardrails (Sat 10/17 ~10:45 PM PDT; branch tm-offers-v2; all numbers synthetic)
- **Honest upsell acceptance.** `P_ACCEPT` step_up / device_upgrade / family_upgrade 0.25 / 0.15 / 0.20 -> **0.04**.
  No carrier publishes offer-acceptance rates; the closest real figures are overall postpaid upgrade rates (AT&T
  3.0-4.7%/quarter, Verizon 2.6% 2Q26), which include organic upgrades, so 4% is a **ceiling**, not a measured
  effect. right_size 0.45 -> **0.03** (cited trials 1-13%: Ascarza 2016 Table 4, Ofgem CMOL/CMOC; range 0.02-0.13).
  variant_switch 0.70 -> **0.10** (customer has to act; Ascarza 2016 1.5%, Ofgem 2017 3.4%, Ofgem 2018 collective
  switch 27% upper; range 0.03-0.27; still forced by SAME_COVERAGE_RULE). home_internet_bundle 0.04 stays uncited.
  Effect: chosen-upsell gain $24.9k -> $4.5k; the action mix does not change (upsells cost nothing but annoyance).
- **Upsell risk guardrail** (`UPSELL_RISK_GUARDRAIL`, default ON; env `TM_UPSELL_RISK_GUARDRAIL=0`): no step-up,
  device / family upgrade or Home Internet bundle for the top churn decile (by p_churn_90d) or 3+ support contacts in
  90 days. why_not: "upsell guardrail: they are in our highest-risk 10% ..." / "... contacted support N times ...".
- **Right-size backfire** (`RIGHT_SIZE_BACKFIRE`): Ascarza, Iyengar & Schleicher 2016 (JMR 53(1):46-60; churn 6% ->
  10% after proactive cheaper-plan outreach) as a relative +66.7% churn penalty netted into right_size's save rate
  (net -0.37 on target). Accounts with volatile (CV > 0.25) or declining (last 3 mo < 0.8x first 3) monthly data use
  are excluded outright (14 accounts in the sandbox). Result: right-size never beats silence at scale >= ~0.45;
  held accounts get do_nothing_reason `plan_fit_held` ("They could save $X/month ... we'll show it if they ask").
  `scale` is the sensitivity knob (0.25 keeps 120 right-sizes). SAME_COVERAGE_RULE, PORT_OUT_ALWAYS_CONTACT,
  fix-first and BILL_SHOCK_RELIEF_OVERRIDE are unchanged.

## v2: field save rate, profit gate, receipt-only plan moves (Sat 10/17 ~11 PM PDT; all numbers synthetic)
- `FIELD_SAVE_RATE` 0.10 (env `TM_FIELD_SAVE_RATE`): SAVE_RATE = SAVE_RATE_BASE x 0.10 / 0.45 (anchor = risk-weighted
  mean save rate of the engine's contacts under the base table). Per-action ratios preserved; the right-size
  backfire is not scaled. Field evidence 5-15% (Ascarza et al. Marketing Science 2018; Verhelst et al. 2023).
- `PROFIT_GATE` (default ON): no non-forced contact with EV <= 0 ("Stay silent: expected to cost more than it
  saves."). pick() already enforces EV > 0, so the gate is a defensive check; forced EV <= 0 contacts are the
  port-out check-ins / fix-firsts (pick_override = port_out).
- `PLAN_MOVES_RECEIPT_ONLY` (default ON): right_size / variant_switch are never texted; they are computed and put on
  the receipt (`receipt_action`, `receipt_skus`, `receipt_monthly_saving`, `receipt_expected_revenue_given_up_mo`,
  `receipt_reason`; `channel` = sms / none). SAME_COVERAGE_RULE forces the variant onto the receipt.
- perk reminder: save 2% / 1% (field units, unscaled), cost $0.50 (RESEARCH.md s12). SERVICE_MARGIN 0.50 = upper bound.
- `scripts/overpaying_accounts.py` reproduces the household optimizer's 682 accounts / $14,830/mo.

## v2 merge round (SYNTHETIC)
- `KEPT_VALUE_MONTHS` 19.338 (default): kept-account value = monthly margin x 19.338 (survival-discounted 24 months,
  tm-research s13; tm-models' $1,478). Env `TM_KEPT_VALUE_MONTHS=24` restores the old undiscounted value. Upsell and
  lock horizons stay at `VALUE_HORIZON_MONTHS` 24.
- `PORT_OUT_CONTACT` off | self_initiated_only | all (default off, pending David). Sandbox signal
  `account_signals.port_out_inquiry` = the customer asked about porting away (self-initiated inquiry), not a carrier
  port request (FCC 2008, 47 U.S.C. 222(b)). Port-out rows are never `in_headline`; when allowed they appear in
  `already_leaving_save_attempt` / channel `save_attempt`.
- `FIX_FIRST_FORCED_OPEN_TICKET` (default on): unresolved_90d >= 1 forces fix-first (pick_override `open_ticket`).
- Receipt: `receipt_limited_time` / `receipt_plan_end_date` (blank: neither plans nor promotions has an end-date
  field); limited-time target plans (plans.status) get a "check it's still offered" line.
- `harness/one_decision.py`: one `decision` column {text_now, wait_until <date>, receipt_only, silent}, tm-models'
  bill-change rule on our picks, `retention_net`, `tmm_*` guardrail join columns (`harness/guardrail_join.py`).
- `harness/moment_replay.py`: the only windowed wait allowed is a care credit gated by min_tenure_months, with the
  90-day support window re-counted from dated contacts.
