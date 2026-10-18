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
- Every policy is picked assuming a 10% save rate and scored at 5% (headline), 10% and 22%.
- Business net is in **full company dollars**: no half-weighting, upsell margin included, customer savings weighted 0.
- Customer savings are a separate series. Plan moves are never texted; they go on the receipt as **money back to
  customers**, and the same dollars appear as a cost on the company side, outside business net.
- Receipt headline: 488 accounts where the plan-mix optimizer and the offer engine agree exactly ($10,395/month if
  every account switched; $3,742/year at an assumed 3% switch rate, range 2-13%: $2,495-$16,216). 85 of the 488
  would lose a price guarantee and the receipt must say so. 194 more accounts are a separate "cheaper, but you'd
  lose something" line and never count in the headline.
- Home Internet take rate: 2% per offer contact per quarter, range 1-4%, eligible addresses only (derived). Bars at
  1%, 2%, 4% and none.
- Policy values are read from the shared policy-evaluation table; bars not computed there yet are marked pending.

| Picked at 10%; business net, full $ (synthetic) | scored 5% (headline) | 10% | 22% |
|---|---|---|---|
| Shipped engine (picks made at its assumed ~44%) | -$69,434 | -$60,009 | -$37,388 |
| Top 10% risk, $25 credit to all | -$9,114 | -$4,116 | +$7,880 |
| Retention-only, picks fixed at 44% | -$10,706 | -$1,540 | +$20,460 |
| **Retention-only, re-picked at 10% (246 contacts)** | **+$538** | **+$6,211** | +$19,825 |
| Profit-ranked incl. upsell, Home Internet 1/2/4% | pending | +$16,676 (334) | pending |
| Do nothing | $0 | $0 | $0 |

Retention-only re-picked at 10%: the expected-value bootstrap (2,000 account resamples) gives 95% CI $4,590-$7,871 at
10% and -$66 to $1,184 at 5% (P > 0 = 0.96). Realized outcomes are much noisier (5%: CI -$5,229 to $9,953, P > 0 =
0.49). Break-even save rate: 4.5%. **Profitable only if real save rates are at least about 4.5%, and at 5% it is a
coin flip on realized outcomes.**

## Honest weak spots
- Our customers have no response labels. The data generator's churn does not respond to contact at all, so **every
  persuadable / sleeping-dog split on our customers is our own assumption**, and every dollar above depends on
  assumed save, accept and take rates.
- The falling/volatile-usage push-away pattern from the 2016 wireless trial cannot occur here: no account swings more
  than 50% month to month or drops more than 30%. That guardrail is a rule that currently excludes 0 accounts.
- The real-data validation is retail e-mail, a different product, channel and outcome.
- Not built yet in v1: per-customer plain-language reasons, the synthetic transfer, and the engine adapter.
