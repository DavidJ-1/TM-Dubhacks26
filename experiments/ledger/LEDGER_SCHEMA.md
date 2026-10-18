# Money ledger: `ledger.csv` + `events.csv`

**All numbers in these files are synthetic (simulated accounts and churn labels), not T-Mobile customer data.** No string
in the CSVs says so, per David's rule. Put that label on the screen once. Strings were checked for "synthetic", internal
words, file paths, names and account-id leaks.

Join key: `account_id`. There is one row per account in `ledger.csv` (**5,042 rows**, same ids and order as `outreach_card.csv`).
tm-offers owns decision, channel, options and messages and joins this file onto those by `account_id`. This file doesn't
carry them.

## Headline number (asserted in the build)
- **Mid total over the 184 `pass` accounts: +$6,428.** The build asserts the column sums to this, to the dollar.
  It went +$4,109 → +$3,939 (open-ticket rule) → **+$6,428 (channel costing)**.
- **Bootstrap** (2,000 resamples of all 5,042 accounts, true churn probability, random churn × save draws; same method as before, and the
  build checks it still reproduces the old −$2,805 to +$13,292): **95% range −$703 to +$15,657** at a 10% save rate (mean +$6,307).
  **P(net > 0) 0.949 at 10%, 0.731 at 5%.**
- **Break-even save rate 2.11%** (same definition as the old 4.80%: the average save rate at which the 184 net $0).
  Effective per attempt: a contact keeps **1.9%** of the would-be leavers it reaches, risk-weighted. That's about **0.5 saved accounts per 100 contacts**.
- Low / high totals: −$270 / +$16,210. 152 non-port-out accounts make up mid +$4,845; the 32 `already_leaving` +$1,583. The 30 `in_holdout` are +$893.
- Text-channel count among the 184 = 64, asserted against `outreach_card.csv`.

### Channel costing (Grok Bot, 23:37)
Each fix-first contact is costed by the channel it actually goes out on (`outreach_card.csv` "Sent as"). Only real calls pay the $15 callback.
A care credit + fix-first keeps its $25 credit. The $4 annoyance charge is unchanged. The engine (`offers.py`, tm-offers-v2 a20b2dd) has no
per-channel costs (only callback $15, check-in $2, perk reminder $0.50), so digital costs come from the research14 channel study (RESEARCH §14a list prices):

| channel | cost per contact | source | fix-first | care credit + fix-first |
|---|---|---|---|---|
| agent call | $15.00 | engine `FIX_FIRST_CALLBACK_COST` | 11 | 3 |
| text | $0.013 | SMS list price (research14) | 49 | 14 |
| in-app message | $0.00 | push/in-app (research14) | 64 | 9 |
| email | $0.0001 | email (research14) | 27 | 3 |

180 of the 184 are fix-first types (166 of them digital). Perk reminders, check-ins and the bill-shock credit keep their engine costs.
**Caveat:** a digital fix-first contact keeps the 35% fix-first save rate but pays no agent time. If fixing the issue still takes an agent
(research14 charges $10.75 per live contact plus $4.25 escalation whenever the customer is reached), the total goes back toward
+$3,939. Read +$6,428 as "the fix is self-serve or already in support's queue."

### Open-ticket rule
The 25 contacted accounts with an open ticket whose planned message was a perk reminder get the fix-first message instead, with the perk mention dropped
(fix-first save rate 0.35 vs 0.08). Those 25: +$28 as reminders → −$142 if every one were a $15 call → **+$218 on their real channels**.
We count 25, not the 21 + 2 that was quoted, using open ticket = an unresolved support contact in the last 90 days. They match the "open support issue comes first"
rows in `outreach_card.csv`. The 2 fix-first accounts tm-offers' engine leaves silent are already fix-first here.

### Flag for tm-offers (wording owner)
ACC-01607's line says "We'll call", but `outreach_card.csv` routes it as an in-app message. We cost it as in-app. The wording needs fixing.

## `ledger.csv`
| column | type | meaning |
|---|---|---|
| `account_id` | str | join key |
| `guardrail_result` | `pass` / `blocked` | `pass` = contact allowed by the do-not-contact rule (184). Taken from the committed guardrail. |
| `guardrail_note` | str (≤130 chars) | one plain sentence on why it passed or was blocked, e.g. "Bill went up when a promo ended, so the message comes with a credit that offsets it." |
| `save_rate_low` / `_mid` / `_high` | float | 0.05 / 0.10 / 0.22: the average share of people about to leave whom a message keeps, for each case |
| `net_low_usd` | float $ | expected net at a 5% save rate **with each account's own survival-weighted kept value** (a kept customer keeps their current high risk for 24 months, 10%/yr discount). The harshest case. 0 if blocked. |
| `net_mid_usd` | float $ | expected net at a 10% save rate, $1,478 average kept value (per-account margin × 19.34 months): chance of leaving in 90 days × chance the message keeps them × kept value − offer cost (by channel, see above) − annoyance cost. 0 if blocked. **Sums to +$6,428.** |
| `net_high_usd` | float $ | same as mid at a 22% save rate. **This is an upper bound, above published field results (about 2–11%).** 0 if blocked. |
| `why_low` / `why_mid` / `why_high` | str (≤90 chars) | one short line each. `why_high` always starts "Upper bound, above published results". Blocked rows read "No message, so nothing is spent or counted." |
| `already_leaving` | bool | the customer asked us about moving their number to another carrier (196 accounts, 32 of them `pass`). Show these on their own line, not in money saved. |
| `already_leaving_note` | str | "Asked us about moving their number to another carrier, so this account is counted on its own line, not in money saved." Empty if false. |
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
