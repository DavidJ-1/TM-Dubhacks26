# DubHacks '26 · T-Mobile · 3-minute demo script (FINAL v2, framed to the brief)
**Directions:** Next Best Moment (core), plus Household Mix (persona 38) and Timekeeper (persona 34, only if live). Earlier brief text: #3 Next Best Moment ("churn-risk score → ranked actions accounting for cost: better-fitting plan, proactive credit, relevant perk, check-in"). **App:** tm-ui's Streamlit dashboard, `dev` branch. **Data:** `e7b98dc` outputs in `demo_data/` + the challenge sandbox. All synthetic.
**Speaker:** David or a teammate. Quoted lines are spoken; *italics* are stage directions. ~440 words ≈ 2:55.
**How each beat maps to the brief:** brief phrases are in the "Brief" line under each beat, so the presenter knows which ask they're answering. Rubric: Customer value 30 · Use of signals 25 · Explainability & trust 20 · Feasibility & demo 25.

---

### 0:00–0:20 · The ask · *App opens on the pipeline band*
"Unlimited and coverage are table stakes. Customers stay when T-Mobile feels on their side. A churn score tells you who might leave, not what to do, and often the right answer is nothing. So we built the decision: one priced action per customer, the exact text to send, and often no text at all. Everything here is synthetic, from the challenge sandbox."
> Brief: market context "win on perceived value"; direction Next Best Moment ("quietly drifting… proportionate… before they call to cancel"), plus parts of Household Mix and Timekeeper · Rubric 4: believable and clear

### 0:20–0:35 · How it decides · *Pipeline band: data in → churn score → every option priced → one decision*
"We combine commerce signals like plan and financing, customer signals like lines and tenure, and real-time ones like support calls and comparing carriers. Every action a customer qualifies for is priced against doing nothing, and every dollar in a text is checked against T-Mobile's promotions. Of 5,042 accounts, we contact 1,314 and leave 3,728 alone. Here's one." *(Click into customer 38.)*
> Brief: inputs "tenure, support interactions, plan fit vs usage, billing changes, competitor-interest proxies" · "ranked actions accounting for cost" · Rubric: use of signals, explainability

### 0:35–1:05 · Better-fitting plan · *Persona 38 card*
*Point at the why-sentence.* "First: the lowest-cost fit for the whole household. This two-line couple is over 55, a segment that churns more, and they pay full price for Experience More. They qualify for the 55+ version of the same plan, so we tell them: $110 a month instead of $150 for both lines, same features."
*Point at the options table, then switch the text to Spanish.* "Every option we weighed, and why it lost. In their language."
> Brief: Household Mix ("lowest-cost best-fit plan across the household") · market context: seniors 55+, multi-line, perceived value · Rubric 1: a real person wants this · Rubric 3: plain-language why

### 1:05–1:20 · Proactive credit, but only with a fix · *Persona 04 card*
"Second: a proactive credit. Bill up 14%, five support contacts in 90 days, three still unresolved. We fix the problem first, with a callback, plus a one-time $25 care credit under T-Mobile's own three-contact rule."
> Brief: Next Best Moment, a proportionate action · Rubric 2: commerce (bill change) plus customer (support history) · Rubric 1: fixing the problem helps the customer, not only the business

### 1:20–1:50 · Check-in, and it changes live · *Persona 21 card*
"Third: a check-in. Over five years with us, but the app's gone quiet, they're comparing carriers, and they asked us about transferring their number out. Credits lose money here, so the pick is a free plan check-in."
*Live (let a judge flip it):* untick **Asked us about transferring their number** → "Risk drops to 3.5%, still a check-in." Untick **Comparing carriers** → "Now 1.1%, and it flips to do nothing. Different situation, different action." *(The risk box shows 1.1% with "what-if, was 5.4%" under it.)*
> Brief: Next Best Moment, "quietly drifting" · Rubric 2: real-time context (port-out inquiry, comparing carriers) changes the decision live

### 1:50–2:10 · Restraint · *Persona 24 card*
"And the one the brief calls out most: restraint. Nine support calls in nine months. A naive rule panics. Ours sees every call resolved, none negative, no shopping, and a plan that fits. Risk 0.3%. We do nothing, and the phone stays silent."
> Brief: "proportionate", and doing nothing is the most proportionate move · Rubric 1: the customer isn't spammed · Rubric 3: trust

