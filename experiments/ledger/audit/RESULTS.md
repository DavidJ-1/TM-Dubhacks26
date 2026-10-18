# Adversarial audit of "money saved" + product ledger
**All numbers are synthetic/simulated:** sandbox stub accounts and simulated churn labels, not T-Mobile customer data.
Scripts in this folder, run with `OMP_NUM_THREADS=1 .venv/bin/python <script>`:
`base.py` (reproduces 184 / +$4,109 / break-even 4.80% exactly), `model.py` (knob model), `adversary.py` (parts 1 and 3),
`falsify.py` (part 2), `ledger.py` (part 4, final design spec), `post_swap.py`. Outputs go to `out/`. All inputs are read-only,
and sandbox.db is opened with `mode=ro`.

## FINAL (23:4x): headline policy and costing. **All numbers synthetic.**
Policy: the same 184, with the open-ticket rule (25 perk reminders become fix-first). Costing per team ruling: every fix-first contact pays $10.75 agent time + $4.25 escalation
(research14) plus the channel's send cost (text $0.013, in-app $0, email $0.0001). Calls pay the $15 callback only, with no double count. $25 credit and $4 annoyance unchanged.
Reproduce with `ledger.py` (headline, bootstrap) and `POLICY=final adversary.py / falsify.py` (audits, written to `out_final/`). `stick.py` covers "do saves stick?".

| headline | value |
|---|---|
| total, mid case (10% save rate, $1,478) | **+$3,938** |
| low (5%, own-risk survival value) / high (22%, upper bound) | −$2,760 / +$13,720 |
| 95% range at 10% (2,000 resamples, realized outcomes; old-range check passes) | **−$3,186 to +$13,148** |
| P(net>0) at 10% / 5% | **0.801 / 0.408** |
| break-even save rate (same definition as 4.80%) | **5.17%** |
| per-attempt effective rate at break-even | 4.67% of reached would-be leavers (risk-weighted), about 1.2 saves per 100 contacts |
| *Q&A only: if the fix is self-serve* | +$6,428; −$703 to +$15,657; P 0.949 / 0.731; break-even 2.11% |

| audit (same methods as below) | value |
|---|---|
| worst case, reasonable box, 10% save rate | **−$4,793** (save rate allowed to fall to 6%: −$6,896; net-effect box −$1,886) |
| CVaR10 bound (worst over reasonable priors) | **−$7,099** (team prior −$4,464; net-effect priors −$2,661) |
| placebo: random accounts, same offers (2,000 draws) | mean **−$2,311** (max −$1,229) vs ours +$3,896 graded on true risk. Beats us in expectation **0%**; in a single realized quarter **7.6%** |
| placebo: random top-10%-risk accounts, same offers | mean −$366 (max +$582). 0% in expectation; 18.8% in a single quarter |
| shuffled labels (200 refits) | 9.9 contacts on average, mean +$50 (max +$582). Never beats us |
| out-of-fold scoring (4 folds fit, 5th scored) | 179 contacts, +$3,856 (AUC 0.843). Harness out-of-fold: 180, +$4,036 |
| robust A (never contact if break-even > 11% under the own-risk-3-months value) | **139 contacts (45 never-contact), +$3,785 central**, +$279 at 5%, reasonable worst −$5,389, break-even 4.61% |

Notes. The shuffled-label, score-shuffle and out-of-fold rows re-pick with the engine's costs and no open-ticket swap. That's within $0.013 per fix-first contact of the
conservative costing, so their numbers are unchanged from the earlier run. Robust A now drops 45 accounts, up from 24. Most of the extra 21 are the open-ticket fix-first
swaps, which lose money at a $15 agent cost on low-risk accounts.

**Do saves stick? (considerations.csv row).** The old 58 / 7.6% / 43% come from `../economics/headline_1478.csv`, row "per-account survival-weighted discounted
(own hazard 24 mo) × NEW guardrail". That run *re-picks* the policy assuming a saved customer keeps their own risk for 24 months, and it reproduces exactly here.
On the **current 184** under that same assumption: mid **−$1,307** at 10%, only **36 of 184** accounts positive, break-even **14.5%**, P(net>0) **0.22** at 10%
and **0.045** at 5% (`out_final/saves_stick.json`).

