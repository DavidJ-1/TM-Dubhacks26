# Device-upgrade backtest on the sandbox's own purchase history (ALL DATA SYNTHETIC: judge sandbox stub data)

Run 2026-10-17 ~9:20 PM PT. Scripts: `backtest.py`, `structural_check.py`. Outputs: `results.csv`, `audit.json`, `single_feature_auc_*.csv`, `lr_coefs_*.csv`, `run.log`.
sandbox.db was opened with `mode=ro`, and demo_data was only read. Nothing in the repo was changed. OMP_NUM_THREADS=1.

## Design
- **Cutoff A:** end of Jun 2026. Outcome window: purchase months Jul–Sep 2026.
- **Cutoff B (robustness):** end of Mar 2026. Outcome window: Apr–Jun 2026.
- **Unit:** account. The 42 personas are excluded, as are accounts not yet open at the cutoff. That leaves 4,630 accounts (A) and 4,330 (B).
- **Label:** any line's `device_purchase_date` falls in the window. Positives: A 1,021 (22.1%), B 791 (18.3%).
  The billing-based label (a `device_installment` event in the window) is a strict subset: 901/1,021 and 684/791. The difference is phones bought outright.
- **Features (pre-cutoff only):**
  - tenure at cutoff, credit tier, autopay, contact preference
  - plan family, tier and cap (no plan-change events exist, so the plan is assumed constant)
  - line roster: n_lines, n_byod, n_device_lines (no line add/remove events exist)
  - pre-cutoff billing: last and mean bill, 3-month trend, count of financing starts and ends, months since the last of each
  - usage in the last 3 pre-cutoff months, and growth vs the prior 3
  - support contacts before the cutoff (count, unresolved, sentiment, device and plan_change topics)
  - account add-ons (current state; no history exists)
- **Forbidden and not used:** anything from a line's *current* device (age, SKU, financing balance or months remaining, trade-in value, protection add-ons). Each line stores only its current device, so these reflect the post-upgrade phone.
  Also excluded: port-out, competitor research, segment, discount group, language, and income/enrichment fields.
- **CV:** StratifiedKFold(5, shuffle, seed 2026) on the label, at account level.

## Results
Base rate is about 22% (A), so the top 10% (463 accounts) can hold at most 45% of positives.

| cutoff | model | AUC [95% CI] | fold mean±sd | PR-AUC | top-10% capture [CI] | Brier | ECE |
|---|---|---|---|---|---|---|---|
| A (Jun) | **LR** | **0.780 [0.767, 0.795]** | 0.781±0.011 | 0.465 | 24.5% [22.6, 26.3] (lift 2.4x, precision ≈ 54%) | 0.146 | 0.047 |
| A | HGB | 0.766 [0.750, 0.777] | 0.766±0.012 | 0.434 | 22.0% | 0.147 | 0.010 |
| A | Heuristic: count of device lines without a pre-cutoff financing start | 0.740 | 0.740±0.013 | 0.389 | 21.7% | n/a | n/a |
| A | Simulated `p_upgrade_90d` score (labels.csv) | **0.342** (worse than random) | 0.342±0.025 | 0.160 | 4.0% | n/a | n/a |
| A | Churn OOF score | 0.566 | 0.566±0.034 | 0.253 | 12.7% | n/a | n/a |
| B (Mar) | **LR** | **0.750 [0.732, 0.767]** | 0.750±0.020 | 0.373 | 23.6% | 0.134 | 0.036 |
| B | HGB | 0.735 | 0.735±0.022 | 0.345 | 21.4% | 0.135 | 0.017 |
| B | Heuristic | 0.723 | 0.723±0.023 | 0.321 | 22.1% | n/a | n/a |
| B | Simulated `p_upgrade_90d` | 0.403 | 0.403±0.032 | 0.146 | 5.6% | n/a | n/a |
| B | Churn OOF | 0.519 | 0.519±0.015 | 0.194 | 10.9% | n/a | n/a |

**HGB vs LR (paired bootstrap):**
- Cutoff A: ΔAUC −0.015 [−0.027, −0.004], Δtop10 −0.025 [−0.045, −0.008]
- Cutoff B: ΔAUC −0.015 [−0.026, −0.003]

So **LR is reliably better**, at both cutoffs. Results are consistent across cutoffs: LR 0.78 at A vs 0.75 at B. B has fewer pre-cutoff months of history.

## Leakage audit
- The best single-feature AUC is 0.718 (n_device_lines), then voice/streaming/data volume (0.66–0.70) and bill (0.65). **Nothing is above 0.95.**
- No current-device field is used. The account's purchase timestamp appears only in the label.
- Pre-cutoff financing starts count against the window (negative LR coefficient). That's legitimate, since "already upgraded recently" is known at the cutoff.

## What actually drives it (structural_check.py, LR)
| feature set | AUC A | AUC B |
|---|---|---|
| Structural only (line counts + pre-cutoff financing events, 8 features) | 0.740 | 0.724 |
| All 45 features | 0.780 | 0.750 |
| Behaviour only (no line counts, bills, usage totals or financing) | 0.585 | 0.561 |

The window purchase rate rises almost linearly with device lines: 0 → 0%, 1 → 11.5%, 2 → 27%, 3 → 31%, 4 → 40%, 5+ → 47% (cutoff A).

**Why:** the sandbox generator (`vendor/dubhacks/datagen/population.py:75`, `realize.py`) draws each line's device age as an independent exponential (mean 22 months). The only limits are account tenure and the device's release date.
**Purchase timing is not tied to usage, plan, bills, support or unhappiness.** The model mostly learns "more phones = more chances one gets replaced." It adds "lines already financed recently can't be replaced in-window," and bill/usage totals stand in for line count.

## Simulated label vs real history
The simulated `p_upgrade_90d` score predicts *backwards* on the real purchases (AUC 0.34 and 0.40). It's computed as of Oct 2026 from current device age, and anyone who just bought a phone now has a young device and a low score. That's the post-upgrade leak this backtest was built to avoid.
More broadly, the simulated recipe (device age, plan headroom, usage growth) and the sandbox's purchase process are unrelated. Neither validates the other.

## Takeaway
- On the sandbox's own purchase history, a leak-free LR ranks accounts at AUC ≈ 0.75–0.78 and puts 2.4x the base rate of upgraders in its top 10%. That holds at two cutoffs, and LR beats HGB.
- But nearly all of that is "households with more phones." In this stub data, device replacement timing is random by construction, so it says nothing about real upgrade behaviour.
- For the demo: present the upgrade score as simulated. Don't cite this backtest as evidence that the upgrade drivers (device age, plan headroom) work.
- What would make it real:
  - per-line device history (every device a line has had, with dates)
  - plan-change and add-a-line events
  - offer exposure and acceptance logs
