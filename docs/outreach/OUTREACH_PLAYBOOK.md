# Outreach playbook: when we reach out, how, and what we say

**All customers and numbers here are synthetic** (judge sandbox stub data, as_of 2026-10-01). No real T-Mobile customer data. No LLM: every message is a fixed template (`templates.json`) whose slots are filled from sandbox fields or the engine output by `draft_outreach.py`. Research basis: `RESEARCH.md` §14 (outreach channel, timing and rules; commit 63067b4) and §15 (family plans, multi-line accounts and lock-in; commit f7cce1e).

**Labels:** "synthetic" stays in internal docs like this one. **No customer message, receipt line or UI card text says "synthetic"** (David's rule). The script fails if one does. Brief line references are to `handoff/plan-doc-2026-10-17.txt`.

**Current run (synthetic):** 184 accounts get a message and 4,858 stay silent. 3,935 accounts get at least one bill/app receipt line (6,339 lines). See `outreach_summary.md`.

## 1. When we contact, and when we stay silent
Maps to: customer value incl. "no good recommendation" (L43), "the one that says wait" (L47), the on-screen do-nothing outcome (L50), "helpful at the right time without being annoying" (L61).

Silence is the default. Rules run in this order, and the first one that applies decides:
1. **The engine says do nothing, so we stay silent.** The reason is stored (`happy` 1,107, `open_ticket` 1,041, `wait_payoff` 877, ...).
2. **Only retention actions that pay at a realistic save rate get a message.** These are the retention-only policy re-picked at a 10% save rate with a $1,478 kept-account value: 202 picks, break-even about 4.8% (tm-models, `inputs/guardrail_detail.csv`). Everything else the shipped engine would do is silent: `not_worth_contacting_at_realistic_save_rates` 724, `plan_move_receipt_only` 388.
3. **Opted out of marketing means no contact.** The sandbox has no opt-out field, so this is a hook (`--opt-out`).
4. **Backfire guardrail (`inputs/guardrail.csv`, the authority).** Of the 1,412 accounts with a non-`stable` `billing_history.change_reason` and an increase in 2026-07..09, an account is contacted only with a credit that offsets the increase. Two exemptions apply: fix-only callbacks, and increases that come only from a new phone the customer chose. We do not use "bill went up in 3 months" (4,679 accounts). This blocks 18 of the 202 picks (13 perk reminders, 5 check-ins), leaving 184.
5. **At most one proactive contact per account per quarter.** The sandbox has no outreach log, so this is a hook (`--contact-log`). Each run sends at most one message per account.
6. **Fix first.** With an unresolved support contact in the last 90 days, the only message allowed is a fix message, never an offer. 25 picked perk reminders become fix callbacks. People stay because nothing is going wrong (L89).

**How 184 maps to tm-models' "184 retention texts":** the accounts are the same 184 (`contact_ok` True). The difference is only what each message is:
- **Channel:** each account's stated preference. 64 are actual SMS texts, 74 in-app, 32 email and 14 agent calls.
- **Message type:** 25 perk reminders are sent as fix callbacks because the account has an open issue.
- **Swaps:** none at $1,478.

## 2. Timing
Maps to: L61, L64.
- **Payoff and promo-end messages go 10–40 days *before* the date, not after.** Churn rises right after a term or promo ends:
  - Becker, Spann & Schulze 2015: German DSL, month-25 churn more than 7× the average.
  - Schweidel, Fader & Bradlow 2008: subscribers drop a service soon after an intro promo ends.

  These are European DSL and 2008 US telecom data, not US wireless. Source: RESEARCH.md §14b.
- In this sandbox the promo ends already happened (August 2026 bills), so today's messages explain a past increase. In production the same template fires 10–40 days ahead. Payoff-upcoming reminders are not sent yet.
- **There's no evidence for a bill-date effect, so we don't claim one.**

## 3. Channel
Maps to: signals (L44), feasibility (L46), "full value of what they have" (L62).

**We choose the channel from the customer's own `accounts.contact_preference` (sms → text, app → in-app, email → email, call → agent call), not from a ranking.** We make no claim that one channel works better than another. No telecom study compares them on the same offer (§14a).

| Message kind | Channel |
|---|---|
| Retention fix or credit that pays at 10% | the customer's stated contact preference |
| Perk reminder (streaming already included) | in-app or on the bill only |
| Cheaper plan, same features (394 lines) | bill/app line, **tap to confirm**. Never an "invitation to shop": proactive plan recommendations raised churn from ~6% to ~10% in a wireless field test (Ascarza, Iyengar & Schleicher 2016, https://doi.org/10.1509/jmr.13.0483) |
| Cheaper plan that gives something up (110 lines, incl. all 44 Experience More → 4 Line) | bill/app line with an explicit **"but you'd lose X"** (price guarantee, high-speed hotspot, plan perks, 50 GB cap) |
| Watch line (66), price guarantee (2,862), trade-in value (2,212), streaming included (695) | bill/app line |

The savings receipt is a customer-first design choice. **It is not proven to retain anyone.** There's no public field evidence for "you're saving $X" receipts (§14d), and the ledger shows it costs T-Mobile money. The student credit is off, and Home Internet is not offered.

**Wording by channel (English and Spanish):**
- **Text:** starts with "T-Mobile:", ends with "Reply YES …" and "Reply STOP to opt out."
- **In-app:** "Tap to set up the call / Tap to accept", plus "Turn off these notes anytime in Settings."
- **Email:** "Use the link below … or reply to this email", plus an unsubscribe line.
- **Agent call:** a short script ("Hi, this is T-Mobile calling about your account … Ask: … If they'd rather not get calls like this, offer to stop them.").

Only texts say Reply YES/STOP. The script checks this.

## 4. Rules we follow (not legal advice; RESEARCH.md §14c)
- **Only offer changes to services the customer already has:** fixes, credits, their plan's perks, cheaper plans, and their own phone's trade-in value. Cross-selling Home Internet would need CPNI approval (opt-out with a 30-day wait, or opt-in), so it is not used.
- **Skip anyone who opted out of marketing.** A marketing opt-out ends all marketing. Opt-outs are honored within 10 business days. We keep fix messages free of promotions.
- **Send only 8 a.m.–8 p.m. in the customer's local time.** The sandbox has no time zone, so this is a send-time rule.
- **Every text carries STOP.** Every channel has its own opt-out.
- **Messages never use port-out or location data.** No template cites them. Note: the engine's risk score and its port-out contact override do read `port_out_inquiry` (see §8).
- **We make no claim about pending FCC rule changes.** The only one checked (FCC 26-67) is not yet in force.

## 5. Tone and framing by customer type
Maps to: explainability and trust (L45), fixed en/es templates (L33), fields used incl. `contact_preference` and `language` (L91).
- **Support pain** (unresolved contacts, topic). Lead with an apology naming the topic in plain words ("your coverage", "your bill"), then the fix. A credit is always "one-time".
- **Family vs single** (line count). 3+ lines open with "a note about your N-line account".
- **Long tenure** (≥ 60 months). "Thanks for N years with us."
- **Promo ended.** Give the bill month and the exact dollar change, and say the plan price didn't change.
- **Price guarantee** (`plans.price_guarantee_years`). Stated as a fact.
- **Trade-in** (paid-off, non-BYOD phones on `tradein_curves`). "About $X today, no pressure." Bill/app only.
- **Language.** `es` gets Spanish (usted, natural phrasing). `en` and the 148 `other` accounts get English, with Spanish included in every row.
- **Senior / student segment labels.** We never mention a label or an age and never change wording because of it. A label matters only when it makes a real plan eligible (for example 55+ Savings, "after a quick eligibility check").

We don't vary the pitch to persuade. In the Hillstrom test, choosing a different message per customer did not beat one good message. So the claim is: **the message matches your account and is easy to act on**. The push-away guardrail belongs to tm-models (taken over from tm-efficacy).

## 6. Family accounts, lock-in and the price guarantee (RESEARCH.md §15)
Maps to: explainability and trust (L45), feasibility (L46).
- **Over 90% of T-Mobile postpaid phone *lines* are on multi-line accounts.** That's lines, not accounts (TMUS Q4'25 call, §15a). Our sandbox has more single-line accounts, about 17% of lines, so we score and message at the account level. Family messages open with "your N-line account".
- **We never claim that multi-line accounts churn X% less, or that adding a line lowers churn.** No US carrier publishes the gap, and multi-line customers self-select (§15a, §15c). The −0.15 per extra line in `harness/labels.py` is an assumption in our generator, not a finding. There's no add-a-line message.
- **A phone upgrade buys lock-in; a plan step-up adds margin but no lock-in** (§15e). The lock-in comes from the device plan and promo credits that are lost on leaving. Step-ups and phone upgrades are not part of outreach today: the retention-only policy picks neither.
- **The early termination fee is $0. The 5-year price guarantee is a price promise, not a lock-in** (§15b, §15e). Templates state it only as "comes with / keeps its N-year price guarantee". The script rejects any customer text containing lock, locked, contract, contrato or permanencia.
- **Line departures** (a member leaving the account) are the risky family moment, but the sandbox has no signal for them. The customer-friendly future play is "keep your number at T-Mobile on your own line" (Change of Responsibility), never a hard save (§15d).

## 7. Non-creepy rules
Maps to: trust (L45), life events as future vision only (L39), no scraping (L122), avoid pushy copy (L248).
- We only cite facts the customer would recognize from their own bill or account.
- We never cite inferred life events, income, jobs, kids, location, or usage beyond the bill. There's no "we noticed you…": the streaming line says the perk is included, not that they stream a lot.
- No fake urgency. Trade-in lines say "no pressure".
- No codenames, SKUs, account ids, tool names or staff names in customer text.
- The script checks all of this, plus forbidden words in English and Spanish (age, income, job, kids, "we noticed", AI).

## 8. Outputs, checks, open items
- **Outputs:**
  - `outreach_drafts.csv` (5,042 rows): `account_id, contact_yes_no, reason, channel, template_id, message_en, message_es, primary_language, facts_used, receipt_lines, receipt_line_en, receipt_line_es, in_bill_change_1412, open_issue_90d, guardrail_block_reason, guardrail_why_line, bill_change_exemption, data_note`
  - `outreach_receipt_lines.csv` (one row per bill/app line)
  - `outreach_summary.md`
- `outreach_card.csv` (5,042 rows) for tm-ui's customer card, with exactly `account_id, outreach_reason, message_en, message_es`. `outreach_reason` is a short plain-English reason; for silent accounts it's the do-not-contact reason. Messages are blank when silent.
- **Inputs:** committed under `inputs/` (see `inputs/README.md`). The script defaults to them.
- **The script exits non-zero if any check fails:**
  - a slot is left unfilled
  - a dollar figure is not in `facts_used`
  - plan savings don't match `plans.line_prices`
  - trade-in values don't match the hidden-value file
  - the row count isn't 5,042, or the 1,412 count doesn't hold
  - a text is over 320 characters (other channels: 420)
  - a message lacks its channel's opt-out
  - text-only wording appears outside texts
  - a forbidden word or label appears (incl. "synthetic" and lock-in wording)
- **Deterministic:** two runs give byte-identical files.
- **Open item:** RESEARCH.md §14c says the engine "never uses port-out data", but `harness/offers.py` uses `port_out_inquiry` for risk and the port-out contact override. Messages never cite it. Whether the engine should stop using it is a product call.

Run: `python3 docs/outreach/draft_outreach.py [--exemptions-applied yes] [--picks …] [--guardrail …] [--opt-out …] [--contact-log …]`
