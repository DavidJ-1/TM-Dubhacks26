# Offer strategy and prompt fit

> **All customers and numbers here are synthetic or simulated.** Accounts, plans and promotions come from the judge
> sandbox (`mageshkumarj/dubhacks`, every row `data_source = 'stub'`, as of 2026-10-01). Save rates, accept rates and
> lock-in effects are our own assumptions. Enrichment columns (job change, income band) are **simulated**. No real
> T-Mobile customer data. Public T-Mobile facts below are cited with links and were read on 2026-10-17. Promos change.

Written Sat 10/17/2026 (PDT) by the offer-strategy lane. Inputs: `handoff/plan-doc-2026-10-17.txt`, `handoff/LANES.md`,
`sandbox.db` (opened read-only), `harness/out/{features,enrichment,churn_scores,offers}.csv`, `harness/OFFERS_README.md`.

---

## 1. The prompt and how we fit it

**Authoritative prompt:** T-Mobile brief "Reimagining Recommendations in Wireless Commerce" (David's rewrite of
`tmobile-brief.docx`, saved at `/workspace/tmobile/strategy/tmobile-brief-summary.md`). Quoted lines below are from it.
Goal (verbatim): "a recommendation that makes sense for this customer, in this situation, at this time."

### 1a. Brief directions → our pieces

