# [Project name: TBD]

*Everything here runs on the judges' synthetic sandbox. Every customer, number and outcome below is synthetic or simulated. None of it is real T-Mobile customer data.*

## Inspiration
A churn score tells you who might leave, but not what to do, and often the right answer is to do nothing. In a 65,000-customer wireless field experiment, proactive outreach about cheaper plans *raised* churn from about 6% to 10% ([Ascarza, Iyengar & Schleicher 2016, JMR](https://doi.org/10.1509/jmr.13.0483)). Another study found the riskiest customers and the most persuadable ones overlap only about half the time ([Ascarza 2018, JMR](https://doi.org/10.1509/jmr.16.0163)). So we set out to build the decision, not just the score.

## What it does
For every customer, it picks one priced action: a better-fitting plan, a fix plus a credit, a free check-in, or nothing at all. It explains why and writes the exact text, in English or Spanish. Of 5,042 synthetic accounts, it contacts 1,314 and leaves 3,728 alone.

**1. Would a real person want it?** Yes, because it often saves them money or leaves them alone.
- **Customer 38**, a two-line couple over 55, pays full price for their plan. They qualify for the 55+ version of the same plan, so we tell them: $110 a month instead of $150 for both lines, same features.
- **Customer 24** has had nine support contacts in nine months. A naive rule would panic. Ours sees that every contact was resolved, there's no shopping around and the plan fits. We do nothing, and their phone stays silent.

**2. Does it use multiple signal types?** Yes, all three:
- **Commerce:** plan, price, phone financing, bill changes.
- **Customer:** lines, tenure, support history.
- **Real-time:** recent support contacts, app activity going quiet, comparing carriers, and whether the customer asked us about transferring their number. Those last two come from what the customer tells us; we don't track calls to competitors.

**Customer 04** shows the mix: their bill is up 14% and they've had five support contacts in 90 days. We fix the problem first with a callback, plus a one-time $25 care credit under the promotion's own three-contact rule.

**3. Does it give a plain-language why?** Each card shows up to three specific reasons, like credit-decision reason codes, plus every option we weighed and why it lost, such as "needs 3+ support contacts in 90 days" or "no bill credits below 5% risk."

**4. Is the prototype believable and the demo clear?** It runs end to end, and judges can change it live. **Customer 21** has been with us over five years, but their app use has gone quiet, they're comparing carriers, and they asked us about transferring their number. Credits would lose money here, so the pick is a free plan check-in. Untick "asked us about transferring their number" and the simulated risk drops from 5.4% to 3.5%, still a check-in. Untick "comparing carriers" and it falls to 1.1% and flips to do nothing.

**The comparison (simulated):** under the same simulated assumptions, discounting everyone spends $126,000 on credits and texts 4,523 people who weren't leaving. Ours spends $6,700 on credits. It also reaches more of the customers who leave than a rule that only targets the highest risk scores, 96 versus 88.

**How it's different:** past T-Mobile hackathon winners built sentiment-score screens with LLM-written suggestions for staff. The closest earlier idea, [The Un-Churner](https://devpost.com/software/the-un-churner) (2019), paired a churn score with a plan pop-up and didn't win. Ours makes one priced decision per customer, where doing nothing is allowed. Every offer is checked against real promotion and eligibility rules, a cheaper plan counts as retention, there's no LLM in the product, and it writes the exact text in English or Spanish.

## How we built it
We started from the judges' sandbox: 5,042 synthetic accounts (5,000 plus 42 test personas) with usage, billing, support logs, risk signals, and real plan and promotion rules. Because the sandbox has no churn outcomes, we generated simulated labels and trained a churn score on them. On synthetic data, its riskiest 10% hold 62% of leavers. That shows the pipeline works, not real-world accuracy.

Every action a customer qualifies for is priced against doing nothing, which is always on the list at $0. An offer has to beat it. Eligibility comes from the sandbox's own tables, plus our guardrails. A simulated upgrade score, built from device age, serves only as a gate for upgrade offers. Texts are built from templates, and every dollar amount is checked against the promotions and plans tables.

## Challenges we ran into
- With no real outcomes, we couldn't measure lift, so we label every number simulated and don't claim one.
- Texts that quote prices have to be right every time.

## Accomplishments that we're proud of
- Restraint you can check: most accounts get no text at all.
- **It still pays at realistic save rates (simulated).** We re-ran the engine assuming the roughly 10% save rate real retention campaigns report, texting retention offers only where they still pay off: 246 accounts. It's profitable if the real save rate is at least about 4.5%. At 10% it comes out ahead in about 7 of 8 resamples, and at 5% it's a coin flip. Measured campaigns land around 6–11% ([Verhelst et al. 2023](https://arxiv.org/abs/2312.07206); [Ascarza 2018](https://doi.org/10.1509/jmr.16.0163)). When an offer isn't worth it, the engine picks doing nothing.
- One customer moved to a cheaper plan with the same features.

## What we learned
Contact can backfire, high risk isn't the same as persuadable, and a churn score is only an input. The useful part is choosing the action and explaining it.

## What's next
- **A holdout test with real customers** to see whether it keeps them for less.
- **Uplift-ready:** each decision is written out with the data fields behind it, and adding a random holdout group would let us measure the true effect over time. At our roughly 5,000-account scale it could only catch very large effects; a reliable read needs about 12,800 accounts per group (synthetic power estimate).
- **Safer plan moves:** the 2016 study's harm was concentrated among customers with volatile or falling usage, so we'd exclude volatile-usage customers from plan moves.
- Testing the simulated upgrade score against real purchases.
