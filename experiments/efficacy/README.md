# Message efficacy: does contacting this customer actually work? (v1, in progress)

Scratch experiments, not used by the demo. **Everything about our own customers is SYNTHETIC/SIMULATED.** The only
real data here is a public retail e-mail experiment (Hillstrom/MineThatData, 2008). It is e-mail and retail, not
telecom: it tests the method, it does not prove anything for a carrier.

## The idea: uplift, not risk
A churn score tells us who is likely to leave. It does not tell us who will stay *because* we contacted them. Uplift
modeling sorts customers into four groups by the effect of contact:
- **sure things** stay anyway (contact is wasted money),
- **persuadables** stay only if contacted (the only group worth paying for),
- **lost causes** leave anyway,
- **sleeping dogs** are pushed away by contact.

High risk does not mean high uplift. In a randomized wireless trial, proactive plan-fit outreach *raised* churn
(about 6% to 10%; Ascarza, Iyengar and Schleicher, "The Perils of Proactive Churn Prevention Using Plan
Recommendations", JMR 2016). Contact volume has a cost too: in a large randomized e-mail test, sending everything
drew 45% more unsubscribes and spam reports (Gupta et al., KDD 2016).

## 1. Real randomized data: Hillstrom e-mail test (`hillstrom_message.py`)
64,000 customers randomized 1/3 each to no e-mail, a men's-merchandise e-mail, or a women's-merchandise e-mail.
Learners per message vs no e-mail: T-learner (logistic regression and gradient boosting), S-learner (logistic
regression with message x feature terms), X-learner (gradient boosting), a plain response ranking that ignores
treatment, and random. Scores are held out (5-fold CV, 2 seeds). Qini coefficient with paired 95% bootstrap CIs
(200 resamples). Policy values are exact, because assignment was 1/3 by design.

| Outcome: site visit | Uplift learners (Qini) | Plain response ranking | Paired difference |
|---|---|---|---|
| Women's e-mail vs none | 0.059 (T-learner LR, CI 0.044-0.073; all four learners 0.058-0.060) | 0.013 | +0.025 to +0.066 (uplift better) |
| Men's e-mail vs none | 0.008 (T-learner LR, CI includes 0) | 0.029 (CI 0.014-0.045) | -0.036 to -0.005 (response ranking better) |

- **Which ranking wins depends on the message.** Where the e-mail's effect differs from baseline behaviour (women's),
  uplift ranks better. Where it doesn't (men's), plain ranking does as well or better. The purchase outcome is noise
  (every Qini CI spans or nearly spans 0).
- **Matching the message to each customer did not help.** Matched message 18.30% visits vs men's e-mail to everyone
  18.25% (difference CI -0.45 to +0.49 points). Conversion 1.23% vs 1.25% (CI -0.11 to +0.07 points). **So we make no
  "tailored message" claim.**
- **Sleeping dogs: our models could not find real ones in this data.** For the best message, 0-0.35% of customers
  get a negative estimate on visits. The flagged groups actually showed *positive* held-out uplift (for example
  +2.1 points, CI +0.5 to +4.0, on conversion). The share's CI resamples rows of fixed scores, not model refits, so it
  is too narrow. This finding is limited to Hillstrom; telecom backfire is real (above). **Our models can't reliably
  pick out who will be pushed away, so we use a rule-based guardrail instead.**
