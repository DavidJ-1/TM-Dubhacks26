# Prior art: The Un-Churner and past T-Mobile hackathon winners
Researched by Grok Bot, Sat Oct 17 2026, ~8:45 PM PT. **Sourced** = stated on the linked page. **Inferred** = our reading, not stated anywhere. Not committed.

## (a) The Un-Churner: facts (all sourced)
- Page: https://devpost.com/software/the-un-churner. Five-person team (Kelley Sheffield, Greg Howlett, Anum Bhamani, Paul Kim, Will Lyons), created Mar 30, 2019.
- Hackathon: **T-Mobile "Closer to the Customer" 2019**, run with Microsoft at Georgia Tech, Atlanta, Mar 29–30, 2019. It had 75 participants, $13k in prizes and 22 gallery projects. https://t-mobilec2chack19.devpost.com/ and https://t-mobilec2chack19.devpost.com/project-gallery
- What it built: a Python ML model giving each customer a churn probability, using "length of account, number of lines, usage, and payments left on devices," behind a Flask backend. The idea was that at-risk users would see "a non-invasive widget at the top of the [T-Mobile app] screen demonstrating a different phone plan or device."
- Self-reported gaps: "We were not able to fully implement an end-to-end demo of a customized front end, but we can demonstrate the algorithm in action." They dropped React as "too ambitious," and plan, phone and accessory recommendations were cut from scope ("Initially, we were also very ambitious…").
- Outcome: **no prize.** Its "Submitted to" entry has no Winner badge. The only three badges in that hackathon went to the projects listed in (d).
- Also: two other churn projects at the same event, **Churn-Burn** (https://devpost.com/software/churn-burn) and **T-Mobile Customer Satisfaction Predictor** (https://devpost.com/software/tmobile-customer-satisfaction-predictor), also won nothing. So did **RepPrep** (https://devpost.com/software/repprep), an ML plan/phone recommender for store reps.

## (b) Their prompt vs ours: **different**
- **Theirs (2019), quoted in full:** open-ended AI/ML theme. "We invite fresh and seasoned developers alike to join us to invent the future of AI & ML… come up with a demo or app to demonstrate your vision for what these technologies can do. The opportunities to transform the way we interact with our customers are limited only by your imagination." No specific challenge, no churn or recommendation direction. **Judging:** Use of Technology / Functionality ("Was a working, functional prototype demonstrated?") / Scalability / Creativity. Source: https://t-mobilec2chack19.devpost.com/
- **Ours (DubHacks '26):** "Reimagining Recommendations in Wireless Commerce." Build a recommendation system for phones, plans, upgrades or bundles, "or helps the carrier respond appropriately when a customer might leave," with "a recommendation that makes sense for this customer, in this situation, at this time." Direction 3, **Next Best Moment**, explicitly asks for a churn-risk score that leads to *ranked, cost-aware actions*, where "the discount is not automatic" and restraint counts. Rubric: Customer value 30% / Signals 25% / Explainability 20% / Feasibility + demo 25%. Source: /workspace/tmobile/handoff/plan-doc-2026-10-17.txt and strategy/tmobile-brief-summary.md
- **Honest read:** the *prompts* differ a lot, but the *idea* overlaps: churn score, then a suggested plan or device. Our prompt practically invites a churn-score project, so the judges will likely see several. What they'll compare is the second half: which action, why, at what cost, and whether "do nothing" is allowed.

## (c) Why it likely lost (inferred)
1. **No working end-to-end demo** (sourced admission). "Functionality: was a working prototype demonstrated?" was one of four criteria, so it likely lost there.
2. **The recommendation half was missing.** The "different plan or device" widget was an idea, not built. That left a bare churn score, the most common entry (3 of 22 projects), which hurts on Creativity.
3. **Out of step with what the judges rewarded.** All three winners used live, real-time AI tooling (speech-to-text, sentiment, BERT, mostly via Microsoft Azure, the co-sponsor) to help *reps during live customer interactions*. A static churn score on a training dataset scores lower on "Use of Technology."
4. **Most likely a stage problem, not an idea problem.** RepPrep, which did build a recommender, also lost. Explaining the loss as "churn is a bad idea" goes further than the evidence.

## (d) What the winners did
**2019 Closer to the Customer** (sourced, each project's page):
- 1st **T-Support**: Twilio call transcripts, with a BERT/attention classifier matching customer questions to the best rep answers. https://devpost.com/software/t-support
- 2nd **T-Gist**: live call transcription, sentiment and key-point summaries for handoffs (Azure). https://devpost.com/software/t-gist
- 3rd **T.E.R.R.A.**: real-time speech sentiment scoring that prompts escalation (Azure). https://devpost.com/software/terratmo
- Pattern (inferred): a working live demo, real-time signals, and an aid for reps during live conversations.

**HackUTD 2025 T-Mobile track** (sourced). The prompt was entirely different: "Build the T-Mobile Customer Happiness Index — a real-time, data-driven solution that captures how customers feel about T-Mobile… streams live sentiment, feedback, and network data to detect issues before they spread… turn customer emotion into actionable insight." https://legend.hackutd.co/ Winners: 1st Beacon, 2nd InsighT, 3rd HarmoniQ (T-Mobile post: https://www.linkedin.com/posts/t-mobile-innovate_innovation-thrives-where-industry-and-education-activity-7407129464977076224-4YP-; Devpost badges: https://hackutd-2025.devpost.com/project-gallery)
- **Beacon**: a 0–100 Happiness Score from calls (Twilio), social and network data, with PII scrubbing; sentiment via **LLaMA on Groq**. https://devpost.com/software/na-504rkg
- **InsighT**: a PM dashboard with "AI-powered actionable opportunities" from **Gemini 2.0 Flash**. https://devpost.com/software/t-insights
- **HarmoniQ**: a "command center" for PMs with outage prediction (scikit-learn) and a **Gemini** assistant writing suggestions. https://devpost.com/software/x-yiqm81
- **Correction for tm-strategy:** two of the three used Gemini. Beacon used LLaMA via Groq. Say "LLM-written suggestions," not "Gemini." The winners answered a different prompt, so they show T-Mobile judges' taste (live data, working demo), not what wins *our* prompt.

## (e) Our differentiators, the risk, and pitch lines
**Differentiators:** we built the recommendation half they never did, end to end. Each customer gets a decision with cost (offer vs doing nothing, priced by expected value). "Do nothing" can win, and so can a cheaper plan or "wait to upgrade." Every customer card explains its choice in plain language. Offers draw only on the sandbox's real promo and eligibility rules. The live demo sends a real text. There's also a simulated test against no outreach and blanket discounts. No LLM, all data synthetic and labeled.
**Risk of looking like the Un-Churner:** real if we open on a churn score, a risk ranking or a ROC chart. The 2019 judges saw three churn models and rewarded none. Mitigation: open on a *decision* (the customer cards, as the app now does), and say "churn score" only as an input.
**Pitch lines:**
1. "A churn score tells you who might leave. It doesn't tell you what to do, and often the right answer is nothing. That decision is what we built."
2. "Churn models have been built at T-Mobile hackathons since 2019. None of the ones we found won, and none showed the next step: the right offer, priced against doing nothing, explained to the customer in one text."
3. "One of these customers we deliberately *don't* text, and another we move to a *cheaper* plan. That's restraint you can check." (Match this to the final card order before using it.)
