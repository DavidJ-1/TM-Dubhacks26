# Data README: features + labels (tm-data lane)

> **⚠️ ALL LABELS AND RATES ARE SYNTHETIC / SIMULATED.** The judge sandbox has no churn outcomes, and every customer in it is synthetic stub data. `churn_90d`, `p_true_90d`, `monthly_hazard`, `toy_p` and `toy_churn` are generated, not observed. Label any number that comes from them "synthetic" or "simulated" on screen, on Devpost and in charts.

## Rebuild
```bash
# from the repo root; needs pandas, numpy (scikit-learn for modelling)
python harness/features.py   # -> harness/out/features.csv
python harness/labels.py     # -> harness/out/labels.csv (default --recipe tuned; reads features.csv + sandbox for toy_p)
python harness/labels.py --recipe doc   # plan-doc recipe as written; overwrites out/labels.csv, same columns
```
Requirements: `pandas>=2`, `numpy>=1.26`, `scikit-learn>=1.4` (tested: pandas 3.0.6, numpy 2.5.4). Both scripts are deterministic: no global RNG, and draws come from a per-account sha256 uniform.
Sandbox path: `$SANDBOX_DB`, else `<repo>/dubhacks/data/sandbox.db`, else `<repo>/../dubhacks/data/sandbox.db`. It is opened **read-only** (`mode=ro` + `PRAGMA query_only`). Nothing ever writes to it. `harness/out/` is gitignored.

## Source
Judge sandbox https://github.com/mageshkumarj/dubhacks (commit b9a9a6a, 2026-10-15), `data/sandbox.db`: schema v9, seed 2026, as_of 2026-10-01, all stub data, money in **cents**.
Tables (rows): accounts 5,042 · lines 11,944 · usage_monthly 125,829 (2025-10..2026-09) · billing_history 53,098 (12 months) · support_interactions 11,214 (2026-01-04..2026-09-30) · account_signals 5,042 · account_addons 2,374 · line_addons 3,091 · plans 11 · devices 62 · addons 31 · promotions 21 · tradein_curves 3,782 · personas 50 · metadata 6.
Accounts: 5,000 regular + 42 `ACC-PERSONA-xx`. Persona NN maps to account_id `ACC-PERSONA-NN`. The churn personas are 04, 10, 21-28.

## features.csv: 5,042 rows × 69 columns, one row per account (`account_id` first)
| group | columns | notes |
|---|---|---|
| id | `account_id`, `is_persona` | is_persona = account_id starts with ACC-PERSONA- |
| accounts | `segment, tenure_months, language, contact_preference, credit_tier, autopay, discount_group` | discount_group blank → `none` |
| account_signals | `competitor_research_score` (0-1), `port_out_inquiry` (0/1), `app_sessions_30d` | point-in-time snapshot only |
| lines/devices | `n_lines, n_byod_lines, n_financed_lines, financing_balance_total_cents, monthly_installment_total_cents, max_financing_months_remaining, min_financing_months_left_financed, financing_ends_within_3m, max_device_age_months, mean_device_age_months, n_lines_device_36m_plus, n_tradein_eligible_lines, n_flagship_devices` | device age = months from device_purchase_date to 2026-10-01. "financed" = financing_months_remaining > 0 |
| plan | `plan_sku, plan_family, plan_tier, plan_data_cap_gb, plan_is_unlimited, plan_price_cents` | plan_price = sum of plan line_prices for n_lines (+ extra_line_cents beyond the list). List price only, excluding taxes, add-ons and installments |
| usage (last 3 months, 2026-07..09) | `data_gb_3m_avg, voice_min_3m_avg, streaming_hours_3m_avg, hotspot_gb_3m_avg` (account totals per month, averaged), `data_growth_pct` (last 3 months vs prior 3), `plan_misfit_share`, `n_lines_light_on_premium, n_lines_over_cap_3m, n_lines_usage_up_30pct` | plan_misfit_share uses the sandbox toy definition: share of lines whose 12-month average data is over the cap, or that are on a premium plan with < 5 GB |
| billing | `last_bill_cents, prior_avg_bill_cents, bill_increase_pct, bill_change_3m_pct, promo_expired_recent, installment_ended_recent, new_installment_recent, bill_changes_12m` | bill_increase_pct = max(0, last / mean(all prior months) − 1) (toy definition). "recent" = a change_reason in the last 3 bill months |
| support | `support_270d, support_90d, unresolved_270d, unresolved_90d, negative_contacts_90d, avg_sentiment, avg_sentiment_90d, min_sentiment_270d, days_since_last_contact, cancel_inquiries_270d, billing_/device_/plan_change_/network_/cancellation_inquiry_contacts_90d` | 90 days = date ≥ 2026-07-03. avg_sentiment covers all contacts (toy definition) |
| add-ons | `has_home_internet, has_streaming_addon, n_account_addons, n_line_addons, n_protection_addons, n_connected_lines` | |

