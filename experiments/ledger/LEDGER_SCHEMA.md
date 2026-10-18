# Money ledger: `ledger.csv` + `events.csv`

**All numbers in these files are synthetic (simulated accounts and churn labels), not T-Mobile customer data.** No string
in the CSVs says so, per David's rule. Put that label on the screen once. Strings were checked for "synthetic", internal
words, file paths, names and account-id leaks.

Join key: `account_id`. There is one row per account in `ledger.csv` (**5,042 rows**, same ids and order as `outreach_card.csv`).
the offer engine owns decision, channel, options and messages and joins this file onto those by `account_id`. This file doesn't
carry them.

## Headline number (asserted in the build). All figures are synthetic.
- **Mid total over the 184 `pass` accounts: +$3,938**, on the conservative costing below. The build asserts the column sums to this, to the dollar.
  History: +$4,109 (shipped), then +$3,939 (open-ticket rule, every fix-first priced as a $15 call), then **+$3,938** (team ruling: agent time on every fix-first contact plus channel send cost).
- **95% range at a 10% save rate: −$3,186 to +$13,148** (mean +$3,817). This is a 2,000-resample realized-outcome bootstrap, the same method as before, and the build checks it still reproduces the old −$2,805 to +$13,292.
- **P(net > 0): 0.801 at 10%, 0.408 at 5%.**
- **Break-even save rate: 5.17%**, same definition as the old 4.80%. Per attempt that's **4.7%** of the would-be leavers a contact reaches, risk-weighted, or about 1.2 saved accounts per 100 contacts.
- Low / high totals: −$2,760 / +$13,720. The 152 regular accounts are +$2,745 and the 32 `already_leaving` accounts +$1,193 (mid). The 30 `in_holdout` accounts are +$458.
- Text-channel count among the 184 is 64, asserted against `outreach_card.csv`.