## 0. Bottom line
- **No placebo or permutation matches or beats the policy in expectation** (P = 0 in every test, table 2). This does not break the claim.
  The caveat is outcome noise: with only about 50 expected churners among the 184, a *random-accounts* placebo beats us on a single realised
  quarter **8% of the time**. A *random top-10%-risk* placebo does it **17%** of the time.
- **Worst case** over the reasonable box at a 10% save rate is **−$4,422**, or −$6,490 if the save rate can drop to 6%. Over the full box it's −$28,841 / −$34,116.
- **CVaR 10%**: from −$4,104 (team prior) to −$6,652 (adverse prior). The distributionally robust bound (worst over the reasonable priors) is **−$6,652**.
  If field save rates are read as net effects (no extra backfire on top), it's **−$2,260**.
- **Verdict: the claim partly survives.** It holds up as "our targeting beats random targeting with the same offers," with a lot of
  margin (+$4,073 vs −$1,886 on average, graded on the true churn probability). It does **not** survive as a robust dollar figure. The sign
  depends on the save rate and on backfire, and we have no data on either. Only a holdout can settle it.
- **Ledger (committed on v2 as `9e4d402`, `experiments/ledger/`):** after the open-ticket rule, the mid total is **+$3,939** (it was $4,109).
  The 25 open-ticket perk reminders became fix-first callbacks, and their total went from +$28 to −$142.

## 1. Worst case over the assumption knobs (policy: the 184, +$4,109)
Knob model, per account: `p(1−dw) · min(1, sr·s/0.444) · V_k · (1−rechurn) − backfire·0.67·p(1−dw)(1−sr')·V_k − cost' − annoyance`,
where `V_k` blends the flat $1,478-scaled value toward the per-account survival value.

