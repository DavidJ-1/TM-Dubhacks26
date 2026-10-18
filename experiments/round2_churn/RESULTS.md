# Round 2 churn models — ALL DATA, LABELS AND NUMBERS SYNTHETIC
Folds: the repo's 5 folds (StratifiedKFold, seed 2026, 5,000 non-persona accounts, 137 churners); the baseline reproduces the demo OOF exactly.
Repeated CV: 3 extra seeds (101–103) × 5 folds. It is a noise estimate only. 1 churner = 0.73 pp of top-10% capture.
Code: common.py (data + recipe terms), run_r2.py (all models, both tracks), eval_r2.py (paired stats), repcv_r2.py.
Outputs: results_r2.csv, repeated_cv_r2.csv, oof_r2.csv, chosen_hparams.json, run_r2.log, repcv.log.
Nothing was written outside this folder. No git/repo operations.
Tracks: **full** = every feature. **compliant** = drops port_out_inquiry, competitor_research_score and their recipe terms; segment (age proxy) was never used in these feature sets.

## Ceilings (eval-only, using labels.csv p_true_90d — never a feature)
| | AUC | Top-10% | PR-AUC |
|---|---|---|---|
| Full generator truth (p_true_90d) | .864 | 64.2% | .291 |
| **Compliant ceiling** (true generator score minus the CPNI terms; approximate) | **.863** | **62.0%** | .270 |
**Key finding:** on top-10% capture the compliant track is already at its ceiling (62.0%). Spline-LR and recipe-spline-LR hit 62.0% on the canonical folds. Full-track headroom is about 3 churners (62.0 → 64.2%).

## Canonical folds (Δ vs the track's baseline: fold mean±sd (folds better) | paired bootstrap 95% CI)
| Track | Model | AUC | PR-AUC | Top-10% | ECE | ΔAUC boot | ΔTop10 fold | ΔTop10 boot |
|---|---|---|---|---|---|---|---|---|
| full | baseline Model A LR | .853 | .255 | .620 | .0040 | — | — | — |
| full | spline-LR tuned (core) | .856 | .252 | .591 | .0043 | +.003 [−.006,+.011] | −.029 (0/5) | −.031 [−.073,+.011] |
| full | spline-LR tuned (core + raw contact counts) | .860 | .255 | .613 | .0040 | +.007 [−.002,+.014] | .000 (2/5) | −.009 [−.044,+.029] |
| full | EBM, 10 interactions (core + contacts) | .857 | .242 | .599 | .0039 | +.004 [−.007,+.015] | −.021 | −.021 |
| full | HGB, tuned with inner CV | .844 | .217 | .569 | .0060 | −.009 | −.050 (0/5) | −.059 [−.109,−.007] |
| full | LightGBM, tuned with inner CV | .847 | .214 | .577 | .0044 | −.006 | −.021 | −.042 |
| full | **RECIPE-LR (generator terms)** ⚠ | .860 | **.267** | **.635** | .0030 | +.007 [−.002,+.015] | +.022±.032 (2/5) | +.007 [−.022,+.036] |
| full | RECIPE-spline-LR ⚠ | .861 | .256 | .613 | .0032 | +.008 [−.003,+.018] | +.008 | −.012 |
| full | **stack: LR meta over [recipe-LR, spline, EBM]** ⚠ | **.863** | .262 | .628 | **.0025** | **+.010 [+.001,+.018]** | +.015±.041 | +.001 [−.029,+.029] |
| compl. | baseline Model A LR (compliant) | .851 | .249 | .591 | .0043 | — | — | — |
| compl. | spline-LR tuned (core) | .854 | .238 | .620 | .0039 | +.004 [−.007,+.014] | +.022 (2/5) | +.025 [−.015,+.058] |
| compl. | **spline-LR tuned (core + raw contact counts)** | .860 | .245 | **.620** | **.0027** | +.009 [−.002,+.019] | **+.037±.001 (5/5)** | +.030 [−.007,+.066] |
| compl. | EBM, 10 interactions | .860 | .241 | .584 | .0045 | +.009 [−.004,+.023] | .000 | −.006 |
| compl. | HGB tuned | .849 | .207 | .584 | .0041 | −.001 | +.015 | −.002 |
| compl. | LightGBM tuned | .851 | .202 | .599 | .0032 | +.001 | +.007 | +.007 |
| compl. | RECIPE-LR ⚠ | .860 | .251 | .591 | .0047 | +.009 [+.001,+.018] | +.007 | +.003 |
| compl. | RECIPE-spline-LR ⚠ | .861 | .245 | .620 | .0033 | +.011 [−.003,+.024] | +.037 (4/5) | +.030 [−.007,+.070] |
| compl. | stack ⚠ | .862 | .246 | .591 | .0038 | +.011 [.000,+.021] | .000 | +.003 |
⚠ = engineered to match harness/labels.py's functional form (same terms, thresholds and caps, e.g. early_tenure = tenure<12, low_app_use = sessions≤3, troubled_4plus, neg_sentiment = max(0,−avg), tenure capped at 60). **This fits the synthetic recipe and would not transfer to real data.** Only pre-cutoff feature columns were used; no label columns.