**Blank values**
- `max_device_age_months` / `mean_device_age_months`: blank for 455 accounts whose lines are all BYOD (no purchase date). labels.py treats these as 0.
- `plan_data_cap_gb`: blank for 2,862 accounts. Blank means an unlimited plan; see `plan_is_unlimited`.
- `prior_avg_bill_cents`: blank for 143 accounts with only one bill month. In that case bill_increase_pct = 0.
- `bill_change_3m_pct`: blank for 370 accounts with no bill 3 months back (new accounts).
- No support contacts: counts = 0, sentiments = 0, `days_since_last_contact` = 999.
- Not computed: promotion eligibility (that belongs to tm-offers via the promotions table or `/v1/promotions`) and trade-in values.

## labels.csv: 5,042 rows (personas included, flagged)
| column | meaning |
|---|---|
| `account_id`, `is_persona` | key + persona flag |
| `churn_90d` | **SYNTHETIC** 0/1: 1 if u < p_true_90d, where u = sha256("tm-churn-2026-label:" + account_id) mapped to [0,1) |
| `p_true_90d` | **SYNTHETIC** true 90-day churn probability = 1 − (1 − monthly_hazard)³ |
| `monthly_hazard` | **SYNTHETIC** monthly churn hazard from the logistic below |
| `toy_p` | exact reproduction of the sandbox's public toy `datagen/reference_model.py`, run on the sandbox's own feature SQL (`datagen/labels.py`). **Native horizon is 90 days**, so it is not converted. Mean is about 14.6% per 90 days (≈5%/month, unrealistic). **Use for ranking checks only, never on charts.** |
| `toy_churn` | **OUR** seeded draw of toy_p (seed "tm-churn-2026-toy"). The judges' draws use a private salt and can't be reproduced. Ranking checks only. |
| `upgrade_90d` | **SYNTHETIC** 0/1: would accept a plan step-up or device upgrade within 90 days (seed "tm-upgrade-2026") |
| `p_upgrade_90d` | **SYNTHETIC** true 90-day upgrade probability (**leak column**) |
| `upgrade_driver_1..3` | the three largest positive upgrade-logit contributions (**leak columns**) |
| `label_driver_1..3` | the three largest positive logit contributions for the account (debug and sanity aid; tm-churn should derive its own reasons) |

**Leak columns.** Never use these as model features: `p_true_90d, monthly_hazard, label_driver_*, p_upgrade_90d, upgrade_driver_*, toy_p, toy_churn`. Train on features.csv against `churn_90d` / `upgrade_90d` only. The upgrade columns come after the churn columns, and the churn columns keep their original order.

### Label recipe (plan doc "Calibration" line, adapted)
`logit(monthly_hazard) = b0 + SHRINK × Σ coef × term`, where SHRINK = 0.5. b0 is solved by bisection so that the **mean monthly hazard over the 5,000 regular accounts = 0.990%** (T-Mobile postpaid account churn, Q2 2026, TMUS Investor Factbook). Result: b0 = −6.3538.
Competitor and port-out terms carry the plan doc's ×1.15 "Verizon loyalty push" multiplier. The weights are judgement calls, **not fitted on real outcomes**.

| term | doc-scale coef | effective coef (×SHRINK) | definition / note |
|---|---|---|---|
| `support_90d` | +0.150 | +0.0750 | support contacts, last 90d (toy uses 0.45; cut so resolved/happy contact is not risk) |
| `unresolved_90d` | +0.450 | +0.2250 | unresolved contacts, last 90d |
| `negative_contacts_90d` | +0.300 | +0.1500 | contacts with sentiment < 0, last 90d |
| `neg_sentiment` | +0.800 | +0.4000 | max(0, -avg_sentiment) over all contacts (toy term) |
| `bill_increase_pct` | +4.000 | +2.0000 | max(0, last bill / prior avg - 1) (toy term) |
| `competitor_research_x` | +2.530 | +1.2650 | competitor_research_score x1.15 threat (toy 2.2) |
| `port_out_inquiry_x` | +1.380 | +0.6900 | port_out_inquiry x1.15 threat (toy 1.2) |
| `tenure_capped60` | -0.010 | -0.0050 | min(tenure_months, 60) (toy term) |
| `plan_misfit_share` | +0.700 | +0.3500 | share of lines over cap or light on premium (toy term) |
| `early_tenure` | +0.900 | +0.4500 | tenure_months < 12 |
| `no_financing` | +0.600 | +0.3000 | no financed lines |
| `no_autopay` | +0.300 | +0.1500 | autopay = 0 |
| `troubled_4plus` | +0.500 | +0.2500 | 4+ contacts in 90d AND at least one unresolved or negative (doc: '4+ contacts') |
| `max_device_age_months_f` | +0.020 | +0.0100 | max device age in months (0 if no dated device) |
| `extra_lines` | -0.150 | -0.0750 | n_lines - 1 |
| `app_sessions_30d` | -0.060 | -0.0300 | app sessions last 30d (doc -0.02; raised so engaged users read as safe) |
| `low_app_use` | +1.000 | +0.5000 | app_sessions_30d <= 3 (silent disengagement; added) |
| `promo_expired_recent` | +0.600 | +0.3000 | promo_expired bill change in last 3 months (added; doc lists promo_expired as a churn field) |
| `billing_contacts_90d` | +0.100 | +0.0500 | billing-topic contacts, 90d |
| `device_contacts_90d` | +0.050 | +0.0250 | device-topic contacts, 90d |
| `cancel_inquiries_270d` | +0.250 | +0.1250 | cancellation-inquiry contacts, 270d |