| knob | central | full box | reasonable box | basis |
|---|---|---|---|---|
| save rate (avg share of would-be leavers kept) | 10% | 2–11% | 6–11% | RESEARCH §13b field range 2–11% relative. Reasonable drops Ascarza 2018's 2–4% (no-incentive) end |
| kept value | $1,478 flat | → own-hazard survival value (24 mo at their own risk) | → own risk 3 months, then base 0.99% | §13b: high-risk customers live shorter than 1/average churn |
| deadweight (predicted leavers who'd stay anyway) | 0 | 0–50% | 0–20% | in-sample vs OOF risk on the picks is only 3.4% lower. The 20% is our own margin |
| backfire (share of contacts at Ascarza 1.67×) | 0 | 0–50% | 0–10% | Ascarza 2016, for plan recommendations, which we never send |
| re-churn after a save | 0 | 0–50% | 0–20% | assumption (no cited figure). Overlaps the value knob |
| credit leakage (credit cost multiplier) | 1.0 | 1–2 | 1–1.3 | assumption. The ledger already pays the credit to every contacted account, so this is extra on top of that |
| callback cost | $15 | $15–27 | $15–20 | §12/§14a: Gartner $8–13.50 per live contact. $27 = $13.50 at 51% reach (Godinho 2018) |
| digital send cost | engine | +$0–2 | +$0–0.50 | §14a: SMS ≤ $0.02, perk reminder ≈ $0.50 |

Worst corners (exhaustive corner search: net is multilinear in the knobs, so the minimum is at a corner). From `out/t1_worst_case.csv`:

| box | save rate | central | **worst** | worst corner |
|---|---|---|---|---|
| full | searched | 4,109 | **−34,116** | save 2%, backfire 50%, re-churn 50%, leakage 2×, call $27, digital $2 (value and deadweight stay central, because a lower value also shrinks the backfire loss) |
| full | 10% | 4,109 | −28,841 | same, at a 10% save rate |
| reasonable | searched | 4,109 | **−6,490** | save 6%, backfire 10%, re-churn 20%, leakage 1.3, call $20 |
| reasonable | 10% | 4,109 | **−4,422** | own-3-month value, deadweight 20%, backfire 10%, re-churn 20%, leakage 1.3, call $20 |
| reasonable, net-effect (no extra backfire) | searched / 10% | 4,109 | −2,822 / −1,503 | everything else at the reasonable worst |

What drives it: each knob moved alone from central, inside the reasonable box. Backfire −$5,267, save rate to 6% −$3,159, value −$2,742,
deadweight −$1,579, re-churn −$1,579, call cost −$775, leakage −$225, digital −$14. Under the field prior, the Spearman correlation with the total is save rate
+0.69 and backfire −0.64. Everything else is ≤ 0.14. **Break-even save rate:** 4.80% central, 22.4% with the reasonable worst frictions, 53.7% with the full worst.

**CVaR (10%) over knob priors** (`out/t1_cvar.csv`, 20k draws each. The save rate is triangular on 2–11%. The other knobs are Beta(1,2) on the reasonable range, which leans toward central, or Beta(2,1) for the adverse prior):

| prior | mean | VaR10 | **CVaR10** | P(net>0) |
|---|---|---|---|---|
| team (save mode 10%) | −945 | −3,249 | −4,104 | 0.31 |
| field (save mode 6%) | −1,797 | −3,941 | −4,700 | 0.14 |
| team, net-effect (no extra backfire) | +540 | −1,345 | −1,901 | 0.66 |
| field, net-effect | −269 | −1,849 | −2,260 | 0.40 |
| uniform, reasonable box | −1,852 | −3,841 | −4,378 | 0.12 |
| adverse skew (save mode 3%) | −4,570 | −6,248 | **−6,652** | 0.00 |
| uniform, full box | −10,297 | −16,844 | −19,671 | 0.00 |

DRO bound = worst CVaR10 over the reasonable-box priors = **−$6,652** (net-effect priors only: −$2,260).
After the open-ticket rule (mid +$3,939; `out/post_swap_worst.json`): reasonable worst at 10% is −$4,792 (any save rate −$6,895), net-effect −$1,885 / −$3,267, full −$29,304 / −$34,749.

## 2. Falsification tests (`out/t2_falsification.csv`, graded on the generator's true churn probability, at a 10% save rate)
| test | contacts | result | ours | P(test ≥ ours) |
|---|---|---|---|---|
| placebo: random accounts eligible for the **same offers** (same action mix), 2,000× | 184 | mean −1,886, max −979 | **+4,073** | **0.000** (expected). Realised single quarter: **0.081** |
| placebo: random **top-10%-risk** accounts, same offers, 2,000× | 184 | mean −271, p95 +191, max +733 | +4,073 | 0.000 (expected). Realised: **0.173** |
| label permutation: shuffle churn labels, refit, select, 200× | 9.9 avg (max 37) | mean +50, max +582 | +4,073 | 0.000 |
| score permutation: shuffle our risk scores across accounts, 500× | 62.9 avg | graded −518 (max +263). **The same picks grade themselves at +1,241** | +4,073 | 0.000 |
| cross-fit: fit on 4 folds, score the 5th, select | 179 (161 overlap) | +3,856 (AUC 0.843, break-even 4.65%) | +4,073 | n/a |
| harness out-of-fold score | 180 (174 overlap) | +4,036 (break-even 4.93%) | | n/a |
| in-sample refit (sanity) | 185 | +3,947, corr 0.989 with the shipped score | | |

Reading: the selection is not overfit. Out-of-fold selection keeps 95–99% of the value. Our realised-outcome 95% range is −$2,718 to +$13,651,
so a single quarter can't tell us apart from random targeting at p < 0.05 (p ≈ 0.08). **The score-permutation row is the most important
caution: a ledger that grades its own picks with its own score reports +$1,241 for random scores whose true value is −$518.** Our own self-grade
is close to the truth (+$4,109 vs +$4,073) only because the model nearly recovers the generator. See circularity below.

## 3. Per-segment adversary, never-contact list, robust policy (`out/t3_*.csv`, `out/never_contact.csv`)
- Segments are action × risk band × port-out (20 segments). With the adversary picking knobs **per segment** inside the reasonable box at a 10% save rate,
  **all 20 segments flip negative**. The biggest losses are fix-first top 2–5% (43 contacts, −$1,017), fix-first top 1–2% (−$663) and care + fix-first top 1% (−$574).
  So the minimax policy over the full reasonable box (including backfire) is **contact nobody**.
- A usable never-contact rule: never contact an account if it needs a save rate **above 11%** (the top of the field range) to break even under a stated adversary.

| policy | contacts | central (10%) | at 5% | worst A | worst net-effect box | worst reasonable box |
|---|---|---|---|---|---|---|
| current 184 | 184 | 4,109 | 161 | 1,367 | −2,822 | −6,490 |
| drop port-out only (the offer engine default) | 152 | 2,906 | −53 | 949 | −2,297 | −5,217 |
| **robust A**: never-contact if break-even > 11% using the own-risk-3-months kept value | **160** (24 never-contact) | **3,808** | **303** | **1,495** | −2,255 | −5,578 |
| robust A, port-out on its own line | 131 | 2,665 | 77 | 1,067 | −1,806 | −4,427 |
| robust B: break-even > 11% under the stacked net-effect frictions | 28 | 1,683 | 488 | 854 | −300 | −1,234 |
| robust C (minimax incl. backfire) | 0 | 0 | 0 | 0 | 0 | 0 |

Recommendation: **robust A**. It gives up $301 of central value (−7%), is better at 5% (+$303 vs +$161), break-even drops to 4.57%, and it never loses
under the value correction. Robust B is the "only sure things" list (28). `never_contact.csv` carries `never_contact_A/B` and per-account break-evens.

## 4. Product ledger (final design spec; see LEDGER_SCHEMA.md)
`ledger.csv` (5,042 rows, same ids and order as outreach_card.csv) and `events.csv` (2,705 rows, ≤3 per account, newest first), committed on local v2
`9e4d402` under `experiments/ledger/` (not pushed). Mid +$3,939 over the 184 (asserted), low −$2,759, high +$13,721. 32 already-leaving accounts make up +$1,193 of it,
and 30 holdout accounts +$458. The text count of 64 is asserted against outreach_card.csv. No forbidden strings (asserted).
Bootstrap 95% range for the old +$4,109: −$2,805 to +$13,292, P(net>0) 0.82 at 10% and 0.44 at 5% (`../economics/headline_1478.csv`). It hasn't been rerun for +$3,939.

## What would change the verdict
- **A holdout readout.** 30 held-out accounts can't detect a 10% save (see `../proofloop/`), but they would catch strong backfire. That knob alone decides the sign.
- If field save rates are taken as net (ITT) effects, backfire is already inside them. Then the reasonable worst is about −$1.5k at 10%, the CVaR about −$2k,
  and P(net>0) 0.66 under the team prior.
- Dropping fix-first callbacks on low-risk accounts (the open-ticket rule moved 25 of them from +$28 to −$142), or adopting robust A.

## Weak spots
- **Generator circularity.** `harness/labels.py` L41–67 defines the true churn hazard as a logistic in the same features our model uses (`COEFS`, `SHRINK` 0.5).
  L239–248 draws `churn_90d` from that probability. So grading on `p_true` (or on the labels) rewards recovering the generator. Every falsification
  win in table 2 shows that our model learns the simulated world (AUC 0.86, corr 0.99 with the refit). **It is not evidence that real customers respond.**
- **Save rates are assumed, not learned.** No test here can validate them, and the dollars scale almost linearly with them (break-even 4.8%).
- Backfire, re-churn and leakage ranges are partly our assumptions (marked above). Value and re-churn overlap, and the adversary stacks both.
- Channel vs cost: the ledger books the engine's $15 callback for fix-first, but the outreach drafts send some fix-first messages as text, in-app or email. If those really are
  digital, costs are overstated. If a callback follows anyway, they're right.
- One mismatch flagged for the offer engine: ACC-01607's guardrail line says "We'll call", but outreach_drafts routes it in-app.
- The open-ticket rule: we count 25 perk reminders with an open ticket (unresolved contact in 90 days), not 21 + 2. That matches the "open support issue comes first" rows in outreach_card.csv.
