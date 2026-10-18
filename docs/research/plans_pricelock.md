# T-Mobile postpaid plans and price guarantees: real offers mapped to the sandbox

Research for DubHacks '26 (strategy research). All facts were accessed on **2026-10-17** unless marked otherwise. The project's customer data is synthetic. Real prices are listed for **fidelity checks only**: customer texts may quote only dollar amounts that exist in the sandbox `plans` or `promotions` tables.
Sandbox: `vendor/dubhacks/data/sandbox.db`, opened read-only (`mode=ro`). metadata: brand "T-Mobile (stub data, not official)", as_of 2026-10-01, schema_version 9, seed 2026.

## Sources (short keys)
- **[PLANS]** https://www.t-mobile.com/cell-phone-plans: plan cards, footnotes and FAQ.
- **[LABELS]** https://www.t-mobile.com/cell-phone-plans/military-discount-plans: the page renders FCC Broadband Facts labels for *every* 2.0 plan (standard, 55+, Military, First Responder, Essentials variants, Student).
- **[PG]** https://www.t-mobile.com/cell-phone-plans/price-lock-faqs: 5-Year Price Guarantee, Price Lock and Un-contract FAQ.
- **[AUTOPAY]** https://www.t-mobile.com/support/account/autopay
- **[AA-2.0]** https://www.androidauthority.com/t-mobile-essential-and-experience-2-plans-3694560/ (Aug 4, 2026): the 2.0 launch on Aug 6, 2026.
- **[VERGE]** https://www.theverge.com/tech/959144/t-mobile-legacy-plan-retire-sprint (Jun 29, 2026): legacy plan retirement.
- **[MIG]** https://tmo.report/2026/07/heres-every-t-mobile-experience-migration-plan-along-with-prices/ and https://www.androidauthority.com/t-mobile-forced-plan-migration-details-3683209/: Experience Signature / "TI" migration plans. *Third-party, leaked from a spreadsheet.*
- **[TECHTIMES]** https://www.techtimes.com/articles/320685/20260716/t-mobile-abandoned-written-rate-promises-millions-what-customers-can-do.htm
- **[FF]** https://www.t-mobile.com/support/new-to-tmobile/family-freedom · **[KS]** https://www.t-mobile.com/support/new-to-tmobile/keep-and-switch · **[TMONEWS-SW]** https://www.tmonews.com/2026/07/t-mobile-restricts-switcher-promos-as-migration-problems-surface/
- **[DOC]** https://www.doctorofcredit.com/ymmv-t-mobile-70-retention-credit-for-remaining-with-the-carrier/ (updated Aug 15, 2026) · **[TMONEWS-RET]** https://www.tmonews.com/2026/06/t-mobile-customers-are-swapping-tips-on-a-possible-insider-style-retention-discount/: *anecdotal retention offers, not official.*
- **[M13]** https://month13mobile.com/leaving/t-mobile (updated Oct 3, 2026): third-party summary of the fee change date.

## 1. Current lineup ("2.0", live since Aug 6, 2026 [AA-2.0])
Prices are the monthly **total for N lines, before AutoPay**, from the Broadband Facts labels [LABELS]. The labels say: "Does not include AutoPay or other discounts", "not an introductory rate", ETF $0.

