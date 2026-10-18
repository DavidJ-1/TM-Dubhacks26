# Prompt-fit audit: DubHacks '26 T-Mobile project (skeptical-judge read)

Audited Sat 10/17/2026 ~7:45 PM PDT. Read-only. All numbers below are **synthetic/simulated** (judge sandbox stub data plus our simulated labels).
Scope: `strategy/tmobile-brief-summary.md` (authoritative brief), `handoff/plan-doc-2026-10-17.txt`, the team plan,
repo `this repo` @ `dev` (HEAD bcc5228, plus uncommitted changes to enrichment/uplift files), canonical outputs
`TM-Dubhacks26/harness/out/*.csv` (`../harness/out/` is empty and deprecated per the team plan), `app/streamlit_app.py`,
sandbox.db schema + `personas` table (opened `mode=ro`).

The test throughout: **does this answer T-Mobile's prompt, judged by T-Mobile's rubric and the sandbox's own personas?** Not "does it match our plan?"

---

## 0. The biggest thing the team may be missing

The sandbox ships **42 customer personas tagged with a `primary_theme`** (next_best_moment 10, timekeeper 10, household_optimizer 9, cart_whisperer 9,
matchmaker 4) plus 8 prospects. The plan doc says "judges likely test against them." I ran every persona through our live `offers.csv`:

| Theme | What judges would expect | What our engine outputs | Verdict |
|---|---|---|---|
| NBM 04 bill jump + calls | fix + credit | care credit + fix-first | PASS |
| NBM 22 promo-ended bill shock | relief, no upsell | $25 care credit (EV only $5.41, runner-up $0.11) | PASS, fragile |
| NBM 23 coverage complaints | fix first, no discount | fix-first callback | PASS |
| NBM 24 happy frequent caller | do nothing | do nothing | PASS |
| NBM 25 outgrowing plan | step-up | step-up to More | PASS |
| NBM 27 locked in, unhappy | fix, not a discount | fix-first | PASS |
| NBM 10 loyal family | do nothing | do nothing | PASS |
| NBM 26 loyal, casually comparing | restraint / light touch | do nothing | OK |
| **NBM 21 long-timer, went quiet, port-out inquiry, competitor 0.85** | **act: check-in / retention** | **do nothing** (p=5.4%, every eligible action negative) | **FAIL** |
| NBM 28 student graduating | timely plan move | step-up, but text says "you're getting close to finishing school" | PASS on action, **FAIL on trust** |
| **HH 05 3 lines on top plan, few GB each** | **save money: right-size** | **do nothing** (right-size eligible, saves $110/mo, EV −$787) | **FAIL** |
| **HH 38 couple 55+ on regular-priced plan** | **switch to 55+ pricing** | **step-UP to Experience Beyond** (55+ right-size was eligible, saves $40/mo, EV −$285) | **FAIL (actively wrong: upsell instead of savings)** |
| **HH 40 eligible for partner pricing, not using it** | switch to partner variant | do nothing | **FAIL** |
| HH 37 family of 4 on unlimited, light use | cheaper fit | do nothing ("no cheaper plan fits") | FAIL/unclear |
| TK 03 / 30 / 36 old paid-off phones | upgrade-or-wait with $ comparison + trade-in curve | do nothing, reason = "churn risk is 0.95% so a device upgrade costs more than it saves" | **FAIL (wrong frame)** |
| TK 29 four payments left, TK 07 upgraded 3 mo ago | honest "wait" with dates | do nothing, no wait-until date | weak |
| Cart / Matchmaker personas | out of scope | do nothing / incidental | acceptable only if we don't claim #1/#2 |

**Root cause (structural, in `harness/offers.py`):** every action's benefit is `p_churn × save_rate × customer_value`. With labels calibrated to
0.99%/month (mean `p_churn_90d` = 2.7%), only retention benefit counts, while right-size's cost is the full lost revenue × 12 × P(accept).
**Right-size can mathematically never win** (219 accounts eligible, 0 chosen), and **device upgrade never wins** (1,467 eligible, 0 chosen). The engine is a
retention-cost minimizer; it cannot express "this helps the customer," which is 30% of the rubric and the whole point of brief directions #4 and #5.

---

## 1. Coverage by brief direction and building block

