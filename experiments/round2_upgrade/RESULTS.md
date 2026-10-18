# Round 2: upgrade models (ALL DATA SYNTHETIC; sandbox = stub data opened read-only)

Run 2026-10-17, 9:45–10:00 PM PT, OMP_NUM_THREADS=1.
Scripts: `common.py`, `task1_real.py`, `task2_sim.py`, `task3_guardrail.py`, `explain_line.py`.
Outputs: `task*_results.csv`, `task2_oof.csv`, `task3_info.json`, `*.log`.
EBM comes from `interpret-core`, installed to the local `.pylib` (free, no system install). No repo, git or demo changes.
Excluded throughout: port-out, competitor research, segment, discount group, language, member role (teen/child = age proxy), and income/enrichment.
CIs are 200-sample stratified bootstraps. Δ is a paired bootstrap against the named reference rule or model.

## Task 1: real sandbox purchase backtest (account- and line-level)
Features are the same pre-cutoff set as round 1. I added two per-account priors:
- `n_eligible`: device lines minus pre-cutoff financing starts
- `eligible_share`

**Per-line financing history at the cutoff can't be built without leakage.** The sandbox stores only each line's *current* device. Billing financing events are account-level and not tied to a line.
So any per-line "months since financing start", "months to payoff" or "paid-off" feature would have to come from the current device's purchase date. For a line that upgraded in the window, that's the new phone, a direct label leak.
The legitimate per-line signal is account-level: pre-cutoff financing starts and ends, and the installment load visible in the pre-cutoff bill.
Line level covers non-BYOD lines only. BYOD lines never buy, so including them is trivial. Folds use StratifiedGroupKFold by account (5, seed 2026).

### Account level ("does any line get a new device?")
| cutoff | model | AUC [CI] | PR-AUC | top-10% capture | lift | Brier / ECE | ΔAUC vs eligible-lines rule |
|---|---|---|---|---|---|---|---|
| Jun (base 22.1%) | Rule: n_device_lines | 0.736 | 0.389 | 20.9% | 2.09x | n/a | n/a |
| Jun | Rule: 1-(1-q)^eligible (calibrated) | 0.738 | 0.399 | 21.6% | 2.15x | 0.150 / 0.011 | ref |
| Jun | **LR** | **0.781 [0.767, 0.795]** | **0.466** | **24.6%** | **2.46x** | 0.144 / 0.025 | **+0.042 [+0.032, +0.055]** |
| Jun | Spline LR | 0.777 | 0.447 | 23.1% | 2.31x | 0.145 / 0.021 | +0.038 |
| Jun | EBM | 0.775 | 0.433 | 22.9% | 2.29x | 0.146 / 0.016 | +0.036 |
| Jun | Tuned HGB (nested) | 0.775 | 0.441 | 22.1% | 2.21x | 0.145 / 0.015 | +0.035 |
| Mar (base 18.3%) | Rule: calibrated eligible | 0.721 | 0.328 | 21.9% | 2.19x | 0.135 / 0.010 | ref |
| Mar | **LR** | **0.750 [0.733, 0.768]** | **0.372** | **24.5%** | **2.45x** | 0.133 / 0.018 | **+0.028 [+0.016, +0.042]** |
| Mar | Spline LR / EBM / HGB | 0.747 / 0.740 / 0.740 | 0.35 / 0.34 / 0.35 | 22.5% / 21.5% / 22.6% | ~2.2x | ~0.134 | +0.018 to +0.025 |

LR beats line count on AUC beyond noise at both cutoffs, and on top-10% capture: +3.0 pts [+1.2, +5.0] in Jun and +2.7 [+0.4, +4.8] in Mar.
Spline LR, EBM and tuned HGB never beat plain LR; HGB loses on AUC.

### Line level ("does this line get a new device?")
| cutoff | model | AUC [CI] | PR-AUC | top-10% capture | lift | Brier / ECE | ΔAUC vs eligible-share rule |
|---|---|---|---|---|---|---|---|
| Jun (9,276 lines, base 12.5%) | Rule: account n_device_lines | 0.509 | 0.129 | 10.4% | 1.04x | n/a | −0.079 |
| Jun | Rule: account eligible_share | 0.588 | 0.149 | 10.6% | 1.06x | n/a | ref |
| Jun | **LR** | **0.671 [0.658, 0.686]** | 0.203 | 19.1% | 1.90x | 0.105 / 0.011 | **+0.084 [+0.071, +0.098]** |
| Jun | Spline LR | 0.668 | 0.203 | 19.1% | 1.91x | 0.105 / 0.010 | +0.080 |
| Jun | EBM | 0.663 | 0.203 | 20.3% | 2.03x | 0.105 / 0.007 | +0.075 |
| Jun | Tuned HGB | 0.667 | 0.207 | 21.1% | 2.11x | 0.105 / 0.009 | +0.079 (Δtop10 +8.8 pts) |
| Mar (8,650 lines, base 10.2%) | **LR** | **0.625 [0.610, 0.642]** | 0.146 | 15.6% | 1.56x | 0.090 / 0.008 | +0.067 [+0.049, +0.080] |
| Mar | Spline LR / EBM / HGB | 0.620 / 0.608 / 0.608 | ~0.15 | 18.2% / 16.6% / 17.8% | 1.7–1.8x | ~0.090 | +0.050 to +0.062 |

Line count is useless per line (AUC 0.51): more lines don't make any *single* line likelier to upgrade.
What predicts a line is the account's **installment load at the cutoff**. LR coefficients:
- eligible_share +0.77
- pre-cutoff bill −0.67 (given usage and plan, a higher bill means more phones still being paid off)
- financing ends −0.27