| Plan | 1 | 2 | 3 | 4 | 5 | Extra lines | Key features |
|---|---|---|---|---|---|---|---|
| Essentials Saver 2.0 | $55 | $90 | – | – | – | max 2 | 50GB premium data, then deprioritized; hotspot at 3G speed; **no price guarantee** |
| Essentials 2.0 | $65 | $100 | $120 | $140 | $160 | 6th line $20 | same as Saver |
| Essentials 2.0 4 Line Offer (limited time) | – | – | – | $120 | $150 | 6th line $30 | 4–6 lines only |
| Experience More 2.0 | $90 | $150 | $185 | $220 | $255 | 6–8: $35, 9–12: $40 | unlimited premium data, 60GB hotspot, 15GB CA/MX, 5GB intl, Netflix w/ ads, Apple TV $3, 4K, **5-yr guarantee**, "upgrade ready every three years" |
| Experience Beyond 2.0 | $105 | $180 | $230 | $280 | $330 | 6–8: $50, 9–12: $55 | 250GB hotspot (then 3G), 30GB CA/MX, 15GB intl, Hulu + Netflix, T-Satellite, $5 watch/tablet lines, early upgrade (6+ months and 50% paid), **5-yr guarantee** |
| Experience More w/ 55+ 2.0 | $75 | $110 | – | – | – | max 2 | More features; 5-yr guarantee |
| Experience Beyond w/ 55+ 2.0 | $90 | $140 | – | – | – | max 2 | Beyond features |
| Experience More w/ Military **or** First Responder 2.0 | $75 | $110 | $135 | $160 | $185 | 6th line $25, 7–12: $35 | FR version adds T-Priority ON US. Military: verify within 45 days or pay up to $20/line more |
| Experience Beyond w/ Military **or** First Responder 2.0 | $90 | $140 | $180 | $220 | $260 | 6th line $40, 7–12: $50 | same as above |
| Essentials Choice 55+ 2.0 | $50 | $70 | – | – | – | max 2 | adds Scam Shield Premium |
| Essentials Military / First Responder 2.0 | $50 | $90 | $105 | $130 | $145 | 6th line $15 | |
| Experience More Student 2.0 | $70 | $120 | | | | | student verification required |
| Experience Beyond Student 2.0 | $85 | $140 | | | | | label lists 120GB of data (?) |
| Student Perks plan | $30/line with AutoPay [AA-2.0] | | | | | | plus 12 months of DashPass and other perks. Not checked on t-mobile.com |

**AutoPay** [AUTOPAY][PLANS]: a $5/line/month credit for up to 8 lines. Requires a debit card or bank account; credit cards and digital wallets don't qualify. The prior bill must be paid on time, and AutoPay must be active when the bill is processed. The home-internet bundle page also says "otherwise $5 more/line/month" (https://www.t-mobile.com/cell-phone-plans/phone-home-internet-bundle). *Note: the AutoPay support page's list of eligible plans still names Go5G, Magenta and Essentials, not Experience. The plan pages show AutoPay applied to Experience.*

**Taxes and fees** (all plans are tax-exclusive) [LABELS]:
- Regulatory Programs & Telco Recovery Fee: **$5.49 per voice line** ($0.50 RPF + $4.99 TRF) and $2.60 per mobile-internet line. T-Mobile states this is not a government tax.
- Federal and local surcharges: typically $0.08–$4.57 per line.
- Government taxes: vary by location.
- One-time device connection charge: $35 per line.
- *Stale data note:* a cached [PLANS] label still shows $4.49. [M13] says it rose to $5.49 on **Oct 12, 2026**.

**3rd Line Free** [PLANS FAQ]: available to **new accounts** with 3 or more voice lines on Essentials, More or Beyond. It's paid as monthly bill credits and lasts as long as 3 or more lines stay on an eligible plan. It can't be combined with 55+, Military or First Responder plans, and is limited to one per account.

