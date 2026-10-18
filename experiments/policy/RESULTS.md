# Decision-policy evaluation: who to contact, which offer, when to do nothing
**All numbers are synthetic** (sandbox stub accounts plus our simulated labels). Scratch only: no repo, git, or demo changes, and the sandbox was not touched.
Run: `OMP_NUM_THREADS=1 python3 make_cw_oof.py && python3 policy_eval.py && python3 emp_and_breakdown.py` (~45 s).
Every assumption is in `config.py`, tagged [repo], [research] or [ours].

## How it works
- **Decisions** use model scores: our out-of-fold (OOF) churn probabilities (`demo_data/churn_oof_pred.csv`) and the upgrade OOF score (`round2_upgrade/task2_oof.csv`, best LR). The compliant variant uses the compliant spline-LR OOF.
- **Value is scored under the generator's true probabilities** (`labels.csv` p_true_90d / p_upgrade_90d). A policy is therefore not graded on its own beliefs, and miscalibration shows up as lost dollars.
- **Retention:** EV = p_churn × save_rate × (monthly revenue × margin × horizon) − offer cost − annoyance. Save rates, costs and annoyance come from the repo's per-action candidates (`offer_candidates.csv.gz`, eligible rows only).
- **Upsell:** EV = P(take) × margin gain × (1 − p_churn) − cost − annoyance − backfire. Upsell is not credited with any churn reduction [research].
  - P(take) = LIFT × upgrade probability, rescaled to a 3.9% per-quarter base rate [research: AT&T/VZ 3–4.7%/qtr].
  - Backfire = 0.67 × p_churn × retained value [ours, extrapolated from Ascarza 2016's 6%→10% on a plan-change nudge].
- **Do nothing:** EV = 0.
- **Company-dollar view:** customer savings from right-size and variant switch count as lost margin, not value. The repo gives them 0.5 "trust value"; that view is shown as a side scenario.
- **Budget:** 500 contacts (10% of 5,000 accounts). The unconstrained case contacts everyone with EV > 0. Risk-only and value-weighted contact everyone with p ≥ 5%.

## 1. Policy comparison (base assumptions, true expected net $)
| Policy | Net $ @ 500 contacts | $/contact | Net $ unconstrained (contacts) |
|---|---|---|---|
| Our current engine (`offers.csv`) | 65,531 | 131 | 36,591 (1,299) |
| Teammates' playbook (care/loyalty credits) | 17,430 | 35 | 6,915 (918) |
| Risk-only top p_churn, best retention action | 56,876 | 114 | 56,868 (505) |
| Value-weighted (p × bill) | 58,265 | 117 | 58,291 (505) |
| EV-optimal (no guardrails) | **66,887** | 134 | **69,199** (883) |
| EV + guardrails (no upsell to top churn decile or ≥3 support/90d) | 66,462 | 133 | 68,685 (876) |
| EV + guardrails, ≥5 support variant | 66,822 | 134 | 69,117 (882) |
| EV + guardrails, **compliant** (spline-LR probs; no port-out/competitor-triggered check-ins; loyalty at off-target rate when the only trigger is shopping) | 65,688 | 131 | 67,623 (835) |

Full table: `policy_results.csv`.
- **At a fixed budget, EV ranking beats the current engine by only about $0.9–1.4k (+1–2%).** The engine already ranks by EV, so the budget case is basically a tie.
- **With no budget, the engine is about $32k behind.** That gap comes from the customer-first actions (`engine_breakdown.csv`): right-size −$26.2k over 290 contacts and variant switch −$5.6k over 93, each negative in company dollars. Take those out and the engine lands at about $68.4k over ~916 contacts, the same as EV-optimal. They are a deliberate trust spend that the persona golden tests require (05, 38, 40), so **label that spend; don't silently drop it.**
- **The engine overstates upsell value by about 2.5×.** Its claimed EV is $13.4k for family upgrade and $10.3k for step-up, against $5.0k and $4.1k here. The cause is P_ACCEPT: 0.25 for step-up and 0.20 for family upgrade, versus a research base rate of ~4% upgrades per quarter.
- **Guardrails are cheap insurance.** Blocking upsell for top-decile risk or ≥3 support contacts costs $425 at budget (0.6%); the ≥5 variant costs $65. The EV formula's backfire term already deters most risky upsells.
- **Compliance costs about $0.8k at budget (1.2%) and $1.1k unconstrained.** It removes all 56 port-out/competitor-triggered contacts.
- **The teammates' playbook loses** because it hands $25/$60 credits off probabilities that run about 5× higher than ours. 17 of its budgeted contacts are triggered by port-out. Caveat: it is scored against *our* generator's true probabilities, not its own label definition.

## 2. Robustness across 729 sensitivity cells
The grid varies save-rate ×{0.5, 1, 1.5}, cost ×{0.5, 1, 2}, margin {0.3, 0.5, 0.7}, horizon {12, 24, 36}, upsell lift {0.5, 1, 2} and backfire {0, 0.33, 0.67}. Files: `grid_robustness.csv`, `grid_results.csv`.
| Policy | Win share (budget / uncon.) | Beats engine (budget / uncon.) | Median net $ (budget) |
|---|---|---|---|
| EV-optimal | 96% / 100% | 100% / 100% | 53.0k |
| EV + guardrails ≥3 | 0.7% / 0% | 100% / 100% | 52.9k |
| EV + guardrails ≥5 | 3.3% / 0% | 100% / 100% | 53.0k |
| EV + guardrails, compliant | 0% / 0% | 90% / 100% | 52.2k |
| Engine | 0% / 0% | – | 50.1k |
| Value-weighted | 0% / 0% | 15% / 86% | 43.0k |
| Risk-only | 0% / 0% | 11% / 84% | 42.0k |
| Teammates | 0% / 0% | 0% / 25% | 9.1k |

The ranking holds in every cell: EV family > engine > value-weighted ≈ risk-only > teammates. The EV variants differ by under 1.5%, so treat them as tied. Win share among them just reflects that adding constraints can't raise EV under the same model.

## 3. Calibration is worth real money
Same policy (EV + guardrails ≥3) with different churn probabilities feeding the decisions. Files: `calibration_results.csv`, `calibration_grid.csv`.
| Churn probs | Mean p | Net $ @ 500 | Net $ uncon. (contacts) | What the model *believes* it earns (uncon.) |
|---|---|---|---|---|
| Oracle (generator p_true) | 2.74% | 66,904 | 69,087 (876) | 69,760 |
| **Baseline LR (calibrated)** | 2.75% | **66,462** | **68,685** (876) | 69,847 |
| Class-weighted LR | 29.1% | 55,798 (−16%) | 38,097 (2,288) (−45%) | 603,346 |
| Class-weighted + Platt recalibration | 2.75% | 65,248 | 67,625 (852) | 65,726 |
| Baseline ×2 (overconfident) | 5.4% | 65,373 | 66,065 (1,243) | 148,644 |
| Baseline ×0.5 (underconfident) | 1.4% | 64,616 | 65,496 (592) | 32,743 |

Across all 729 cells, the calibrated LR beats class-weighted in 100% of them. The median loss from class weighting is 21% at budget and 54% unconstrained. The class-weighted model's ranking is fine (AUC 0.855), but its probabilities make the engine pick the wrong offers, contact 2.6× too many people, and claim roughly 9× its true value. Calibration lets us get within about $0.4k of the oracle.

## 4. Expected Maximum Profit (Verbraken et al., TKDE 2013), Python implementation
EMP depends only on ranking, so calibration does not affect it. Defaults: CLV $200, incentive δ $10, contact φ $1, acceptance γ ~ Beta(6, 14). "Our CLV" uses the median retained value of $1,562 (24 months × 50% margin). File: `emp_results.csv`.
| Model | AUC | Top-10% capture | EMP $/cust (default) | Profit-optimal contact % | EMP $/cust (our CLV) | Optimal contact % |
|---|---|---|---|---|---|---|
| Baseline LR | 0.853 | 62.0% | 0.351 | 3.5% | 7.99 | 17.9% |
| Compliant spline LR | 0.854 | 62.0% | 0.365 | 3.5% | 8.03 | 21.0% |
| Class-weighted LR | 0.855 | 58.4% | 0.329 | 3.6% | 8.06 | 20.8% |
| Oracle p_true | 0.864 | 64.2% | 0.385 | 3.7% | 8.29 | 18.0% |

EMP agrees with the other results: the compliant spline LR is at least as good as the baseline. The headroom to the oracle is about 4–10% of EMP. EMP's γ (mean 30% acceptance-and-save) is far more generous than our per-action save rates, which explains why its optimal contact fraction (18–21%) is higher than the ~17.5% our EV policy actually contacts.

## Plain-English takeaway
- **The model is already near the ceiling. The money is in the decision layer, and our engine already captures most of it.** A strict EV policy matches the engine at a fixed budget (+1–2%).
- **Without a budget, it reaches the same dollars with fewer contacts,** once you see that right-size and 55+/partner switches are a deliberate ~$32k (synthetic) trust spend.
- **Upsell value is overstated about 2.5×** unless acceptance is pinned to real upgrade rates.
- **Calibration is not optional.** A class-weighted model with the same ranking quality loses 16–45% of the value.
- **Guardrails and compliance are cheap:** about 1% each.

**Honest one-line pitch claim:** "On synthetic data, scoring every offer in expected dollars with calibrated probabilities beat risk-only and value-weighted targeting in every one of 729 assumption scenarios. Dropping the privacy-risky port-out and competitor triggers cost only about 1%."

## Caveats
- Everything is synthetic and circular: the true probabilities come from our own generator.
- Save rates, costs, the backfire size and the upsell lift are assumptions, which is why the grid exists.
- No uplift or holdout data exists, so "save rate" is assumed, not measured.
- Results are in expected value; no outcome-sampling noise was simulated.
