# [Project name: TBD]

*Everything here runs on the judges' sandbox data. None of it is real T-Mobile customer data, and every dollar figure rests on the assumptions stated next to it.*

## Inspiration
A churn score tells you who might leave, but not what to do, and often the right answer is to do nothing. In a 65,000-customer wireless field experiment, proactive outreach about cheaper plans *raised* churn from about 6% to 10% ([Ascarza, Iyengar & Schleicher 2016, JMR](https://doi.org/10.1509/jmr.13.0483)). Another study found the riskiest customers and the most persuadable ones overlap only about half the time ([Ascarza 2018, JMR](https://doi.org/10.1509/jmr.16.0163)). So we set out to build the decision, not just the score.

## What it does
For every customer, it picks one priced action: a better-fitting plan, a fix plus a credit, a free check-in, or nothing at all. It explains why and writes the exact text, in English or Spanish. It checks all 5,042 sandbox accounts, flags 505 as at risk and messages 184. For the rest, doing nothing wins.

**1. Would a real person want it?** Yes, because it often saves them money or leaves them alone.
- **Customer 38**, a two-line couple over 55, pays full price for their plan. They qualify for the 55+ version of the same plan, which costs $40 a month less for the same features. We don't text it, because unprompted plan suggestions can backfire: it shows on their bill and in the app as a tap-to-confirm line.
- **Customer 24** has had nine support contacts in nine months. A naive rule would panic. Ours sees that every contact was resolved, there's no shopping around and the plan fits. We do nothing, and their phone stays silent.

**2. Does it use multiple signal types?** Yes, all three:
- **Commerce:** plan, price, phone financing, bill changes.
- **Customer:** lines, tenure, support history.
- **Real-time:** recent support contacts, app activity going quiet, a carrier-shopping score that comes with the account data, and whether the customer asked us about transferring their number. We don't track visits to other carriers' sites or calls to competitors.

**Customer 04** shows the mix: their bill is up 14% after a promo ended, and they've had five support contacts in 90 days with three still unresolved. With an open issue, the only message allowed is a fix, so they get an in-app note that our team is working on it, with no sales pitch. A $25 care credit on top was weighed and scored lower, so it isn't sent.

**3. Does it give a plain-language why?** Each card shows up to three specific reasons, like credit-decision reason codes, plus every option we weighed and why it lost, such as "needs 3+ support contacts in 90 days" or "no bill credits below 5% risk."

**4. Is the prototype believable and the demo clear?** It runs end to end as one scroll page, and judges can watch a decision change live. Press **Live what-if** on **customer #02363** and step through four real-time events:

| Event | Churn risk (90 days) | Decision |
|---|---:|---|
| Start | 5.83% | Do nothing |
| 1. Logged into the app | 5.62% | Do nothing |
| 2. Dropped call, with a coverage chat still open | 9.07% | Do nothing |
| 3. Carrier-shopping score up (0.21 → 0.80, a field in the account data) | 18.42% | Do nothing |
| 4. Asked about moving their number to another carrier | 26.31% | **In-app fix-first message**, in English or Spanish |

At each step the page shows which reason moved the score and why the engine still holds back. At event 4 a fix-first note finally beats doing nothing, so it's sent in the app with no sales pitch. The week's totals (184 messages, +$3,938) don't move during the what-if.

**Checking our own picks:** giving the same offers to randomly picked customers loses money on average, and so does picking at random among the high-risk ones. Shuffling the churn answers wipes out the gain. Scoring every customer with a model that never saw them in training picks almost the same set, 179 contacts, with about the same result.

**How it's different:** past T-Mobile hackathon winners built sentiment-score screens with LLM-written suggestions for staff. The closest earlier idea, [The Un-Churner](https://devpost.com/software/the-un-churner) (2019), paired a churn score with a plan pop-up and didn't win. Ours makes one priced decision per customer, where doing nothing is allowed. Every offer is checked against real promotion and eligibility rules, a cheaper plan counts as retention, there's no LLM in the product, and it writes the exact text in English or Spanish.

## How we pick the deal (the deal engine)
This is the heart of the project: one priced decision per customer, where staying silent is a real option.

For every customer, the engine lists 15 possible moves and scores **doing nothing** first, at $0. Every other move has to beat it, and for 4,858 of 5,042 customers none does: 4,361 get nothing at all, and 497 just get a bill line.

- **Real rules first.** Most of the 15 moves are ruled out before any math, about 13 for a typical customer, by the sandbox's real plan and promotion eligibility rules (line counts, discount groups, the care credit's three-contact rule) and by our guardrails.
- **Expected profit for what's left.** Each remaining move is priced as chance of leaving × chance it keeps them × what a saved account is worth, minus the offer's cost, agent time (about $15 for each fix-first contact) and an annoyance charge of $2 to $6 per contact (team estimate).
- **An open issue comes first.** If a customer has an unresolved support contact, the only message allowed is a fix. Of the 184 messages, 151 are fix-first, 29 are a $25 care credit plus a fix, 2 are check-ins, 1 is a bill-shock credit and 1 is a perk reminder. Only the 14 calls promise a call.
- **Their channel, their language.** 64 texts, 74 in-app notes, 32 emails and 14 calls, each by the customer's own preference, written in English and Spanish.
- **Cheaper plans go on the bill, not in a text.** 390 customers get a bill line for a plan with the same features at a lower price, and 107 more get a "cheaper, but you'd lose X" line that names what they'd give up.

Grounded in Ascarza 2018, ["Retention Futility"](https://doi.org/10.1509/jmr.16.0163) (JMR); Ascarza, Iyengar & Schleicher 2016, ["The Perils of Proactive Churn Prevention Using Plan Recommendations"](https://doi.org/10.1509/jmr.13.0483) (JMR); Godinho de Matos, Ferreira & Belo 2018, ["Target the Ego or Target the Group"](https://doi.org/10.1287/mksc.2018.1099) (Marketing Science); and Gupta, Lehmann & Stuart 2004, ["Valuing Customers"](https://doi.org/10.1509/jmkr.41.1.7.25084) (JMR).

## How we built it
We started from the judges' sandbox: 5,042 accounts (5,000 plus 42 test personas) with usage, billing, support logs, risk signals, and real plan and promotion rules. Because the sandbox has no churn outcomes, we built stand-in labels: we extended the judges' public example formula from 7 terms to 21 (unresolved vs. negative support contacts, early tenure, app use, promo expiry and more), set the level to T-Mobile's reported postpaid churn (about 2.7% over 90 days), and drew one outcome per account. Then we trained a plain logistic regression on 20 fields. It explains itself exactly: each field's push on the score becomes the top three reasons to leave and to stay.

**How good is it, honestly?** Measured against the judges' public example model's churn probabilities, our out-of-fold AUC is **0.797**, where about **0.825** is the best possible (the example model scored against itself). Against our own labels it scores 0.85, but those labels come from the same fields, so that only shows the pipeline works. The judges' hidden model is built differently, so 0.797 is our best stand-in, not a prediction.

**What we tried.** We didn't stop at one model. Every candidate was scored out-of-fold on the same 5,000 accounts, both on our labels and against the judges' example model:

| Model | AUC on our labels | AUC vs judges' example model |
|---|---:|---:|
| **Logistic regression, 20 fields (shipped)** | **0.853** | **0.797** |
| Spline logistic regression + raw support-contact counts | 0.860 | 0.806 |
| Weibull survival model | 0.861 | 0.802 |
| Explainable boosting (EBM) | 0.857 | 0.794 |
| LightGBM, tuned | 0.847 | 0.789 |
| Gradient-boosted trees, tuned | 0.844 | 0.786 |
| Same model without port-out or carrier-shopping fields | 0.851 | 0.780 |
| Rule: rank by support contacts in 90 days | 0.834 | 0.776 |
| *Ceiling: the judges' example model itself* | *0.859* | *0.825* |
| *Ceiling: our own label formula* | *0.864* | *0.804* |

Fold-to-fold noise is about ±0.03, so nothing fancier beat the plain model by more than noise, and trees were consistently a bit worse. Our own label formula only reaches 0.804 against the judges' model, so 0.797 is close to the most our labels allow: better labels, not a fancier model, are the way up. We kept the simplest model because its probabilities are well calibrated (the deal engine multiplies them by dollars) and its reasons are exact. Leakage checks: label columns are banned from features, no single field scores above 0.84, and every score is out-of-fold.

Every action a customer qualifies for is priced against doing nothing, which is always on the list at $0. An offer has to beat it. Eligibility comes from the sandbox's own tables, plus our guardrails. Texts are built from templates, and every dollar amount is checked against the promotions and plans tables.

## Challenges we ran into
- With no real outcomes, we couldn't measure lift, so we don't claim one. Every money figure is an estimate under the save rate it names.
- Texts that quote prices have to be right every time.
- Profit depends on a save rate we can only assume: retention-only outreach breaks even at a 5.17% save rate and comes out ahead only 41% of the time at 5%. Measured retention campaigns run from about 2% to 11% relative; this pays off in the stronger ones and loses money in the weakest.
- We value a saved account at its own monthly margin times 19.3 months, about $1,500 for an average account and about $2,000 for the ones we message. If a saved customer stays as risky as before, most of the money disappears. That's the first thing a real rollout tests.

## Accomplishments that we're proud of
- Restraint you can check: 4,858 of 5,042 accounts get no message at all.
- **The next version pays at realistic save rates.** In the next version of the engine, we re-ran it assuming a 10% save rate, our central assumption, and sent retention messages only where they still pay off, after our do-not-contact rules. Of 5,042 accounts scored, 505 are flagged and 184 get a message, each by the channel the customer prefers (64 by text; the rest in-app, by email or a call). Those 184 messages come out +$3,938 ahead, with a 95% range of −$3,186 to +$13,148, and break even at a 5.17% save rate. Customers with an open support ticket get a fix-your-issue-first message instead of a perk reminder, and we charge about $15 of agent time for each fix-first contact, because an open issue takes an agent to fix. Measured retention campaigns run from about 2% to 11% relative ([Ascarza 2018](https://doi.org/10.1509/jmr.16.0163); [Verhelst et al. 2023](https://arxiv.org/abs/2312.07206); [Marketing Science 2018](https://doi.org/10.1287/mksc.2018.1099)), so this pays off in the stronger campaigns and loses money in the weakest. There's an 80% chance of coming out ahead at our central 10% assumption (41% at 5%). When an offer isn't worth it, the engine picks doing nothing.
- One customer moved to a cheaper plan with the same features.
- **A fairness audit we'd run weekly.** In our test on the sandbox data, at the same churn risk, accounts labeled senior or student were about 2.7 points less likely to get a retention message, roughly 10 and 16 accounts. Counting the cheaper-plan savings on the bill, they were shown a savings line more often than others, about 8 and 5 points. This is the audit we'd run weekly on real data.

## What we learned
Contact can backfire, high risk isn't the same as persuadable, and a churn score is only an input. The useful part is choosing the action and explaining it.

## What's next
- **A rollout with real customers** to see whether it keeps them for less.
- **Uplift-ready:** each decision is written out with the data fields behind it, and a holdout is built in so a rollout can measure saves.
- **Safer plan moves:** the 2016 study's harm was concentrated among customers with volatile or falling usage, so we'd exclude volatile-usage customers from plan moves.