## 2. The 5-Year Price Guarantee: what's locked and what isn't [PG][PLANS]
- **Who gets it:** new accounts on an Experience smartphone plan, or existing accounts that switch to one (since Apr 23, 2025). Also any account T-Mobile **moved to a qualifying plan in 2026**, which covers the legacy migration.
- **What's locked:** the monthly price of talk, text and T-Mobile 5G data, for 5 years from activation or plan enrollment. This also covers data on watch, tablet and mobile-internet lines attached to the plan.
- **No reset:** adding lines, or switching from one Experience plan to another, does **not** restart the 5 years. The locked price is the published price on the date each line was activated.
- **Not locked:** taxes and fees (including the $5.49 fee), per-use charges, plan add-ons, third-party services (streaming, international data, satellite), equipment prices and promotions, one-time credits, some features (Scam Shield Premium, voicemail-to-text), JUMP!, and network management. For the internet version, discounts such as AutoPay and limited-time promos such as free lines are also excluded. The voice FAQ lists "discounts" as excluded for Price Lock, not explicitly for the 5-Year Guarantee.
- **Switching off forfeits it:** moving to a non-qualifying plan loses the price promotion, and you can't go back to restore it.
- **Essentials plans are not covered.**
- **Legacy guarantees:** "Last Month Price Lock" (Jan 18, 2024 to Apr 22, 2025) covered Go5G, Go5G Plus, Go5G Next, Essentials, Magenta, 55+, Military and FR. If T-Mobile raises the price and you leave within 60 days, it pays your final month. "Original Price Lock" covers Apr 28, 2022 to Jan 17, 2024, and the "Un-contract Promise" covers accounts from before Apr 28, 2022.
- **Trust caveat:** in the July 2026 legacy migration, T-Mobile moved customers off Price Lock and Un-contract plans, some at higher prices [VERGE][TECHTIMES]. A "guarantee" pitch will sound hollow to those customers, so messages should say exactly what is locked.

## 3. Legacy plans (Go5G / Go5G Plus / Go5G Next / Magenta)
- Starting Jun 29, 2026, T-Mobile notified customers that it was retiring Simple Choice, ONE, Magenta, Magenta MAX and Sprint plans. The migration took effect around Jul 13, 2026 [VERGE][TECHTIMES]. Customers couldn't choose their destination plan. More than 1,100 plan codes were retired.
- **Go5G, Go5G Plus and Go5G Next were not migrated** [TECHTIMES]. These are no longer sold, but existing customers keep them. [PLANS] still mentions Go5G Next (T-Satellite included).
- **Migration destinations** [MIG] (*leaked spreadsheet; treat as uncertain*):
  - Experience Signature: priced like Experience More, with variants A/B/C/Family/55+/Military/FR. Family (A) is $81 for 1 line and $142 for 2 lines with AutoPay, plus $31 per extra line.
  - Experience Signature (Select): fewer perks.
  - Experience More TI and Experience Beyond TI (taxes included): More TI (A) $90/$150, plus $35 per line; Beyond TI $100/$170, plus $45 per line.
  - All of these get the 5-year guarantee.
- The migration also wiped some customers' free lines. T-Mobile says it is restoring and backdating them [TMONEWS-SW].

## 4. Changing plans
- **Upgrading or downgrading between Experience plans** keeps the original 5-year clock [PG].
- **Moving to Essentials** loses the guarantee [PG].
- Plan-tied promos can end: home-internet bundle and 3rd-line credits "end if you cancel any lines or change plans" (bundle page above). The 3rd Line Free promo needs an eligible plan with 3 or more lines [PLANS].
- **Beyond's early upgrade** needs a qualifying financed device kept 6+ months with 50% paid off. Upgrading ends the current financing and any promo credits [PLANS fn1]. The new **EIP Flex/Standard 36-month** financing [AA-2.0] means "50% paid" takes about 18 months.
- *Uncertain:* the [PLANS] card text (likely cached) says More is "upgrade every 2 years" and Beyond "every year". The 2.0 labels on [LABELS] say More is "upgrade ready every three years" and Beyond offers "early upgrade". **Use the 2.0 label wording (3 years).**

