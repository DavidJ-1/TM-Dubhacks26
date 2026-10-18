# Money ledger: `ledger.csv` + `events.csv`

**All numbers in these files are synthetic (simulated accounts and churn labels), not T-Mobile customer data.** No string
in the CSVs says so, per David's rule. Put that label on the screen once. Strings were checked for "synthetic", internal
words, file paths, names and account-id leaks.

Join key: `account_id`. There is one row per account in `ledger.csv` (**5,042 rows**, same ids and order as `outreach_card.csv`).
tm-offers owns decision, channel, options and messages and joins this file onto those by `account_id`. This file doesn't
carry them.

## Headline number (asserted in the build)
- **Mid total over the 184 `pass` accounts: +$3,939** (the build asserts the column sums to this, to the dollar).
- It used to be +$4,109. The change comes from the open-ticket rule: the 25 contacted accounts with an open ticket
  whose planned message was a perk reminder now get the fix-first message instead, with the perk mention dropped.
  At the fix-first cost ($15 callback + $4 annoyance, against $0 + $2) and save rate (0.35 vs 0.08, scaled to a 10% average),
  those 25 go from +$28 to −$142 in total. **Cause in one line: a callback costs about $17 more than a reminder, and on these
  low-risk accounts (about 8% chance of leaving) the extra saves are worth only about $10.** The 2 fix-first accounts
  tm-offers' engine leaves silent are already fix-first here, so they don't change.
  (Our count is 25, not the 21 + 2 that was quoted, using open ticket = an unresolved support contact in the last 90 days.
  The 25 match the "open support issue comes first" rows in `outreach_card.csv`.)
- Low / high totals over the 184: −$2,759 / +$13,721.
- Lines: 152 non-port-out accounts, mid +$2,746; 32 `already_leaving`, mid +$1,193. 30 `in_holdout`, mid +$458 (excluding them gives +$3,481 on 154).
- Text-channel count among the 184 = 64, asserted against `outreach_card.csv`.

## `ledger.csv`
| column | type | meaning |
|---|---|---|
| `account_id` | str | join key |
| `guardrail_result` | `pass` / `blocked` | `pass` = contact allowed by the do-not-contact rule (184). Taken from the committed guardrail. |
| `guardrail_note` | str (≤130 chars) | one plain sentence on why it passed or was blocked, e.g. "Bill went up when a promo ended, so the message comes with a credit that offsets it." |
| `save_rate_low` / `_mid` / `_high` | float | 0.05 / 0.10 / 0.22: the average share of people about to leave whom a message keeps, for each case |
| `net_low_usd` | float $ | expected net at a 5% save rate **with each account's own survival-weighted kept value** (a kept customer keeps their current high risk for 24 months, 10%/yr discount). The harshest case. 0 if blocked. |
| `net_mid_usd` | float $ | expected net at a 10% save rate, $1,478 average kept value (per-account margin × 19.34 months): chance of leaving in 90 days × chance the message keeps them × kept value − offer cost − annoyance cost. 0 if blocked. **Sums to +$3,939.** |
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