**Deviations from the doc recipe, and why**
1. The doc's `support 0.45` on the raw contact count is split into support_90d 0.15 + unresolved_90d 0.45 + negative_contacts_90d 0.30. The doc's "4+ contacts +0.5" now applies only when at least one contact was unresolved or negative. Without this change, persona 24 (6 resolved, positive contacts, heavy app use) would score high-risk.
2. app_sessions is raised from −0.02 to −0.06, plus `low_app_use` (≤3 sessions) +1.0, so engaged users read as safe and the silent churner (persona 21) reads as risky.
3. Added `promo_expired_recent` +0.6. The doc lists promo_expired as a churn field.
4. SHRINK 0.5. At doc scale, monthly hazards reach about 0.94 and mean p_90d is only about 2.1%, because hazard is very uneven across accounts. Halving every coefficient changes no account's rank (Spearman 1.0 against the unshrunk score). It caps the maximum monthly hazard at about 0.49 and brings mean p_90d to about 2.74%, close to 1 − (1 − 0.0099)³ = 2.94%. The two can't match exactly while both the mean monthly hazard and heterogeneity are kept.
5. The doc writes `logit(p_12m)`, but its b0 is solved on monthly hazard. Here the logit is of the monthly hazard directly.

### Alternative: `--recipe doc` (plan-doc line 205 as written, no persona tweaks)
This recipe uses raw support 0.45, app sessions −0.02, an unconditional "4+ contacts" +0.5, and no unresolved, negative, low-app or promo-expired terms. b0 is solved the same way, for a 0.99%/month mean.
Halving: at full strength the maximum monthly hazard is 0.822 (above the guard `DOC_MAX_HAZARD` = 0.5) and the mean p_90d is 2.47%. So the doc recipe **is halved too** (SHRINK 0.5, b0 = −6.2145). This doesn't change any account's rank.

| term | doc coef | effective (×0.5) | definition |
|---|---|---|---|
| `support_90d` | +0.450 | +0.2250 | support contacts, last 90d (toy term) |
| `neg_sentiment` | +0.800 | +0.4000 | max(0, -avg_sentiment) (toy term) |
| `bill_increase_pct` | +4.000 | +2.0000 | max(0, last bill / prior avg - 1) (toy term) |
| `competitor_research_x` | +2.530 | +1.2650 | competitor_research_score x1.15 |
| `port_out_inquiry_x` | +1.380 | +0.6900 | port_out_inquiry x1.15 |
| `tenure_capped60` | -0.010 | -0.0050 | min(tenure_months, 60) (toy term) |
| `plan_misfit_share` | +0.700 | +0.3500 | plan misfit share (toy term) |
| `early_tenure` | +0.900 | +0.4500 | tenure_months < 12 |
| `no_financing` | +0.600 | +0.3000 | no financed lines |
| `no_autopay` | +0.300 | +0.1500 | autopay = 0 |
| `contacts_4plus` | +0.500 | +0.2500 | 4+ support contacts in 90d (unconditional) |
| `max_device_age_months_f` | +0.020 | +0.0100 | max device age in months |
| `extra_lines` | -0.150 | -0.0750 | n_lines - 1 |
| `app_sessions_30d` | -0.020 | -0.0100 | app sessions last 30d |
| `billing_contacts_90d` | +0.100 | +0.0500 | billing-topic contacts, 90d |
| `device_contacts_90d` | +0.050 | +0.0250 | device-topic contacts, 90d |
| `cancel_inquiries_270d` | +0.250 | +0.1250 | cancellation-inquiry contacts, 270d |

Doc-recipe results (synthetic): mean monthly hazard 0.990%, mean p_true_90d 2.87%, churn_90d 134 / 5,000 (2.68%), maximum monthly hazard 0.271. Spearman against toy_p 0.917; AUC against toy_churn 0.815.
Doc-recipe persona percentiles: 04 94.2 (OK) · **21 86.2 (miss)** · **22 81.7 (miss)** · **27 88.0 (miss)** · 10 1.6 (OK) · **24 75.8 (miss: 6 contacts read as risk)** · 23 87.4 · 25 77.0 · 26 16.1 · 28 38.6.
Both recipes print persona percentiles after each run.