## 5. Switcher and retention credits that are publicly described
- **Family Freedom** [FF]: up to $800 per line (maximum 4 lines), paid as a virtual prepaid card, toward the old carrier's device balance or ETF. Requires a port-in, trade-in, new phone on EIP and qualifying credit. **New accounts only since Jul 9, 2026.** Plan page pitch: 4 phones On Us for $100/month (https://www.t-mobile.com/switch/pay-off-carrier-etf-phone-deal).
- **Keep and Switch** [KS]: same $800/line card for customers who keep their current phone (unlocked, financed 90+ days, 3+ payments made). **New accounts only since Jul 9, 2026** [TMONEWS-SW].
- **Retention:** T-Mobile has published **no official retention offer**. Anecdotal reports: "$30 + $10/month for 6 months" is the most common, with other reports of $10–$20/month for 6–12 months [DOC]. Some customers report a roughly 20% "Insider-style" discount if they move to a premium plan [TMONEWS-RET]. These are useful only as **plausibility anchors** for synthetic save-offer sizes, never as real offers.

## 6. Mapping table

| Real offer | Key terms | Source | Sandbox match | Fit signals (sandbox fields) | Retention use |
|---|---|---|---|---|---|
| Essentials Saver 2.0 | $55/$90 for 1/2 lines; 50GB premium data; no guarantee | [LABELS] | `TMO-STUB-PLAN-ESSENTIALS-SAVER` (5500,3500 ✓) | `usage_monthly.data_gb` low, `segment` single/couple/student, budget, BYOD | Downgrade target for low-use customers who are overpaying ("better-fitting plan"). Warn that they'd lose the guarantee and perks |
| Essentials 2.0 | $65/100/120/140/160 | [LABELS] | `TMO-STUB-PLAN-ESSENTIALS` (6500,3500,2000×3 ✓) | same; `n_lines` | Downgrade target. **Upgrade source:** lines averaging >50GB are deprioritized (229 sandbox lines on Essentials average >50GB over the last 3 months) |
| Essentials 4 Line Offer 2.0 | $120 for 4 lines, $150 for 5; 4–6 lines; limited time | [LABELS] | `TMO-STUB-PLAN-ESSENTIALS-4LINE` (3000×5 ✓) | `n_lines`≥4, family, low data use | Household optimizer: a family of 4–5 on standard Essentials saves $20 |
| Experience More 2.0 | $90/150/185/220/255; 60GB hotspot; Netflix; 5-yr guarantee; 3-yr upgrade | [LABELS] | `TMO-STUB-PLAN-MORE` (9000,6000,3500×3 ✓; upgrade_note "three years" ✓) | data_gb 20–50, streaming_hours, hotspot_gb, `language`, `billing_history.promo_expired` | Upgrade target for heavy Essentials users. Downgrade target for Beyond users who don't use hotspot or international data |
| Experience Beyond 2.0 | $105/180/230/280/330; 250GB hotspot; satellite; Hulu; $5 watch/tablet lines; early upgrade | [LABELS] | `TMO-STUB-PLAN-BEYOND` (10500,7500,5000×3 ✓) | hotspot_gb, financed device age (`device_purchase_date`, `financing_balance_cents`), `line_addons` connected lines | Upgrade target for heavy hotspot users, travelers and multi-device households. **Downgrade source:** 1,363 sandbox Beyond lines average <15GB data and <2GB hotspot. Check that they don't value the perks first |
| More / Beyond w/ 55+ 2.0 | More $75/$110, Beyond $90/$140; max 2 lines | [LABELS] | `TMO-STUB-PLAN-MORE-55`, `-BEYOND-55` (✓ prices, max 2) | `accounts.discount_group='55_plus'` (262 accounts), `segment='senior'` | Move eligible 55+ customers who are on standard plans: saves $15–40/month with the guarantee kept |
| More / Beyond w/ Military 2.0 | More $75/110/135/160/185; Beyond $90/140/180/220/260 | [LABELS] | **Inferred:** `-MORE-PARTNER`, `-BEYOND-PARTNER` (prices match exactly) | `discount_group='partner'` (96 accounts) | Eligibility-based savings, the same idea as 55+ |
| More / Beyond w/ First Responder 2.0 | same prices as Military; plus T-Priority | [LABELS] | **Inferred:** `-MORE-COMMUNITY`, `-BEYOND-COMMUNITY` (prices match; `priority_network=1` ≈ T-Priority) | `discount_group='community'` (85 accounts) | same as above |
| Essentials Choice 55+, Essentials Military/FR 2.0 | $50/$70; $50/90/105/130/145 | [LABELS] | **no sandbox equivalent** | – | Can't be texted; mention only in the strategy doc |
| Student plans (More/Beyond Student 2.0, Student Perks $30) | $70/$120; $85/$140; $30 with AutoPay | [LABELS][AA-2.0] | **Partial:** `PROMO-STUB-STUDENT` ($20/line/month, max 2 lines, `discount_groups='student'`) | `discount_group='student'` (431 accounts), `segment='student'` | Budget-sensitive student or graduating customer: student credit, or keep the current phone (BYOD) |
| 5-Year Price Guarantee | talk/text/5G data price for 5 years; excludes taxes, fees, add-ons and third-party services; switching between Experience plans doesn't reset it | [PG][PLANS] | `plans.price_guarantee_years=5` on all More/Beyond variants; NULL on Essentials ✓. **No standalone "price lock" promo.** | `billing_history.change_reason` in ('promo_expired','installment_ended'), `change_cents`>0 | **Bill-shock action:** "move to Experience to lock your price" for Essentials or legacy customers. It isn't a credit, so its cost is $0 in credits. Only fair if the plan price doesn't rise. Don't promise taxes or fees are locked |
| Last Month Price Lock / Un-contract (legacy) | if T-Mobile raises the price, it pays your final month | [PG] | **no sandbox equivalent** | – | Background only |
| Go5G / Go5G Plus / Go5G Next (still on existing accounts) | not sold; not migrated in 2026 | [TECHTIMES][PG] | **no sandbox equivalent** (sandbox has only the 2.0 plans) | – | Could become synthetic "legacy" lines in the future |
| Experience Signature / More TI / Beyond TI (2026 migration targets) | e.g. Signature Family (A) $81/$142 + $31/line with AutoPay | [MIG] (third-party) | **no sandbox equivalent** | – | Migrated customers are a natural churn-risk group (forced move, price increase). Not modeled in the sandbox |
| AutoPay discount | $5/line/month, up to 8 lines; debit or bank only | [AUTOPAY] | `accounts.autopay` (3,499 yes / 1,543 no); `plans.prices_include_autopay=1` | autopay=0 together with bill-shock | **Cheapest save:** "turn on AutoPay to save $5/line". There's no promo row, so the dollar amount can't be texted unless it's added. See uncertainty #1 |
| 3rd Line Free | new accounts with 3+ lines; bill credits | [PLANS] | **no sandbox equivalent** | – | Acquisition only, so it doesn't fit retention |
| Family Freedom | up to $800/line (max 4); port-in + trade-in + EIP; new accounts only | [FF] | `PROMO-STUB-FAMILY-PAYOFF` ($800, prepaid card, new line + port-in) ✓ | – | Acquisition only. Useful as the *competitor-mirror* case: rivals pay off phones too, so it's a churn-risk signal |
| Keep and Switch | up to $800/line for a kept, financed phone; new accounts only | [KS] | **Partial:** `PROMO-STUB-BYOD-CARD` ($200/line, BYOD, port-in) | – | Acquisition only |
| Retention credits (unofficial) | ~$30 + $10/month for 6 months; $10–20/month for 6–12 months; ~20% for moving to premium | [DOC][TMONEWS-RET] | `PROMO-STUB-LOYALTY-CREDIT` ($5/month, 36+ months tenure, source 'stub'); `PROMO-STUB-CARE-CREDIT` ($25 once, 3+ support contacts in 90 days, 6+ months tenure, source 'stub') | `tenure_months`, `support_interactions`, `account_signals.port_out_inquiry`, `competitor_research_score` | Proactive credit **only** for care or bill-shock problems. Sandbox amounts sit at the low end of the real anecdotes, which is fine |
| Home Internet bundle | $15/month off with a phone line (bundle page) | bundle page | `PROMO-STUB-BUNDLE-HINT` ($15/month) ✓ | `account_addons` no home internet | Perk or bundle action (outside this doc's scope) |

## 7. Rules for "better-fitting plan" actions (for the offer engine's EV engine)
1. **Upgrade a heavy user:** an Essentials line averaging >50GB/month over 3 months (deprioritized above 50GB), or using a lot of hotspot or travel data, moves to More. Hotspot >60GB or a connected device moves to Beyond. Message the benefit ("no slowdowns, price locked 5 years"), not the inference.
2. **Downgrade an overpayer:** a Beyond line using <15GB and ~0 hotspot, with no connected lines, no satellite or travel signal and no financed early-upgrade need, moves to More, saving $15–50/month on the sandbox prices. A More line using <15GB with a low streaming signal *could* move to Essentials. **Caveat:** that move loses the 5-year guarantee, Netflix and international data. The EV engine should require a strong price-sensitivity signal, and the explanation must state what the customer gives up. Downgrades cost revenue but show "customer value first" (30% of the rubric).
3. **Eligibility savings:** a `discount_group` of 55_plus, partner or community on a standard-price plan moves to the matching variant, keeping features and the guarantee. This is a clean, no-creep win.
4. **Household:** 4–6 lines on standard Essentials move to the Essentials 4 Line Offer (limited time). The sandbox has **no mixed-plan accounts** (checked: 0 accounts have more than one `plan_sku`). So a Household Mix Optimizer picks one plan per account, unless it deliberately introduces mixing as a synthetic extension.
5. **Bill shock after `promo_expired` or `installment_ended`:** a price-lock framing (move to Experience if on Essentials) or a care credit. Only promise what [PG] locks.
6. **Do nothing:** a customer on the right plan with stable bills and no risk signal gets nothing. Moving an Experience customer between Experience plans doesn't reset the guarantee, so there's no "lock in longer" benefit to sell them.

## 8. Uncertainties and gaps (top first)
1. **Sandbox `prices_include_autopay=1`, but its prices equal the real *pre*-AutoPay label prices.** So either the sandbox overstates prices by $5/line, or the flag is wrong. the offer engine should decide on one interpretation and label it.
2. **The $5.49 vs $4.49 fee:** current labels say $5.49. A cached copy of the main page shows $4.49. The change date of Oct 12, 2026 comes from a third party [M13].
3. **Experience More upgrade cycle:** 2.0 labels say 3 years; older card copy says 2 years.
4. **The partner = Military and community = First Responder mapping** is my inference from exact price matches and `priority_network`. The sandbox doesn't say.
5. **The 5-Year Guarantee doesn't lock "longer"** when someone switches between Experience plans, so a "multi-year lock-in" action has no real counterpart unless the customer is coming from Essentials or Go5G. **This is a critical point for the family-upgrade bundle:** a real lock-in comes from a 24–36-month EIP plus promo credits that stop if the customer leaves (sandbox `payout_months` 24/36), not from the price guarantee.
6. Retention credit amounts are anecdotal (forums), not official.
7. Migration plan names and prices come from a leaked spreadsheet [MIG].
8. Not modeled in the sandbox: Go5G legacy plans, migration plans, Essentials 55+/Military/FR, 3rd Line Free, the $5.49 fee, and the device connection charge on Essentials Saver and the 4 Line Offer.
9. The Beyond Student label says "120GB" of data, which may be a page glitch. The Student Perks $30 plan hasn't been checked on t-mobile.com.

_All customer data in the project is synthetic. Real prices are listed as of 2026-10-17 for realism checks only._