- Context from a larger public benchmark run alongside this (risk vs uplift ranking, same Qini definition): on the
  Criteo ad experiment (1.5M-row sample) risk ranking tied or did better than every uplift model (visit Qini 0.091
  vs 0.089; conversion 0.180 vs 0.165). On Orange Belgium's randomized telecom data (11,896 customers), uplift models
  did no better than a plain churn model (Verhelst et al. 2023, https://arxiv.org/abs/2312.07206).

## 2. Value split for the strategy chart (`value_split.py`, all synthetic)
Rebuilds the old strategy chart from the engine outputs and splits each policy into business net, customer savings,
and revenue given back on purpose. It reproduces the old chart exactly (ours $27,658 vs top-10%-risk credit $30,245).
The $2,587 gap is entirely the cheaper-plan moves: retention offers alone net +$60,828 (822 contacts); 389 plan moves
net -$32,859 while returning $68,973 to customers. The old chart charged only half of that revenue (a 0.5 customer-
benefit weight), so in full company dollars "ours" is negative. At realized save rates near the field evidence
(5-15%), every fixed-pick contact policy loses money against doing nothing.

## 3. Chart data (`chart_data.py` -> `out/chart_bars.csv`, `out/chart_receipt.csv`, `out/chart_preview.png`)
All numbers synthetic / simulated.
- Every policy is picked assuming a 10% save rate and scored at 5% (headline), 10% and 22%.
- Business net is in **full company dollars**: no half-weighting, upsell margin included, customer savings weighted 0.
- Headline bar (bold): **Retention-only, re-picked at 10%**. Subtitle: "Profitable if real save rates are at least
  about 4.5%. At 10% it wins ~7 in 8; at 5% it's a coin flip."
- Whiskers are the **realized-outcome bootstrap** (2,000 account resamples that also draw who churns and who is
  saved), read from the policy table (CI, P(net>0)) and its RESULTS.md section 4 (mean). The expected-value bootstrap
  CI is kept in `chart_bars.csv` only (`ev_*` columns), not drawn.
- **Money back to customers** sits on its own small panel ("also a cost to T-Mobile; not in business net"), so it
  does not stretch the business-net axis. Plan moves are never texted; they go on the receipt.
- Receipt headline, **strict like-for-like rule**: losing a price guarantee, adding a 50 GB cap, losing hotspot or
  losing perks all mean "you'd lose something". **394 like-for-like accounts** ($4,600/month if every account
  switched; **$1,656/year at an assumed 3% switch rate**, range 2-13%: $1,104-$7,176). 142 moves go on the separate
  "cheaper, but you'd lose something" line ($8,965/month), which never counts in the headline. Source: the
  receipt table named in the policy table's RESULTS.md section 6 was not present as `receipt.csv`, so the script
  reads the per-move classification `plan_moves_classified.csv` (cap / guarantee / hotspot flags) and the
  optimizer's reason text for perks (no strict-set account mentions perks). If neither file exists it falls back to
  the older optimizer-agrees-with-engine set minus price-guarantee losses (403 accounts) and says FALLBACK.
- "Receipt only" bar = the receipt part alone (no texts, no contact cost) of the texts + like-for-like receipt run
  (`receipt_net_full`). It is a small net company cost at every save rate.
- Every bar, including the shipped engine (-$60,009 at 10%), is in full company dollars; the script asserts it.
- Footnote: "Perk reminders never pay as texts; shown on the bill/app instead."
- Profit-ranked incl. upsell is one **Q&A-only** row: its gain rests on the 3.9%/quarter upgrade assumption
  ($10,946 of the $16,676 at 10% is step-up/family upsell margin). Home Internet is a footnote, not a bar: "never
  picked at a 1-4% take rate (derived)". The script checks that the 1/2/4% rows pick zero Home Internet and equal the
  no-Home-Internet row before printing that line.
- Pending bars are hidden on the chart, kept in `chart_bars.csv` with `status=pending`, and listed in one footnote.
  Rows decided at their own rate (not picked at 10%) are not used for the 5%/22% columns.
- Inputs: the shared policy-evaluation table (env `TM_POLICY_BY_SAVE_RATE`); the plan-mix optimizer output
  `data/household_plan.csv` (env `HOUSEHOLD_PLAN_CSV`; 5,042 rows). That file is a copy of the household plan
  optimizer's output (`harness/household_optimizer.py`, commit d3adf09, run read-only on the sandbox), originally
  written to a temp folder at 22:47 PT on 2026-10-17 and copied here so it doesn't vanish
  (sha256 63eccb2e13f235e367436fe5cd6550d9c061d63176d1a0290836b058905a3933). `data/` is gitignored; this file is
  force-added.

| Picked at 10%; business net, full $ (synthetic) | scored 5% (headline) | 10% | 22% |
|---|---|---|---|
| Shipped engine (picks made at its assumed ~44%) | -$69,434 | -$60,009 | -$37,388 |
| Top 10% risk, $25 credit to all | -$9,114 | -$4,116 | +$7,880 |
| Top 10% risk, best fix for each (fix chosen at each rate; 498 contacts) | -$2,730 | +$3,640 | +$21,552 |
| Retention-only, picks fixed at 44% | -$10,706 | -$1,540 | +$20,460 |
| **Retention-only, re-picked at 10% (246 contacts)** | **+$538** | **+$6,211** | +$19,825 |
| Receipt only, like-for-like, no texts (3% switch) | -$1,643 | -$1,629 | -$1,598 |
| Retention texts + like-for-like receipt (3% switch) | -$1,104 | +$4,582 | +$18,227 |
| Profit-ranked incl. upsell (Q&A only; 3.9%/qtr upgrade assumption) | +$11,003 | +$16,676 (334) | +$30,290 |
| Do nothing | $0 | $0 | $0 |

No bar is pending.

Retention-only re-picked at 10%, realized-outcome bootstrap: at 10% mean +$6,328, 95% CI -$3,375 to +$18,970,
P(net > 0) = 0.876; at 5% mean +$491, CI -$5,229 to +$9,953, P = 0.487. (Expected-value bootstrap, CSV only: 10% CI
$4,590-$7,871; 5% CI -$66 to $1,184.) Break-even save rate: 4.5%.

## Honest weak spots
- Our customers have no response labels. The data generator's churn does not respond to contact at all, so **every
  persuadable / sleeping-dog split on our customers is our own assumption**, and every dollar above depends on
  assumed save, accept and take rates.
- The falling/volatile-usage push-away pattern from the 2016 wireless trial cannot occur here: no account swings more
  than 50% month to month or drops more than 30%. That guardrail is a rule that currently excludes 0 accounts.
- The real-data validation is retail e-mail, a different product, channel and outcome.
- Not built yet in v1: per-customer plain-language reasons, the synthetic transfer, and the engine adapter.