### Results, default `tuned` recipe (all synthetic, 5,000 regular accounts)
- Mean monthly_hazard **0.990%**. Mean p_true_90d **2.74%** (implied monthly ≈ 0.92%). churn_90d positives **137 / 5,000 (2.74%)**; 138 / 5,042 including personas. Max monthly hazard 0.486.
- toy_p mean 14.65% per 90 days. toy_churn positives 781 / 5,000.
- Spearman(p_true_90d, toy_p) = 0.879. AUC of p_true_90d against toy_churn = 0.807 (toy_p itself scores 0.827). AUC of p_true_90d against churn_90d = 0.864 (the oracle ceiling for tm-churn).
- Personas: p_true_90d, then percentile among the 5,000 regular accounts. Expected high: 04 0.173 (97th), 21 0.061 (92nd), 22 0.051 (90th), 27 0.072 (93rd). Expected low: 10 0.004 (2nd), 24 0.005 (11th). Others: 23 0.089 (94th), 25 0.019 (74th), 26 0.006 (13th), 28 0.009 (42nd).

## Upgrade target (`upgrade_90d`): SYNTHETIC
**ALL UPGRADE LABELS AND RATES ARE SYNTHETIC.** The target is "would accept a plan step-up or device upgrade within 90 days". It is independent of `--recipe`: the churn-risk term always uses the tuned churn hazard.
`logit(p_upgrade_90d) = b0 + Σ coef × term`. b0 is solved so the mean p_upgrade_90d over the 5,000 regular accounts = **6.0%**. Source: the plan doc's v2 assumes 2.0% upgrades per account-month (Verizon's 2.6%/quarter phone upgrade rate × 2.37 lines per account), and 1 − (1 − 0.020)³ = 5.88%, rounded to 6.0%. This is a synthetic assumption; T-Mobile does not publish a per-account upgrade rate. b0 = -3.9492.

| term | coef | definition |
|---|---|---|
| `tier_basic` | +1.00 | plan_tier = basic (most headroom) |
| `tier_standard` | +0.50 | plan_tier = standard |
| `capped_plan` | +0.50 | plan has a data cap |
| `top_tier` | -1.00 | already on experience_beyond (top) family |
| `over_cap_share` | +1.50 | share of lines over plan cap (last 3 months) |
| `near_cap` | +0.60 | capped plan and avg data per line >= 80% of cap (last 3 months) |
| `usage_growth` | +0.80 | data_growth_pct clipped to [-0.5, 1.0] (last 3 vs prior 3 months) |
| `hotspot_heavy` | +0.40 | hotspot >= 5 GB per line per month (last 3 months) |
| `device_age_years` | +0.45 | years of max device age beyond the first 12 months: max(0, months - 12) / 12 (0 if no dated device) |
| `old_device_36m` | +0.30 | any line with a device >= 36 months old |
| `installment_ended_recent` | +0.50 | phone paid off in last 3 bill months (freed budget) |
| `tenure_years_capped5` | +0.10 | min(tenure_months, 60) / 12 (moderate positive) |
| `student` | +0.70 | segment or discount_group = student (life-stage step-up, e.g. graduation; doc lists student as an upgrade moment) |
| `bill_increase_pct` | -4.00 | bill shock: max(0, last / prior avg - 1) |
| `promo_expired_recent` | -1.00 | bill shock: promo expired in last 3 bill months |
| `churn_risk_z` | -0.25 | max(0, z-score of logit(tuned monthly churn hazard)): mild negative for above-average risk only; tuned recipe always |

Results (synthetic, 5,000 regular accounts): mean p_upgrade_90d 6.00%; upgrade_90d positives 300 (6.00%); median 3.6%, max 0.71. Correlation with p_true_90d: Spearman −0.28, Pearson −0.16 (bill shock and risk push the two apart). Most common top driver: device age beyond 12 months (1,397 accounts), then tenure, standard tier, basic tier, student.
Persona upgrade percentiles: 25 (upsell) 95.8 · 28 (graduating student) 93.8 · 22 (bill shock) 3.3 · 27 (bill shock) 3.9 · 24 (do nothing) **50.7, about the median** (p = 3.7%, below the 6% mean; premium plan, 55-month tenure). Others: 04 5.7 · 10 24.2 · 21 53.3 · 23 38.5 · 26 21.7.
Tuning steps taken to reach these persona ranks, each a judgement call: churn-risk penalty applies only above average risk; tenure weight 0.10 per year; student weight 0.70; device age counts only after the first 12 months.