## Repeated CV (3 seeds; mean±sd, paired Δ vs the track baseline within each seed)
| Model | AUC | Top-10% | ΔAUC | ΔTop10 |
|---|---|---|---|---|
| [full] baseline | .851±.004 | .620±.007 | — | — |
| [full] RECIPE-LR ⚠ | .856±.005 | .613±.000 | +.006±.003 | −.007±.007 |
| [full] spline + contacts | .855±.004 | .618±.011 | +.004±.003 | −.002±.011 |
| [full] stack ⚠ | .855±.002 | .613±.007 | +.004±.003 | −.007±.000 |
| [compl.] baseline | .850±.004 | .601±.011 | — | — |
| [compl.] spline-LR tuned (core) | .852±.004 | .608±.004 | +.002±.001 | +.007±.007 |
| **[compl.] spline + contacts** | **.857±.003** | **.611±.004** | **+.007±.003** | **+.010±.008** |
| [compl.] RECIPE-spline ⚠ | .857±.002 | .606±.007 | +.008±.002 | +.005±.017 |
| [compl.] EBM | .853±.005 | .589±.026 | +.004±.008 | −.012±.015 |
| [compl.] stack ⚠ | .856±.005 | .596±.008 | +.006±.005 | −.005±.015 |

## Verdict
- **AUC gains are real but small.** Spline-LR and recipe models add +.005 to +.008 AUC, consistently positive across 3 seeds and the canonical folds. Most of this comes from **raw contact counts (support_90d, billing_contacts_90d, device_contacts_90d), which harness prepare() drops**, plus spline shapes. Caveat: support_90d, billing_contacts_90d and device_contacts_90d are generator terms, so this is partly the recipe too. On real data, contact volume is still a plausible signal.
- **Top-10% gains are not real beyond noise in the full track.** RECIPE-LR's 63.5% on the canonical folds fails to replicate (−0.7 pp in repeated CV). The full track has about 3 churners of headroom, and nothing reliably captures them.
- **Compliant track:** spline-LR + raw contacts is the best compliant model. Canonical: AUC .860, top-10% 62.0% (+3.7 pp vs the compliant baseline, 5/5 folds, bootstrap CI [−.007,+.066]). Repeated CV: +1.0±0.8 pp, +.007±.003 AUC, best ECE. It matches the full baseline's 62.0% without CPNI fields, and **62.0% is the compliant ceiling**, so there is nothing left to gain there on this data.
- Trees (HGB/LightGBM, tuned) stay worse. EBM is fine on AUC but noisier at top-10%. Stacking adds AUC (+.010, CI excludes 0 in full) but not top-k.
- **TabPFN: skipped.** It installed (tabpfn + torch CPU), but downloading weights requires a one-time license acceptance and an API key from a Prior Labs account (ux.priorlabs.ai → TABPFN_TOKEN). That's an account signup for David to decide on; I did not do it.

## Recommendation
Ship-candidate: **compliant spline-LR (knots/C tuned in inner CV) on the core features + support_90d, billing_contacts_90d, device_contacts_90d.** Claim "matches the full-feature baseline's top-10% capture (62%) without CPNI fields, AUC .853→.860, better calibration (synthetic)". Don't claim top-10% gains beyond that: the data's ceiling is the limit. The recipe-matched models are useful only as an upper-bound sanity check and shouldn't be presented as a modeling win.
