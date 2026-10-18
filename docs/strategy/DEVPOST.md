# [Project name: TBD]

*Everything here runs on the judges' synthetic sandbox. Every customer, number and outcome below is synthetic or simulated. None of it is real T-Mobile customer data.*

## Inspiration
A churn score tells you who might leave, but not what to do, and often the right answer is to do nothing. In a 65,000-customer wireless field experiment, proactive outreach about cheaper plans *raised* churn from about 6% to 10% ([Ascarza, Iyengar & Schleicher 2016, JMR](https://doi.org/10.1509/jmr.13.0483)). Another study found the riskiest customers and the most persuadable ones overlap only about half the time ([Ascarza 2018, JMR](https://doi.org/10.1509/jmr.16.0163)). So we set out to build the decision, not just the score.

## What it does
For every customer, it picks one priced action: a better-fitting plan, a fix plus a credit, a free check-in, or nothing at all. It explains why and writes the exact text, in English or Spanish. It checks all 5,042 synthetic accounts, flags 505 as at risk and messages 184. For the rest, doing nothing wins.

**1. Would a real person want it?** Yes, because it often saves them money or leaves them alone.
- **Customer 38**, a two-line couple over 55, pays full price for their plan. They qualify for the 55+ version of the same plan, which costs $40 a month less for the same features. We don't text it, because unprompted plan suggestions can backfire: it shows on their bill and in the app as a tap-to-confirm line.
- **Customer 24** has had nine support contacts in nine months. A naive rule would panic. Ours sees that every contact was resolved, there's no shopping around and the plan fits. We do nothing, and their phone stays silent.

**2. Does it use multiple signal types?** Yes, all three:
- **Commerce:** plan, price, phone financing, bill changes.
- **Customer:** lines, tenure, support history.
- **Real-time:** recent support contacts, app activity going quiet, comparing carriers, and whether the customer asked us about transferring their number. Those last two come from what the customer tells us; we don't track calls to competitors.

**Customer 04** shows the mix: their bill is up 14% after a promo ended, and they've had five support contacts in 90 days with three still unresolved. With an open issue, the only message allowed is a fix, so they get an in-app note that our team is working on it, with no sales pitch. A $25 care credit on top was weighed and scored lower, so it isn't sent.

**3. Does it give a plain-language why?** Each card shows up to three specific reasons, like credit-decision reason codes, plus every option we weighed and why it lost, such as "needs 3+ support contacts in 90 days" or "no bill credits below 5% risk."

**4. Is the prototype believable and the demo clear?** It runs end to end, and judges can change it live. **Customer 21** has been with us over five years, but their app use has gone quiet, they're comparing carriers, and they asked us about transferring their number. The engine weighs a free check-in, a loyalty credit and a keep-your-phone credit, and each is expected to cost more than it brings back, so it picks doing nothing and says why. Judges can flip signals in the what-if panel and watch the risk and the pick change.

**Checking our own picks (simulated):** giving the same offers to randomly picked customers loses money on average, and so does picking at random among the high-risk ones. Shuffling the churn answers wipes out the gain. Scoring every customer with a model that never saw them in training picks almost the same set, 179 contacts, with about the same result.

**How it's different:** past T-Mobile hackathon winners built sentiment-score screens with LLM-written suggestions for staff. The closest earlier idea, [The Un-Churner](https://devpost.com/software/the-un-churner) (2019), paired a churn score with a plan pop-up and didn't win. Ours makes one priced decision per customer, where doing nothing is allowed. Every offer is checked against real promotion and eligibility rules, a cheaper plan counts as retention, there's no LLM in the product, and it writes the exact text in English or Spanish.

## How we pick the deal
For every customer, the engine lists 15 possible moves and scores **doing nothing** first, at $0. Every other move has to beat it, and for 4,858 of 5,042 customers none does (simulated).

- **Real rules first.** Most of the 15 moves are ruled out before any math, about 13 for a typical customer, by the sandbox's real plan and promotion eligibility rules (line counts, discount groups, the care credit's three-contact rule) and by our guardrails.
- **Expected profit for what's left.** Each remaining move is priced as chance of leaving × chance it keeps them × what a saved account is worth, minus the offer's cost, agent time (about $15 for each fix-first contact) and an annoyance charge of $2 to $6 per contact (team estimate).
- **An open issue comes first.** If a customer has an unresolved support contact, the only message allowed is a fix. Of the 184 messages, 151 are fix-first, 29 are a $25 care credit plus a fix, 2 are check-ins, 1 is a bill-shock credit and 1 is a perk reminder. Only the 14 calls promise a call.
- **Their channel, their language.** 64 texts, 74 in-app notes, 32 emails and 14 calls, each by the customer's own preference, written in English and Spanish.
- **Cheaper plans go on the bill, not in a text.** 394 customers get a bill line for a plan with the same features at a lower price, and 94 more get a "cheaper, but you'd lose X" line that names what they'd give up.

Grounded in Ascarza 2018, ["Retention Futility"](https://doi.org/10.1509/jmr.16.0163) (JMR); Ascarza, Iyengar & Schleicher 2016, ["The Perils of Proactive Churn Prevention Using Plan Recommendations"](https://doi.org/10.1509/jmr.13.0483) (JMR); Godinho de Matos, Ferreira & Belo 2018, ["Target the Ego or Target the Group"](https://doi.org/10.1287/mksc.2018.1099) (Marketing Science); and Gupta, Lehmann & Stuart 2004, ["Valuing Customers"](https://doi.org/10.1509/jmkr.41.1.7.25084) (JMR).

## How we built it
We started from the judges' sandbox: 5,042 synthetic accounts (5,000 plus 42 test personas) with usage, billing, support logs, risk signals, and real plan and promotion rules. Because the sandbox has no churn outcomes, we generated simulated labels and trained a churn score on them. On synthetic data, its riskiest 10% hold 62% of leavers. That shows the pipeline works, not real-world accuracy.

Every action a customer qualifies for is priced against doing nothing, which is always on the list at $0. An offer has to beat it. Eligibility comes from the sandbox's own tables, plus our guardrails. A simulated upgrade score, built from device age, serves only as a gate for upgrade offers. Texts are built from templates, and every dollar amount is checked against the promotions and plans tables.

## Challenges we ran into
- With no real outcomes, we couldn't measure lift, so we label every number simulated and don't claim one.
- Texts that quote prices have to be right every time.
- Profit depends on a save rate we can only simulate: retention-only outreach breaks even at a 5.17% save rate and comes out ahead only 41% of the time at 5%. Measured retention campaigns run from about 2% to 11% relative; this pays off in the stronger ones and loses money in the weakest (simulated).
- We value a saved account at its own monthly margin times 19.3 months, about $1,500 for an average account and about $2,000 for the ones we message. If a saved customer stays as risky as before, most of the money disappears. That's the first thing a real rollout tests.

## Accomplishments that we're proud of
- Restraint you can check: 4,858 of 5,042 accounts get no message at all.
- **The next version pays at realistic save rates (simulated).** In the next version of the engine, we re-ran it assuming a 10% save rate, our central assumption, and sent retention messages only where they still pay off, after our do-not-contact rules. Of 5,042 accounts scored, 505 are flagged and 184 get a message, each by the channel the customer prefers (64 by text; the rest in-app, by email or a call). Those 184 messages come out +$3,938 ahead, with a 95% range of −$3,186 to +$13,148, and break even at a 5.17% save rate. Customers with an open support ticket get a fix-your-issue-first message instead of a perk reminder, and we charge about $15 of agent time for each fix-first contact, because an open issue takes an agent to fix. Measured retention campaigns run from about 2% to 11% relative ([Ascarza 2018](https://doi.org/10.1509/jmr.16.0163); [Verhelst et al. 2023](https://arxiv.org/abs/2312.07206); [Marketing Science 2018](https://doi.org/10.1287/mksc.2018.1099)), so this pays off in the stronger campaigns and loses money in the weakest. There's an 80% chance of coming out ahead at our central 10% assumption (41% at 5%). When an offer isn't worth it, the engine picks doing nothing.
- One customer moved to a cheaper plan with the same features.
- **A fairness audit we'd run weekly (simulated).** In our test on simulated data, at the same churn risk, accounts labeled senior or student were about 2.7 points less likely to get a retention message, roughly 10 and 16 accounts. Counting the cheaper-plan savings on the bill, they were shown a savings line more often than others, about 8 and 5 points. This is the audit we'd run weekly on real data.

## What we learned
Contact can backfire, high risk isn't the same as persuadable, and a churn score is only an input. The useful part is choosing the action and explaining it.

## What's next
- **A rollout with real customers** to see whether it keeps them for less.
- **Uplift-ready:** each decision is written out with the data fields behind it, and a holdout is built in so a rollout can measure saves.
- **Safer plan moves:** the 2016 study's harm was concentrated among customers with volatile or falling usage, so we'd exclude volatile-usage customers from plan moves.
- Testing the simulated upgrade score against real purchases.