That is the "financing payoff / recently upgraded" driver from the research notes, and it's observable before the cutoff.
Tenure has no per-line effect (11–14% across buckets). In the generator (`population.py:75`), device age is memoryless (exponential, mean 22 months), so there is **no device-age effect to find**.
Best single-feature AUC is 0.59. Nothing comes near 0.95; no leakage flags.

**Honest read:** at account level, the gain over line count is real but small (+0.03–0.04 AUC, +3 pts top-10%). It comes from "who is still paying off phones," not usage behaviour.
The fancier learners (spline, EBM, HGB) add nothing over LR.

## Task 2: simulated `upgrade_90d` (exact churn folds; 322/5,000 = 6.44%)
| model | AUC [CI] | PR-AUC | top-10% capture | lift | Brier / ECE | ΔAUC vs LR [CI] | Δtop10 vs LR [CI] |
|---|---|---|---|---|---|---|---|
| LR baseline (round 1) | 0.762 [0.736, 0.787] | 0.203 | 33.2% | 3.32x | 0.0562 / 0.010 | ref | ref |
| Spline LR | 0.751 | 0.191 | 33.2% | 3.32x | 0.0565 / 0.009 | −0.011 [−0.020, −0.002] | +0.003 |
| EBM | 0.761 | 0.215 | 34.5% | 3.45x | 0.0556 / 0.008 | −0.001 | +0.013 [−0.019, +0.043] |
| **LR on 16 generator-matched transforms** | **0.771 [0.747, 0.796]** | **0.221** | **34.8%** | **3.48x** | 0.0554 / 0.009 | +0.009 [−0.004, +0.020] | +0.014 [−0.019, +0.047] |
| LR features + transforms | 0.761 | 0.204 | 32.6% | 3.26x | 0.0563 / 0.013 | −0.001 | −0.005 |
| EBM features + transforms | 0.763 | 0.218 | 35.1% | 3.51x | 0.0554 / 0.007 | +0.001 | +0.018 [−0.016, +0.050] |
| *Ceiling: true recipe coefficients without student/income* | 0.774 | 0.231 | 34.2% | n/a | n/a | +0.012 | +0.011 |
| *Oracle p_upgrade_90d (includes income + student)* | 0.808 | 0.266 | 37.6% | n/a | n/a | +0.046 | +0.047 |

The transforms are copied from `harness/labels.py` `upgrade_terms()`: tier, cap, over-cap share, near-cap ≥80%, clipped usage growth, hotspot ≥5 GB per line, device age beyond 12 months, 36m+ device, recent payoff, capped tenure, bill shock, promo expired, and a churn-risk z-score from the OOF churn score.
Dropped: student (age proxy), the step-up-cost-to-income term and the income term.

**Nothing beats the round-1 LR beyond noise.** The generator-matched LR (0.771) is essentially at the ceiling achievable without income and age proxies (0.774, the true formula itself).
The rest of the gap to the 0.808 oracle is the excluded proxies plus coin-flip label noise. **There is no more to squeeze from this label without using income or age.**

## Task 3: upsell-eligible ranking with churn guardrail
Score: generator-matched LR (OOF). Guardrail: exclude the top 10% of churn risk (OOF churn score) and anyone with 3+ support contacts in 90 days.
Applied to the 5,000 accounts and the simulated label:
- **Excluded: 1,486 accounts** (500 top-churn-decile, 1,462 with 3+ support contacts; they mostly overlap). **Eligible pool: 3,514 (70%).**
- The guardrail drops 87 of 322 upgraders (27%). The upgrade rate is 5.9% among excluded accounts vs 6.7% among eligible ones.

| strategy | accounts targeted | upgraders hit | capture of all 322 | precision | expected (sum of scores) | true churners contacted | 3+-support contacted |
|---|---|---|---|---|---|---|---|
| Unguarded top 10% | 500 | 112 | 34.8% | 22.4% | 120.5 | 4 | 126 |
| **Guarded top 500 (eligible only)** | **500** | **103** | **32.0%** | **20.6%** | **107.7** | **3** | **0** |
| Guarded, same score threshold as unguarded top 10% | 374 | 85 | 26.4% | 22.7% | 90.4 | 2 | 0 |
| Whole eligible pool | 3,514 | 235 | 73.0% | 6.7% | 238.6 | 31 | 0 |

The guardrail costs 9 upgraders (−2.8 pts capture) at the same 500 contacts. It removes all 126 contacts to accounts with 3+ support calls and the 13 top-churn-decile accounts.
On this data, the "3+ support contacts" rule is the binding one: 29% of accounts are blocked by it. If that's too aggressive, a 5+ threshold is worth testing.

## Takeaway
- **Real sandbox purchases:** the best model is still plain logistic regression. It beats the line-count rule by a small, real margin (account AUC 0.78 vs 0.74, top-10% 24.6% vs 21.6%).
  The extra signal is "who is still paying off phones," visible in the pre-cutoff bill. Per line it reaches AUC 0.67 / 2x lift.
  Spline LR, EBM and tuned HGB add nothing. The stub generator has no device-age effect, so the claimed driver can't be validated here.
- **Simulated label:** we're at the ceiling (0.771 vs 0.774 true-formula ceiling without income and age). Keep LR, optionally swapping in the 16 generator-matched transforms. More model complexity won't help.
- **Upsell list:** target the top 500 upgrade scores among the 3,514 guardrail-eligible accounts. That reaches about 32% of expected upgraders (vs 35% unguarded) with zero contacts to high-churn or 3+-support accounts.