### Costing (team ruling, 23:39). The net columns use this.
Every fix-first contact, including care credit + fix-first, pays agent time whatever the channel goes out on: **$10.75 per live contact + $4.25 escalation = $15.00**
(research14 channel study, from Gartner's $8.01–13.50 per assisted contact). The channel's own send cost goes on top. **Agent calls pay the engine's $15 callback only.** That callback *is*
the agent contact plus escalation (it's equal to $10.75 + $4.25), so adding the split on top would count the same agent twice. The $25 credit and $4 annoyance charge stay.
The other 4 contacts (1 perk reminder, 2 check-ins, 1 bill-shock credit) keep their engine costs. The engine's `offers.py` (offers v2, a20b2dd) has no per-channel send costs, so those come from research14 (RESEARCH §14a list prices).

| channel | cost per fix-first contact | made of | fix-first | care credit + fix-first (+$25 credit) |
|---|---|---|---|---|
| agent call | $15.00 | engine callback (agent + escalation) | 11 | 3 |
| text | $15.013 | $15 agent + $0.013 SMS | 49 | 14 |
| in-app message | $15.00 | $15 agent + $0 push | 64 | 9 |
| email | $15.0001 | $15 agent + $0.0001 email | 27 | 3 |

### Secondary, Q&A only: "if the fix is self-serve"
Only calls pay $15, and digital fix-first contacts pay the send cost only. **+$6,428**, 95% range −$703 to +$15,657, P(net>0) 0.949 at 10% and 0.731 at 5%,
break-even 2.11% (1.9% per attempt). Low/high −$270 / +$16,210. This is in `ledger_summary.json` → `self_serve_secondary`. **It's not in the net columns and shouldn't be on the meter.**

### Open-ticket rule
The 25 contacted accounts with an open ticket whose planned message was a perk reminder get the fix-first message instead, and the perk mention is dropped (save rate 0.35 vs 0.08).
Those 25 add up to +$28 as reminders and **−$142** on the conservative costing (+$218 if self-serve). We count 25, not the 21 + 2 that was quoted. "Open ticket" here means an unresolved
support contact in the last 90 days, and these 25 match the "open support issue comes first" rows in `outreach_card.csv`. The 2 fix-first accounts the offer engine's engine leaves silent are already fix-first here.

### Agreement with the offer engine's decisions.csv (v2 6b53f7c)
The build reads `data/decisions/decisions.csv` and asserts: the same 184 messaged accounts; channels in_app 74 / text 64 / email 32 / call 14; mid total +$3,938;
bill-line notes on exactly the 390 `clean` + 107 `tradeoff` accounts (`receipt_kind`) and on no others; no "callback" on a non-call row.
Reported, not forced (the counts are in `ledger_summary.json` → `note_mismatches_vs_decisions`):
- 47 accounts the committed guardrail marked cheaper-plan-on-bill have no bill line in decisions.csv. They're silent, and the note says so. (This was quoted as 48. decisions.csv has 47.)
- 45 bill-line accounts carry a different guardrail block reason: 33 bill rose with nothing to offset it, 12 nothing worth messaging. The guardrail's rule order puts those reasons ahead of
  the cheaper-plan rule. Their note gives the reason first, then the bill line, e.g. "Bill rose, nothing offsets it; a same-features cheaper plan shows on the bill."

### Flag for the offer engine (wording owner)
ACC-01607's line says "We'll call", but `outreach_card.csv` routes it as an in-app message. Under this costing the cost is the same either way ($15), but the wording needs fixing.

## `ledger.csv`
| column | type | meaning |
|---|---|---|
| `account_id` | str | join key |
| `guardrail_result` | `pass` / `blocked` | `pass` = contact allowed by the do-not-contact rule (184). Taken from the committed guardrail. |
| `guardrail_note` | str (≤15 words) | one plain sentence on why the account got a message or didn't. It uses the offer engine's shortened wording from `data/decisions/decisions.csv` where that exists, and the same style elsewhere. Every bill-line account says so: 390 "No message; a same-features cheaper plan shows on the bill." and 107 "...the bill shows a cheaper plan and its trade-offs." The 47 cheaper-plan accounts the offer engine made silent say "No message, and no cheaper plan is a close enough match to suggest." The build checks there are ≤15 words, no column-style names, and no "callback" outside call rows. |
| `save_rate_low` / `_mid` / `_high` | float | 0.05 / 0.10 / 0.22: the average share of people about to leave whom a message keeps, for each case |
| `net_low_usd` | float $ | expected net at a 5% save rate **with each account's own survival-weighted kept value** (a kept customer keeps their current high risk for 24 months, 10%/yr discount). The harshest case. 0 if blocked. |
| `net_mid_usd` | float $ | expected net at a 10% save rate, $1,478 average kept value (per-account margin × 19.34 months): chance of leaving in 90 days × chance the message keeps them × kept value − offer cost (conservative costing above) − annoyance cost. 0 if blocked. **Sums to +$3,938.** |
| `net_high_usd` | float $ | same as mid at a 22% save rate. **This is an upper bound, above published field results (about 2–11%).** 0 if blocked. |
| `why_low` / `why_mid` / `why_high` | str (≤90 chars) | one short line each. `why_high` always starts "Upper bound, above published results". Blocked rows read "No message, so nothing is spent or counted." |
| `already_leaving` | bool | the customer asked us about moving their number to another carrier (196 accounts, 32 of them `pass`). Show these on their own line, not in money saved. |
| `already_leaving_note` | str (≤15 words) | 31 messaged with an open issue: "Asked us about moving their number; we still reach out to fix their open issue." 1 other messaged: "...because it's likely worth it." 164 not messaged: "Asked us about moving their number to another carrier; no money is counted." Empty if false. |
| `in_holdout` | bool | random holdout (30, all `pass`). **It changes nothing else in this file**, and it's asserted that holdout rows are still `pass` with their nets. |
| `timing` | `now` / `wait` / empty | from the timing rule, for `pass` rows only (177 now, 7 wait). Empty if blocked. |
| `wait_until` | ISO date or empty | send date when `timing` = `wait` (2026-11-05 or 2026-12-03) |

Display: card number = `net_mid_usd`; card range = `net_low_usd` to `net_high_usd`, with the `why_*` lines. Values are
rounded to cents; show them as whole dollars.

## `events.csv` (long format)
`account_id, event_date, event_type, event_text`. At most 3 rows per account, **newest first**. Only events on or before
the data date (2026-10-01): 2,705 rows over 1,855 accounts. Accounts with no event have no rows.
- `event_type`: `open_ticket` (an unresolved support contact, dated the day it was opened) or `bill_up` (the monthly bill rose more than 20% over the month before).
- `event_text`: plain words, e.g. "billing ticket opened, still open", "bill up $38".
Future dated unlocks (a phone paid off, a tenure milestone) aren't listed. They drive `timing` / `wait_until` in `ledger.csv`.

## Known limits
- `guardrail_note` names one bill-change reason per account. 71 accounts had both a new phone payment and a promo ending,
  and the note names whichever the guardrail listed.
- Per-account nets use the same accounting as the planning engine (one shared formula). See RESULTS.md for the adversarial audit
  of these numbers.
