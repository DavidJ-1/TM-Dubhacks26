# Outreach playbook: when we reach out, how, and what we say

**All customers and numbers here are synthetic** (judge sandbox stub data, as_of 2026-10-01). No real T-Mobile customer data. No LLM: every message is a fixed template (`templates.json`) whose slots are filled from sandbox fields or the engine output by `draft_outreach.py`.

Brief line references are to `handoff/plan-doc-2026-10-17.txt`.

## 1. When we contact, and when we stay silent
Maps to: customer value incl. "no good recommendation" (L43), the track slogan "the one that says wait" (L47), the on-screen do-nothing outcome (L50), and the judges' hard part, "helpful at the right time without being annoying" (L61).

Silence is the default. Rules run in this order, and the first one that applies decides:
1. **The engine says do nothing, so we stay silent.** The reason is stored (`happy`, `open_ticket`, `wait_payoff`, ...).
2. **Only retention actions that pay at a realistic save rate get a message.** The source is the retention-only policy re-picked at a 10% save rate (`picks_retention_10.csv`, 246 accounts; break-even is about 4.5%). Anything else the shipped engine picks, like upsells or Home Internet, is `not_worth_contacting_at_realistic_save_rates`.
3. **Cheaper-plan moves are never outreach.** They go on the bill or in the app as a single tap-to-confirm line (section 2).
4. **Backfire guardrail (owned by the efficacy lane).** The 1,412 accounts with a non-`stable` `billing_history.change_reason` and an increase (`change_cents > 0`) in the last 3 bill months (2026-07..09) are contacted only with a credit that offsets the increase. We do *not* use "bill went up in the last 3 months", which flags 4,679 accounts, mostly on cents of noise. The efficacy file (`v2:experiments/efficacy/out/guardrail.csv`) is the authority when present. Two exemptions are applied by the script until the guardrail file applies them itself (`--exemptions-applied`):
   - **fix-only callbacks:** fixing an open issue isn't an offer.
   - **increases that are only a new phone installment the customer chose.**
5. **At most one proactive contact per account per quarter.** The sandbox has no outreach log, so this is a hook: `--contact-log account_id,last_contact_date`. Every run sends at most one message per account.
6. **Fix first.** If an account has an unresolved support contact in the last 90 days, the only message allowed is a fix message (a callback, optionally with the $25 care credit), never an offer. A picked perk reminder or check-in is replaced by the fix callback. People stay because nothing is going wrong (L89).
7. **No opt-out or do-not-contact field exists in the sandbox.** Opt-out is honored at the channel (STOP / Settings / unsubscribe) and would be a hard block in production.

## 2. Channel
Maps to: signals (L44: commerce + customer + live), feasibility (L46), "help customers get full value of what they have" (L62).

