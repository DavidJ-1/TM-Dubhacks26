# RESEARCH: public benchmarks for the churn + offer engine

> **Disclaimer:** our customer data is synthetic and simulated. The figures below are public benchmarks; none of this is real T-Mobile customer data. Compiled 2026-10-17 (PDT). Q2 2026 is the latest reported quarter (Q3 reports: AT&T Oct 21, Verizon Oct 26, T-Mobile Oct 28).

Strength: **strong** = SEC/IR filing or peer-reviewed; **medium** = reputable press, call transcript, or a researcher white paper; **weak** = vendor case study, blog, Reddit-sourced, or undated.

## 1. Top pitch facts (for "Same assumptions, different strategies (simulated)")
1. **High risk ≠ persuadable.** In two field experiments (one at a wireless carrier), the top-risk and top-responsive customers overlapped only ~50% (no better than random). "Half of the retention money is wasted," and targeting by uplift cut churn a further 4.1 and 8.7 pp. Ascarza, *JMR* 55(1), 2018, https://doi.org/10.1509/jmr.16.0163 *(answers "top-10% risk + credit")*
2. **Reaching out can backfire.** In a 65,000-customer wireless field experiment, proactive "switch to a cheaper plan" outreach raised 3-month churn from **6% (control) to 10% (treated)**. Ascarza, Iyengar & Schleicher, *JMR* 53(1):46-60, Feb 2016, https://doi.org/10.1509/jmr.13.0483 *(answers "discount everyone" and over-contacting; this is why "do nothing" can win)*
3. **Even the riskiest barely move.** In Ascarza 2018, the incentive cut churn in the top-risk decile by only **1.6 pp (95.3% → 93.7%)**. https://evaascarza.com/papers/ascarza_18.pdf
4. **Small churn, huge base.** Q2 2026 postpaid churn was **0.99%/mo** (T-Mobile, account level), **0.92%** (Verizon phone) and **0.86%** (AT&T phone). A few basis points matter. SEC filings linked in the table below.
5. *(medium)* **Persuadability beats risk.** One mobile operator's campaign raised churn from 9% to 10%; treating only the uplift model's top 30% turned that into a 1 pp cut. At another operator, uplift targeting saved 6 pp instead of 5 pp with about 22% fewer contacts. Radcliffe & Simpson 2007 (authors are an uplift vendor), https://www.stochasticsolutions.com/pdf/SavedAndDrivenAway.pdf
6. **Households, not phones.** T-Mobile now reports churn per **account** (0.99%/mo; ARPA $152.91; 34.7M accounts, Q2 2026), and a port-out usually takes every line. So we score and value accounts. SEC Ex 99.1, https://www.sec.gov/Archives/edgar/data/1283699/000128369926000100/tmus06302026ex991.htm
7. **The payoff cliff is real.** AT&T's CFO attributed part of a 14 bp YoY churn rise to "customers reaching the end of device financing periods" (Q3 2025). T-Mobile's CEO said 2025 churn "normalized" after 36-month plans had suppressed it (Q4'25 call, Feb 11, 2026). https://www.phonearena.com/news/hidden-in-its-q3-report-is-news-that-could-lead-to-big-problems-at-at-t_id175350 ; https://www.fool.com/earnings/call-transcripts/2026/02/11/t-mobile-tmus-q4-2025-earnings-call-transcript/
8. **Reasons, built to a legal standard.** Every recommendation ships with ≤3 reasons taken from the model's actual contributions. That mirrors the "specific, actual factors, ≤4 reasons" rule US credit law (Reg B) sets for automated decisions, used here as an analogy. https://www.law.cornell.edu/cfr/text/12/appendix-Supplement_I_to_part_1002
Not used as headline facts: "5-25x cheaper to retain" (unsourced, not telecom-specific); the 0.85% T-Mobile Q2'26 phone churn (a CFO remark on the call, not in the filing); and our AUC 0.85, which is against our own labels (against the judges' public example model it's 0.797; see Round 2).

## 2. Benchmark table
| Figure | Number | Source | Date | Strength | Maps to |
|---|---|---|---|---|---|
| T-Mobile postpaid **account** churn, Q1'25 through Q2'26 | 0.94 / 0.92 / 0.97 / 1.04 / 1.04 / **0.99%** | https://www.sec.gov/Archives/edgar/data/1283699/000128369926000100/tmus06302026ex992.htm (Ex 99.1 also gives 0.99%) | 2026-07-23 | strong | `MOCK_MEAN_MONTHLY_HAZARD` 0.0099 |
| T-Mobile stopped reporting **phone** churn from Q1 2026 (reports account churn + ARPA instead) | n/a | https://www.fierce-network.com/wireless/t-mobiles-new-metric-policy-turns-heads | late 2025 | medium | context |
| T-Mobile phone churn, FY2025 (Q4'25) | 0.93% (1.02%) | https://www.t-mobile.com/news/business/t-mobile-q4-2025-earnings | 2026-01/02 | strong | context |
| T-Mobile phone churn, Q2'26 | 0.85% (**CFO remark on call**, not filed) | https://www.investing.com/news/transcripts/earnings-call-transcript-tmobile-posts-q2-2026-eps-beat-shares-fall-premarket-93CH-4808922 | 2026-07-23 | medium | context only |
| Verizon retail postpaid phone churn, 2Q26 (2Q25) | 0.92% (0.97%) | https://www.sec.gov/Archives/edgar/data/732712/000073271226000040/a2026q2exhibit99.htm | 2026-07-24 | strong | `MOCK_MEAN_MONTHLY_HAZARD` |
| AT&T postpaid phone churn, 2Q26 (2Q25) | 0.86% (0.87%) | https://www.sec.gov/Archives/edgar/data/732717/000073271726000294/t-2q2026exhibit992.htm | 2026-07-22 | strong | `MOCK_MEAN_MONTHLY_HAZARD` |
| T-Mobile postpaid ARPA, Q2'26 | $152.91 (+2% YoY) | https://www.sec.gov/Archives/edgar/data/1283699/000128369926000100/tmus06302026ex991.htm | 2026-07-23 | strong | `SERVICE_MARGIN`, value |
| Verizon postpaid ARPA, 2Q26 | $168.35 | Verizon Ex 99 (above) | 2026-07-24 | strong | value |
| **Illustrative LTV estimate (ours, derived)** | life ≈ 1/0.0099 ≈ 101 months; AT&T $56.57 ARPU ÷ 0.86% ≈ $6.6K revenue per line (revenue, not margin, undiscounted) | arithmetic on filings above | n/a | derived | `VALUE_HORIZON_MONTHS` 24 |
| Acquisition cost (CPGA), **old figures only** | US wireless $300-400 per gross add (2005); AT&T Wireless $350 (Q2'04); T-Mobile USA $301 (Q3'04) | https://rcrwireless.com/20050307/archived-articles/carriers-must-reduce-acquisition-costs-to-make-thrifty-customers-profitable ; https://www.sec.gov/Archives/edgar/data/1138234/000095012404003300/v00384exv99w2.htm | 2004-05 | medium/strong but **20+ years old** | none (no current carrier figure exists) |
| Retention credit sizes (US wireless) | Verizon loyalty $10/line/mo × 12 mo; T-Mobile "Appreciation Savings" ~$10/mo off (2+ yr tenure); generic $5-15/mo | https://www.androidauthority.com/verizon-retention-offer-trick-3542674/ (2025-04-08); https://www.phonearena.com/news/t-mobile-experience-more-wappreciation-savings-loyalty-plans_id177978 (2026-02-05) | 2025-26 | weak/medium | sandbox $5/mo loyalty, $25 care credit, `LOYALTY_CREDIT_MONTHS` 12 |
| Save-desk (inbound cancel) save rates | 70%; 61→73%; 14% (port-out bot); 9.5→24.9%; AOL 18→44% | Foundever, InfiniteWatch, Oriserve/Airtel, Qualfon, Schaeffer (links in §5) | mostly undated | **weak** | `SAVE_RATE`, `P_ACCEPT`, `POLICY_ACCEPTANCE` |
| Proactive incentive effect by risk decile | top decile −1.6 pp (95.3→93.7%); best decile −2.9 pp (71.2→68.3%), i.e. ~2-4% relative | Ascarza 2018 PDF (above) | 2018 | strong | `SAVE_RATE` |
| Risk vs uplift overlap; money wasted | ~50% overlap; "half wasted"; +4.1 / +8.7 pp from uplift targeting | https://doi.org/10.1509/jmr.16.0163 | 2018 | strong | `MIN_CREDIT_P_CHURN`, `RISK_FLOOR` |
| Plan-recommendation outreach backfire | churn 6% → 10% (n = 65,000, wireless) | https://doi.org/10.1509/jmr.13.0483 (Crossref-verified: JMR 53(1):46-60) | 2016-02 | strong | `right_size`/`variant_switch` `SAVE_RATE` & `ANNOYANCE`, `SAME_COVERAGE_RULE` |
| Operator campaigns with negative effects | 9→10% churn; uplift-selected 30% → <8%, −70% spend | https://stochasticsolutions.com/pdf/sig-based-up-trees.pdf | 2011 | medium | `ANNOYANCE` |
| T-Mobile Austria uses uplift modelling to avoid "side effects in pro-active targeting" | qualitative | https://ref2014impact.azurewebsites.net/casestudies2/refservice.svc/GetCaseStudyPDF/23933 | 2014 | medium | `ANNOYANCE` |
| Message fatigue | 68% say too many messages is the top reason to unsubscribe (n = 6,000) | https://www.marketingprofs.com/charts/2026/54295/how-many-marketing-emails-and-texts-is-too-many | 2026-02-18 | weak | `ANNOYANCE` (direction only) |
| Profit-based churn targeting (uplift × value − cost) | method plus 2 field experiments | https://doi.org/10.1287/mksc.2020.1229 (Lemmens & Gupta, *Marketing Science*) | 2020 | strong | EV engine design |
| Uplift evaluation: Qini / uplift curves, "sleeping dogs" | method | https://proceedings.mlr.press/v67/gutierrez17a/gutierrez17a.pdf | 2017 | strong | holdout eval |
| Holdout size rule of thumb | 5% at ~10K customers; 10-20% under 2K | https://www.optimove.com/resources/learning-center/control-groups-in-marketing | undated | weak (vendor) | (no constant yet) |
| Academic control groups | 32% (Ascarza 2018 telecom); 50/50 (membership study) | Ascarza 2018 PDF | 2018 | strong | (no constant yet) |
| Uplift tooling | CATE estimators (Uber CausalML) | https://causalml.readthedocs.io/en/latest/about.html | accessed 2026-10-17 | medium | future `SAVE_RATE` |

## 3. Assumption check (`harness/offers.py` CONFIG, `harness/config.py`)
| Constant | Value | Verdict | Reason |
|---|---|---|---|
| `MOCK_MEAN_MONTHLY_HAZARD` | 0.0099 | **realistic** | Exactly T-Mobile's Q2'26 account churn. |
| `VALUE_HORIZON_MONTHS` | 24 | **pessimistic** | Implied average life is ~100+ months, so 24 is conservative (fine for a pitch). |
| `SERVICE_MARGIN` / `STEP_UP_MARGIN` / `DEVICE_UPGRADE_MARGIN` / `HINT_MARGIN` | 0.50 / 0.80 / $80 / 0.30 | not benchmarked | Carriers don't disclose per-customer margin. |
| `SAVE_RATE` on_target (most actions) | 0.12-0.35 | **optimistic** | Proactive experiments show ~2-4% relative / single-digit pp effects. Our rates fit inbound save desks only (weak sources). |
| `SAVE_RATE` `right_size` / `variant_switch` | 0.30 / 0.30 | **optimistic, possibly wrong sign** | Plan-fit outreach raised churn 6→10% in a wireless RCT. |
| `SAVE_RATE` `home_internet_bundle` | 0.03 | realistic | Small effect assumed. |
| `BILL_SHOCK_RELIEF.credit_save_boost` | +0.05 | optimistic | Stacks on rates that are already high. |
| `P_ACCEPT` (e.g. `variant_switch` 0.70, `right_size` 0.45, `step_up` 0.25) | | not benchmarked (`variant_switch` likely optimistic) | No public take-rate data for proactive plan offers. |
| `POLICY_ACCEPTANCE` (config.py) | 0.25 | optimistic for proactive | Low end of inbound save rates, which is a different, higher-intent population. |
| `ANNOYANCE` (most actions) | $2-6 | direction realistic, magnitude not benchmarked | No public $-per-contact figure. Backfire evidence supports a real cost. |
| `ANNOYANCE` `right_size` / `variant_switch` | $2 (lowest) | **optimistic** | These are the actions with the strongest published evidence of raising churn. |
| `SAME_COVERAGE_RULE` | True | **at odds with the evidence** | It forces `variant_switch` to win, which is exactly the outreach type shown to backfire. |
| `UPSELL_AFTER_PAIN_PENALTY` / `UPSELL_BLOCK_DAYS_AFTER_BILL_SHOCK` | $25 / 90 days | directionally supported | Harm concentrates in volatile or declining customers (JMR 2016). |
| `LOYALTY_CREDIT_MONTHS` + sandbox $5/mo loyalty | 12 mo | realistic-to-pessimistic | Real loyalty credits run ~$10/line/mo for 12 mo (weak sources). |
| sandbox $25 care credit | one-time | not benchmarked | No public one-time goodwill-credit data found. |
| `MIN_CREDIT_P_CHURN` / `RISK_FLOOR` | 0.05 / 0.15 | OK as a cost guard, not an effectiveness rule | Risk ≠ responsiveness (Ascarza 2018). |
| `CHECK_IN_COST` / `FIX_FIRST_CALLBACK_COST` | $2 / $15 | not benchmarked | Old figures: call-center transaction $8-10 (2005); vendor ~$8.20 labour per save. |
| Holdout / control group | **none in code** | gap | Can't measure uplift without one. |

## 4. Round 2: uplift, signals, households, devices, explainability
*Researched 2026-10-17 (PDT). Same strength key. Full notes: `research-notes/notes_{uplift,signals,household,device,explain}.md` (outside the repo).*

### 4a. Uplift readiness
| Finding | Number | Source | Date | Strength |
|---|---|---|---|---|
| Two mobile-operator RCTs: uplift vs risk targeting | Op 1: churn 30% control vs 25% treated; uplift on ~80% → −6 pp vs −5 pp with ~22% fewer contacts. Op 2: 9%→10% (harmful); uplift top 30% → −1 pp | https://www.stochasticsolutions.com/pdf/SavedAndDrivenAway.pdf | 2007 | medium (vendor) |
| Orange Belgium public randomized telco churn dataset | a plain churn random forest scored **highest AUUC**; uplift was high-variance, "not always preferable" (2-month outcome window) | https://arxiv.org/abs/2312.07206 | 2023-12 | strong (one dataset) |
| Adding "reach" (did the call connect) to an X-learner | beat plain churn and plain uplift; telecom is where uplift "has failed so far" to clearly win | https://dipot.ulb.ac.be/dspace/bitstream/2013/335292/3/Theo_Verhelst_Reach_modeling.pdf | undated | medium |
| Insurance retention, Qini-optimized logistic uplift | overall effect −0.5%; top-20% predicted uplift +6.41%, bottom 20% about −6% | https://doi.org/10.1214/21-aoas1465 | 2022 | strong |
| Cost-aware multi-offer uplift (Uber), and uplift + ROI knapsack (Booking.com, RCT-validated) | method plus production use | https://arxiv.org/abs/1908.05372 ; https://arxiv.org/abs/2008.06293 | 2019 / 2020 | strong |
| Detecting an interaction effect needs far more data | ~16× the sample of a main effect (interaction half the size) | https://statmodeling.stat.columbia.edu/2023/11/09/you-need-16-times-the-sample-size-to-estimate-an-interaction-than-to-estimate-a-main-effect-explained/ | 2023-11-09 | weak–medium (heuristic) |

**Read:** pitch our engine as **uplift-ready, not uplift**. Our synthetic data has no treatment/control signal. The path is log → randomize (5-10% holdout) → learn: an X-learner for a small holdout, class transformation on our logistic model for a 50/50 split, an uplift forest at volume. Always benchmark against the risk model, because on Orange's real data it won. Per contact, log `offer_id`, `assignment_prob`, `holdout_flag`, `reached`, `accepted`, and `churned_within_60d`.

### 4b. Churn signals & AUC sanity check
- **Signals with the best support:** contract or device-plan runway; tenure; usage *trend* and recency (Ahn et al. 2006, n = 5,789 Korean mobile customers, https://doi.org/10.1016/j.telpol.2006.09.006, strong; WSDM Cup 2018 winner, https://arxiv.org/abs/1802.03396, medium); dropped calls and complaints (Ahn, strong for direction); overage. On overage: UK panel data show overage payments raise switching about as much as the savings would (LSE CEP DP1939, Jul 2023, https://researchonline.lse.ac.uk/id/eprint/121294/1/dp1939.pdf, strong), and pay-per-use-biased customers churned 340-1,040% more (Lambrecht & Skiera 2009, strong, but not mobile).
- **A few good features beat model choice.** 11 telecom datasets, 21 classifiers: Verbeke et al., EJOR 2012, https://doi.org/10.1016/j.ejor.2011.09.031 (strong). In the Duke tournament, logistic regression and trees were among the best (Neslin et al., JMR 2006, https://doi.org/10.1509/jmkr.43.2.204, strong).

| Benchmark (real data) | Reported | Source | Date | Strength |
|---|---|---|---|---|
| Orange KDD Cup 2009 churn (French telco, 1,299 teams) | best AUC **0.7651**; Orange in-house 0.7435 | https://kdd.org/kdd-cup/view/kdd-cup-2009/Results | 2009 | strong |
| Duke/Teradata (Cell2Cell) tournament, 44 entries | top-decile lift 1.07-3.01 (mean ~2.1) | Neslin et al. 2006 (above); numbers from search summary | 2006 | medium |
| **Ours** | AUC **0.85** against our own labels (0.797 against the judges' public example model), top-10% captures **62%** (lift ≈ 6.2) | synthetic | — | — |

**Read:** our numbers are well above every real benchmark. That is almost certainly because the model is **recovering the synthetic generator's own rules**, not because it is better than real-world models. On the slide: "synthetic; real-world churn models reach AUC ~0.65-0.77, top-decile lift ~2-3." Leakage checks: point-in-time features with an out-of-time split; household-grouped folds; no retention-call or cancel-intent fields (Kaufman et al., ACM TKDD 2012, https://dl.acm.org/doi/10.1145/2382577.2382579, strong).

### 4c. Household economics
| Figure | Number | Source | Date | Strength | Maps to |
|---|---|---|---|---|---|
| Verizon converged (home internet + mobile) churn | mobility churn **~30% lower** (as of Q4'25); a 2024 claim said 50% | https://www.verizon.com/about/sites/default/files/2026-03/vz-ms_transcript_2026-03-02.pdf ; https://www.sec.gov/Archives/edgar/data/732712/000119312524216012/d876956dex991.htm | 2026-03-02 / 2024-09 | medium (exec, company-corrected) | `SAVE_RATE.home_internet_bundle` |
| AT&T converged customers | **15%+ higher LTV** | https://investors.att.com/~/media/Files/A/ATT-IR-V2/reports-and-presentations/2024-analyst-day-with-notes.pdf | 2024-12 | strong | bundle value |
| Verizon converged discount | $15/mo broadband discount; warns bundling only works if both products have strong NPS | https://www.verizon.com/about/sites/default/files/2025-05/cowen_conference_transcript_052825.pdf | 2025-05-28 | medium | sandbox $15 BUNDLE-HINT (it matches) |
| Verizon consumer connections per account | 2.95 (Q4'25) | https://fortune.com/company-assets/1534/quartr/earnings-release-8-k-c5658-2026-01-30-11-41-31.pdf | 2026-01-30 | strong | account value |
| T-Mobile: account churn rose 7 bp YoY from broadband-only accounts; selection-bias warning on multi-product churn gaps | qualitative | https://www.sec.gov/Archives/edgar/data/1283699/000128369926000100/tmus06302026ex992.htm ; https://www.fool.com/earnings/call-transcripts/2025/01/29/t-mobile-us-tmus-q4-2024-earnings-call-transcript/ | 2026-07 / 2025-01 | strong / medium | single-product flag |

**Read:** value a save at the **account** level (ARPA × margin × horizon). A 3-line account is worth about 3× one line (derived). If modelling the bundle's churn effect, use a conservative 10-20% reduction (our assumption), well below the observed 30-50% gap because of selection bias. Our `home_internet_bundle` save rate of 0.03 is conservative. Suppress bundle offers after network or support complaints.

### 4d. Device financing timing
| Figure | Number | Source | Date | Strength |
|---|---|---|---|---|
| AT&T CFO: churn rise partly from customers "reaching the end of device financing periods" | 0.92%, +14 bp YoY (3Q25) | https://www.phonearena.com/news/hidden-in-its-q3-report-is-news-that-could-lead-to-big-problems-at-at-t_id175350 | 2025-10 | strong (CFO quote, reported) |
| T-Mobile CEO: 2025 churn "normalized" after 36-month suppression | +7 bp for 2025 | https://www.fool.com/earnings/call-transcripts/2026/02/11/t-mobile-tmus-q4-2025-earnings-call-transcript/ | 2026-02-11 | strong (his interpretation) |
| Upgrade cycle | Verizon CFO: "now around **44 months**", up 2 months YoY (Sep 2026; was "beyond 42" in Mar 2025); average US trade-in age 3.81 yrs (Q1'26) | https://www.verizon.com/about/sites/default/files/2026-09/vz-citi_transcript_2026-09-09.pdf ; https://www.assurant.com/news-insights/infographics/q1-trade-in-upgrade-data-trends | 2026-09-09 / 2026 | strong |
| Plans: AT&T/Verizon 36 mo; T-Mobile phones 24 mo; early payoff or leaving forfeits remaining promo credits | — | https://www.verizon.com/support/device-deals-faqs/ ; https://www.phonearena.com/news/t-mobile-36-months-installments-eips-tablets-watches_id176095 | n.d. / 2025-11 | strong / medium |
| Rivals buy out device balances (T-Mobile Keep & Switch, up to $800/line; new accounts only since 2026-07-09) | $800/line | https://www.t-mobile.com/support/new-to-tmobile/keep-and-switch ; https://www.tmonews.com/2026/07/t-mobile-restricts-switcher-promos-as-migration-problems-surface/ | n.d. / 2026-07 | strong / medium |
| Q4 seasonality (launches, holidays) | T-Mobile Q4'25 phone churn 1.02% vs FY 0.93% | https://www.t-mobile.com/news/business/t-mobile-q4-2025-earnings | 2026-02 | strong |

**Read:** with phones kept 3.5-4 years (Verizon: ~44 months) on 2-3 year plans, customers sit paid-off and credit-free for months. The real lock-in is **remaining promo credits**, not the device balance (rivals buy out balances). That supports `months_to_payoff`, `remaining_promo_credit`, and a pre-payoff offer window. There is **no public data** on how big the payoff churn spike is, so ours is an assumption (relevant to `LOCK_CUT` 0.50 and `FAMILY_UPGRADE_ENDING_MONTHS` 2). The simulation ignores Q4 seasonality; say so.

### 4e. Explainability & compliance (not legal advice)
- **CPNI basics.** Using customer data (CPNI) to market within service categories the customer already buys needs no approval (47 CFR 64.2005(a)). Carriers **may not use CPNI to track customers who call competitors** (64.2005(b)(2)). https://www.law.cornell.edu/cfr/text/47/64.2005 — strong.
- **Port-out information can't drive retention.** The FCC (2008) found Verizon violated 47 U.S.C. §222(b) by using carrier-change and porting information for retention marketing. Upheld in *Verizon California v. FCC*, 555 F.3d 270 (D.C. Cir., 2009-02-10). https://storage.courtlistener.com/pdf/2009/02/10/Verizon_California_Inc._v._FCC.pdf — strong.
  - **⚠ Risk in our code:** `PORT_OUT_ALWAYS_CONTACT = True` (`harness/offers.py` line 113) forces a contact on any `port_out_inquiry`, and `port_out_inquiry` is also a churn-model feature (`model_a.py`, `churn_features.py`). The case concerned porting requests that arrive from the *new* carrier. A customer asking us about porting is a grey area, but the safe call is to turn the setting off by default, or to drop the feature and the trigger. Also confirm `competitor_research_score` isn't built from tracking calls to competitors.
- **Enforcement is real.** On 2024-04-29 the FCC fined the carriers about $200M (T-Mobile $80.08M) for sharing location data under §222. https://www.fcc.gov/document/fcc-fines-largest-wireless-carriers-sharing-location-data — strong.
- **Data we deliberately exclude:** port-out and porting signals, calls to competitors, location, and protected attributes or proxies (age, sex, race, ZIP-as-proxy; Reg B prohibited bases). Put this in a slide box.
- **Reason-code standard (Reg B, used as an analogy).** Reasons must describe the factors *actually scored*, be specific, and number "more than four… not likely to be helpful." Accepted method: rank the factors where the customer is furthest from average, which is the same as LR coefficient × (x − mean). https://www.law.cornell.edu/cfr/text/12/appendix-Supplement_I_to_part_1002 — strong. (CFPB Circular 2022-03 was **withdrawn 2025-05-12**; don't cite it as current.)
- **Explanations raise acceptance even when the AI is wrong.** Bansal et al., CHI 2021, n = 1,626, https://dl.acm.org/doi/10.1145/3411764.3445717 — strong. So reasons must be true contributions, shown with EV and a "do nothing" option.
- **People use algorithms more when they can adjust them.** Dietvorst et al., *Mgmt Sci* 2018, https://doi.org/10.1287/mnsc.2016.2643 — strong. Give agents accept / swap / skip with a logged reason.
- **Not applicable:** EU AI Act Art. 86 (retention marketing isn't high-risk) and Art. 50 (no chatbot/LLM in our product). https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-86 — strong.

## 5. Round 3: US market & retention vs upsell
*Researched 2026-10-17 (PDT). Full notes: `research-notes/notes_{market,upsell}.md`.*

**Bottom line**
1. **Saturated market.** 98% of US adults own a cellphone. Industry phone net adds are shrinking toward ~7.9M (2026 forecast), and cable takes about ⅓-½ of them, so incumbent gains mostly come from rivals.
2. **Base upsell is a small lever.** Big-3 ARPA grows ~2%/yr, much of it from fees and price moves. T-Mobile's premium mix comes mainly from *new* accounts.
3. **Blunt price or plan pushes cost churn.** Verizon's CEO blames past price hikes for churn, and T-Mobile guided "temporary elevated" churn from its forced plan migration.
4. **"Buys more → stays longer" is mostly selection.** Cross-buying follows loyalty rather than causing it. Cross-selling high-service customers can lose money, and adding a cross-sell to a service contact erodes its churn benefit.
5. **So: retention first.** Upsell only where it lowers churn risk (e.g., home-internet bundles; Prince & Greenstein found bundling cut churn even after addressing selection). Default to do-nothing or a light touch for at-risk accounts. Verizon's 2026 "targeted retention" pivot is essentially our EV engine.

| Figure | Number | Source | Date | Strength |
|---|---|---|---|---|
| US adult cellphone / smartphone ownership | 98% / 91% | https://www.pewresearch.org/internet/fact-sheet/mobile/ | survey date not captured | strong |
| Industry postpaid phone net adds trend | ~8.7M (2023 est.) → ~8.4M (2025 fcst) → **~7.9M (2026 fcst)**; "the pool of potential subscribers declines" | https://www.fierce-network.com/wireless/t-mobile-expected-retain-lead-q4-phone-net-adds (2024-01-12); https://telecomreseller.com/2025/07/17/u-s-wireless-industry-connecting-in-2025-with-risks-on-the-rise-in-2026/ (S&P, 2025-07-16) | 2024-25 | medium (analyst definitions differ) |
| Cable share of industry postpaid phone net adds | **45%** in 2025 Q1-Q3 (Recon); quarterly 33-58% (MoffettNathanson); Q2'26 cable +904K lines vs AT&T + Verizon 616K phones | https://www.lightreading.com/wireless/the-great-convergence-the-state-of-u-s-wireless-competition ; https://www.lightreading.com/5g/us-cable-mobile-net-adds-hold-steady-again-in-q4 (2026-03-24); https://mvnoplanet.com/us-mvno-scorecard-q2-2026/ | 2025-26 | medium (cable lines include non-phones) |
| T-Mobile ARPA growth drivers | $152.91, +2%, "primarily" from fee revenue (tax-and-fee-exclusive plans) and more customers per account; offset by promotions | https://www.sec.gov/Archives/edgar/data/1283699/000128369926000100/tmus06302026ex992.htm | 2026-07-23 | strong |
| T-Mobile premium mix | 60%+ of new accounts choose premium plans | https://fiscal.ai/company/NASDAQ_TMUS/investor-relations/Q2-2026/ | 2026-07-23 | medium |
| Verizon 2025 growth = price, not volume | ARPA +2.0% vs phone connections +0.4% (our arithmetic on filing inputs) | https://www.sec.gov/Archives/edgar/data/732712/000073271226000003/a2025q4exhibit99.htm | 2026-01 | strong inputs / derived |
| AT&T postpaid upgrade rate (quarterly) | FY 15.6% (2023), 14.0% (2024), 15.6% (2025); 1Q26 3.5%; Q4 peak ~4.6-4.7% | https://investors.att.com/~/media/Files/A/ATT-IR-V2/financial-reports/quarterly-earnings/2026/1Q-2026/T_1Q26_Trending_Schedule.pdf | 2026-04 | strong |
| Verizon retail postpaid upgrade rate | 2.8 / 3.6 / 3.3 / 4.4% (2025 Q1-Q4); 3.0 / 2.6% (1Q26 / 2Q26); 2Q26 upgrade volumes down ~27% | https://www.verizon.com/about/sites/default/files/2026-07/vz_2q2026_foi_072426.pdf ; https://www.verizon.com/about/sites/default/files/2026-08/vz_2q2026_transcript_072426rm.pdf | 2026-07-24 | strong |
| Verizon upgrade cycle | ~**44 months** (+2 mo YoY); "not every problem needs four free handsets"; upgrades down >20% while churn fell 5 bp | https://www.verizon.com/about/sites/default/files/2026-09/vz-citi_transcript_2026-09-09.pdf | 2026-09-09 | strong |
| Reinartz, Thomas & Bascoul, *J. Interactive Mktg* 22(1) | "cross-buying is a consequence and not an antecedent of behavioral loyalty" | https://doi.org/10.1002/dir.20106 | 2008-02 | medium-strong (abstract; not telecom) |
| Shah, Kumar, Qu & Chen, *J. Marketing* 76(3) | 10-35% of cross-buyers are unprofitable and account for 39-88% of customer losses; heavy service requesters get *more* unprofitable | https://doi.org/10.1509/jm.10.0445 | 2012-05 | strong (abstract; not telecom) |
| Becker, Spann & Barrot, *J. Service Research* | telecom field experiment: proactive service contact cuts churn; adding a cross-sell raises suspicion of motives and erodes the benefit | https://doi.org/10.1177/1094670519883347 | 2020 (online 2019-11) | medium (abstract; arm-level numbers unverified) |
| Prince & Greenstein, *JEMS* 23(4) | bundling reduced churn for phone, TV and broadband after addressing selection | https://doi.org/10.1111/jems.12073 | 2014 | medium (summary; cable, not wireless) |
| Verizon CEO Schulman: retention first | "at least half, if not more than half, of our net adds are going to come from improvements in churn"; "we will not rely on empty across-the-board price increases"; acquisition + retention cost down ~35% (Mar vs end of Q4) via micro-segmentation; "Not every retention is going to be a free handset" | https://www.verizon.com/about/sites/default/files/2026-06/vz_1q26_transcript_042726rm.pdf | 2026-04-27 | medium-strong (company transcript) |
| Price-lock / loyalty strategies | T-Mobile 5-year price guarantee (2025-04-22); T-Mobile forced legacy migration up to +$6/line (2026-07); Verizon loyalty program: 3% back, no upgrade fees (2026-06-16); Verizon 3-yr price lock closed to new enrollments 2026-06-16 | https://www.t-mobile.com/news/un-carrier/t-mobile-and-metro-unveil-new-plans-with-more-value-and-a-5-year-price-guarantee ; https://www.cnet.com/tech/mobile/t-mobile-customers-on-old-plans-are-being-pushed-to-new-ones-starting-this-week/ ; https://www.verizon.com/about/news/verizon-puts-customers-first ; https://www.droid-life.com/2026/09/05/verizons-3-year-price-lock-guarantee-is-already-gone/ | 2025-26 | strong / medium / strong / weak |

**For the engine:** don't model upsell as causally cutting churn unless it's labelled as an assumption. Penalize or block upsell for high-risk and 3+-support-call accounts. Simulator upgrade base rate: ~3-4.5% of postpaid subscribers per quarter, peaking in Q4.

## 6. Recommendations
1. **Add a random holdout of 5-10%** of contact-eligible accounts (bigger, 30-50%, for a pilot to learn uplift). Report Qini/uplift curves, not accept rates.
2. **Sensitivity run:** rerun the strategy comparison with all `SAVE_RATE`s cut to ~0.25× (and 0.5×). Show whether "ours" still beats "discount everyone" and "top-10% risk".
3. **Raise `ANNOYANCE` on `right_size`/`variant_switch`** (or add a churn penalty for volatile or declining usage) and revisit `SAME_COVERAGE_RULE`.
4. On the slide, label save rates "simulated; optimistic vs field experiments", LTV "illustrative estimate", and AUC "synthetic; real benchmarks ~0.65-0.77".
5. **Compliance:** set `PORT_OUT_ALWAYS_CONTACT` off by default (or drop `port_out_inquiry` as a feature and trigger), and add a "data we don't use" box.
6. **Account-level value and timing:** value saves per account; add `months_to_payoff` / `remaining_promo_credit` features and a pre-payoff offer window (window length is our assumption).
7. **Uplift-ready logging:** `offer_id`, `assignment_prob`, `holdout_flag`, `reached`, `accepted`, `churned_within_60d`.

## 7. Weak-source / unverified list
- T-Mobile Q2'26 phone churn 0.85%: CFO remark on the call, not in the filing.
- T-Mobile Q1'26 phone churn ~0.94%: our inference from a transcript remark ("+3 bp YoY").
- Save-desk rates, all vendor or undated: Foundever 70% (https://foundever.com/case-studies/u-s-telecoms-provider-surpasses-its-customer-retention-targets-in-just-five-months/); InfiniteWatch 61→73% and ~$8.20 per save (https://infinitewatch.ai/resources/ai-voice-agents-telecom-retention); Oriserve/Airtel 14% blended (https://oriserve.com/customers/case-studies/airtel); Qualfon 9.5→24.9% (https://www.qualfon.com/resources/case-studies/telecom-customer-retention-160-percent-improvement/); AOL 18→44% (https://krisschaefferassociates.com/aol).
- Retention credit sizes: Reddit-sourced press and content farms (Android Authority, Droid Life, PhoneArena, The Money Overview).
- "5-25x acquire vs retain" (HBR 2014, unsourced, not telecom) and "+5% retention → +25-95% profit" (Bain, financial services). **Do not use.**
- CPGA figures are 2004-2005, from before the carriers stopped disclosing them.
- Radcliffe & Surry 2011 and the Optimove holdout guidance are vendor-authored.
- Mailchimp/Ascend2 fatigue survey: marketing messages in general, not telecom retention.
- Round 2: Radcliffe & Simpson 2007 operator cases (vendor white paper); Duke tournament lift range and Cell2Cell AUCs (from search summaries, not verified line by line); Ahn's ~1.7× dropped-call odds (not verified; direction only).
- IBM Telco churn percentages (fictional sample dataset, secondary analyses). Do not quote.
- Verizon converged-churn figures are exec statements (30% as of Q4'25 vs 50% in 2024); AT&T converged churn bps were in graphics and are not quoted.
- Payoff → churn evidence is exec commentary only (no carrier microdata); T-Mobile RDC/trade-in policy details come via leaked docs (Android Authority, PhoneArena).
- Upgrade-cycle figures from Omdia and Counterpoint (report summaries, paywalled); Verizon 2025 quarterly churn series from a search summary.
- Explainability: MSI 20-138 (single-firm working paper), SSRN 7574318 and SSRN 3640862 (working papers; the ~15.8 pt figure is unverified). No public number exists for "explanations raise retention-offer uptake".
- `PORT_OUT_ALWAYS_CONTACT` CPNI risk is our reading of the 2008/2009 rulings, not legal advice.
- Round 3: industry net-add totals (TD Cowen vs S&P definitions conflict); cable-share figures (MoffettNathanson/Recon via press, partly paywalled); Optimum line count (MVNO Planet).
- T-Mobile "~30% of base on premium" (analyst summary, not in the transcript text); AT&T 2Q26 upgrade rate 3.2% (Barclays via aggregator).
- Verizon 3-year price lock ending: confirmed only by Verizon's AI support assistant (Droid Life). T-Mobile "price-hike churn was temporary" is from search summaries.
- Recon Analytics LTV ($1,900 financed vs $1,516 BYOD) and "half wait until device fails" (paywalled report abstract); churncost.com SAC/retention costs (unknown site, **do not use**); BTIG Comcast $1,260 per gross add (2018).
- Becker 2020 arm-level churn numbers and Prince & Greenstein details (abstract/summary only); immigration share of growth (TBR, search summary).

## 8. Further reading & datasets (ranked; free; full notes in research-notes/notes_whitepapers.md)
Strength: A = peer-reviewed, regulator, or primary dataset; B = industry paper or survey; C = consulting or thesis. Our demo data is synthetic, so external numbers are "industry evidence", not our results.
1. [Criteo Uplift dataset](https://ailab.criteo.com/criteo-uplift-prediction-dataset/) + [benchmark paper](https://arxiv.org/abs/2111.10106): ~25M randomized rows. Validate uplift-vs-risk ranking and Qini on real data (A).
2. [Hillstrom MineThatData email test](https://blog.minethatdata.com/2008/03/minethatdata-e-mail-analytics-and-data.html): 64k customers in 3 arms, including no email. A small real "best offer or nothing" check (A).
3. [MegaFon uplift dataset](https://www.uplift-modeling.com/en/latest/api/datasets/fetch_megafon.html): operator-published synthetic telecom uplift data. Precedent for our synthetic approach (B).
4. [Ascarza et al. 2018, retention review](https://evaascarza.com/papers/ascarza_et_al_cns_18_author_copy.pdf): 12-author consensus that at-risk ≠ should-target. Core-thesis citation (A).
5. [LinkedIn email volume, KDD'16](https://www.kdd.org/kdd2016/papers/files/adf0710-guptaA.pdf): send-all drew 45% more unsubscribes and spam reports. Backs our contact cap and annoyance cost (B+).
6. [EMP metric (R pkg)](https://cran.r-project.org/package=EMP) / [TKDE 2013](https://doi.org/10.1109/tkde.2012.50): a profit metric plus the profit-optimal contact share. Report it next to AUC (A).
7. [Profit-driven churn trees](https://arxiv.org/abs/1712.08101): profit-trained models pick different customers than accuracy-trained ones (A).
8. [Booking.com knapsack + uplift](https://arxiv.org/abs/2108.13298): one offer per customer under a budget. Our answer to "what if the budget is capped?" (A-).
9. [E3IR, RecSys'24](https://arxiv.org/abs/2408.11623): state of the art for budget-constrained incentives. Future-work bullet (A-).
10. [Multi-treatment revenue uplift](https://arxiv.org/abs/2101.03336): academic precedent for multi-offer EV choice with explanations (A-).
11. [InterpretML EBM](https://interpret.ml/docs/ebm.html): glass-box model with exact per-feature contributions. Faithfulness check on our reason codes (A-/B).
12. [EconML customer-segmentation case](https://github.com/py-why/EconML): policy tree that explains who gets the offer, built on synthetic data (B).
13. [Ofcom 2021, better deals](https://www.ofcom.org.uk/siteassets/resources/documents/consultations/category-2-6-weeks/130197-helping-consumers-get-better-deals-on-their-broadband/associated-documents/helping-customers-get-better-deals-2021.pdf?v=327229): loyal out-of-contract customers pay £9–10/mo more. "Fair retention" slide (A; open in a browser before quoting).
14. [Ofcom 2019, fair deals](https://www.ofcom.org.uk/siteassets/resources/documents/phones-telecoms-and-internet/information-for-industry/fairness-for-customers/fairness-for-customers-progress-update-june-2019.pdf?v=324004): overpaying after handset term ends. Supports pro-customer payoff timing (A).
15. [CMA loyalty-penalty super-complaint](https://www.gov.uk/cma-cases/loyalty-penalty-super-complaint): mobile is a named loyalty-penalty market (A).
16. [Ericsson ConsumerLab 2023](https://www.ericsson.com/en/reports-and-papers/consumerlab/5g/reports/5g-value-turning-performance-into-loyalty): ~half of 5G switchers left over network, not price (B, stated intent).
17. [McKinsey 2017, telecom churn](https://www.mckinsey.com/industries/technology-media-and-telecommunications/our-insights/reducing-churn-in-telecom-through-advanced-analytics): offer library plus microsegments, 10–15% churn cut (C, self-reported).
18. [BCRLSP offline RL promotions](https://arxiv.org/abs/2207.07790): sequential retention offers under a per-period budget. Post-hackathon step (B+).
19. [RecSim (Google)](https://arxiv.org/abs/1909.04847): precedent for comparing strategies in a simulator (A-).
20. [Guelman et al., uplift RF for insurance retention](http://ub.edu/rfa/research/WP/UBriskcenterWP201406.pdf): real non-telecom retention uplift (A-, working-paper version).
21. [Telco bandit retention gym (thesis)](http://hdl.handle.net/10400.14/45824): closest analogue to our simulator. **Unverified** (C).

## 9. Live signals: cited base rates (full table in research-notes/notes_live_signals.md)
Public sources give **direction**, rarely size, and nearly all sizes are survey intent or correlation. **Every effect size in our engine is our assumption**, shown in a sensitivity range. "Real field" = exists in the judge sandbox; everything else is a simulated event.

| Event | Direction | Best public number | Source (strength) | Data |
|---|---|---|---|---|
| Bill shock | ↑ | 17% of US mobile users hit; 84% got no warning. Overage raises switching about as much as equal savings | [FCC white paper, Oct 2010](https://transition.fcc.gov/stage/Bill-Shock-White-Paper.pdf) (A); [Genakos et al. 2023](https://researchonline.lse.ac.uk/id/eprint/121294/1/dp1939.pdf) (A-) | real field: `billing_history` |
| Network problem / dropped calls | ↑ | Dropped calls raise churn (Ahn 2006). T-Mobile leavers had 3x more no-signal time. 24% with >12 problems/100 "definitely will" switch | [Ahn et al. 2006](https://doi.org/10.1016/j.telpol.2006.09.006) (A); [Opensignal, Oct 2022](https://insights.opensignal.com/2022/10/20/how-mobile-network-experience-affects-churn-in-us-wireless-carriers) (B); [J.D. Power 2016](https://www.jdpower.com/business/press-releases/2016-us-wireless-network-quality-performance-study-volume-2/) (B, intent) | simulated |
| Price-change notice | ↑ (size disputed) | Verizon: "only 2 basis points of churn" from a large Q1'24 hike. Its 2026 CEO blames "blunt price increases". T-Mobile guided elevated Q3'26 churn | [VZ, May 2024](https://www.verizon.com/about/sites/default/files/2024-05/MN_Conference_Transcript_051424.pdf) (A-, exec); [VZ 1Q26, Apr 2026](https://www.verizon.com/about/sites/default/files/2026-06/vz_1q26_transcript_042726rm.pdf) (A-) | simulated |
| Device payoff month | ↑ after payoff | AT&T: churn +14 bps YoY, partly from customers "reaching the end of device financing periods" | [AT&T CFO via PhoneArena, Oct 2025](https://www.phonearena.com/news/hidden-in-its-q3-report-is-news-that-could-lead-to-big-problems-at-at-t_id175350) (A-, exec) | real field: `lines.financing_months_remaining` |
| Promo/credit ending | ↑ | Promo expiry is a top FCC bill-shock cause. Ofcom: out-of-contract customers pay £9–10/mo more | FCC 2010 (A); Ofcom 2021, §8 #13 (A) | simulated (no promo end dates in sandbox) |
| Data cap ≥90% / throttled | weak | Throttling: "no evidence" US subscribers change behavior | [Bauner & Espín 2023](https://doi.org/10.1016/j.telpol.2023.102665) (A) | simulated; treat as an upsell moment, not churn |
| Unresolved / high-effort support | ↑ (largest gap) | 41% of high-effort resolvers "definitely will" switch vs 5% when easy | [J.D. Power 2017](https://www.jdpower.com/business/press-releases/us-wireless-customer-care-full-service-performance-study/) (B, intent) | real field: `support_interactions` (re-score; don't double-count) |
| Move / address change | ↑ | Canada: 11% switched cellphone provider in a year; 14% of them cited a move or life change | [Competition Bureau Canada, 2020](https://competition-bureau.canada.ca/en/how-we-foster-competition/promotion-and-advocacy/advocacy-promoting-benefits-competition/consumer-switching-behaviour) (A-) | simulated |
| Competitor promo in market | ↑ | 21% of Canadian cellphone switchers cited a promo and 44% price. Verizon blamed Q4'25 churn partly on competition | Competition Bureau Canada (A-); [VZ 4Q25](https://www.verizon.com/about/sites/default/files/2026-02/vz_4q25_transcript_013026.pdf) (A-) | simulated; regional multiplier |

Accessed 2026-10-17. Caution: answering bill shock with a cheaper-plan nudge can backfire (Ascarza et al. JMR 2016: churn rose from 6% to 10%; §4a).

## 10. Customer-advocate evidence (Fair Bill Receipt)
Thesis: the carrier tells customers when they're overpaying, says "don't upgrade yet," and shows a receipt of money saved. Below is what public evidence supports. Full notes: `research-notes/notes_trust.md`. Strength: A = peer-reviewed or regulator evaluation; B = official statement without an outcome. Accessed 2026-10-17.

| Claim | Number | Source (date) | Strength |
|---|---|---|---|
| Telling customers their best deal mostly made them **re-sign, not leave** (UK broadband) | Out-of-contract share fell from 40% (8.7M) to 35% (7.4M), Sep 2019 → Sep 2020, "largely driven by... re-contracting with their existing provider, rather than switching" | [Ofcom review, Nov 2021](https://www.ofcom.org.uk/siteassets/resources/documents/consultations/category-2-6-weeks/130197-helping-consumers-get-better-deals-on-their-broadband/associated-documents/helping-customers-get-better-deals-2021.pdf) | A |
| End-of-contract alerts raised re-signing (broadband) | +8–13 pp by provider (Plusnet +13, BT/EE/Virgin ~+10); some customers saved >£110/yr | [Ofcom, 2022](https://www.ofcom.org.uk/phones-and-broadband/saving-money/end-of-contract-notifications-driving-better-deals-for-customers) | A |
| **Mobile is weaker**: annual best-tariff notices lifted re-signing and switching; end-of-contract notices were "small and generally mixed" for re-signing and "slightly negative for switching" (varies by provider, about −8.6 to +11.9 pp) | see table 3B | [Ofcom mobile ex-post evaluation, 2024](https://www.ofcom.org.uk/siteassets/resources/documents/consultations/category-2-6-weeks/130197-helping-consumers-get-better-deals-on-their-broadband/ex-post-evaluation/ex-post-evaulation-ecn-2024.pdf) | A |
| What the rule requires (Ofcom GC C1, from 15 Feb 2020) | Alert 10–40 days before contract end showing the post-contract price **and the provider's best tariffs, including new-customer prices**, plus a yearly reminder while out of contract | [Ofcom statement, 2019](https://www.ofcom.org.uk/siteassets/resources/documents/consultations/category-2-6-weeks/130197-helping-consumers-get-better-deals-on-their-broadband/ecn-consultation-and-statement/statement-helping-consumers-get-better-deals.pdf) | A |
| **Backfire risk**: a cheaper-plan recommendation raised churn (randomized, ~65k wireless customers) | 3-month churn 10% treated vs 6% control. Mechanism: it **lowered inertia** and **made past usage and overpaying salient**. Hardest hit: customers with **high usage variability and steeply falling usage** | [Ascarza, Iyengar & Schleicher, JMR 2016](https://journals.sagepub.com/doi/10.1509/jmr.13.0483) ([PDF](https://evaascarza.com/papers/ascarza_iyengar_schleicher_16.pdf)) | A |
| Target by response to the offer, not by risk | Highest-risk customers are not the best targets; uplift targeting beat risk targeting in two field experiments | [Ascarza, JMR 2018](https://doi.org/10.1509/jmr.16.0163) | A |
| Counterpoint on real telecom data (Orange Belgium, randomized, 11,896 customers, 2020): a plain churn model scored ≥ uplift models | AUUC 0.26% (outcome RF) vs 0.25% (T-learner) vs 0.19% (uplift RF), but SDs are ±0.4–0.5, so **not separable**. Treated churn 3.4% vs control 3.6% | [Verhelst, Mercier, Shrestha & Bontempi, arXiv Dec 2023](https://arxiv.org/abs/2312.07206) | A- (preprint; Orange Belgium co-author) |
| Uplift beat churn prediction on profit (**financial-industry** case, not telecom) | MPU measure | [Devriendt, Berrevoets & Verbeke, Inf. Sci. 2021](https://doi.org/10.1016/j.ins.2019.12.075) | A |
| "Warn before the fee" alerts cut customer charges (UK banks, >1M customers) | Auto-enrolled unarranged-overdraft alerts cut charges by **25%** and unpaid-item alerts by 21–24% (OP36). Just-in-time alerts −13–18% and low-balance warnings weak (OP40). **No "alert fatigue"** | [FCA OP36](https://www.fca.org.uk/publications/occasional-papers/occasional-paper-no-36-sending-out-sms-impact-automatically-enrolling-consumers-overdraft-alerts); [FCA OP40, Jul 2018](https://www.fca.org.uk/publications/occasional-papers/occasional-paper-no-40-time-act-field-experiment-overdraft-alerts) | A (measures money saved, not loyalty) |
| Netflix cancelled inactive paid accounts | <0.5% of members ("a few hundred thousand"). **No retention or trust outcome published** | [Netflix, 21 May 2020](https://about.netflix.com/en/news/helping-members-who-havent-been-watching-cancel) | B |

**How we use it:** pitch the receipt as the UK-style "here's your best deal" notice, which in broadband mostly produced re-signing. Avoid the Ascarza backfire by suppressing cheaper-plan nudges for customers whose usage is volatile or falling, and by choosing who to contact by modeled response rather than risk alone.

**Do not claim:**
- That any company measured a **trust or retention lift** from telling customers to spend less (none found; Netflix published no outcome; FCA measured fees, not loyalty).
- That best-tariff notices reduce **mobile** churn (Ofcom 2024: small and mixed).
- That uplift models are proven better than churn models in telecom (Orange Belgium: tie or worse, within noise).
- That a US carrier today proactively flags overpaying (not verified; Ascarza 2016 only mentions Verizon, AT&T and Vodafone plan recommendations at the time).
- Any trust → churn number from J.D. Power or ACSI (not verified).

## 11. Plan-switch acceptance (replaces unsourced 45%)
`harness/offers.py` currently sets `CONFIG["P_ACCEPT"]["right_size"] = 0.45`, with no source. Randomized public evidence puts acceptance far lower. Full table: `research-notes/notes_trust.md` §7. Accessed 2026-10-17.

| Setting | Treated vs control | Source (date) | Strength |
|---|---|---|---|
| Wireless operator, phone call recommending a money-saving plan + $15/mo credit for 3 months (54,089 treated) | **1.5% accepted** (828). Any plan change in 3 mo: 9.59% vs 6.54% | [Ascarza, Iyengar & Schleicher, JMR Feb 2016](https://evaascarza.com/papers/ascarza_iyengar_schleicher_16.pdf) | A |
| UK energy, Cheaper Market Offers Letter (RCT, 137,876) | 2.4–3.4% vs 1.0% switched (30 days) | [Ofgem, Nov 2017](https://www.ofgem.gov.uk/sites/default/files/docs/2017/11/cmol_report_0.pdf) | A |
| UK energy, cheaper-offer letter + reminder | 6.8–7.5% vs 2.9% | [Ofgem, Sep 2019](https://www.ofgem.gov.uk/sites/default/files/docs/2019/09/cmoc_report_final_updated_template_0.pdf) | A |
| UK energy, on default tariff 3+ yrs | 12.1–13.4% vs 6.8% (14 weeks) | [Ofgem, Nov 2017](https://www.ofgem.gov.uk/sites/default/files/docs/2017/11/small_scale_database_trial_paper_pdf.pdf) | A |
| UK broadband, end-of-contract notices | 62% vs 47% re-signed or switched **at contract end**: any action at a natural decision point, *not* acceptance of a single offer | [Ofcom, Nov 2021](https://www.ofcom.org.uk/siteassets/resources/documents/consultations/category-2-6-weeks/130197-helping-consumers-get-better-deals-on-their-broadband/associated-documents/helping-customers-get-better-deals-2021.pdf) | A (before/after) |

**Recommendation:** set `right_size` acceptance to a **3% base (range 2–5%)** with a **sensitivity of up to 13%**. Apply a timing bump only at contract end or device payoff (Ofcom: +8–15 pp at contract end). No public source supports 45%. Caveat: Ascarza's plans saved money by cutting overage, and Ofgem's are energy, not telecom.

**Synthetic implication (our 5,042 synthetic accounts; all figures synthetic):** 682 accounts are right-size-eligible, worth about **$450/mo at 3%** and about **$1,900/mo at 13%**, against a **$14,830/mo ceiling** if everyone accepted.

## 12. T-Mobile-side value and hidden-value messaging
David's ask: show what each offer is worth **to T-Mobile** (churn avoided × account value − revenue given up − contact cost), and add a "hidden value" play (remind customers of perks they already pay for). Full notes: `research-notes/notes_hidden_value.md`. Accessed 2026-10-17. Strength: A = filing / peer-reviewed; B = company or analyst statement; C = weak. All engine numbers stay synthetic.

| Claim | Number | Source (date) | Strength | Maps to `harness/offers.py` |
|---|---|---|---|---|
| T-Mobile postpaid ARPA; account churn (Q2'26) | $152.91/mo; 0.99%/mo | [TMUS Ex 99.1](https://www.sec.gov/Archives/edgar/data/1283699/000128369926000100/tmus06302026ex991.htm) (2026-07-23) | A | account value inputs |
| Core Adj. EBITDA ÷ service revenue (Q2'26, **derived**) | $9.537B ÷ $19.0B ≈ **50%** (≈42% of total revenue) | same filing | A inputs / derived | `SERVICE_MARGIN` 0.50 now has an anchor (upper bound: EBITDA is pre-capex) |
| Account value over our horizon (**derived**) | $152.91 × 0.50 × 24 ≈ **$1.8K**; undiscounted full life (1/0.0099 ≈ 101 mo) ≈ $7.7K | arithmetic | derived | `VALUE_HORIZON_MONTHS` 24 = conservative |
| Analyst net LTV per wireless customer | ≈$1,900 financed vs ≈$1,516 BYOD | [Recon Analytics](https://www.reconanalytics.com/products/demanded-and-hated/) (2025-26) | B | cross-check: matches the 24-mo figure |
| Current acquisition / retention $ per sub | **Not disclosed by any US carrier.** Verizon: CoA + CoR down ~35% via micro-segmentation, no $ | [VZ 1Q26 transcript](https://www.verizon.com/about/sites/default/files/2026-06/vz_1q26_transcript_042726rm.pdf) (2026-04-27) | A (statement) | none; old CPGA $300-400 (2004-05, §2) |
| "5-25x cheaper to retain" | Traced to [HBR, Gallo, 2014-10-29](https://hbr.org/2014/10/the-value-of-keeping-the-right-customers): "depending on which study you believe", **no study named** | — | **C: do not use** | — |
| Cost of a live support contact vs self-service | **$8.01 vs $0.10** (2019 poll); newer median **$13.50 vs $1.84** | [Gartner 2019-09-25](https://www.gartner.com/en/newsroom/press-releases/2019-09-25-gartner-says-only-9--of-customers-report-solving-thei); [Gartner benchmark abstract](https://www.gartner.com/en/documents/5164231) (~2024) | A- / B | `FIX_FIRST_CALLBACK_COST` $15 = plausible (≈1-2 assisted contacts); `CHECK_IN_COST` $2 = between self-service and live; perk reminder in-app ≈ $0.10-1.84 |
| ContactBabel $7.16 per inbound call | relayed by secondary sites; not in the free PDF | ContactBabel 2025 guide | C (unverified) | don't cite |
| Perk-salience RCT in telecom (35k Canadian mobile subs, 12 mo): "perceived value" treatment **no causal effect** on satisfaction; **fewer marketing messages** reduced frustration and, with a discount, raised loyalty | [McKenzie, U. Reading thesis](https://centaur.reading.ac.uk/115294/1/McKenzie_thesis.pdf) (RCT 2019-20) | B- (thesis) | **null**: reminders aren't free; cap frequency |
| Salience can backfire: "you could save" outreach raised churn 6% → 10% | [Ascarza et al., JMR 2016](https://doi.org/10.1509/jmr.13.0483) | A | **negative**: no price/bill framing in a perk reminder |
| Non-price "reminder" messages beat price-savings messages on subscription sign-up **and retention** (RCT, retailer) | no effect sizes in abstract | [EMAC 2025](https://proceedings.emac-online.org/pdfs/A2025-126023.pdf) | B- | supports value framing over discounts |
| Bundled streaming retains better | 59% 12-mo survival (Disney+/Hulu/Max bundle), +4 pts vs Netflix alone, +28 vs components | [Antenna, Mar 2026](https://www.antenna.live/insights/the-power-of-the-pack-bundling-and-retention) | B (selection, not causal) | supports perk *use* as a stickiness signal, not a reminder effect |
| T-Mobile perk usage | ~40M members ever redeemed Tuesdays (since 2016); 60M people use "benefits on Us" | [T-Mobile newsroom, 2026-06-02](https://www.t-mobile.com/news/un-carrier/t-mobile-tuesdays-turns-10-celebrating-the-weekly-perks-millions-love) | B (cumulative; no active rate) | — |
| Share of customers unaware of included perks | **No credible current number found** | — | — | don't claim one |
| T-Mobile stated perk values (retail, not T-Mobile's cost) | Netflix $107/yr (one page variant: $95), Apple TV $119/yr value ($3/mo on More/Beyond), Hulu $143/yr (Beyond); Beyond "built-in benefits worth $650" yr 1; Magenta Status "more than $1,500/yr" | [t-mobile.com/benefits](https://www.t-mobile.com/benefits); [newsroom 2026-08-04](https://www.t-mobile.com/news/un-carrier/eip-flex-36); [Magenta Status 2024-02-07](https://www.t-mobile.com/news/un-carrier/magenta-status) | B (marketing) | message copy (sandbox perk codes stay authoritative) |

**Unsourced constants and suggested replacements:**
- `SAVE_RATE.perk_reminder` 0.08 / 0.03: **no evidence for 8%**. Use **0.02 on-target (range 0-0.05), 0.01 off-target**, below field retention-offer effects (~5-15% relative, §10) because there's no incentive. Add a sensitivity row at 0 and at −0.01 for volatile-usage / bill-shocked accounts (Ascarza backfire).
- perk_reminder cost `0.0`: set ≈ **$0.50** (in-app/SMS; Gartner self-service $0.10-1.84). Keep `ANNOYANCE` $2.
- `SERVICE_MARGIN` 0.50: now **anchored** (TMUS EBITDA/service revenue ≈ 50%), label "upper bound, derived".
- `CHECK_IN_COST` $2 / `FIX_FIRST_CALLBACK_COST` $15: replace "not benchmarked" with the Gartner band ($8-13.50 per assisted contact). A $2 check-in only holds if it's digital.
- `STEP_UP_MARGIN` 0.80, `DEVICE_UPGRADE_MARGIN` $80, `HINT_MARGIN` 0.30: still **unsourced** (no carrier discloses incremental margin). Keep labelled synthetic.

**How to show T-Mobile's side:** per offer, print `p_churn × Δsave × $1.8K (24-mo margin) − p_accept × revenue given up − contact cost`, next to the customer's savings. For a perk reminder the cost line is ~$0.50, so even a 1-2% relative save on a high-risk account is positive, but frequency must be capped (McKenzie) and price wording avoided (Ascarza).

**Do not claim:** that perk reminders are proven to cut churn; any "% of customers don't know their perks" figure; "5-25x"; that T-Mobile's perk retail values are its cost.

### 12a. Home Internet (HSI) take rate: anchors for `P_ACCEPT["home_internet_bundle"]` = 0.04
`harness/offers.py:93` sets 4% with no source. Public anchors below (accessed 2026-10-17). **R** = reported in a filing or by the company; **D** = my arithmetic.

| Anchor | Number | Source (date) | R/D |
|---|---|---|---|
| T-Mobile **postpaid** 5G broadband customers, end Q4'25 | 7,602K (total 5G broadband 8,450K; all broadband incl. fiber 9,447K) | [TMUS Q4'25 Ex 99.2](https://www.sec.gov/Archives/edgar/data/1283699/000128369926000007/tmus12312025ex992.htm) (2026-02-11) | R |
| Postpaid 5G broadband **net** adds by quarter, 2025 | 387 / 427 / 466 / 439K (FY 1,719K) | same | R |
| T-Mobile stopped publishing broadband customer counts in 2026 releases (account metrics only); Q2'26 says ARPA was helped by "continued adoption of 5G broadband" | — | [TMUS Q2'26 Ex 99.2](https://www.sec.gov/Archives/edgar/data/1283699/000128369926000100/tmus06302026ex992.htm) (2026-07-23) | R |
| T-Mobile postpaid accounts | Q1'26 34,439K; Q2'26 34,700K; **Q4'25 ≈ 34,222K** (= 34,439 − 217 Q1 net adds, ignores base adjustments) | [TMUS Q2'26 Ex 99.1](https://www.sec.gov/Archives/edgar/data/1283699/000128369926000100/tmus06302026ex991.htm) | R / D |
| **HSI penetration of postpaid accounts, upper bound** | 7,602 ÷ 34,222 ≈ **22%**. Upper bound: some HSI customers are broadband-only accounts (T-Mobile cites "broadband-only accounts" raising churn) and the overlap with wireless isn't disclosed | arithmetic | D |
| **Quarterly HSI add rate as share of accounts** | Q4'25: 439 ÷ 34,222 ≈ **1.3%**; 2025 average ≈ 430K/qtr ÷ ~32-34M ≈ **1.3-1.4%** | arithmetic | D (net adds, so gross is higher; includes brand-new non-wireless customers, so the existing-wireless attach is lower) |
| Eligibility limits | Available to "70 million households"; "eligibility is determined by the home service address… based off network capacity… can also change as more customers join" | [T-Mobile HSI FAQ](https://www.t-mobile.com/home-internet/faq) (accessed 2026-10-17) | R |
| Capacity model / target | "fallow capacity model"; target 15M 5G broadband customers by end-2030 (was 12M by 2028) | [T-Mobile CMD update](https://www.t-mobile.com/news/business/t-mobile-capital-markets-day-update-feb-2026) (2026-02-11) | R |
| Waitlist | ">1 million households on a waiting list" at one point | [telecomtrendwatch](https://telecomtrendwatch.com/unpacking-t-mobiles-expansion-strategy-from-network-growth-to-fiber-acquisitions/) | **weak** (blog, undated) |
| Verizon: broadband customers who also have mobility | **58%** of 17.1M (≈9.9M, D); FWA net adds 193K in 2Q26 (6,208K FWA total) vs 126.6M postpaid connections (≈0.15%/qtr, D) | [VZ 2Q26 transcript](https://www.verizon.com/about/sites/default/files/2026-08/vz_2q2026_transcript_072426rm.pdf); [VZ 2Q26 FOI](https://www.verizon.com/about/sites/default/files/2026-07/vz_2q2026_foi_072426.pdf) (2026-07-24) | R / D |
| AT&T convergence | **42.5%** of advanced home-internet households also take AT&T postpaid phone; fixed-wireless net adds 279K in 2Q26, AT&T Internet Air 1,951K total | [AT&T 2Q26 Ex 99.1](https://www.sec.gov/Archives/edgar/data/732717/000073271726000294/t-2q2026exhibit991.htm); [Ex 99.2](https://www.sec.gov/Archives/edgar/data/732717/000073271726000294/t-2q2026exhibit992.htm) (2026-07-22) | R |
| T-Fiber, where launched | "approximately 20% year-one penetration" (of homes passed; fiber, not FWA) | CMD update (above) | R |
| Take rate of a cross-sell **offer contact** to existing mobile customers | **Not published by any carrier or analyst I found** | — | — |

**Recommendation.** Treat 4% as the **top** of the range, not the base. Use **2% per contact per quarter (range 1-4%)**, applied **only to address-eligible accounts**. If the engine can't check eligibility, scale the rate by an assumed eligible share and label it. Reasoning (D): T-Mobile's whole base adds HSI at only ~1.3% of accounts a quarter (net, unprompted plus all marketing, and including new non-wireless customers). A targeted offer to eligible multi-line accounts with no home internet should beat that, but proactive offer take-up in wireless field data is low single digits (Ascarza 2016: 1.5% for a money-saving plan, §11). The 22% penetration and the 42.5-58% peer convergence figures are **stock** levels built over years. They are not per-contact rates and shouldn't be used as one.

## 13. Keep vs upgrade economics
Researched 2026-10-17 (PDT). Full notes are in `research-notes/notes_keep_vs_upgrade.md`. **D** marks our arithmetic on the cited inputs. Engine numbers stay synthetic.

### 13a. PRIORITY: the paid-off-phone trade-in nudge (`P_ACCEPT["device_upgrade"]` 0.15, `DEVICE_UPGRADE_MARGIN` $80; both unsourced)
| Claim | Number | Source (date) | Strength | Maps to `harness/offers.py` |
|---|---|---|---|---|
| T-Mobile postpaid device upgrade rate, whole base, per quarter | 2.8 / 2.5 / 2.7 / **3.8** / 2.8 / **2.6%** (Q1'25 to Q2'26). FY25 ≈ 11.8% (D, all devices) | [TMUS Q2'26 Ex 99.2](https://www.sec.gov/Archives/edgar/data/1283699/000128369926000100/tmus06302026ex992.htm) (2026-07-23) | strong | `P_ACCEPT.device_upgrade` |
| Verizon retail postpaid upgrade rate | **2.6%** 2Q26 (3.6% 2Q25). Equipment revenue −19.7% on "significantly lower upgrade volumes" and less subsidy spending | [VZ 2Q26 Ex 99](https://www.sec.gov/Archives/edgar/data/732712/000073271226000040/a2026q2exhibit99.htm) (2026-07-24) | strong | same |
| AT&T postpaid phone upgrade rate | 3.5% 1Q26; FY25 15.6% | §5 above (2026-04) | strong | same |
| Equipment gross margin (equipment sales − cost of equipment) | **T-Mobile −$1,531M (−43%)** Q2'26, −37% Q1'26, −36% Q2'25. **Verizon −$835M (−17%)** 2Q26. **AT&T −$160M (−3%)** 2Q26 (D) | TMUS Ex 99.2; VZ Ex 99; [AT&T 2Q26 Ex 99.2](https://www.sec.gov/Archives/edgar/data/732717/000073271726000294/t-2q2026exhibit992.htm) | strong inputs / D | `DEVICE_UPGRADE_MARGIN` **wrong sign**: devices sell below cost |
| Upgrading re-locks: new EIP, credits forfeited on early payoff or leaving | policy | [T-Mobile Yearly Upgrade terms](https://www.t-mobile.com/support/plans-features/upgrade-ready-every-year) (accessed 2026-10-17); [Android Authority](https://www.androidauthority.com/t-mobile-bill-credits-policy-goes-live-3454430/) (2024-06-26) | strong / medium | value belongs in `lock_value` (already there), not in margin |
| Phone age at trade-in | iPhone **4.03 yrs** (Q2'26); all devices 3.81 (Q1'26) | [Assurant Q2'26](https://www.assurant.com/news-insights/news_releases/q2-trade-in-upgrade-data-trends) (2026) | medium-strong | upgrade-moment window |
| Share of upgrades that include a trade-in | **No public figure found** | — | gap | don't claim one |

**Recommendation (assumptions, labelled).**
- `DEVICE_UPGRADE_MARGIN`: set to **$0** (sensitivity −$50 / +$80). All three carriers book equipment below cost. The −$50 end is our assumption, because no per-unit loss is disclosed.
- `P_ACCEPT["device_upgrade"]`: set to **0.03 incremental per contact per quarter (range 0.01–0.06)**. The whole base already upgrades at 2.5–3.8% a quarter with no targeted nudge. Paid-off phones upgrade more, but most of those upgrades would happen anyway, and proactive offer take-up in wireless field data is ~1.5% (Ascarza 2016, §11). At 15%, the take rate is ~4–6× the whole-base rate (D).
- In the shipped `offer_candidates.csv` (synthetic), 293 accounts are eligible, mean EV is −$20.53, and the action is chosen 0 times. The +$25.4k item comes from a re-run policy driven by these same two constants. Rerun that policy with these values.

### 13b. Other keep-vs-upgrade economics
| Claim | Number | Source (date) | Strength | Maps to `harness/offers.py` |
|---|---|---|---|---|
| Value of a save, CLV practice | CLV = Σ m·r^t/(1+i)^t. Expected-lifetime (1/churn) CLV "generally overestimates" it. Retention rises with tenure because of heterogeneity, so high-risk customers live far shorter than 1/average churn | [Gupta, Lehmann & Stuart, JMR 2004](https://doi.org/10.1509/jmkr.41.1.7.25084); [Gupta et al., JSR 2006](https://www.anderson.ucla.edu/sites/default/files/documents/areas/fac/marketing/JSR2006%280%29.pdf); [Fader & Hardie, JIM 2007](https://faculty.wharton.upenn.edu/wp-content/uploads/2012/04/Fader_hardie_jim_07.pdf) | strong | `VALUE_HORIZON_MONTHS` 24 cap is justified |
| Account value under alternatives (D; $76.46/mo margin, h 0.99%, 10%/yr discount is our assumption) | flat 24 mo **$1,835** (engine now); survival-weighted 24 mo $1,624; **survival + discount 24 mo $1,478**; 36 mo $2,011; discounted infinite $4.2K; undiscounted 1/h $7.7K | arithmetic on TMUS Q2'26 | D | `value = margin × 24` overstates by ~20% vs $1,478, which matches Recon's $1,516 BYOD (§12) |
| Bundled/converged customers churn less | AT&T: "lowest churn profile and highest lifetime values" (no %); Verizon ~30% lower (§4c) | [AT&T 3Q25 transcript](https://investors.att.com/~/media/Files/A/ATT-IR-V2/financial-reports/quarterly-earnings/2025/3Q-2025/t-usq-transcript-2025-10-22.pdf) (2025-10-22) | strong statement; **selection-biased** | `SAVE_RATE.home_internet_bundle`; keep any causal cut ≤10–20% (assumption) |
| T-Mobile 2024 legacy hike (+$2/+$5/line) | Q2'24 phone churn 0.80%, **+3 bp YoY**. FY24 0.86% "best-ever" | [T-Mobile Q2'24 release](https://www.t-mobile.com/news/business/t-mobile-q2-2024-earnings); [Fierce](https://www.fierce-network.com/wireless/t-mobile-raising-prices-some-older-plans) (2024-05/07) | strong number / medium attribution | price-hike churn term `4.0 × bill_increase_pct` (synthetic) |
| UK mobile price rises: who actually left | aware customers: 59% did nothing, 15% thought about switching, **8% left penalty-free** | [Ofcom quant. summary, mobile](https://www.ofcom.org.uk/siteassets/resources/documents/consultations/category-1-10-weeks/272754-consultation-review-of-inflation-linked-telecoms-price-rises/associated-documents/secondary-documents/inflation-linked-price-rises-summary-of-quantitative-research-findings-mobile?v=330532) (2023) | medium (search summary; PDF blocked; self-report) | bill-increase backfire rule |
| Stated intent vs behaviour | 62% "would leave" (Uswitch/Opinium survey) vs Ofcom's 8% | [Uswitch](https://www.uswitch.com/media-centre/2023/11/broadband-mobiles-85-percent-users-call-mid-contract-price-hikes-unfair/) (2023-11) | **weak: do not use** | — |
| Proactive retention field effect (corrected attribution) | pay-TV at a telecom, intent-to-treat: churn **17.2% → ~15.3% (−1.9 pp ≈ 11% relative, D)** | [Godinho de Matos, Ferreira & Belo, Marketing Science 2018](https://doi.org/10.1287/mksc.2018.1099) (**not Ascarza**) | strong | `SAVE_RATE` field range |
| Field range for relative saves | ≈ **2–11% relative**: Ascarza 2018 ~2–4%, Orange Belgium ~6% (3.6→3.4%), Godinho ~11% (D) | §1, §10 above | strong / D | supports the ~4.5% break-even framing |
| Retention desk sizes / save rates | no new credible source; still vendor-only | §2, §7 | weak | `SAVE_RATE`, credits |

**Engine implications.** (1) The device-upgrade gain should be ~$0 at accounting level, so value upgrades only through re-lock (`lock_value`) and any plan step-up. (2) A save is worth ~$1.5K (survival-weighted and discounted), not $1.8K. Run a sensitivity at $1.5K and $1.8K. (3) Treat carrier "bundled customers churn X% less" figures as selection, not effect.

**Do not claim:** that devices or upgrades are profitable per sale; any trade-in share of upgrades; that bundling or upgrading *causes* the reported churn gaps; survey "would leave" percentages as churn; that the 11% field save is Ascarza's.

## 14. Outreach channel, timing and rules
Researched 2026-10-17 (PDT). Full notes: `research-notes/notes_channels.md`. **D** = my arithmetic. Not legal advice. Engine data stays synthetic, and messages are deterministic templates (no LLM).

### 14a. Channel response and cost (`CHECK_IN_COST` $2, `FIX_FIRST_CALLBACK_COST` $15, `SAVE_RATE`, `P_ACCEPT`)
| Claim | Number | Source (date) | Strength | Maps to `harness/offers.py` |
|---|---|---|---|---|
| Outbound retention **call** at a telecom (pay-TV RCT): who actually gets reached | listed likely churners reached **51%** of the time; **34%** got an offer. Effect of being listed (ITT): churn 17.2% → −1.9 pp | [Godinho de Matos, Ferreira & Belo, *Marketing Science* 2018](https://doi.org/10.1287/mksc.2018.1099) ([author PDF](https://ciencia.ucp.pt/ws/portalfiles/portal/98997623/20590148.pdf)) | strong | new call `REACH` ≈ 0.5. The −1.9 pp already includes the unreached half |
| US adults who don't answer calls from unknown numbers | **80%** (19% answer); n = 10,211, Jul 2020 | [Pew, 2020-12-14](https://www.pewresearch.org/short-reads/2020/12/14/most-americans-dont-answer-cellphone-calls-from-unknown-numbers/) | strong (self-report) | call reach ≤ ~50% is plausible |
| Head-to-head **SMS vs email vs letter** RCT (Rwanda tax authority, 2016) | "low-cost delivery methods like SMS and emails can be highly effective as compared to letters"; arm-level numbers not verified | [Mascagni, Nell & Monkam, ICTD WP58 (2016-11-07)](https://ictd.ac/publication/ictd-wp58/); [EDCC 70(2)](https://doi.org/10.1086/713929) | strong (abstract) / numbers unverified | direction only. Not telecom |
| **Text reminders**, 19 nudges, n = 47,306 | **+5%** average relative lift. Best: "reserved for you", and congruent with the messages patients expect (not surprising, casual or interactive) | [Milkman et al., PNAS 2021](https://doi.org/10.1073/pnas.2101165118) | strong | SMS template style |
| **Text reminders**, 22 nudges, n = 689,693 (Walmart) | **+2.0 pp (6.8%)** average. Best: 2 texts 3 days apart, "waiting for you". Forecasters didn't predict the winner | [Milkman et al., PNAS 2022](https://doi.org/10.1073/pnas.2115126119) | strong | ≤2 touches per offer; A/B test copy |
| App **push** | median direct open ≈ **3%** (90th pct ~8–11%). Android opt-in fell across all percentiles in 2024 (my reading of chart labels) | [Airship 2025 benchmarks](https://growth.airship.com/rs/313-QPJ-195/images/Airship-2025-Push-Notification-Benchmarks-EN.pdf) | **weak (vendor)** | push reach is gated by opt-in |
| Email (telecom) / SMS (retail) engagement | email open 32.5%, click 2.8% (Mailchimp); SMS campaign CTR 12.39%, conversion 0.12% (Omnisend) | [Mailchimp](https://mailchimp.com/resources/email-marketing-benchmarks/); [Omnisend 2026](https://www.omnisend.com/blog/sms-marketing-benchmarks/) | **weak (vendor; opens inflated by Apple Mail privacy)** | none. Don't use these to set save rates |
| Regulator: providers mostly used email for end-of-contract notices; **no systematic engagement difference** by timing, method or content | qualitative | Ofcom 2021 review (§8 #13). PDF behind Cloudflare; from search summaries | medium/weak (not read line by line) | channel may matter less than the offer and its timing |
| **SMS cost**, third-party platform, to a T-Mobile number | $0.0083 + $0.0045 carrier fee = **$0.0128 per segment** (D) | [Twilio US pricing, "current as of October 2026"](https://www.twilio.com/en-us/sms/pricing/us) | medium (list price) | upper bound. T-Mobile's internal cost to text its own subscribers isn't public |
| **Email** / **push** cost | $0.10 per 1,000 emails; FCM push no cost | [Amazon SES](https://aws.amazon.com/ses/pricing/); [Firebase](https://firebase.google.com/products/cloud-messaging) (accessed 2026-10-17) | medium | ≈ $0 |
| Agent contact | $8.01–13.50 per live contact (Gartner, §12). With 51% reach, ~1.96 listed per reached customer (D) | §12; Godinho (above) | medium / D | `FIX_FIRST_CALLBACK_COST` $15 holds |

**Read.** No peer-reviewed telecom study compares SMS, email, push and calls on the *same* retention offer. The only measured telecom channel is the call (51% reach, −1.9 pp ITT). Text-reminder RCTs outside telecom show small gains (~5–7% relative). Sending costs ≤ $0.03 for digital, so a digital contact really costs its annoyance/backfire risk (`ANNOYANCE`), not postage. A `CHECK_IN_COST` of $2 is too high for SMS/app and too low for an agent.

### 14b. Timing (does churn spike at contract or promo end?)
| Claim | Number | Source (date) | Strength | Maps to |
|---|---|---|---|---|
| Churn spike right after a 24-month term (German DSL ISP, ~80k cohort, 36 mo) | month-25 churn **> 7× the 36-month average**; months 25–36 **+60.8%**; months 1–24 −30.4%. Less-satisfied customers leave more at term end | [Becker, Spann & Schulze, *Marketing Letters* 26(4), 2015](https://doi.org/10.1007/s11002-014-9293-2) (author version read) | strong (broadband, Europe) | payoff/term-end trigger; act **before** the end month |
| Same study: incentive contracts attract defaulters | involuntary share of churn 48.1% vs 13.2% | same | strong | big credits can attract the wrong customers |
| Churn jumps after a 3-month intro promo ends (7 services at one telecom) | subscribers "kept the service for the duration of the promotional period, and then discarded it soon after" | [Schweidel, Fader & Bradlow, *J. Marketing* 72(1), 2008](https://doi.org/10.1509/jmkg.72.1.082) ([PDF](https://faculty.wharton.upenn.edu/wp-content/uploads/2007/08/Cohortretention.pdf)) | strong | promo-end trigger (`bill_shock_price_lock`) |
| US payoff-month churn; UK 10–40-day notice window; just-in-time alerts beat early warnings | see §4d, §10 | AT&T CFO; Ofcom GC C1; FCA OP40 | strong | send window 10–40 days before payoff/promo end |
| Bill-date timing for retention offers | **no public evidence found** | — | gap | don't claim a bill-date effect |

### 14c. Rules the engine must respect (not legal advice)
1. **CPNI.** Offers within services the customer already buys need no approval (47 CFR 64.2005(a), §4e). Using CPNI to market other *communications-related* services (e.g., Home Internet to a wireless-only account) needs **opt-out or opt-in** approval. Opt-out means written/electronic notice and a **30-day** wait. Everything else needs **opt-in** ([64.2007](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-B/part-64/subpart-U/section-64.2007), [64.2008](https://www.law.cornell.edu/cfr/text/47/64.2008)). Customers set this in T-Mobile's Privacy Dashboard ([T-Mobile, 2025-06-12](https://www.t-mobile.com/privacy-center/education/phone-privacy)).
2. **TCPA, texts.** Commercial autodialed texts need **written** consent; informational texts can rely on oral consent ([FCC guide](https://www.fcc.gov/consumers/guides/stop-unwanted-robocalls-and-texts)). **Carrier exception:** a carrier needs no additional consent to text its **own subscribers when they aren't charged** (1992, reaffirmed in [FCC 12-21](https://transition.fcc.gov/Daily_Releases/Daily_Business/2012/db0215/FCC-12-21A1.pdf)). The FCC's 2024 FNPRM proposed narrowing it ([FCC 24-24](https://docs.fcc.gov/public/attachments/FCC-24-24A1.pdf)); that isn't final. Honor opt-outs anyway.
3. **Opt-outs.** STOP/QUIT/END/REVOKE/OPT OUT/CANCEL/UNSUBSCRIBE are always valid; honor within **10 business days** ([64.1200(a)(10)](https://www.ecfr.gov/on/2026-03-25/title-47/chapter-I/subchapter-B/part-64/subpart-L), since 2025-04-11). **New order FCC 26-67 (released 2026-10-01, not yet effective):** informational opt-outs can be per category, but **a marketing opt-out still ends all marketing** ([Nixon Peabody, 2026-10-07](https://www.nixonpeabody.com/insights/alerts/2026/10/07/fcc-scraps-revoke-all-and-lets-businesses-pick-how-consumers-opt-out)). Keep service messages free of promos so they stay "informational."
4. **Quiet hours.** Federal: no solicitation before **8 a.m. or after 9 p.m.** in the recipient's local time (64.1200(c)(1)). Plaintiffs apply it to texts ([Benesch](https://www.beneschlaw.com/insight/time-of-day-tcpa-cases-inundate-the-federal-docket/)). Florida and Oklahoma: **8 a.m.–8 p.m.** and **≤3** messages on the same subject per 24 h ([Fla. Stat. 501.616](https://flsenate.gov/Laws/Statutes/2023/501.616)). Engine default: **08:00–20:00 local time**.
5. **CTIA Messaging Principles (May 2023).** Express written consent for promotional texts; a coupon/CTA can make an informational text promotional. The opt-in confirmation states the program, help contact, how to opt out, **frequency** and fees. Honor STOP plus plain-language opt-outs, then send one confirmation and nothing more ([CTIA PDF](https://api.ctia.org/wp-content/uploads/2023/05/230523-CTIA-Messaging-Principles-and-Best-Practices-FINAL.pdf)). The document has **no quiet-hours rule**.

**Q&A answer (one line):** "The engine only offers changes to services the customer already has, skips anyone who opted out of marketing, sends between 8 a.m. and 8 p.m. their local time with STOP on every text, honors opt-outs within 10 business days, and never uses port-out or location data." (Not legal advice.)

### 14d. Framing
| Claim | Number | Source | Strength |
|---|---|---|---|
| Name in the email subject (randomized, millions, 3 firms, including retention emails) | open **+20%** (9.05→10.80%), leads **+31%**, unsubscribes **−17%** | [Sahni, Wheeler & Chintagunta, *Marketing Science* 37(2), 2018](https://doi.org/10.1287/mksc.2017.1066) | strong |
| Loss vs gain framing (meta-analysis, 165 effects, N = 50,780) | **no overall difference** (r = .016); prevention slightly favors gain (r ≈ .03–.05) | [O'Keefe & Jensen 2006](https://doi.org/10.1080/23808985.2006.11679054); [2007](https://doi.org/10.1080/10810730701615198) | strong (not telecom) |
| Ownership wording ("reserved / waiting for you") was the best text | above | Milkman 2021/2022 | strong (health) |
| Making overpaying salient backfired | churn 6% → 10% | Ascarza 2016 (§1) | strong |
| "You're saving $X" receipts in telecom/subscription retention | **no public field evidence found** | — | gap |

**Engine implications.** (1) Per-channel cost: sms $0.02 (≤2 segments, list-price upper bound), email ~$0, app $0, call $8–13.50, with `ANNOYANCE` carrying the real cost. (2) Call `REACH` 0.5. App reach = push opt-in (unknown; sensitivity 0.3–0.7). (3) Gates with no $: marketing opt-out, CPNI approval for cross-category offers (Home Internet), 08:00–20:00 local, ≤1 marketing message per account per 24 h, ≤2 touches per offer. (4) Schedule term-end/payoff offers 10–40 days **before** the date. (5) Template copy: name + their own numbers, a normal account-message tone, "already yours" wording. No loss framing, and no overpaying salience for volatile/declining-usage accounts.

**Do not claim:** that SMS beats email (or any channel ranking) for telecom retention; vendor open/click rates as outcomes; a bill-date timing effect; that savings receipts are proven; that the 8–9 p.m. rule definitely applies to a carrier's own texts, or that the carrier exception definitely exempts them (both unsettled); that FCC 26-67 is already in force; Becker's 7× as a US wireless figure (it's European DSL).

## 15. Family plans and multi-line accounts
Researched 2026-10-17 (PDT). Full notes: `research-notes/notes_family.md`. **D** = my arithmetic on the cited inputs. Engine data stays synthetic. Builds on §4c (converged churn, Verizon 2.95 connections/account, T-Mobile's selection-bias remark) without repeating it.

### 15a. Churn by number of lines
| Claim | Number | Source (date) | Strength | Maps to |
|---|---|---|---|---|
| Single- vs multi-line churn | **No US carrier publishes it** | TMUS / VZ / AT&T filings and transcripts checked | gap | don't quote a gap |
| Share of T-Mobile postpaid **phone lines** on multi-line accounts | **"over 90%"** (CFO); CEO: multi-line accounts are "the thing that's most correlated with CLV" | [TMUS Q4'25 call transcript](https://www.fool.com/earnings/call-transcripts/2026/02/11/t-mobile-tmus-q4-2025-earnings-call-transcript/) (2026-02-11) | medium | account-level scoring (already done) |
| Whole-account vs single-line loss | CEO: a whole account leaving "truly hurts CLV"; someone dropping an idle line "doesn't cause any value loss" | same | medium | value = account, not line |
| T-Mobile 2025 account vs phone churn | account 0.94 / 0.92 / 0.97 / 1.04%; phone 0.91 / 0.90 / 0.89 / 1.02%. Mixed with partial-line drops and broadband-only accounts, so **no line-count gap can be backed out** (D) | [TMUS Q4'25 Ex 99.2](https://www.sec.gov/Archives/edgar/data/1283699/000128369926000007/tmus12312025ex992.htm); [Q2'26 Ex 99.2](https://www.sec.gov/Archives/edgar/data/1283699/000128369926000100/tmus06302026ex992.htm) | strong inputs / D | context |
| "Multiple-line accounts generally have lower churn" (no number). Sievert: most single-line phone customers "tend to buy prepaid" | qualitative | [Fierce Wireless](https://www.fierce-network.com/wireless/carriers-sharpen-focus-family-plans-as-single-line-users-look-to-prepaid) (2017-01-17) | weak (old) / medium (exec quote) | selection warning |
| Verizon tracks ARPA by line-count cohort; has "historically under-indexed" in 1-2-line accounts | no churn number | [VZ at Citi TMT](https://www.verizon.com/about/sites/default/files/2026-09/vz-citi_transcript_2026-09-09.pdf) (2026-09-09) | medium | — |
| **Our sandbox (synthetic, D)** | 40% of 5,042 accounts single-line → ~17% of lines on single-line accounts vs T-Mobile < 10%. `labels.py` gives each extra line −0.15 log-odds (~14% lower odds, exp(−0.15) ≈ 0.86): **an assumption in our data, not a finding** | read-only `lines` table; `harness/labels.py` | D | reweight sensitivity; no circular claims |

### 15b. Value of adding a line
| Claim | Number | Source (date) | Strength | Maps to |
|---|---|---|---|---|
| T-Mobile list price, no AutoPay (Broadband Facts) | More 2.0 **$90 / 150 / 185 / 220 / 255** (1-5 lines); Beyond 2.0 **$105 / 180 / 230 / 280 / 330**; Essentials 2.0 $65 / 100 / 120 / 140 / 160; Essentials 4 Line Offer $120 for 4. **Early termination fee $0** | [t-mobile.com/cell-phone-plans](https://www.t-mobile.com/cell-phone-plans); [Broadband Facts (military page)](https://www.t-mobile.com/cell-phone-plans/military-discount-plans) (accessed 2026-10-17) | strong | sandbox `plans` **match exactly** (checked read-only) |
| Marginal line (D) | More: 2nd +$60, 3rd-5th **+$35**; Beyond +$75, then **+$50**; Essentials +$35, then +$20. More per-line price: $90 → $51 at 5 lines | arithmetic | D | add-a-line value |
| ARPA trend and drivers | $146.22 → **$152.91** (Q1'25 → Q2'26); +2% YoY "primarily" from fee revenue **and "an increase in customers per account"**, partly offset by fiber/UScellular accounts and promotions | [TMUS Q2'26 Ex 99.1](https://www.sec.gov/Archives/edgar/data/1283699/000128369926000100/tmus06302026ex991.htm), Ex 99.2 (2026-07-23) | strong | context |
| Lines per account (D) | Q4'25: 85,594K phones ÷ 34,240K accounts = **2.50 phones/account**; 3.40 connections/account (Q4'24: 2.56 / 3.37). Phone ARPU $50.71 vs ARPA $150.17 | TMUS Q4'25 Ex 99.2 (2026-02-11) | strong inputs / D | calibration |
| Value of one added line (D) | $35 × 0.50 × 19.34 (survival + discount, 24 mo; §13b) ≈ **$338** (More); $50 Beyond line ≈ **$484**. Before promos: 8 of 11 sandbox device credits need a new line ($301-$1,200 over 24-36 mo), which can make the line net negative over 24 months | arithmetic; read-only `promotions` | D | new add-a-line action, if built |

### 15c. Does a line lower churn, or are multi-line customers different?
| Claim | Number | Source (date) | Strength |
|---|---|---|---|
| Causal "add a line → lower churn" estimate | **none public** | — | gap |
| Households coordinate carrier choice: other members' choice outweighs total network size | econometric (UK) | [Birke & Swann, *J. Evol. Econ.* 16(1):65-84](https://ideas.repec.org/a/spr/joevec/v16y2006i1p65-84.html) (2006) | strong (on-net pricing era) |
| Churn is contagious: a defecting contact → **+80% defection hazard** (1M cellular customers, with controls) | +80% | [Nitzan & Libai, *J. Marketing* 75(6):24-38](https://doi.org/10.1509/jm.10.0209) (2011-11) | strong (observational; call network, not households) |
| Retention spillover: randomized campaign (~6,000 prepaid mobile customers); untargeted connections churned less; their effect = **28% of the targets'** (multiplier 1.28) | 1.28 | [Ascarza, Ebbes, Netzer & Danielson, *JMR* 54(3)](https://doi.org/10.1509/jmr.15.0442) ([PDF](https://evaascarza.com/papers/ascarza_ebbes_netzer_danielson_17.pdf)) (2017) | strong (RCT) |
| Selection: financing picks "the young, multi-line, high-income postpaid household" (financing share 37% under $50K → nearly half over $100K) | survey, ~337K interviews | [Recon Analytics, "Demanded and Hated"](https://www.reconanalytics.com/demanded-and-hated/) (2026-07-25) | medium |
| T-Mobile's own selection-bias caution; cross-buying follows loyalty | qualitative | §4c; §5 (Reinartz 2008) | medium / medium-strong |

**Read:** the stickiness mechanism is real (coordination, contagion), but the observed multi-line gap is confounded by who picks family plans. Treat it as correlation. Don't give an add-a-line offer a churn cut unless it's a labelled assumption.

### 15d. Family-plan risks
| Claim | Number | Source (date) | Strength |
|---|---|---|---|
| Account holder leaves → every line goes | qualitative | 15a; §1 #6 | medium/strong |
| A departing member can keep their number at T-Mobile (**Change of Responsibility**) | line active 90 days; new owner 18+, credit check/deposit possible; **service promotions don't transfer**; add-a-line promos break if the line count no longer qualifies; EIP moves once | [T-Mobile Support](https://www.t-mobile.com/support/account/transfer-account-or-line-ownership) (accessed 2026-10-17) | strong |
| T-Mobile's product for the kid going solo: **Student Perks, $30/mo** single line | $30 | [T-Mobile newsroom](https://www.t-mobile.com/news/un-carrier/eip-flex-36) (2026-08-04) | strong (price) |
| When kids leave | 57% of 18-24s live in a parental home (dorms count) vs **16%** of 25-34s | [Census CB24-TPS-110](https://www.census.gov/newsroom/press-releases/2024/families-and-living-arrangements.html) (2024-11-12) | strong |
| Divorce base rate | 2.4 per 1,000 population (672,502; provisional 2023, 45 states + DC) | [CDC/NCHS FastStats](https://www.cdc.gov/nchs/fastats/marriage-divorce.htm) (reviewed 2025-03-17) | strong |
| Partial-line churn rate | **no public number** (T-Mobile stopped reporting line churn in 2026) | — | gap |

**Read:** the risky moment is a line departure: promos tied to line count can break, and contagion raises the others' risk. Our engine has no line-departure signal. The customer-friendly play is "keep them at T-Mobile on their own line," never a hard save.

### 15e. Phone upgrade vs plan upgrade (lock-in only)
David's question: an upgraded **phone** buys lock-in; an upgraded **plan** buys margin.
| Claim | Number | Source (date) | Strength |
|---|---|---|---|
| No contract: ETF $0; the 5-year price guarantee is a price promise, not a lock | $0 | 15b Broadband Facts | strong |
| Phone lock = device plan + monthly promo credits lost on leaving; EIP now 24 or **36** months (EIP Standard 36 / Flex 36 from 2026-08-06); phones sold below cost (−43%, §13a) | 24/36 mo | [newsroom 2026-08-04](https://www.t-mobile.com/news/un-carrier/eip-flex-36); §4d; §13a | strong |
| Churn while paying vs not | financing **~0.7%/mo** while the balance runs; BYOD **~1.4%/mo**; financed blended **0.95%**; ~$1,450 device cost per subsidized customer over life; net LTV ~$1,900 vs $1,516 | Recon Analytics (2026-07-25) | medium (selection-biased) |
| Term-end spike (DSL) and payoff cliff (US exec remarks) | month 25 > 7× average | §14b (Becker 2015); §1 #7 | strong (not US wireless) / strong exec |
| Upward plan switchers churn less (Chinese operator; observational) | direction | [Jin, *JRCS* 66 (2022)](https://ideas.repec.org/a/eee/joreco/v66y2022ics0969698922000078.html) | medium (selection) |

**Lock-in ledger (D; $76.46/mo margin, 0.99%/mo hazard, 10%/yr discount):**
- **Phone upgrade.** Halving hazard over the device term (`LOCK_CUT` 0.50) = **+$89 (24 mo) / +$176 (36 mo)** per accepted upgrade. At Recon's 0.7% rate: +$52 / +$90-101. At 3%/mo risk: +$217 / +$386. T-Mobile pays $150-$1,200 in device credits and sells the phone below cost. It pays only on high-risk accounts with small credits.
- **Plan step-up** (50% margin × 19.34): More→Beyond **+$15/mo (1 line) ≈ $145; +$45 (3 lines) ≈ $435; +$60 (4 lines) ≈ $580**; Essentials→More, 4 lines (+$80) ≈ $774. No device cost, no lock, and affordability risk (§13b).
- **`LOCK_CUT` anchor:** 0.7 vs 1.4 is 50% below a self-selected BYOD group; vs the financed blended 0.95% it's ≈ **26%** (D). Use 0.25 base, 0.50 upper.

**Engine implications (synthetic).** (1) No add-a-line action exists; the 4 Line Offer appears only as a cheaper-variant / right-size target. If one is built: value = marginal line price × 0.50 × 19.34 − promo credit − contact cost, churn effect **0** base. (2) `STEP_UP_MARGIN` 0.80 → 0.50 base (0.80 sensitivity); replace `delta × margin × 24 × (1 − p)` with the survival-and-discount factor (~19.3 at average risk). (3) `P_ACCEPT` `step_up` 0.25 / `family_upgrade` 0.20 and `SAVE_RATE` `step_up` 0.15 / `family_upgrade` 0.18 are unsourced. Suggest ~0.03 acceptance (0.01-0.06, per §11) and ~0 save rate (§5), labelled. (4) `LOCK_CUT` 0.50 → 0.25. (5) Account value already scales with lines (`margin_mo` uses account service revenue); keep it. (6) Add a simulated line-departure / Change-of-Responsibility trigger → "own line at T-Mobile" offer.

**Do not claim:** any "multi-line churns X% less" figure, or that adding a line *causes* lower churn; Recon's 0.7% vs 1.4% as a causal financing effect; that the price guarantee locks customers in; that phone upgrades profit per sale; "90% of **accounts** are multi-line" (it's phone lines); Compete's 2005 "20% churn cut → +30% NPV"; Nitzan & Libai's +80% as a family-plan or causal number; T-Mobile's "two-thirds of students" marketing line.
