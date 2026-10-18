# Value-aware churn ranking: SYNTHETIC DATA AND LABELS
Run Sat 2026-10-17, about 8:50–8:59 PM PDT. Same harness folds (StratifiedKFold 5, seed 2026), 5,000 accounts, 137 churners. The repo was not touched.
Value = last monthly bill / ARPA (sample mean bill $199.98). Top 10% = 500 accounts. Churner-$ capture = the share of all churners' monthly bill
that falls inside the selected 500. CIs are 300 paired bootstrap resamples vs (a). Fold Δ = mean±sd of the per-fold paired deltas. Code: value_eval.py, raw: value_results.csv.

| Ranking | AUC | PR-AUC | Churners caught (top 10%) | Δ count CI | Churner-$ caught | Δ $ CI | Avg bill top 10% (all: $200) | Call |
|---|---|---|---|---|---|---|---|---|
| (a) baseline LR, by p | 0.853 | 0.255 | **62.0% (85)** | – | **65.2%** | – | $206 | reference |
| (b) baseline p × value | 0.853 | 0.255 | 57.7% (79) | [−9.9, 0.0]pp | 64.2% | [−5.0, +4.3]pp | $261 | loses 6 churners (borderline) and **no $ gain** |
| (c1) LR, sample_weight = value | 0.852 | 0.251 | 60.6% (83) | [−5.9, +2.8]pp | 62.7% | [−8.8, +1.6]pp | $201 | noise, slightly worse |
| (c2) LR, sample_weight = √value | 0.853 | 0.257 | 61.3% (84) | [−4.2, +1.9]pp | 64.0% | [−4.5, +0.8]pp | $203 | noise, no gain |
| (f) √-weighted LR p × value | 0.853 | 0.257 | 57.7% (79) | [−10.2, 0.0]pp | 64.2% | [−5.4, +3.9]pp | $260 | same as (b) |
| (d0) HistGBM, unweighted | 0.811 | 0.170 | 53.3% (73) | **[−16.5, −3.3]pp** | 55.9% | **[−17.4, −3.0]pp** | $196 | real loss |
| (d1) HistGBM, weight = value | 0.808 | 0.152 | 48.9% (67) | **[−20.5, −7.1]pp** | 49.5% | **[−25.0, −7.2]pp** | $183 | real loss |
| (e) value-weighted HGB p × value | 0.808 | 0.152 | 52.6% (72) | [−17.4, −3.6]pp | 56.9% | [−18.3, −1.0]pp | $219 | real loss |

Per-fold Δ (count / $): (b) −0.1±4.5 / +2.7±5.3pp; (c1) +0.7±1.6 / +0.6±1.3pp; (c2) +0.7±1.6 / +0.6±1.3pp; (d0) −3.7±2.5 / −4.3±4.3pp;
(d1) −2.2±7.1 / −5.0±7.5pp. Fold sd is around 4–7pp, so only the HGB losses are clearly beyond noise. HGB wasn't tuned, and the synthetic label is a logistic
formula, so LR is the correct model by construction.

**Why value-ranking doesn't help here:** the 85 churners LR already catches are worth about the same per account as the rest. Re-ranking by p × bill fills
the list with big multi-line bills (avg $261) whose churn probability is lower. You drop about 6 real churners and pick up roughly the same dollars.
Remaining-life horizon: not used. A tenure-based horizon would multiply in a tenure term that is already a churn driver (circular), and with a constant
90-day horizon p × bill × 3 ranks the same as p × bill.

## Fairness / protected-proxy check (value = bill)
- Bill vs senior segment: Spearman −0.20 (senior mean bill $120 vs $206). Bill vs 55_plus: −0.17 ($117 vs $205). Bill vs household income: +0.30.
  Bill vs n_lines: +0.88, so value is mostly line count.
- Area median income: no usable variation, correlation NaN (median $80,734 in every group), so I could not test it.
- **Effect on selection:** under (b) p × value the senior share of the top 10% falls from 7.0% to 4.0% (base 7.4%) and 55_plus from 4.4% to 2.2% (base 5.2%).
  Median household income of the selected group rises from $84.8k to $96.3k (base $81.8k). **This is a fairness flag:** value-ranking de-prioritizes
  seniors and 55+ and favors higher-income households. The 55_plus churn rate is 3.1%, above the 2.7% base, so they are not low-risk. The weighted LRs (c1, c2) leave
  the mix basically unchanged (senior 7.0–7.2%, 55+ 4.6–4.8%).

## Recommendation
For "protect revenue" on this data, keep ranking by baseline LR probability. It catches the most churners (62%) **and** the most churner dollars (65%).
p × value buys no dollars, costs about 6 churners, and skews the list away from seniors and 55+. Sample weighting is neutral, and HistGBM is clearly worse.
If revenue emphasis is needed for the narrative, use value **after** risk selection, to size the offer budget per account (spend more on
high-bill accounts inside the top-risk list), rather than to decide who gets contacted. Report the age-mix check alongside it.