| Message kind | Channel | Why |
|---|---|---|
| Retention fix or credit that pays at 10% | the customer's own `accounts.contact_preference` (sms → text, app → in-app, email → email, call → agent callback script) | the only kind of message that interrupts |
| Perk reminder (streaming already included) | in-app / bill only | a reminder isn't worth an interruption |
| Cheaper plan, same features | bill / app line, **tap to confirm** | never an "invitation to shop". Proactive plan recommendations raised churn from ~6% to ~10% in a wireless field test (Ascarza, Iyengar & Schleicher 2016, https://doi.org/10.1509/jmr.13.0483) |
| Cheaper plan that gives something up | bill / app line with an explicit **"but you'd lose X"** (price guarantee, high-speed hotspot, plan perks, 50 GB cap) | honest trade-off, so the customer decides |
| Watch line, price guarantee, trade-in value | bill / app line | full value of what they already have |

The like-for-like headline is the 394 receipt moves with no trade-off (synthetic, $4,600/mo if all accepted). The 110 trade-off moves include all 44 Experience More → Essentials 4 Line moves and always carry the "you'd lose" line. Student credit is off (likely a generator gap). Old-phone upgrade credits and payoff reminders are not used yet.

## 3. Tone and framing by customer type
Maps to: explainability and trust (L45), fixed en/es templates (L33), fields we use, including `contact_preference` and `language` (L91).

We use real sandbox fields only:
- **Support pain** (`support_interactions`: unresolved, topic). Lead with an apology naming the topic in plain words ("your coverage", "your bill"), then the fix. A credit is only ever "one-time" so we don't overclaim.
- **Family vs single** (`lines` count). 3+ lines open with "a note about your N-line account", so the person knows it covers everyone.
- **Long tenure** (`accounts.tenure_months` ≥ 60). Opener: "thanks for N years with us." It's a fact on their account.
- **Promo ended** (`billing_history.change_reason = promo_expired`). Give the bill month and the exact $ change, and say the plan price did not change.
- **Price guarantee** (`plans.price_guarantee_years`). Stated as a fact about their plan.
- **Trade-in** (paid-off, non-BYOD phones on `tradein_curves` at today's age). "About $X today, no pressure." It sits on the bill/app only.
- **Language** (`accounts.language`). `es` gets Spanish (usted, natural phrasing, not word-for-word). `en` and the 148 `other` accounts get English, with Spanish included in every row.
- **Senior / student segment labels.** We never mention a label or an age and never change wording because of it. A label only matters when it makes a real plan eligible (for example 55+ Savings, which carries "after a quick eligibility check").

We don't vary the pitch to persuade. In the Hillstrom e-mail test, choosing a different message per customer did not beat one good message. So the claim is: **the message matches your account and is easy to act on**, not "tailored to persuade". The efficacy lane owns the push-away guardrail.

## 4. Non-creepy rules
Maps to: trust (L45), life events kept as future vision only (L39), no scraping of personal info (L122), avoid pushy copy (L248).
- We only cite facts the customer would recognize from their own bill or account: open support requests, bill amounts and months, plan name, line count, tenure, phone model.
- We never cite inferred life events, income, jobs, kids, location, or usage beyond what's on the bill. There's no "we noticed you...". The streaming line says the perk is included, not that they stream a lot.
- No fake urgency, no countdowns, no "last chance". Trade-in lines say "no pressure".
- Every direct message has an easy opt-out (Reply STOP / Settings / unsubscribe / agent offers to stop calls).
- Quiet hours: send only 9 AM–8 PM in the customer's local time. The sandbox has no region field, so this is a send-time rule for production.
- No codenames, SKUs, account ids, tool names or staff names in any customer text. The script asserts this, together with a forbidden-word check (age, income, job, kids, "we noticed", AI, and their Spanish forms).

## 5. Outputs and checks
- `outreach_drafts.csv` has one row per account (5,042), with columns `account_id, contact_yes_no, reason, channel, template_id, message_en, message_es, primary_language, facts_used, receipt_lines, receipt_line_en, receipt_line_es, in_bill_change_1412, open_issue_90d, guardrail_block_reason, guardrail_why_line, bill_change_exemption, data_note`.
- `outreach_receipt_lines.csv` has one row per bill/app line, in long format.
- `outreach_summary.md` has counts by channel and reason (synthetic).
- The script exits non-zero if any of these fail:
  - every slot is filled (no `{` left)
  - every `$` figure appears in `facts_used`, which is read from the sandbox or engine
  - plan-move savings recomputed from `plans.line_prices` match the receipt file
  - trade-in values match the hidden-value file
  - row count is 5,042
  - the 1,412 count holds
  - direct messages are 100–320 characters and carry an opt-out
  - forbidden words are absent

Run: `python3 docs/outreach/draft_outreach.py [--picks ... --offers ... --receipt ... --hidden ... --guardrail v2:experiments/efficacy/out/guardrail.csv --exemptions-applied auto|yes|no --contact-log ...]`. It's deterministic: the same inputs give byte-identical CSVs.