### Direction 3, Next Best Moment (our primary): **mostly covered, with three named gaps**
Brief: churn-risk score → *ranked actions accounting for cost*: **better-fitting plan, proactive credit, relevant perk, check-in**. Inputs: tenure, support,
plan fit vs usage, billing changes, competitor-interest proxies. Convincing = different problems → different actions; discount not automatic; restraint.

| Brief element | Evidence | Status |
|---|---|---|
| Churn-risk score | `harness/out/churn_scores.csv` `p_churn_90d`, `risk_rank`, `risk_reason_1..3`, `stay_reason_1..3` (Model A logistic, `churn_model.py`); persona check PASS (`out/churn_persona_check.txt`) | ✅ |
| Ranked actions | `out/offer_candidates.csv` (9 actions × account, `eligible, expected_value, offer_cost, save_rate, annoyance, reason`); `offers.csv` `ev_*` columns + `runner_up_action` | ⚠️ computed, but **UI shows only winner + runner-up** (`streamlit_app.py` L341-355) |
| Accounting for cost | `offer_cost`, `annoyance`, `customer_value_usd`; EV formula on screen (L251) | ✅ computed; ⚠️ per-action cost breakdown not shown in UI |
| Better-fitting plan | step-up (356 chosen); right-size (0 chosen, structurally can't win) | ⚠️ half: only the upsell direction ever fires |
| Proactive credit | `$25 care credit` (26) + `care credit + fix-first` (274); loyalty credit 0 chosen | ✅ |
| Relevant perk | none (`OFFER_STRATEGY.md` §1a proposes `perk_reminder`) | ❌ |
| Check-in | only `fix-first callback` when there is an open/network issue (359); no no-offer check-in | ❌ for silent churners (persona 21) |
| Inputs: tenure / support | `tenure_months`, `support_90d`, `unresolved_90d`, `avg_sentiment_90d`, `network_contacts_90d`, `cancel_inquiries_270d` | ✅ |
| Plan fit vs usage | `n_lines_over_cap_3m`, `um_near_plan_limit`, `um_plan_overpay`, `plan_misfit` in Model A | ✅ for outgrowing; ⚠️ overpay detected (219) but never acted on |
| Billing changes | `bill_change_3m_pct`, `promo_expired_recent`, `bill_shock_recent`, `days_since_bill_shock`, bill-shock upsell block | ✅ strong |
| Competitor-interest proxies | `competitor_research_score`, `port_out_inquiry`, `app_sessions_30d` in Model A + UI "live" | ⚠️ raise the score, but **no action targets them** (persona 21 → do nothing; 37 step-up upsells go to accounts whose #1 risk reason is "shopping other carriers") |
| Different problems → different actions | crosstab action × top reason: network → fix-first, promo bill → credit, usage → step-up, happy → nothing | ✅ |
| Restraint | do nothing 4,027 / 5,042 (80%); all 130 accounts with p>0.2 get an action | ✅ (maybe *too* much: see §3) |

### Direction 4, Timekeeper: **weak (flags only)**
Have: `um_device_paid_off`, `um_payoff_soon`, `um_old_device` (offers.csv), sandbox `tradein_curves` 0-60 months (unused in UI), device-upgrade action (never chosen).
Missing: now-vs-later $ comparison, trade-in value chart, an explicit "wait until <date>" output, any case where "upgrade now" wins. The brief's convincing
result needs *both* outcomes from visible math. Today all 10 timekeeper personas get the same retention-framed "do nothing."

### Direction 5, Household Mix Optimizer: **weak, and currently gives wrong answers**
Have: right-size search (`offers.py`: cheapest allowed plan where every line's 3-mo peak ≤ 70% of cap, saves ≥ $10/mo); kid lines from real `lines.member_role`
(`enrichment.csv` `n_kid_lines`, `kid_age_band`); `is_family_plan`.
Missing: the recommendation itself (never chosen), savings-vs-current display, 55+/partner variant switches (personas 38/40). Sandbox shares one plan per account,
so per-line mixing is limited; the variant switch and tier right-size are the realistic Household wins.

### Direction 1, Cart Whisperer: **not covered** (fine; brief allows picking). Don't claim it. Sandbox has `/cart` + `personas.starting_cart` if ever wanted.
### Direction 2, Matchmaker: **not covered** (fine). Don't claim it.

### Building blocks
| Block | Covered (evidence) | Missing |
|---|---|---|
| **Commerce & transactions** | plans (`line_prices`, caps, `eligibility`, `price_guarantee_years`), promotions + eligibility rules (care/loyalty/old-phone/trade-in), financing (`financing_months_remaining`, installments), bills; message validator checks every $ against sandbox (`out/message_validation.csv`) | trade-in values (`tradein_curves`) not surfaced; addons/perks (31 rows) unused in actions; no cart |
| **Customer & household** | segment, tenure, language (en/es messages), contact_preference (shown), autopay, discount_group; household: `n_lines`, `member_role`-derived kid lines (enrichment.csv) | household structure **not shown on the card and not used by any chosen action**; contact_preference shown but not used to pick channel; discount_group eligibility (55+/partner) not turned into savings |
| **Timely context** | support 90d/unresolved/sentiment/network, bill change + promo expired, usage growth, payoff soon, competitor score, port-out, app sessions | no support-topic timeline on card; no "why now" line |

---

## 2. Rubric scorecard (honest estimate, current state)

| Criterion | Weight | Est. now | Why | Top fixes (biggest movers first) | Est. after |
|---|---|---|---|---|---|
| Customer value | 30 | **17** | NBM personas mostly right, do-nothing is real, no upsell after bill shock, fix-first beats discounts. But engine cannot recommend saving the customer money (right-size 0/219), upsells the 55+ couple instead of giving 55+ pricing, ignores the port-out silent churner, never says "upgrade now" or "wait until X". Reads as business-only. | (1) Add customer-benefit term / "customer-first" actions that win on their own (right-size, 55+/partner variant, wait-until-payoff) with a trust/retention credit; (2) add `check_in` (no $) for shopping/quiet signals; (3) fix 38/05/40/21. | 24 |
| Use of signals | 25 | **18** | Real commerce + customer + timely signals combined; labeled in UI; validated $ amounts. Competitor signals only raise the score; household (member roles) unused in decisions; enrichment income/job are per-account random draws. | (1) Make competitor/port-out drive a distinct action; (2) show household block (lines, roles, kid lines from real `member_role`) on card and use it in a family action; (3) drop income/job from decisions. | 21 |
| Explainability & trust | 20 | **13** | Plain-English reasons + stay reasons, en/es texts, no names, validated amounts, "we know but don't say" concept. But: persona 28 text mentions school; do-nothing reason is business-speak ("costs more than it saves"); EV breakdown hidden; income/job enrichment is a creepiness risk if shown or used; two different Model Bs in the repo. | (1) Customer-facing "why" line for every outcome incl. wait; (2) show per-action ranked table with cost/save/annoyance; (3) remove "finishing school" + add validator blocklist; (4) show enrichment only as "real plan data" (kid lines) or drop it. | 17 |
| Feasibility & demo | 25 | **15** | Deterministic, runs on judge's own data, nice Streamlit screens, tests. But clean clone: `make run` launches the *old* `app/console_app.py` with a different engine; README describes that old app; `harness/out/` is gitignored so `streamlit_app.py` falls back to mocks; Insights says "14.6% churn" while every card shows ~1-5% risk (labels mean 2.7%); lots of ML eval (Model C, Qini, learning curves, 250k scaled data) that eats demo time without answering the prompt. | (1) One app, one engine, `make demo` that builds out/ then runs streamlit_app; (2) reconcile the churn number; (3) live what-if toggle on card; (4) cut Model C/bench from the 3-min story. | 21 |
| **Total** | 100 | **≈63** | | | **≈83** |

---

## 3. Specific checks

| Check | Answer | Evidence |
|---|---|---|
| Churn produces a ranked SET of actions? | **Computed yes, shown no.** | `offer_candidates.csv` has all 9 with EV; card shows winner + runner-up only (L341-355). |
| Action cost accounted? | **Yes** (offer cost, annoyance, P(accept) for credits); not visible per action in UI. | `offers.py` EV; `offer_candidates.csv offer_cost, annoyance`. |
| Check-in / non-monetary action? | **Partly.** fix-first callback ($15 agent time) only when an issue exists. No pure check-in. | 359 fix-first; persona 21 gets nothing. |
| Do-nothing / no-good-rec wins sometimes? | **Yes, 80%** (4,027/5,042), incl. persona 24 and 10. Risk: it also wins where the honest answer is "save money" or "upgrade/wait," so "restraint" partly = inability. | offers.csv `action` counts. |
| Plan fit vs usage used? | **Outgrowing: yes** (step-up 356). **Overpaying: detected, never acted on** (`um_plan_overpay` 219 → 0 right-size). | offers.csv. |
| Billing changes used? | **Yes, well.** promo-expired, bill shock window, upsell block, care-credit relief. | `bill_shock_recent`, guardrails in OFFERS_README. |
| Competitor-interest proxies used? | **In the score yes; in the decision no.** 37 step-ups go to accounts whose top risk reason is "shopping other carriers", 9 to "asked about porting out". | crosstab of `risk_reason_1` × action. |
| Explanations plain-language? | **Mostly.** Risk/stay reasons and texts are plain. Do-nothing reason is internal math ("Simulated churn risk is 0.95%, so even the best option (device upgrade) costs more than it saves"). | offers.csv `reason`. |
| Recommendation changes when customer changes? | **Across customers yes; within a customer no.** Precomputed CSV, no what-if. The brief's #1/#3 "convincing result" is literally "changes when the customer changes." | streamlit_app.py has no input controls on the card. |
| Enrichment defensible? | **Split verdict.** `kid lines` from real `lines.member_role` + `n_lines` + financing = defensible (carrier's own account data). `recent_job_change` (BLS-rate random draw), `household_income_usd`/`income_band` (ACS-marginal random draw tied to credit tier/bill) are **per-account fabrications**: steering offers on them is "use of noise," and income-based offer steering reads as price discrimination / surveillance to a carrier judge. "We know, but we don't say" can backfire: "you know my income?" The plan doc itself rejected scraping/life-events for the demo. | `harness/enrichment.py` docstring; `OFFER_STRATEGY.md` §5c boosts p_accept on job/income. Not yet used by `offers.py`. |
| Off-prompt drift? | **Yes, moderate.** Model C simulated randomized trial + IPW/DR policy value + Qini (`uplift.py`, `model_c_artifacts/`, Charts screen) = simulated lift vs control, which the plan doc marked RESOLVED as *not in demo*, and it's circular (we wrote the simulator). `harness/bench` learning curves, 50k/250k scaled synthetic data, public-dataset validation: good engineering, zero rubric points beyond a footnote. Income/job enrichment maps to no direction. | git log 6705fb9, b3d1ea6, 9c8924f; `out/scaled_250k/` (98 MB). |

Also noted: Insights hard-codes plan-doc stats (14.6%, 61%, 346, 553, 240/188/234/800) instead of computing them; persona 22's win margin is $5 (one assumption tweak flips the demo beat); `scipy` used by `enrichment.py` but not in requirements.

---

## 4. CRITICAL FLAWS (ranked by judging damage)

1. **The engine cannot recommend anything that saves the customer money or says "upgrade now", so it fails the sandbox's own Household and Timekeeper personas, including one actively wrong answer.** Benefit = churn save only; at 2.7% mean 90-day risk, right-size (0/219 chosen) and device upgrade (0/1,467) can never win. Persona 38 (55+ couple on regular pricing) gets an **upsell to Experience Beyond** while the eligible 55+ move would save $40/mo; persona 05 (top plan, few GB) gets do nothing while $110/mo savings is eligible; 40 (partner pricing unused) gets nothing. Hits Customer value (30) hardest: "does it help the customer as well as the business?"
   **Fix:** add a customer-benefit lane that is *not* priced as pure revenue loss: score `customer_savings × trust_weight + Δretention from fairness` (e.g. right-size gets a lifetime-extension term, or rule: "if an eligible plan/variant saves ≥$10/mo with same coverage, recommend it; restraint means not upselling, not hiding savings"). Add a variant-switch action (55+/partner/community from `plans.eligibility` × `accounts.discount_group`). Block step-up when an eligible cheaper variant exists. Re-run personas 05/37/38/40.

2. **Persona 21 (the brief's textbook competitor-interest case: 6-yr customer, quiet, port-out inquiry, competitor 0.85) gets "do nothing."** The brief names competitor-interest proxies and **check-in** explicitly; we use the proxies only to raise a score, then have no action that addresses them. A judge testing the silent churner sees the system shrug.
   **Fix:** add `check_in` (no $, low cost ~$2-5, on-target for shopping/quiet/port-out, message = neutral "here's what your plan includes / anything we can do?" without mentioning shopping) and a price-lock/plan-review action for shoppers (sandbox `plans.price_guarantee_years`). Block upsells when top driver is shopping/port-out (37+9 step-ups today).

3. **Clean-clone demo is a different product.** `make run` launches `app/console_app.py` (old "Retention Console", old `harness/engine.py` Model B with a 25%-acceptance formula), README documents that app's four screens, and `harness/out/` is gitignored so `app/streamlit_app.py` silently shows **mock** data from a fresh clone. Public repo is a requirement; judges reading it see two contradictory Model Bs.
   **Fix:** one `make demo` = setup → features → labels → churn_model → offers → `streamlit run app/streamlit_app.py`; delete or move console_app/engine to `legacy/`; rewrite README to the current pipeline; or commit a small precomputed `demo_data/` (plan doc already said "precompute so the demo can't break").

4. **On-screen numbers contradict each other.** Insights headline: "Expected to churn in 90 days: 14.6%" (toy labels, hard-coded from plan doc). Every customer card/model: mean 2.7% per 90 days (0.99%/mo calibration). A judge who asks "so is it 15% or 3%?" undermines trust and the 61%-in-top-20% hook.
   **Fix:** pick one (the team plan says 0.99%/mo calibrated) and compute all Insights stats live from `harness/out/` with "synthetic" labels; or show 14.6% only as "sandbox toy score, ranking only."

5. **Inferred life details leak into customer texts, and simulated income/job enrichment is a trust liability.** Persona 28's live text: "We noticed you're getting close to finishing school" (from a student+tenure≥36 heuristic) — exactly the "creepy" pattern our own guardrail forbids. Planned boosts on `recent_job_change`/`income_band` (OFFER_STRATEGY §5c) steer offers on per-account random draws: no signal, plus income-based targeting looks like price discrimination to a carrier judge (Explainability & Trust 20%).
   **Fix:** add the blocklist to `validate_messages()` now (school, graduat, job, promot, income, kid, child, competitor, switch, port) and reword 28 to plan-led ("Your student pricing ends soon; here's a plan that keeps your price at $X"). Keep enrichment to carrier-owned facts (kid lines from `member_role`, lines, financing, promo end) and label "from your account"; drop income/job from decisions, or show them only as a clearly separate "future: consented data" slide.

6. **Ranked set + cost not visible; recommendation can't be changed live.** The brief asks for ranked actions accounting for cost and a result that changes when the customer changes; we compute both but the card shows a single winner and a runner-up from a static CSV. Judges can't see the restraint math or poke it.
   **Fix:** on the card, table of all eligible actions from `offer_candidates.csv` (save value, cost, annoyance, EV, ineligible reason) with do-nothing as the $0 line; add 2-3 what-if toggles (resolve open ticket, remove port-out inquiry, +20 GB usage) that re-score via `offers.py` functions and flip the action live.

7. **Timekeeper is claimed but absent.** "Upgrade moments" are flags; the 10 timekeeper personas all get the same retention-framed "do nothing" with no now-vs-later math or trade-in chart, despite `tradein_curves` being in the sandbox. Either deliver a minimal honest version or stop claiming it.
   **Fix (small):** for any line with an upgrade moment, show a now-vs-wait panel: trade-in value today vs in N months (`tradein_curves`), remaining financing, promo credit; output "Upgrade now / Wait until <payoff date> / Keep it" with the $ difference. Customer-facing text for "wait" is the slogan beat ("the one that says wait").

8. **Demo time goes to off-prompt ML.** Model C (simulated RCT, DR policy value, Qini), learning curves, 250k scaled data appear on the Charts screen. The plan doc resolved "no simulated before/after or control group in the demo," the brief says complex ML isn't required, and judges will spot circularity (we built the simulator we're scoring against).
   **Fix:** keep them in the repo/README as "how we'd measure lift on real data"; remove from the 3-minute path; replace with personas-as-tests table (theme → expected → ours → pass).

9. **Do-nothing explanations are written for us, not the customer.** "Simulated churn risk is 0.95%, so even the best option (device upgrade) costs more than it saves" makes restraint sound like cost-cutting.
   **Fix:** two lines: customer-facing ("Your plan fits how you use it and nothing's wrong, so we won't bother you") + operator line with the math.

10. **Persona 22's showcase win is fragile** (EV $5.41 vs runner-up $0.11; one assumption tweak flips it), and the "price lock for bill shock" story isn't in the engine yet.
    **Fix:** implement the bill-shock relief action (explain promo end + `price_guarantee_years` + care credit) as on-target for `promo_expired`, and add persona golden tests that fail CI if 04/21/22/23/24/25/27/28/05/38 drift.