| Direction (brief, verbatim core) | Our fit | What answers it | Honest gaps |
|---|---|---|---|
| **3 Next Best Moment (primary):** "churn-risk score (model or rules) -> ranked actions accounting for cost: better-fitting plan, proactive credit, relevant perk, check-in. Inputs: tenure, support interactions, plan fit vs usage, billing changes, synthetic competitor-interest proxies. Convincing = different problems -> different actions; discount not automatic; restraint." | **Full** | Model A `p_churn_90d` + reasons (inputs: `tenure_months`, support counts/unresolved/sentiment, `plan_misfit_share`/over-cap, `bill_increase_pct`/`promo_expired_recent`, `competitor_research_score`/`port_out_inquiry`). Model B scores every action by EV with cost (`offer_candidates.csv` = the ranked set). Better plan = right-size / step-up; proactive credit = care / loyalty; problem→action = fix-first for network, credit for billing, price-lock for bill shock; restraint = do nothing wins 4,027 / 5,042. | **Relevant perk** has no action yet (propose `perk_reminder`, §5). **Check-in** only exists as fix-first callback for unresolved issues; no no-offer check-in for medium risk (propose `check_in`). The UI must show the *ranked* list with costs, not just the winner. |
| **4 Timekeeper:** "upgrade now vs wait from device age, financing balance, trade-in value decline, usage; transparent now-vs-later cost comparison + trade-in value chart; honest 'wait'." | Partial (upgrade moments) | `um_device_paid_off`, `um_payoff_soon`, `um_old_device`, device-upgrade action, family-upgrade bundle. | No now-vs-later $ comparison and no trade-in chart, though `tradein_curves` (0-60 mo) is in the sandbox. An honest "wait until payoff in N months" isn't an action. Cheap add: `wait_until_payoff` reason text when `financing_months_remaining` ≤ 3. |
| **5 Household Mix:** "2-5 line household ... lowest-cost best-fit config, savings vs current mismatched setup, preserves requirements." | Partial | Right-size (cheapest eligible plan that fits every line's peak), 4-line offer, family-upgrade bundle, kid lines from `member_role`. | One plan per household in the sandbox, so no per-line mix search. Savings vs current is shown only for right-size. |
| **1 Cart Whisperer:** cart → 1-3 add-ons with reasons, "customer benefit over basket size." | Light touch | Family-upgrade bundle adds Protection tier / watch line only when a new phone is in it. | No live cart. Only if cheap. |
| **2 Matchmaker:** quiz → 2-3 bundles. | Not covered | (prospects; out of scope) | Skip. |

Brief framing we use: "financing/trade-in affect affordability & timing" (lock-in and payoff timing), "whole households
and small businesses" (family bundle; **gap:** no SMB-specific action for 392 `smb` accounts), "internet/streaming/insurance/
protection change bundle value" (**gap:** `BUNDLE-HINT` $15 and Protection not yet in the engine; proposed), "retain
before cancellation", "students/young adults budget-sensitive, may keep device" (persona 28; keep-your-phone),
"trust & perceived value" (non-creepy rule, §4).

### 1b. Suggested rubric → evidence

| Rubric row (weight) | Evidence we show | Weak spot |
|---|---|---|
| Customer value (30%): "would a real person want it; helps customer and business; honestly handles no-good-recommendation" | Do-nothing for happy customers (persona 24, 10); fix-first before discounts; price-lock explains a bill jump instead of selling; family upgrade is value, not a discount | Synthetic save rates; can't prove a real person wants it |
| Use of signals (25%): "combine commerce + customer + timely context" | Commerce (plans, promotions, trade-in), customer (lines, kid roles, segment, language), timely (bill change, support, competitor score, payoff) labeled in UI | Enrichment is simulated; tag it |
| Explainability & trust (20%): "plain language a customer accepts" | `why_this_offer` sentence; texts quote only sandbox amounts; "we know, but we don't say" | Persona-28 text currently says "finishing school" (fix) |
| Feasibility & demo (25%) | Deterministic Python + Streamlit on the judge sandbox; validator | Ranked-actions view and perk/check-in actions still to build |

Other sources we checked: sandbox README theme `next_best_moment`: "Who is drifting towards leaving, who is a false
alarm, and what proportionate action fits?"; judge notes in the plan doc ("being helpful at the right time without being
annoying"; "how is this different from typing it into ChatGPT?": no LLM in the product, our own model decides).

**Above and beyond (keep secondary):** lock-in valued in EV, family-upgrade bundle, simulated enrichment that steers
but is never stated, Spanish texts, amount validator, Model C uplift. **Don't drift:** no prospects, no chatbot, no
scraping, no promises T-Mobile can't keep.

## 2. Sandbox catalog (read-only dump, `sandbox.db`)

**Plans (11).** Monthly $ for 1/2/3/4/5 lines (cumulative from `plans.line_prices`), AutoPay included:

| sku | 1/2/3/4/5 lines | extra | guarantee | limits / eligibility |
|---|---|---|---|---|
| `TMO-STUB-PLAN-ESSENTIALS-SAVER` | 55/90 | 35 | none | max 2 lines, 50 GB |
| `TMO-STUB-PLAN-ESSENTIALS` | 65/100/120/140/160 | 20 | none | 50 GB |
| `TMO-STUB-PLAN-ESSENTIALS-4LINE` | –/–/–/120/150 | 30 | none | min 4 lines, `limited_time` |
| `TMO-STUB-PLAN-MORE` | 90/150/185/220/255 | 35 | **5 yr** | upgrade every 3 yrs (stub note) |
| `TMO-STUB-PLAN-MORE-{COMMUNITY,PARTNER}` | 75/110/135/160/185 | 25 | 5 yr | `discount_group` community / partner |
| `TMO-STUB-PLAN-MORE-55` | 75/110 | 35 | 5 yr | 55_plus, max 2 |
| `TMO-STUB-PLAN-BEYOND` | 105/180/230/280/330 | 50 | 5 yr | early upgrade |
| `TMO-STUB-PLAN-BEYOND-{COMMUNITY,PARTNER}` | 90/140/180/220/260 | 40 | 5 yr | community / partner |
| `TMO-STUB-PLAN-BEYOND-55` | 90/140 | 50 | 5 yr | 55_plus, max 2 |

**Promotions (21).** Retention-usable for *existing* customers (no new line / port-in needed) in bold:

| sku | value | payout | key rules |
|---|---|---|---|
| **`PROMO-STUB-CARE-CREDIT`** | $25 | 1 mo | tenure ≥ 6, ≥ 3 support contacts in 90 d (judge-invented) |
| **`PROMO-STUB-LOYALTY-CREDIT`** | $5/mo | open | tenure ≥ 36 (judge-invented) |
| **`PROMO-STUB-OLD-PHONE-UPGRADE`** | $150/device | 24 mo | trade-in, device age ≥ 36 mo (judge-invented) |
| **`PROMO-STUB-TRADEIN-ANY`** | $200/device | 36 mo | trade-in + device, Essentials/More/Beyond |
| **`PROMO-STUB-S26FE`** | $800 | 36 mo | trade-in, DEV-0028, More/Beyond |
| **`PROMO-STUB-STUDENT`** | $20/line | – | discount_group student, ≤ 2 lines |
| **`PROMO-STUB-BUNDLE-HINT`** | $15/mo | – | home_internet add-on, ≥ 1 line |
| `PROMO-STUB-WATCH-LINE` | $300 | 36 mo | ≥ 2 lines + connected_line add-on |
| `PROMO-STUB-FREE-SELECT` | $300.99 | 36 mo | **new line**, prime credit, 4 select devices |
| `PROMO-STUB-IPHONE18PRO` / `FLIP8` / `PIXEL11PROXL` | $1,000 / $1,200 / $1,000 | 36 mo | new line **or** trade-in, More/Beyond (18 Pro: Beyond) |
| `PROMO-STUB-HINT-CARD` | $200 card | – | adds home internet |
| `PROMO-STUB-GROUP-NEW-PHONE` | $900 | 24 mo | new line + port-in, discount plans only |
| `IPHONE17`, `IPHONE17E`, `RAZRPLUS`, `FAMILY-PAYOFF`, `BYOD-CARD`, `KEEP-YOUR-PHONE` | – | – | new line + port-in (switchers): **not usable for retention** |
| `PROMO-STUB-ACC-BUNDLE` | 25% off | – | ≥ 3 accessories |

**Add-ons:** Protection T1–T6 $7/9/13/16/19/26; Home Internet Basic/Plus/Premium $50/60/70; Smartwatch line $10 / Plus $15;
Connected line (Beyond only) $5; Streaming video $3 (More/Beyond).

**Customer signals for offers (real fields):** `accounts.tenure_months, segment, discount_group, credit_tier, language,
contact_preference`; `lines.member_role` (child 1,544 / teen 1,538 lines), `financing_months_remaining, device_purchase_date,
byod, tradein_eligible`; `billing_history.change_reason` (promo_expired 553, installment_ended 752); support topic /
resolved / sentiment; `account_signals.competitor_research_score, port_out_inquiry, app_sessions_30d`.
**Not in sandbox:** contract or price-guarantee start dates, promo end dates (inferred only), income, job, kid ages, geography.

## 3. Real T-Mobile offers → sandbox mapping

| Real public offer (source) | Sandbox match | Fit signals |
|---|---|---|
| Experience Beyond 2.0, $105/180/230/280/330 ([SOC list, 10/13/26](https://tmo.centers.diy/soc/C26L9T1); [t-mobile.com plans](https://www.t-mobile.com/cell-phone-plans)) | `PLAN-BEYOND` (prices match) | heavy hotspot/intl, upgrade-every-year buyers, family upsell from More |
| Experience More 2.0, $90/150/185/220/255 ([SOC list](https://tmo.centers.diy/soc/C26L9T2)) | `PLAN-MORE` (prices match) | near/over 50 GB cap on Essentials, families stepping up |
| Essentials / Essentials Saver ([plans](https://www.t-mobile.com/cell-phone-plans)) | `PLAN-ESSENTIALS`, `-SAVER` | price-sensitive, light users |
| Essentials 4 Line Offer, limited time ([plans](https://www.t-mobile.com/cell-phone-plans)) | `PLAN-ESSENTIALS-4LINE` | 4+ lines on Essentials (right-size) |
| **5-Year Price Guarantee** on Experience plans: talk, text, data price; excludes taxes/fees, add-ons, promos; clock doesn't restart on line adds/plan changes ([FAQ](https://www.t-mobile.com/cell-phone-plans/price-lock-faqs)) | `plans.price_guarantee_years = 5` (More/Beyond only; **no promo row**, no start date) | bill-shock customers already on More/Beyond; lock-in for step-ups |
| Better Value: 3 lines $140, 5-yr guarantee, existing customers need 5+ yrs tenure (Jan 7 2026, [newsroom](https://www.t-mobile.com/news/offers/better-value)) | **no sandbox equivalent** | long-tenure 3+ line families. Doc only, never in texts. |
| Go5G / Go5G Plus / Go5G Next (legacy; Experience More "includes all the benefits of Go5G Plus", [newsroom](https://www.t-mobile.com/news/un-carrier/why-new-experience-plans-are-for-you)) | **no sandbox equivalent** (sandbox has only 2.0 plans) | n/a |
| 55+ plans: Experience More 55+ $75/1 line, $110/2 ([t-mobile.com 55+](https://www.t-mobile.com/cell-phone-plans/unlimited-55-senior-discount-plans)) | `PLAN-MORE-55`, `PLAN-BEYOND-55` (match) | `discount_group = 55_plus`, ≤ 2 lines |
| Military / first responder plans ([military](https://www.t-mobile.com/cell-phone-plans/military-discount-plans)) | probable analog `*-COMMUNITY` / `*-PARTNER` (**unconfirmed**; sandbox has no military group) | `discount_group` community / partner |
| iPhone trade-in up to $1,000 over up to 36 credits, from 10/1/26 ([promo details](https://www.t-mobile.com/offers/promotional-offer-details); [Kiplinger 10/14/26](https://www.kiplinger.com/personal-finance/gadgets/t-mobile-iphone-18-deals)) | `PROMO-STUB-IPHONE18PRO` ($1,000 / 36 mo, Beyond) | old/paid-off phone, Beyond or stepping up |
| Trade-in any condition ([trade-in](https://www.t-mobile.com/devices/phone-trade-in)) | `PROMO-STUB-TRADEIN-ANY` ($200) / `OLD-PHONE-UPGRADE` ($150) | `tradein_eligible`, device age ≥ 36 mo, `installment_ended` |
| Upgrade-ready every year / 2 years ([plans](https://www.t-mobile.com/cell-phone-plans); [support](https://www.t-mobile.com/support/plans-features/upgrade-ready-every-year)) | `plans.upgrade_note` (text only) | upgrade moment on More/Beyond |
| SyncUP KIDS Watch: needs own watch line; $5/mo with Beyond ([SOC list](https://tmo.centers.diy/soc/C25KIDNEB); [product](https://www.t-mobile.com/smart-watch/t-mobile-syncup-kids-watch-2)) | `ADD-LINE-WATCH` $10, `ADD-LINE-CONNECTED-BEYOND` $5, `PROMO-STUB-WATCH-LINE` $300 | `kid_age_band = 0-12`, ≥ 2 lines |
| Kid's first phone on a new line ("3rd line free" on More for new customers, [bundle page](https://www.t-mobile.com/cell-phone-plans/phone-home-internet-bundle)) | `PROMO-STUB-FREE-SELECT` ($300.99, new line, prime) + plan's next-line price | family plan, prime credit |
| 5G Home Internet $50/60/70, $15 off with a voice line, 5-yr guarantee ([HINT plans](https://www.t-mobile.com/home-internet/plans)) | `ADD-HINT-BASIC/PLUS/PREMIUM` (match) + `PROMO-STUB-BUNDLE-HINT` $15 | no HINT add-on, family/couple |
| Protection 360 $7/9/13/16/19/26 by tier (from 3/1/26, [Assurant notice](https://mytmoclaim.com/media/53uhgd5s/ms98691-1025.pdf)) | `ADD-PROT-T1..T6` (exact match) | new phone in bundle, device-topic contacts |
| T-Mobile Tuesdays / Magenta Status perks ([Tuesdays](https://www.t-mobile.com/support/new-to-tmobile/t-mobile-tuesdays); [Magenta Status](https://www.t-mobile.com/news/un-carrier/magenta-status)) | **no sandbox equivalent** (non-monetary) | low-risk "full value" nudge, no $ in text |
| Loyalty $5/mo, care $25 goodwill | `LOYALTY-CREDIT`, `CARE-CREDIT` (**judge-invented**, `source=stub`, no public equivalent) | tenure / support pain |

Public facts with no t-mobile.com page we could read (JS-loaded prices) cite the third-party SOC list; treat as lower confidence.

## 4. The recommendation story

1. **Model A flags** `p_churn_90d` + reasons (tm-churn). 2. **Signals + enrichment** decide the segment:
real fields (lines, kid lines from `member_role`, financing left, promo expired, support, plan fit) plus simulated
enrichment (`recent_job_change`, `income_band`). 3. **Model B** scores every eligible action by EV with lock-in
value, "do nothing" = 0. 4. **Message** quotes only sandbox amounts and only facts the customer already knows.

**"We know, but we don't say."** Non-creepy means the text only references things a customer *expects* their carrier
to know: their plan, bill, lines, phone age/payoff, usage vs cap, their own support contacts. Inferred or enriched
details (job change, income, kids' ages, "graduating", competitor research, port-out inquiry) may **steer** the
offer but are **never** mentioned. No "we saw you got promoted", no "your kids", no "we noticed you're shopping around".
Note: today's persona-28 text ("We noticed you're getting close to finishing school") breaks this rule; reword.

### Synthetic examples (sandbox accounts; enrichment simulated)

| Account | Signals | Segment → action | Sample message (en) |
|---|---|---|---|
| `ACC-03170` | 4 lines on Essentials, 2 `child` lines (band 0-12), ~45 of 50 GB used, primary phone from 2022 paid off; sim: `recent_job_change=1`, `$100-150k` | **family upgrade**: Experience More (+$80/mo for 4 lines) + `TRADEIN-ANY` $200 on the old phone; lock 36 mo credits, 5-yr guarantee | "Hi there. Your 4 lines are close to your 50 GB limit. Experience More gives every line unlimited premium data for $80/month more, with your talk, text and data price guaranteed for 5 years, plus $200 off a new phone when you trade one in (over 36 months). Reply YES for details. Reply STOP to opt out." |
| `ACC-PERSONA-22` | More plan, bill +22% after promo ended, 2 unresolved billing contacts | **bill-shock price lock**: explain + 5-yr guarantee + `CARE-CREDIT` $25 (no upsell) | "Hi there. Your bill went up because a promo credit ended, not your plan price: your talk, text and data price on Experience More is guaranteed for 5 years. We'd like to add a one-time $25 credit. Reply YES to accept. Reply STOP to opt out." |
| `ACC-PERSONA-24` | 9 contacts, all resolved, heavy app use, p_churn 0.3% | **do nothing** (false alarm) | (no message) |
| `ACC-01310` | 3 lines Essentials, teen phone from 2022 paid off; bill +26%, unresolved device issue; sim: job change, `$200k+` | **fix-first now**, family upgrade *queued* until resolved + 90 d after bill shock | "Hi there. You have 1 support request we haven't resolved yet. Reply YES and a specialist will call you to fix it. Reply STOP to opt out." |
| `ACC-PERSONA-28` | 1 line Saver, `student`, tenure 40 | **step-up** (life-event heuristic), reworded | "Hi there. Your plan is our Essentials Saver. Essentials 2.0 lets you add lines later for $10/month more. Reply YES to learn more. Reply STOP to opt out." |

## 5. Proposals for tm-offers (drop-in spec)

Same text is in `handoff/tm-offers-proposals.txt` (not committed). All rates synthetic.

### 5a. New `offers.csv` columns (for tm-ui)
`segment` (e.g. `family upgrade`, `bill-shock price lock`, `fix first`, `do nothing`), `why_this_offer` (one sentence),
`lock_in_months` (int), `message_en`, `message_es`, `enrichment_signals` (`;`-list of drivers, e.g.
`recent_job_change;kid_age_band=0-12;income_band=$100-150k`, each tagged `enrichment (simulated)` or `real` in the UI),
`promo_skus` (`;`-list of sandbox skus the amounts come from).

### 5b. EV with lock-in
```
EV = p_churn × save_rate × value + p_accept × upsell_gain + lock_value − p_accept × credit_cost − annoyance
h          = 1 − (1 − p_churn_90d)^(1/3)                         # monthly hazard
lock_value = p_accept × [ (1 − h·(1−LOCK_CUT))^L − (1 − h)^L ] × monthly_margin × VALUE_HORIZON_MONTHS
L          = lock_in_months;  LOCK_CUT = 0.50 if a 36-mo device credit is forfeited on leaving, 0.20 for price guarantee alone (synthetic)
```

### 5c. Segment → offer rules (YAML-ish)
```yaml
config:
  LOCK_TERM_MONTHS: {device_credit_36: 36, device_credit_24: 24, price_guarantee: 60}
  LOCK_CUT: {device_credit: 0.50, price_guarantee: 0.20}
  MARGIN_FLOOR_USD: 0          # EV after costs must be > 0, else do nothing
  MAX_STEP_UP_PCT_INCOME: 1.5  # step_up_cost_pct_income cap (enrichment, simulated)
  CONTACT_COOLDOWN_DAYS: 30

do_nothing:            # always eligible, EV 0; forced when p_churn_90d < 0.02 and no upgrade moment
  segment: do nothing

family_upgrade:        # NOT a discount: better plan + new phones + longer lock
  maps_to: [plans.next_plan_sku (Essentials->More, More->Beyond), PROMO-STUB-TRADEIN-ANY, PROMO-STUB-OLD-PHONE-UPGRADE,
            PROMO-STUB-FREE-SELECT (only if adding a line), PROMO-STUB-WATCH-LINE (kid_age_band 0-12, connected line)]
  eligible: is_family_plan==1 AND likely_kid_flag==1 AND plan_family in (essentials, experience_more)
            AND n_tradein_eligible_lines>=1 AND (n_lines_device_36m_plus>=1 OR um_device_paid_off OR um_near_plan_limit)
            AND NOT bill_shock_recent AND unresolved_90d==0
  boost (steer only, never in text): recent_job_change==1 -> p_accept×1.5; income_band>=$100k -> p_accept×1.3;
            step_up_cost_pct_income <= MAX_STEP_UP_PCT_INCOME
  fallback without enrichment: kid lines from lines.member_role (child/teen) + plan data only
  p_accept: 0.20 base (synthetic); save_rate on/off target 0.18/0.05
  cost: p_accept × Σ device credits (one promo per device, best of TRADEIN-ANY $200 / OLD-PHONE-UPGRADE $150)
  upsell_gain: p_accept × plan delta × 0.8 × 24 + p_accept × $80 per device
  lock_in_months: 36 (credit) ; price guarantee 60 if moving onto More/Beyond
  why: "Their family plan is near its data limit and a phone is paid off, so a better plan with new phones and a 5-year price guarantee fits."

bill_shock_price_lock:  # replaces the plain $25 care credit when the plan has a guarantee
  maps_to: [plans.price_guarantee_years (More/Beyond), PROMO-STUB-CARE-CREDIT, PROMO-STUB-LOYALTY-CREDIT (tenure>=36)]
  eligible: bill_shock_recent AND plan.price_guarantee_years>=5
  essentials_case: no guaranteed plan within $10/mo (sandbox: +$25..$95/mo), so keep care credit / right-size; do NOT upsell
  save_rate on/off: 0.30/0.08 ; cost: $25 (+ $5×12 if loyalty) ; lock_in_months: 12 if loyalty credit, else 0
  why: "Their bill jumped because a promo ended, so we explain their 5-year price guarantee and add a $25 credit instead of selling."

fix_first: unchanged (unresolved_90d>0 or 2+ network contacts); queue upsells until resolved.

perk_reminder:         # brief's "relevant perk"; zero $ cost
  maps_to: [plans.perks (streaming-video-ads, streaming-video-bundle, satellite-connectivity), ADD-STREAM-VIDEO $3]
  eligible: plan has perks AND streaming_hours_3m_avg >= 20 AND has_streaming_addon==0 AND p_churn_90d >= 0.05
  save_rate on/off: 0.08/0.03 ; cost: 0 ; annoyance: 2 ; lock_in_months: 0
  text: "Your Experience More plan already includes a streaming video service with ads. ..." (perk wording from plans.perks only; the sandbox doesn't name Netflix)

check_in:              # brief's "check-in"; no offer, no $
  eligible: 0.05 <= p_churn_90d < 0.15 AND unresolved_90d==0 AND no other action EV > 0
  save_rate: 0.05 ; cost: $2 message ; annoyance: 2 ; channel = contact_preference

home_internet_bundle:  # brief's internet bundle value
  maps_to: [ADD-HINT-BASIC/PLUS/PREMIUM, PROMO-STUB-BUNDLE-HINT ($15/mo), PROMO-STUB-HINT-CARD ($200)]
  eligible: has_home_internet==0 AND n_lines>=2 AND NOT bill_shock_recent ; p_accept 0.05 (synthetic)
step_up / device_upgrade / care_credit / loyalty_credit / right_size: unchanged.

guardrails:
  - no bill credit / goodwill credit when p_churn_90d < 0.05 (not at risk); purchase-attached device promos
    (trade-in credits paid only if they buy) are allowed for upsells
  - no upsell for 90 d after bill shock; no upsell with unresolved contacts
  - EV must beat do nothing by MARGIN_FLOOR_USD after credit cost (margin floor)
  - one device promo per device; only promos usable without new line/port-in, except FREE-SELECT for a new line
  - never quote public-only offers (Better Value, Go5G, Tuesdays $) in texts; validator checks $ and "N years" against plans/promotions
  - enrichment never appears in message_en/es (validator blocklist: job, promot, income, kid, child, school, graduat, competitor, switch)
```

### 5d. Message templates (validated amounts only)
- family_upgrade en: "Hi there. {why_fact}. {next_plan} gives every line unlimited premium data for ${delta}/month more, with your talk, text and data price guaranteed for {years} years, plus ${credit} off a new phone when you trade one in (over {months} months). Reply YES for details. Reply STOP to opt out."
- family_upgrade es: "Hola. {why_fact_es}. {next_plan} le da datos premium ilimitados en cada línea por ${delta} más al mes, con el precio de llamadas, textos y datos garantizado por {years} años, y ${credit} de descuento en un teléfono nuevo al entregar uno (en {months} meses). Responda SÍ para más detalles. Responda STOP para no recibir mensajes."
- bill_shock_price_lock en: "Hi there. Your bill went up because a promo credit ended, not your plan price: your talk, text and data price on {plan} is guaranteed for {years} years. We'd like to add a one-time $25 credit. Reply YES to accept. Reply STOP to opt out."
- bill_shock_price_lock es: "Hola. Su factura subió porque terminó un crédito promocional, no el precio de su plan: el precio de llamadas, textos y datos en {plan} está garantizado por {years} años. Queremos darle un crédito único de $25. Responda SÍ para aceptar. Responda STOP para no recibir mensajes."

## 6. Key uncertainties
- **Prompt text:** we used David's rewrite of the brief (rubric marked "suggested"), not the original .docx. Confirm the rubric with the judges.
- **Parallel research not folded in:** `/workspace/tmobile/strategy/research/` was empty when this was committed; §3 uses this lane's own searches. Merge later.
- **Price guarantee:** the sandbox has the 5-yr flag on plans but no start date, so remaining guarantee months are unknown. Publicly it covers talk/text/data only, not expiring promos or fees, so we never say "your bill won't change".
- **Essentials bill shock (245 accounts):** no guaranteed plan within $10/mo, so a price lock there would be an upsell. Better Value would fit but has no sandbox row.
- **No sandbox match:** Better Value, Go5G family, military/first-responder (community/partner is only a guess), Tuesdays/Magenta Status, kid-specific lines.
- **Kid ages:** `member_role` child/teen → bands are an assumption (tm-data's enrichment, uncommitted at time of writing). "Reaching phone age" can't be seen; kids with no line are invisible.
- **Stale public info:** device promos rotate monthly (the iPhone promo started 10/1/26); some prices come from a third-party SOC list because t-mobile.com loads them with JavaScript.
- **Rates:** every save/accept/lock rate here is synthetic and untested; Model C's simulated trial is the only check.
