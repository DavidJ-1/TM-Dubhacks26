# Inputs for `draft_outreach.py` (ALL SYNTHETIC)

These are committed copies of other lanes' files, so a clean clone can reproduce `outreach_drafts.csv` byte for byte. Every row is a synthetic sandbox stub account; none of it is real T-Mobile customer data. The only other input is the judge sandbox at `vendor/dubhacks/data/sandbox.db` (from `make setup`), which the script opens read-only.

| File | Copied from (shared box, Sat 2026-10-17 ~23:05 PDT) | Owner | Used for |
|---|---|---|---|
| `guardrail.csv` | `/workspace/tmobile/scratch_models/economics/guardrail/out/guardrail.csv` (new rule at a $1,478 kept-account value; fix-only and new-phone-only exemptions already applied) | tm-models (took over `guardrail.py` from tm-efficacy) | the authority on whether we may contact each account: `contact_ok`, `block_reason`, `why_line` |
| `guardrail_detail.csv` | same folder | tm-models | who the policy picks and with what action: `policy_selected`, `policy_action` (202 picks re-picked at 10% with $1,478; there is no separate picks file at $1,478) |
| `guardrail_summary.txt` | same folder | tm-models | reference only (184 contacts, 318 bill_change_no_fix) |
| `picks_retention_10.csv` | `/workspace/tmobile/scratch_models/chart_check/picks_retention_10.csv` (246 picks at the $1,835 engine value) | tm-models | not the default; kept so the earlier $1,835 run can be reproduced with `--picks inputs/picks_retention_10.csv` |
| `offers_min.csv` | `harness/out/offers.csv` (gitignored engine output, 2026-10-17 21:34), columns `account_id, action_code, do_nothing_reason` only | tm-offers | the engine's silence reason for accounts we don't contact; a plan move means receipt only |
| `receipt.csv` | `/tmp/value_ledger/receipt.csv` (2026-10-17 22:53) | tm-offers | cheaper-plan receipt lines: `in_headline`, `no_tradeoff`, `current_plan`, `best_plan`, `tradeoff_line`, `money_back_to_customers_mo` |
| `hidden_value_items.csv` | `/workspace/tmobile/scratch_models/hidden_value/hidden_value_items.csv` (2026-10-17 22:49) | tm-models | which accounts get a watch-line, streaming, price-guarantee or trade-in line on the bill/app. Dollar amounts are recomputed from the sandbox and cross-checked |

To refresh, copy the newer file over the old one, run `python3 docs/outreach/draft_outreach.py`, and commit the inputs together with the outputs.
