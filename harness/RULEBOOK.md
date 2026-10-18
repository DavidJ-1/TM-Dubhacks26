# Outreach rulebook numbering used by `decisions.csv` (`decided_by_rule`)

Numbers are synthetic (sandbox stub data). This copies the numbering of `docs/outreach/OUTREACH_PLAYBOOK.md` §1 on dev, so
`decided_by_rule` means the same thing in both places. Rules run in order and the first one that applies decides.

| # | Rule | In decisions.csv |
|---|---|---|
| 1 | The engine says do nothing, so we stay silent. | silent; our engine's own pick is do nothing |
| 2 | Only retention actions that pay at a realistic save rate (10%) get a message. The contact set is model experiments' policy picks that pass the guardrail (184). Plan moves are a bill/app line only. | message (picked, guardrail pass); receipt_only (plan move on the bill); silent (not worth contacting) |
| 3 | Opted out of marketing means no contact. No opt-out field in the data, so this is a hook. | never fires on this data |
| 4 | Backfire guardrail: bill went up and nothing offsets it, so no contact. | silent (or receipt_only if a plan-move line exists, still counted as rule 4) |
| 5 | At most one proactive contact per account per quarter. No contact log in the data, so this is a hook; one message per account per run. | never fires on this data |
| 6 | Fix first: with an unresolved support contact in the last 90 days, the only message is a fix message. | message, perk reminder replaced by fix-first (25 accounts) |

Channel follows `accounts.contact_preference` (sms → text, app → in_app, email → email, call → call); receipt_only is
`bill`, silent is `none`. Only `call` rows may promise a call. Text, in-app and email fix-first messages say our team is
working on the open request.

If a saved-account value is mentioned anywhere on screen, the wording is: "We value a saved account at its own monthly
margin times 19.3 months."