### 2:10–2:40 · Proof (evidence charts, last) · *Comparison chart ("Same assumptions, different strategies (simulated)") + persona scorecard*
"Under the same simulated assumptions, discounting everyone spends $126,000 on credits and texts 4,523 people who weren't leaving. Ours spends $6,700, reaches more of the customers who leave than a risk-score-only rule, 96 versus 88, and saves the most." [Source: demo_data/ f46508a, simulated. No net-value claim. Golden-test pass count: say it only if re-verified on the shipped commit.]
> Rubric: customer value (business side), feasibility. Say "simulated" once; never "41 of 42 correct."

### 2:40–3:00 · Close
"One customer we didn't text, another we moved to a cheaper plan. That's restraint you can check. It runs on T-Mobile's own offers and rules today. Next step: a holdout test with real customers to prove it keeps them for less."
> Brief: "different problems → different actions; discount not automatic; restraint" (its own definition of convincing) · Rubric: feasibility

*(Persona 34 / Timekeeper beat CUT: nothing landed at 8:50.)*

*Relevant perk (the brief's 4th action):* we rank a perk reminder for every eligible customer (it's in 04's options table). If a judge asks, point there. It rarely wins because it's weaker than fixing the problem.

---
## Cut from the demo (do not mention unless asked)
Model C / Qini / uplift curves, learning curves, calibration plots, the acceptance-rate slider, income and job-change enrichment (it's off in decisions: `enrichment_in_decisions = False` for every account), the 250k scaled data, and the $25 credit as a headline (04 shows it only as fix-plus-credit), and the upgrade-or-wait chart unless tm-offers confirms the persona has forfeitable device credits.

## Options-considered rows for the featured personas (source: `harness/out/offer_candidates.csv`, synthetic)
"Cost" is the engine's expected cost to T-Mobile (`offer_cost`). "Customer change" is what the customer gets.

**Persona 38: Experience More → Experience More w/ 55+ Savings 2.0** (risk 0.80%)
| Option | Cost to T-Mobile | Customer change | Why not / status |
|---|---|---|---|
| **Switch to 55+ variant (chosen)** | $168 expected | −$40/mo ($150 → $110), same features | EV $3.10: only $3.10 ahead of do nothing, so don't claim it's profitable |
| Do nothing | $0 | none | EV $0, lower |
| Loyalty credit | n/a | n/a | Guardrail: no bill credits below 5% risk |
| $25 care credit | n/a | n/a | Needs 3+ support contacts in 90 days (has 0) |
| Keep-your-phone credit | n/a | n/a | Still paying off a phone |
| Right-size plan | n/a | n/a | No cheaper plan fits their usage |
| Step-up / device upgrade / Home Internet | n/a | n/a | Blocked: a cheaper eligible version of their plan exists |
| Fix-first | n/a | n/a | No open or network issue |

**Persona 21: check-in / plan review** (risk 5.4%)
| Option | Cost to T-Mobile | Customer change | Why not / status |
|---|---|---|---|
| **Check-in / plan review (chosen)** | $2 | none (no offer; the 5-year price guarantee is stated as a fact) | EV $4.27 |
| Do nothing | $0 | none | EV $0, lower |
| Loyalty credit ($5/mo) | $60 | −$5/mo | EV −$54.73, loses money |
| Keep-your-phone credit ($20/mo × 6) | $120 | −$20/mo for 6 months | EV −$109.21, loses money |
| Care credit | n/a | n/a | Needs 3+ support contacts (has 0) |
| Family / device upgrade | n/a | n/a | Simulated upgrade score: not in the top 15% (pct 47) |
| Step-up, right-size, variant, fix-first, bill-shock, Home Internet | n/a | n/a | No matching signal (single line, no open issue, no bill shock) |

**Persona 24: do nothing** (risk 0.32%)
| Option | Cost | Customer change | Why not / status |
|---|---|---|---|
| **Do nothing (chosen)** | $0 | none, no text sent | The only eligible action |
| Care / loyalty credits | n/a | n/a | Guardrail: no bill credits below 5% risk |
| Keep-your-phone | n/a | n/a | Still paying off a phone |
| Check-in | n/a | n/a | No shopping, port-out or quiet signal |
| Upgrades | n/a | n/a | Simulated upgrade score not in the top 15% (pct 51); no paid-off phone |
| Everything else | n/a | n/a | No open issue, no bill shock, no cheaper fit |

**Persona 04 (optional): $25 care credit + fix-first** (risk 19.7%)
| Option | Cost to T-Mobile | Customer change | Why not / status |
|---|---|---|---|
| **$25 care credit + fix-first (chosen)** | $40 | callback + one-time $25 credit | EV $189.59 |
| Fix-first callback alone | $15 | callback | EV $131.65, lower |
| Bill-shock relief (explain the promo end + $25 + $5/mo loyalty) | $85 | $25 once + $5/mo | EV $41.13, lower |
| Perk reminder | $0 | none | EV $32.43, lower |
| Loyalty credit | $60 | −$5/mo | EV $10.17, lower |
| Do nothing | $0 | none | EV $0 |
| Check-in | n/a | n/a | Open support issue (fix first) |
| Home Internet bundle | n/a | n/a | Blocked: bill-shock guardrail, open issue, shopping driver |
| Upgrades | n/a | n/a | Simulated upgrade score pct 4 |

## Judge Q&A cheat sheet (short, honest answers)
1. **Why not an LLM?** "A customer text that quotes a price has to be right every time. Ours are built from templates, and every dollar amount is checked against the sandbox promotions and plans tables. All 5,042 pass. It's deterministic, auditable and free to run. An LLM could help an agent phrase things later, but it should never pick the offer or the price."
2. **How would you prove lift?** "We can't from sandbox data, because the labels are simulated. With real outcomes we'd run an A/B test: the policy against a random holdout that gets business-as-usual, and compare churn, revenue and credit spend over 90 days. Until then, we don't claim a lift number."
3. **Is this real T-Mobile data?** "No. It's the judges' sandbox: 5,000 synthetic households plus 42 test personas, labeled 'stub data, not official'. The churn labels are simulated too, so our model metrics only show the pipeline works. They're not real-world accuracy."
4. **Why would you ever do nothing?** "Contacting a happy customer costs money, can annoy them, and can even remind them to shop around. 'Do nothing' is always on the list at $0, and an offer has to beat it. It wins for 3,728 of 5,042 accounts. Persona 24 calls a lot but is happy, so we leave them alone."
5. **How is eligibility enforced?** "From the sandbox's own tables. Plans carry their eligibility and price-guarantee years, for example 55+ pricing needs the 55+ discount group. Promotions carry their rules, for example the $25 care credit needs 3+ support contacts in 90 days. Ineligible options show up in the table with the rule that blocked them, plus our own guardrails, like no bill credits below 5% risk."
6. **Price guarantee and lock-in, are you being straight with people?** "We say 'covered by your 5-Year Price Guarantee' only when the customer's plan actually has it in the sandbox. That's Experience More and Beyond, not Essentials. Every featured action has zero lock-in. The one kind that adds lock-in is the 17 family upgrades, where the device credit is paid as bill credits over 36 months. We say that in the text instead of calling it free."

## Persona pass counts: why there are two numbers
- **41/42 (tm-offers' golden tests, `tests/test_persona_golden.py`, re-run read-only on the e7b98dc outputs: 41 passed, 1 failed).** These check *direction* only. Cart and quiz personas pass if they get no unprompted discount or upsell, and several personas pass with any "quiet" action. The only failure is persona 37 (a family of four on unlimited with light use gets do nothing instead of a cheaper fit).
- **25/30 in our directions, 27/42 overall (tm-strategy rubric scorer, `strategy/rubric/rescore_e7b98dc.md`).** This scorer needs the *ideal* action. Our 30: 19 match, 6 acceptable, 2 wrong (08, 37), 3 missing (34, 41, 42). All 42: also counts 8 cart and 2 matchmaker personas as missing, since we built no cart or quiz.
- On stage, say "41 of 42 pass our safety tests; 25 of 30 hit the ideal action in our direction." Don't say "41 of 42 correct."

## Open items / [TBD]
- **Persona 21 live toggle:** with the `e7b98dc` model, unticking port-out *alone* does **not** flip the pick. Risk drops from 5.4% to 3.5%, they're still "shopping" (score 0.85 ≥ 0.6) and "quiet" (2 app sessions), and by my calculation check-in still beats do nothing (about +$1.34). It flips only when shopping is also turned off (risk 1.7%, check-in EV below $0). The script reflects this. **Confirmed** by tm-offers with `choose_offer` (`36567db`): `port_out_inquiry=0` gives check-in at p=0.035; also `competitor_research_score=0` gives do nothing at p=0.017. tm-ui to confirm the toggle labels on screen. 
- If the 8:50 tm-offers commit lands and passes, re-check: the 41/42 count (persona 37 may pass), the action mix, and all four personas' rows.

## Comparison-slide Q&A (added 8:13 PM)
7. **"Score-only targeting is cheaper per save ($532 vs your $957). Why not just do that?"** "Score-only sends credits to the top 10% and nothing else. It reaches 88 churners to our 96, and it never saves anyone money, fixes a problem, or checks in. Part of our extra cost goes to fixing problems and moving people to cheaper plans, and a save count doesn't capture that. If T-Mobile only cares about cost per save, raising one threshold makes ours behave like score-only. And the riskiest customers aren't the most persuadable ones; research found only about half overlap ([Ascarza 2018, *Retention Futility*, JMR](https://doi.org/10.1509/jmr.16.0163)). That's why the next step is a holdout to find who a contact actually changes."
8. **"172 of your low-risk contacts are upsells. Isn't that just marketing?"** If the 8:50 usage gate landed: "Each is a plan move with a usage reason, like near the data cap. Every one says there's no need to do anything, and none goes to someone with an open ticket." If it didn't (71 of the 8:15 upsells have no usage reason): "These are plan-upgrade suggestions; the next rule we're adding requires a usage reason before any upgrade text goes out." (Don't claim any have a usage reason, or the open-ticket exclusion, unless tm-offers confirms it in the shipped data.) Default to this line until tm-offers confirms the 8:50 count. Never call them all usage-based.
9. **"Isn't the scoring circular, since you grade yourselves with your own assumptions?"** "Partly, yes. The sandbox churn labels are simulated, and value uses our assumed save rates. That's why we lead with numbers that don't depend on assumptions: who we reach, how many low-risk people we text, and credit spend. We don't claim lift until a holdout test with real outcomes."
10. **"Why would doing nothing ever be the best action?"** "Because contact can backfire. In a 65,000-customer wireless experiment, proactive plan outreach *raised* churn from about 6% to 10% ([Ascarza, Iyengar & Schleicher 2016, JMR](https://doi.org/10.1509/jmr.13.0483)). So our engine has to earn every contact."
Do not use the "5 to 25 times cheaper to retain than acquire" stat; it's unsourced.
11. **"Persona 38's switch barely wins on value. Is that rigged?"** "No, it's a deliberate customer-benefit rule. If the same customer would pay less on another plan, we tell them, even when the value math is close (here it's $3.10). Saving the customer money is how you earn trust."
12. **"Your simulated net value is lower than score-only. Why?"** "The simulation counts every move to a cheaper plan as a full year of lost revenue, and it gives no credit for the customer trust that buys. Right-sizing is the brief's 'better-fitting plan' action. We'd rather prove its value with a holdout than tune a simulation to flatter it."
13. **"What if your save rates are too optimistic?"** "We tested half our assumed rates. We still save the most customers in every scenario we simulated, but net value goes negative at half rates. That's exactly why the next step is a holdout test with real outcomes."
Close option (reconciled: $40k is total retention cost = ~$6.7k bill credits + callback/fix-first handling + revenue given back on cheaper plans; budget caps total cost, not credits): "Capped at half the total retention cost, meaning credits, callbacks and plan discounts, the engine keeps about 99% of the simulated value." Never say "credit budget" next to $40k. Show demo_data/budget_curve.png. All synthetic.

## Judges' brief check (8:25 PM): direction and rubric per card
| Card | Direction | Rubric line it answers |
|---|---|---|
| 38: 55+ couple, same plan $40/mo cheaper | Household Mix + Next Best Moment | 1 (a real person wants it), 3 (plain why); seniors, multi-line, perceived value |
| 04: fix first + $25 care credit | Next Best Moment, proportionate | 2 (commerce + customer signals), 1 |
| 21: check-in, flips live | Next Best Moment, quietly drifting | 2 (real-time context), 4 (live demo) |
| 24: nine calls, do nothing | Next Best Moment, restraint | 1, 3 |
| 34: upgrade or wait (optional) | Timekeeper, trade-in timing | 1, 3 |

Honest limits: Household Mix here is plan-variant moves on an account, not a full re-plan of every line. Timekeeper is shown only if the 8:50 wait chart passes. Home-internet bundle offers exist but go to only 3 accounts, so they're Q&A only.

14. **"Is this just a churn model?"** "No. Most churn demos stop at a risk score. Ours prices every action the customer qualifies for, including doing nothing, and picks the one that helps both sides. The same engine handles household plan fit and upgrade timing."
15. **"What about bundles and home internet?"** "The engine ranks T-Mobile's home-internet bundle like any other offer. It wins for a handful of customers, because for most of them it isn't the cheapest fix."

Household Mix backups if asked (committed, synthetic): customer 39 moves to the Essentials 4-Line Offer and saves $10/mo (one of 94 such moves). Customer 05 right-sizes to Essentials and saves $110/mo, and the text lists what they give up. The 55+ savings come from the sandbox's plan variants, not a promo. Product name in the hook follows David's pick; "Next Best Moment" stays as the name of the brief direction.
16. **Trap: "That same 2016 paper found cheaper-plan recommendations raised churn. Isn't persona 38 exactly that?"** "Yes, that's the closest risk to our hero card, and we take it seriously. The harm in that study was concentrated among customers whose usage was volatile or falling. Customer 38 has five years with us, no issues and a same-features plan, and the text says nothing else changes. Before scaling, we'd exclude volatile-usage customers from plan moves and test it against a holdout." (Source: tm-research, RESEARCH.md. Don't cite the 2016 paper in the spoken script; Q&A only.)

## Differentiation vs past T-Mobile winners (research 8:32 PM)
Past winners (HackUTD 2025: Beacon, InsighT, HarmoniQ) were happiness-index dashboards with LLM-written suggestions. The closest prior idea, [The Un-Churner](https://devpost.com/software/the-un-churner) (2019: churn score plus a "suggest a plan" pop-up), did not win. Never say "dashboard", "command center", "happiness index" or "AI-powered insights". Lead with the decision and the restraint; show the insights dashboard last, as evidence.
17. **"How is this different from a churn dashboard?"** "A dashboard tells staff who's unhappy. Ours decides what to do for each customer, prices it against doing nothing, and writes the text. Every promise in it is one T-Mobile's own rules allow."
18. **"Why households, not phones?"** "T-Mobile itself now reports churn by account, not by line, so the unit we save is the household. That's why customer 38's text covers both lines." (tm-research; check RESEARCH.md for the source link before saying the 0.99% number.)
19. **"Why not push the home-internet bundle harder?"** "Bundled customers churn less, but part of that gap is just who chooses to bundle. We'd assume a modest effect, and never offer a bundle to someone with open network complaints. That's why it wins for only a few customers."
20. **Compliance trap: "Isn't using port-out data illegal?"** "Using a *competitor's* port request to target retention offers is what the FCC barred in 2008, and the D.C. Circuit upheld it in 2009 (47 U.S.C. §222(b)). Our signal is different: the customer asked *us* about leaving, which is a normal inbound save moment. When a customer asks us about leaving, we always respond, because ignoring that question would be the wrong kind of restraint. The engine still picks the proportionate response, and it's often a free check-in. In production we'd keep carrier-to-carrier port data out of the model entirely." Also: no calls-to-competitor records, location data or protected attributes. Reasons follow the credit-law style: specific, real factors, four or fewer. (Source: tm-research notes_explain.md; verify citations before quoting.)
21. **"Churn models have been done before."** "Since at least 2019 at T-Mobile hackathons, and none we found won. None showed the next step either: the right offer, priced against doing nothing, explained to the customer in one text." Back-pocket stat: on synthetic data, our churn score's riskiest 10% hold 62% of leavers (out-of-fold). Always say "on synthetic data"; it beats every real benchmark (Orange KDD Cup 2009 best AUC 0.765), so never imply real-world performance. See PRIOR_ART.md.

22. **"Are you tracking calls to competitors?"** "No. 'Comparing carriers' and 'asked about transferring their number' come from what the customer tells us. We don't track anyone's calls to competitors."
23. **"Is this uplift modeling?"** "It's uplift-ready. Every decision is logged and we'd hold out a random 5 to 10% of customers, so the true effect of each offer can be learned from real results."
24. **"Why only three reasons?"** "Like credit-decision reason codes: specific, actual factors, four or fewer, so a rep or a customer can check them." (Don't cite the CFPB algorithm circular; it was withdrawn in May 2025.)

**Freeze notes (9:06, app `a0680ea` + scorer `6ab4eb9`):** Only press send-to-phone on 38; the button also shows on 04 and 21. On 24, the facts line reads "6 in 90 days (9 in 270)", so "nine support calls in nine months" matches. Demo ships on `f46508a` data. Don't open 05's Spanish text (no opt-out line yet) or send 21's text (273 characters, goes out as two parts); the fix `c45c74d` lands after 9:30. Scorer fallback `ad34a8a`: nobody writes to `harness/out` until 9:30.
25. **"How good is your upgrade score?"** "It's simulated. It's built from device age and used only as a gate on upgrade offers. We haven't validated it against real purchases, and that's on the list for the holdout test." Never call it validated or say it predicts purchases.
