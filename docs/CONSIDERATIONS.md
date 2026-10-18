# Everything we considered

A plain-English ledger of everything the system accounts for. One line each: **what it is**, how we handle it, and *the file or number behind it*.

**Every account and number here is simulated** (the hackathon sandbox's 5,042 stub accounts plus our simulated churn labels). None of it is real T-Mobile customer data. Numbers were read from the cited files, not retyped from chat; a few were recounted from the committed CSVs (marked "recounted").

The app panel reads `docs/considerations.csv` (columns `group, item, how_handled, source`). That file uses the same lines but names sources in plain words, with no file paths, people's names or the word "synthetic", so it can go on screen as is.

Groups 1a-1c are the complete list of inputs the risk model and offer engine read, for the customer walk-through. "Used by" says which part reads each one.

| group | items |
|---|---:|
| 1. Signals used | 6 |
| 1a. Inputs: commerce | 18 |
| 1b. Inputs: customer | 8 |
| 1c. Inputs: live | 9 |
| 2. How a customer is scored and explained | 9 |
| 3. Offer or do nothing | 10 |
| 4. Do-not-contact rules and guardrails | 15 |
| 5. Channel and language | 7 |
| 6. Money honesty (simulated) | 9 |
| 7. Savings line on the bill | 4 |
| 8. Fairness audit (simulated) | 5 |
| 9. Privacy and compliance | 8 |
| 10. Left out on purpose | 11 |
| 11. Known limits | 10 |
| **total** | **129** |

## 1. Signals used

- **Three signal types**: Every input is tagged commerce, customer or live, and the engine uses all three. The full input list follows in the three Inputs groups. *Source: `harness/offers.py (drivers: commerce/customer/live); docs/strategy/DEVPOST.md 'multiple signal types'`*
- **Commerce examples**: Plan, price, phone financing and payoff, device age, trade-in value, promotions, bill changes. *Source: `demo_data/features.csv; harness/offer_detectors.py (plans, promotions, devices, tradein_curves)`*
- **Customer examples**: Lines on the account, tenure, support history, segment label, contact preference, language. *Source: `demo_data/features.csv; sandbox accounts table`*
- **Live examples**: Recent support contacts and how they went, app use going quiet, comparing carriers, asking about transferring a number, a promo just ending. Comparing carriers and number-transfer questions come from what the customer tells us; we do not track calls to competitors. *Source: `demo_data/features.csv; docs/strategy/DEVPOST.md`*
- **Simulated enrichment (job change, income, kid age band)**: Listed for transparency but switched off permanently: no code path reads it for eligibility, value or wording. *Source: `harness/offers.py CONFIG ENRICHMENT_IN_DECISIONS = False`*
- **Kid and teen lines**: Taken from the account's real line roles, never inferred; can shape an offer, but messages say 'your 4 lines', never 'your kids'. *Source: `harness/offers.py (lines.member_role); OFFER_STRATEGY.md`*

## 1a. Inputs: commerce

- **Bill increase**: Last bill vs the prior average, floored at zero. Used by: risk model, offer engine. *Source: `demo_data/features.csv bill_increase_pct`*
- **Promo ended recently**: A promotion credit dropped off a recent bill. Used by: risk model, offer engine (no upsell for 90 days after). *Source: `demo_data/features.csv promo_expired_recent`*
- **Plan misfit**: Share of lines whose usage doesn't fit the plan. Used by: risk model, offer engine. *Source: `demo_data/features.csv plan_misfit_share`*
- **Phone age**: Age of the oldest phone on the account. Used by: risk model, offer engine (upgrade moments). *Source: `demo_data/features.csv max_device_age_months`*
- **Bring-your-own-phone account**: No financed or carrier phone on record. Used by: risk model. *Source: `demo_data/features.csv is_byod (from blank device age)`*
- **Phone payoff within 3 months**: A financed phone finishes paying off soon. Used by: risk model, offer engine (upgrade moment), messages (no payoff-timing text). *Source: `demo_data/features.csv financing_ends_within_3m; lines.financing_months_remaining`*
- **Short billing history**: Too few bills to compare against. Used by: risk model. *Source: `demo_data/features.csv short_history`*
- **Home Internet on the account**: Whether the account already has Home Internet. Used by: risk model, offer engine. *Source: `demo_data/features.csv has_home_internet`*
- **Plan, family and price**: Current plan, its family and monthly price, checked against the sandbox plan table. Used by: offer engine, messages. *Source: `demo_data/features.csv plan_sku, plan_family, plan_price_cents; plans.line_prices`*
- **Last bill**: Latest monthly bill amount. Used by: offer engine (value of the account, credit sizing). *Source: `demo_data/features.csv last_bill_cents`*
- **Bill change reason**: Why the bill moved in July to September: promo ended, new phone payment, payment ended, or stable. Used by: guardrail, messages. *Source: `billing_history.change_reason (1,412 accounts non-stable and up)`*
- **Phone financing and trade-in value**: Per-line balance, months left, and trade-in value from the sandbox curve for paid-off phones. Used by: offer engine, bill/app lines. *Source: `lines table; tradein_curves; docs/outreach/draft_outreach.py`*
- **Promotion rules**: Each promotion's own eligibility, including its credit-tier and contact-count rules. Used by: offer engine eligibility. *Source: `promotions table; harness/offers.py`*
- **Price guarantee**: Years of price guarantee on the plan. Used by: messages, bill/app lines, 'you'd lose X' lines. *Source: `plans.price_guarantee_years`*
- **Add-ons and streaming perk**: Add-ons on the account and whether streaming is already included. Used by: offer engine (perk reminder), bill/app lines. *Source: `demo_data/features.csv has_streaming_addon; account_addons; addons`*
- **Connected lines (watch, tablet)**: Number of non-phone lines. Used by: offer engine (plan moves), bill/app lines. *Source: `demo_data/features.csv n_connected_lines`*
- **AutoPay**: Whether AutoPay is on. Used by: offer engine (dropped from the risk model: its fitted sign contradicted common sense). *Source: `demo_data/features.csv autopay; harness/out/churn_model_card.md`*
- **Upgrade score**: A simulated upgrade score from device age; only a gate for upgrade offers (top 15%). Used by: offer engine gate. *Source: `demo_data/upgrade_scores.csv; harness/offers.py UPGRADE_GATE`*

## 1b. Inputs: customer

- **Tenure**: Months with us, capped at 60, plus a flag for under 12 months. Used by: risk model, offer engine, messages ('Thanks for N years'). *Source: `demo_data/features.csv tenure_capped60, early_tenure`*
- **Lines on the account**: Extra lines beyond the first. Used by: risk model, offer engine, messages ('your N-line account'). *Source: `demo_data/features.csv extra_lines, n_lines`*
- **Cancellation inquiries**: Times the customer asked about cancelling in the last 270 days. Used by: risk model. *Source: `demo_data/features.csv cancel_inquiries_270d`*
- **Segment and discount group**: Sandbox labels such as senior or student, never ages. Used by: offer engine (only to unlock a real plan like 55+), fairness audit; never shown or used in wording. *Source: `demo_data/features.csv segment, discount_group`*
- **Credit tier**: Sandbox credit tier. Used by: offer engine, only where a promotion's own rules require it; kept out of the risk model. *Source: `harness/offers.py L402; harness/churn_features.py FAIRNESS_DROP`*
- **Language**: en, es or other. Used by: messages (Spanish for es); kept out of the risk model. *Source: `accounts.language; harness/churn_features.py FAIRNESS_DROP`*
- **Contact preference**: Text, app, email or call. Used by: channel choice. *Source: `accounts.contact_preference`*
- **Total support contacts in 90 days**: Raw count, used only alongside how the contacts went. Used by: offer engine (care credit contact rule); raw counts kept out of the risk model so a happy frequent caller isn't flagged. *Source: `demo_data/features.csv support_90d; harness/churn_features.py RAW_CONTACT_COUNTS`*

## 1c. Inputs: live

- **Unresolved support contacts (90 days)**: Contacts still open. Used by: risk model, offer engine (fix first), messages. *Source: `demo_data/features.csv unresolved_90d`*
- **Unhappy support contacts (90 days)**: Contacts with negative sentiment. Used by: risk model. *Source: `demo_data/features.csv negative_contacts_90d`*
- **Negative sentiment**: Negative part of support sentiment, recent and overall. Used by: risk model, offer engine. *Source: `demo_data/features.csv neg_sentiment (from avg_sentiment, avg_sentiment_90d, min_sentiment_270d)`*
- **Troubled (4+ contacts and one bad)**: Four or more contacts in 90 days with at least one unresolved or unhappy. Used by: risk model. *Source: `demo_data/features.csv troubled_4plus`*
- **Comparing carriers**: Competitor research score, from what the customer tells us. Used by: risk model, offer engine. *Source: `demo_data/features.csv competitor_research_score`*
- **Asked about transferring their number**: Port-out inquiry flag. Used by: risk model, offer engine (always gets a check-in or fix); never cited in a message. *Source: `demo_data/features.csv port_out_inquiry; harness/offers.py PORT_OUT_ALWAYS_CONTACT`*
- **App use**: App sessions in the last 30 days, plus a flag for 3 or fewer. Used by: risk model, offer engine. *Source: `demo_data/features.csv app_sessions_30d, low_app_use`*
- **Recent usage**: Per-line data peaks and streaming hours over 3 months. Used by: offer engine (plan fit, right-sizing, near data cap). *Source: `usage_monthly; demo_data/features.csv streaming_hours_3m_avg`*
- **Open issue topic**: What an open support contact is about (coverage, bill, phone). Used by: messages (fix-first wording names the topic). *Source: `support_interactions; docs/outreach/outreach_drafts.csv open_issue_90d`*

## 2. How a customer is scored and explained

- **Churn score**: A standardized logistic regression scores 90-day churn on 20 inputs; the 42 hand-built demo accounts are scored but never trained on. *Source: `harness/churn_model.py; harness/out/churn_model_card.md`*
- **How good it is (simulated)**: Out-of-fold AUC 0.853; its riskiest 10% hold about 62% of leavers. This shows the pipeline works, not real accuracy. *Source: `harness/out/churn_model_card.md; docs/strategy/DEVPOST.md`*
- **Who is flagged**: The riskiest 10% of the 5,000 regular accounts: 500 flagged (504 if the demo accounts are mixed in). *Source: `demo_data/churn_scores.csv (recounted)`*
- **Why this score**: Each account gets up to 3 reasons to leave and 3 reasons to stay, written from its own fields, e.g. '6 unresolved support contacts in 90 days'. *Source: `demo_data/churn_scores.csv risk_reason_1..3, stay_reason_1..3`*
- **How reasons are computed**: Each input's push on the score vs an average account, grouped; a reason must move the score by at least 0.05 and a risk-raising value is never shown as a stay reason. *Source: `harness/out/churn_model_card.md (29 reasons blocked by the direction guard)`*
- **Common-sense check on inputs**: Inputs whose effect pointed the wrong way were removed and the model refit (AutoPay, no financing). *Source: `harness/out/churn_model_card.md`*
- **Happy frequent callers**: Raw contact counts are left out, so someone with many resolved contacts isn't read as at risk. *Source: `harness/churn_features.py RAW_CONTACT_COUNTS; DEVPOST Customer 24`*
- **Why this action**: Each card shows the pick, the runner-up, every option weighed with its value, and why each one lost (e.g. 'needs 3+ support contacts in 90 days'). *Source: `demo_data/offers.csv (reason, why_this_offer, runner_up_action, eligible_actions, ev_*, do_nothing_reason)`*
- **Why we're reaching out (or not)**: One plain sentence per account that ends with the channel, or the do-not-contact reason. *Source: `docs/outreach/outreach_card.csv outreach_reason (5,042 rows)`*

## 3. Offer or do nothing

- **Doing nothing is always an option**: It is priced at $0 and every offer has to beat it. *Source: `harness/offers.py; docs/strategy/DEVPOST.md`*
- **Expected value**: Chance of churn x chance the action saves them x value of the account, minus the offer cost and a contact cost. *Source: `harness/offers.py; scratch_models/economics/RESULTS.md Task 1`*
- **Value of a kept customer: $1,478**: About $76.46 a month margin over 24 months, weighted for the chance they leave anyway (0.99% a month) and discounted 10% a year. *Source: `RESEARCH.md §13b; scratch_models/economics/RESULTS.md P1`*
- **Save rate assumption**: The next version picks at a 10% save rate, scaling each action's rate down to match. *Source: `docs/outreach/inputs/guardrail_summary.txt (scale 0.2254)`*
- **Contact costs**: A fix-first callback costs $15, a check-in $2, plus an annoyance cost of $2 to $6 per contact. *Source: `harness/offers.py FIX_FIRST_CALLBACK_COST, CHECK_IN_COST, ANNOYANCE`*
- **Retention picks**: 202 accounts are worth contacting at 10%; 184 remain after the do-not-contact rules. *Source: `docs/outreach/inputs/guardrail_summary.txt`*
- **What the 184 get**: Fix first 126, care credit plus fix 29, perk reminder 26, check-in 2, bill-shock credit 1. *Source: `docs/outreach/inputs/guardrail_summary.txt`*
- **No credits at low risk**: No bill or goodwill credit below 5% churn risk. *Source: `harness/offers.py MIN_CREDIT_P_CHURN = 0.05`*
- **Same features, lower price wins**: An eligible cheaper plan with the same features beats upsells and check-ins. *Source: `harness/offers.py SAME_COVERAGE_RULE`*
- **Prices checked**: Every dollar figure in a message is checked against the sandbox plan and promotion tables, or the run fails. *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §8`*

## 4. Do-not-contact rules and guardrails

- **Silence is the default**: 4,858 of 5,042 accounts get no message; the reason is stored for each. *Source: `docs/outreach/outreach_summary.md`*
- **Bill-increase guardrail**: Of 1,412 accounts whose bill rose for a real reason in July to September, a retention message goes only with a credit that offsets it; 18 of 202 picks blocked. *Source: `scratch_models/economics/guardrail/GUARDRAIL.md; docs/outreach/inputs/guardrail_summary.txt`*
- **Exemption: fix-only calls**: A call to fix an open problem is always allowed, even after a bill rise. *Source: `scratch_models/economics/guardrail/GUARDRAIL.md (new rule)`*
- **Exemption: a new phone the customer chose**: A bill rise that is only a new phone payment doesn't block (850 accounts); new phone plus a promo ending still blocks (71). *Source: `scratch_models/economics/guardrail/GUARDRAIL.md`*
- **We don't use 'bill went up' alone**: That would flag 4,679 accounts, mostly cents of noise. *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §1`*
- **Fix first**: With an open support issue in the last 90 days, the only message allowed is a fix; 25 perk reminders became fix callbacks. *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §1 rule 6`*
- **Phone payoff coming up (313 accounts)**: No payoff or upgrade-timing message; contacting them early is pure timing and loses money (-$156). 12 of them still get an unrelated fix call for an open issue. *Source: `scratch_models/economics/RESULTS.md P3; docs/outreach/outreach_drafts.csv (recounted)`*
- **Trade-in nudge dropped**: No trade-in messages: at a $0 device margin the nudge never adds money at any take rate. Trade-in value shows only as a bill/app line. *Source: `scratch_models/economics/RESULTS.md P3`*
- **Cheaper plans are never a message**: They go on the bill as tap-to-confirm; unprompted plan recommendations raised churn from about 6% to 10% in a field test. *Source: `scratch_models/economics/guardrail/GUARDRAIL.md (Ascarza, Iyengar & Schleicher 2016)`*
- **No upsell after a bill shock**: Plan step-ups and phone upgrades are blocked for 90 days after a promo ends or the bill jumps 15% or more. *Source: `harness/offers.py UPSELL_BLOCK_DAYS_AFTER_BILL_SHOCK`*
- **Affordability cap on upsells**: An upsell is blocked if it raises the bill by more than 25% (40% when a line is already over its data cap); never based on income. *Source: `harness/offers.py AFFORDABILITY_MAX_BILL_INCREASE`*
- **Once a quarter at most**: At most one proactive contact per account per quarter; the sandbox has no outreach log, so this is a hook, and each run sends at most one message. *Source: `scratch_models/economics/guardrail/GUARDRAIL.md`*
- **Marketing opt-out**: Opted-out accounts get no marketing; the sandbox has no opt-out field, so this is a hook. *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §1 rule 3, §4`*
- **Reply STOP**: Every text ends with 'Reply STOP to opt out'; in-app, email and calls each carry their own opt-out. The run fails if one is missing. *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §3, §8`*
- **Send hours**: Only 8 a.m. to 8 p.m. local time (a send-time rule; the sandbox has no time zone). *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §4`*

## 5. Channel and language

- **184 messages**: Each goes by the customer's own stated preference, not a ranking: 74 in-app, 64 texts, 32 emails, 14 calls. *Source: `docs/outreach/outreach_summary.md; outreach_drafts.csv channel`*
- **Same set of accounts**: Over the 5,000 regular accounts: 5,000 scored, 500 flagged, 182 messaged, 64 by text (2 messages go to demo accounts). *Source: `docs/outreach/outreach_drafts.csv; scratch_models/economics/fairness184/RESULTS_fairness184.md`*
- **Wording per channel**: Texts start 'T-Mobile:' and say Reply YES/STOP; in-app says 'Tap to...'; email says 'Use the link below...'; calls are a short script. *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §3`*
- **Spanish**: 18 messages are in Spanish (usted); 166 in English, and every row also carries a Spanish version. *Source: `docs/outreach/outreach_summary.md; OUTREACH_PLAYBOOK.md §5`*
- **Length limits**: Texts at most 320 characters (longest 257 English, 293 Spanish); other channels at most 420. *Source: `docs/outreach/outreach_summary.md Validation`*
- **No claim one channel works better**: No telecom study compares channels on the same offer. *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §3; RESEARCH.md §14a`*
- **Same text everywhere**: Fixed templates; two runs give byte-identical files. *Source: `docs/outreach/outreach_summary.md; docs/outreach/templates.json`*

## 6. Money honesty (simulated)

- **Result at a 10% save rate**: 184 messages come out $4,109 ahead (simulated). *Source: `scratch_models/economics/RESULTS.md HEADLINE; headline_1478.csv`*
- **Break-even about 4.8%**: Below a 4.80% save rate it loses money; at 5% it is $161 ahead, a coin flip. *Source: `scratch_models/economics/RESULTS.md HEADLINE`*
- **Measured campaigns run 2% to 11%**: Published retention results run about 2% to 11% relative, so this pays in the stronger campaigns and loses in the weakest. *Source: `docs/strategy/DEVPOST.md`*
- **Bootstrap**: 2,000 account resamples (seed 2026): at 10% it comes out ahead 82% of the time (mean $3,953, range -$2,805 to $13,292); at 5%, 44%. *Source: `scratch_models/economics/RESULTS.md HEADLINE`*
- **Do saves stick?**: If each saved customer stays as risky as before, only 58 are worth contacting, break-even rises to 7.6%, and it is ahead only 43% of the time at 10%. A holdout test is the only way to know. *Source: `scratch_models/economics/RESULTS.md HEADLINE, P2`*
- **The shipped demo engine**: The earlier engine contacts 1,314 accounts and is -$71,838 at a 10% save rate in full dollars. That is why the next version contacts far fewer. *Source: `scratch_models/chart_check/RESULTS.md §3`*
- **Blanket discount rule**: A $25 credit to the top 10% by risk is -$4,116 at 10%. *Source: `scratch_models/chart_check/RESULTS.md §3`*
- **Not statistically proven**: At about 5,000 accounts, no 5% result is distinguishable from zero. *Source: `scratch_models/economics/RESULTS.md Circularity`*
- **Cheaper plans cost money**: Shown as money back to customers, never as profit. *Source: `brief Google Doc §3`*

## 7. Savings line on the bill

- **394 accounts, give up nothing**: Could pay $4,600 a month less in total for the same features; shown on the bill or app as a tap-to-confirm line, never a text. *Source: `docs/outreach/inputs/receipt.csv (in_headline & no_tradeoff); outreach_receipt_lines.csv plan_move_like_for_like`*
- **Cheaper, but you'd lose X**: 94 more accounts get a line that names what they'd give up (price guarantee, hotspot, perks, data cap). *Source: `docs/outreach/inputs/receipt.csv (488 in headline minus 394)`*
- **Other bill/app lines**: Price guarantee 2,862, trade-in value 2,212, streaming included 695, watch line 66. *Source: `docs/outreach/outreach_summary.md`*
- **Not proven to keep anyone**: A customer-first choice with no public field evidence that savings receipts retain; it costs T-Mobile money. *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §3`*

## 8. Fairness audit (simulated)

- **Final wording**: In our test on simulated data, at the same churn risk, accounts labeled senior or student were about 2.7 points less likely to get a retention message, roughly 10 and 16 accounts. Counting the cheaper-plan savings on the bill, they were shown a savings line more often than others, about 8 and 5 points. This is the audit we'd run weekly on real data. *Source: `docs/strategy/DEVPOST.md (a21e433)`*
- **Method**: 5,000 regular accounts, matched on risk deciles, gap vs everyone else with 1,000 bootstrap resamples. *Source: `scratch_models/economics/fairness184/RESULTS_fairness184.md`*
- **Small counts**: Only 4 of 370 senior-labeled and 7 of 611 student-labeled accounts get a message. *Source: `scratch_models/economics/fairness184/RESULTS_fairness184.md`*
- **Labels, not ages**: Segment labels never appear in wording or change it; they matter only to unlock a real plan such as 55+. *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §5`*
- **Kept out of the risk model**: Language and credit tier are not risk inputs. *Source: `harness/churn_features.py FAIRNESS_DROP`*

## 9. Privacy and compliance

- **No AI text generation**: Every message is a fixed template filled from account fields; our own model decides. *Source: `docs/outreach/draft_outreach.py; harness/offer_messages.py; requirements.txt`*
- **Only facts the customer would recognize**: Messages cite only their bill, plan, lines, phone and own support contacts; never income, job, kids, location, comparing carriers or number transfers. A forbidden-word check fails the run. *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §7`*
- **Number-transfer data: open question**: The risk score and the always-contact rule read the port-out question; messages never cite it. Whether the engine should use it at all is an open product decision. *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §8 open item; harness/offers.py PORT_OUT_ALWAYS_CONTACT`*
- **Only services they already have**: No Home Internet cross-sell, which would need separate customer-data consent. *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §4`*
- **No lock-in language**: No contracts, $0 early termination fee; any text with lock, contract, contrato or permanencia fails the run. *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §6`*
- **Demo phone send**: Dry run by default: nothing leaves the machine unless the presenter arms it, and the only destination is one private chat set in local config. The app can't pass a number. *Source: `harness/phone_push.py header`*
- **Judge data is read-only**: The sandbox database is opened read-only. *Source: `harness/offer_detectors.connect_ro (sqlite mode=ro)`*
- **Simulated data only**: Every account is from the hackathon sandbox; no real T-Mobile customer data. *Source: `docs/strategy/DEVPOST.md`*

## 10. Left out on purpose

- **Income, job and kid-age guesses**: Never used in decisions or wording; too creepy and unsourced. *Source: `harness/offers.py ENRICHMENT_IN_DECISIONS`*
- **Upsells in outreach**: No plan step-ups or phone upgrades in the 184; the retention-only policy picks neither. *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §6`*
- **Home Internet**: Never picked at realistic 1-4% take rates, and would need consent. *Source: `brief Google Doc §3; OUTREACH_PLAYBOOK.md §4`*
- **Student credit**: Switched off. *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §3`*
- **Add-a-line pitch**: No claim that adding a line lowers churn; multi-line customers self-select. *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §6`*
- **Trade-in and payoff texts**: Dropped: they lose money at a $0 device margin or are pure timing. *Source: `scratch_models/economics/RESULTS.md P3`*
- **Different pitch per person**: In the Hillstrom test, picking a message per customer didn't beat one good message. *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §5`*
- **Event-triggered texting**: Would add 413 extra texts for 197 of the picks; one message per run instead. *Source: `scratch_models/economics/RESULTS.md Task 4`*
- **A model for who gets pushed away**: On a real randomized test, our uplift model's 'pushed away' group actually responded well, so we use rules. *Source: `scratch_models/economics/guardrail/GUARDRAIL.md`*
- **Win-back**: Out of scope: we act before they leave. *Source: `brief Google Doc glossary`*
- **Claims about pending FCC rules**: None made; the one checked is not in force. *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §4`*

## 11. Known limits

- **No real churn outcomes**: Labels are simulated from a formula we wrote, so the model's accuracy is partly by construction. *Source: `harness/out/churn_model_card.md; scratch_models/economics/RESULTS.md Circularity`*
- **Save rate unknown**: Every dollar figure rests on an assumed save rate; only a holdout test can measure it. *Source: `scratch_models/economics/RESULTS.md`*
- **Holdout size**: A reliable read needs about 12,800 accounts per group; at our ~5,000 only very large effects show. *Source: `docs/strategy/DEVPOST.md (power estimate)`*
- **Contacts lean on bill changes**: Only 35 of the 184 have no recent bill change, because bill changes are churn terms in our own generator. *Source: `scratch_models/economics/RESULTS.md GUARDRAIL weak spot`*
- **No outreach log, opt-out field or time zone**: Quarterly cap, opt-out and send hours are hooks, untested on this data. *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §1, §4`*
- **Promo ends already happened**: In the sandbox, promo-end messages explain a past increase; in production they'd go 10-40 days before. *Source: `docs/outreach/OUTREACH_PLAYBOOK.md §2`*
- **Trade-in flag on financed lines**: The sandbox marks 6,575 financed lines trade-in eligible; real T-Mobile requires payoff, so we only value paid-off phones. *Source: `docs/research/devices_tradein.md; OFFER_STRATEGY.md §6b`*
- **Demo still runs the earlier engine**: The live app's engine is the 1,314-contact version until the next version is wired in. *Source: `brief Google Doc §3`*
- **Bill-shock credit override**: Relaxing the care credit's 3-contact rule after a bill shock is our policy choice, not a sandbox rule, and still an open decision. *Source: `harness/offers.py BILL_SHOCK_RELIEF_OVERRIDE`*
- **Fairness counts are tiny**: The message gap rests on 4 seniors and 7 students. *Source: `scratch_models/economics/fairness184/RESULTS_fairness184.md`*

## Open questions for David

- **Port-out data:** should the risk score and the always-contact rule keep reading the port-out inquiry? Messages never cite it either way (`OUTREACH_PLAYBOOK.md` §8; `harness/offers.py` `PORT_OUT_ALWAYS_CONTACT`).
- **Bill-shock credit override:** keep relaxing the care credit's 3-contact rule after a bill shock? (`harness/offers.py` `BILL_SHOCK_RELIEF_OVERRIDE`, marked OPEN DECISION).
