# Do-not-contact guardrail + a plain-English line per account (`guardrail.py`)

**ALL NUMBERS SYNTHETIC/SIMULATED** (sandbox stub accounts, simulated labels; not T-Mobile customer data). No LLM; rules only.

**Our models can't reliably pick out who will be pushed away, so we use a rule-based guardrail instead.** On the real
randomized Hillstrom e-mail test (section 1 of README.md), the customers our uplift models flagged as pushed away by
contact (0-0.35%) actually showed positive held-out uplift. So we don't use a model for this.

Run from the repo root: `python experiments/efficacy/guardrail.py` (~2 s). Outputs in `out/`:
- `guardrail.csv`: `account_id, contact_ok, block_reason, why_line`. One row per account (5,042), so tm-strategy's script can join on `account_id`.
- `guardrail_detail.csv`: the same columns plus the fields behind each decision (bill-change reason and $, policy action and EV, swap, receipt plan move and what it gives up, open-issue topic, risk).
- `guardrail_summary.txt`: counts and 10 example rows.

Inputs (read-only): `demo_data/features.csv`, `offers.csv`, `offer_candidates.csv.gz`, plus the sandbox tables `billing_history`,
`support_interactions` and `plans`, opened through `harness/offer_detectors.connect_ro` (sqlite `mode=ro`; nothing is written there).

## Rules, highest priority first
Each account gets the first code that applies. `contact_ok` is True only when none applies.

| code | rule | source / why |
|---|---|---|
| `bill_change_no_fix` | **Recent bill change with a real reason:** the **1,412** accounts with a non-`stable` `change_reason` and an increase (`change_cents > 0`) in the last 3 billed months (2026-07..09). That breaks down as promo ended 511, new device installment 892, installment ended 9. The count is checked by an assert. (We do **not** use `bill_increase_pct > 0`, which flags 4,679 accounts mostly on cents of noise.) **We contact them only with a credit that offsets the increase** (bill-shock credit, loyalty, care, care + fix-first, keep-your-phone). If the policy's best action for one of them is something else, we take their best positive-EV offsetting credit instead (56 swaps). If none is eligible or worth it, we never contact them. | A message after a price rise with nothing to offset it mostly reminds people of the rise. The randomized trial in the next row attributes its churn increase to outreach that prompted customers to re-examine their plan and options. |
| `receipt_only_plan_move` | **Cheaper-plan / plan-variant moves are never outreach.** We show them on the bill/receipt only. The why_line says what the plan saves and, if it gives up a price guarantee, unlimited data or high-speed hotspot, says that too. 536 accounts have a plan move: 394 give up nothing and 142 give up something. | Ascarza, Iyengar & Schleicher (2016), "The Perils of Proactive Churn Prevention Using Plan Recommendations", *Journal of Marketing Research* 53(1). Field experiment with about 65k wireless customers: churn rose from about 6% to about 10% among customers proactively sent cheaper-plan recommendations. |
| `contacted_this_quarter` | **Fatigue: at most one proactive contact per 90 days.** **The data has no outreach or marketing-contact log.** `support_interactions` / `days_since_last_contact` are inbound support contacts, which aren't proactive contacts, so we don't block on them. The rule is a hook: put `account_id,last_proactive_contact_date` in `experiments/efficacy/proactive_contacts.csv` and any account contacted in the last 90 days is blocked (tested with a one-row file). Without that file it blocks nobody, and we don't invent any data. Within this playbook every account gets at most one message per run. | Contact volume has a cost: in a large randomized e-mail test, sending everything drew 45% more unsubscribes and spam reports (Gupta et al., KDD 2016; see README.md). Once a quarter is our own conservative design choice, not a measured optimum. |
| `not_worth_contacting` | **Not picked by the retention-only policy re-picked at a 10% save rate.** That policy picks 246 accounts with policy EV of $6,211. It's reproduced here with the same accounting as the room's chart check (`scratch_models/chart_check/chart_check.py`, `ev_retention_only_unlimited` at 10%): EV = p × min(1, save_rate × 10%/44.37%) × value − offer cost − annoyance, best positive-EV non-upsell action per account. The count is checked by an assert. The policy never picks a plan move. | Break-even is about a 4.5% true save rate. At 10% the policy beats do-nothing and the top-10% credit rule (policy_by_save_rate.csv). |
| (open service issue) | Not a block. If the account has an unresolved support contact in the last 90 days, the why_line leads with fixing that issue (topic named, e.g. "your open coverage issue") before any credit. Not-contacted accounts with an open issue are told it stays with support. | Fix-first beats a credit for an unresolved issue (the engine's own fix-first actions). |

## Result (synthetic)
- **contact_ok True 154, False 4,888.** Codes: not_worth_contacting 3,293, bill_change_no_fix 1,173, receipt_only_plan_move 422, contacted_this_quarter 0 (no log).
- **Of the 1,412 bill-change accounts, 107 are contacted and 1,305 blocked** (1,173 bill_change_no_fix, 123 not_worth_contacting, 9 receipt only). Contacted by reason: promo ended 86/511, device installment 20/892, installment ended 1/9.
- Of the policy's 246, 92 are blocked by rule 1: 62 fix-first callbacks, 19 perk reminders and 11 check-ins sent to people whose bill just went up, with nothing to offset it. Contacted policy EV is $5,100 of $6,211 (decision-time EV at 10%; not re-graded).
- Contacted mix: care credit + fix-first 106, fix-first 24, perk reminder 20, check-in 2, care credit 1, bill-shock credit 1. Four contacted accounts also get a receipt plan line (see the detail CSV).

## why_line style
Plain, warm, specific, and built only from billing, plan and support fields: the bill change in $ and its cause, the
open-issue topic, the plan saving in $/mo and what it gives up. It never uses income, job, household or kids, never
says "tailored" or "personal match", and contains no codenames, SKUs, account ids or tool names. All of this is
checked by an assert. Lines are at most 140 characters (max 134).

## Weakest assumptions
- **Rule 1 is blunt.** It blocks 62 fix-first callbacks for open issues just because the bill also rose. The 892 device-installment increases are the customer's own new phone, so blocking them protects against a weaker reminder effect than promo endings do. Exempting fix-first-only messages, or device-installment increases, would bring back up to about 90 contacts. That's a product call.
- The "offsetting credit" set is our judgment. A one-time $25 credit doesn't undo a $49/month rise, and the line says "one-time" so we don't overclaim.
- No proactive-contact log, so fatigue is untested on this data.
