# RESEARCH: public benchmarks for the churn + offer engine

> **Disclaimer:** our customer data is synthetic and simulated. The figures below are public benchmarks; none of this is real T-Mobile customer data. Compiled 2026-10-17 (PDT). Q2 2026 is the latest reported quarter (Q3 reports: AT&T Oct 21, Verizon Oct 26, T-Mobile Oct 28).

Strength: **strong** = SEC/IR filing or peer-reviewed; **medium** = reputable press, call transcript, or a researcher white paper; **weak** = vendor case study, blog, Reddit-sourced, or undated.

## 1. Top pitch facts (for "Same assumptions, different strategies (simulated)")
1. **High risk ≠ persuadable.** In two field experiments (one at a wireless carrier), the top-risk and top-responsive customers overlapped only ~50% (no better than random). "Half of the retention money is wasted," and targeting by uplift cut churn a further 4.1 and 8.7 pp. Ascarza, *JMR* 55(1), 2018, https://doi.org/10.1509/jmr.16.0163 *(answers "top-10% risk + credit")*
2. **Reaching out can backfire.** In a 65,000-customer wireless field experiment, proactive "switch to a cheaper plan" outreach raised 3-month churn from **6% (control) to 10% (treated)**. Ascarza, Iyengar & Schleicher, *JMR* 53(1):46-60, Feb 2016, https://doi.org/10.1509/jmr.13.0483 *(answers "discount everyone" and over-contacting; this is why "do nothing" can win)*
3. **Even the riskiest barely move.** In Ascarza 2018, the incentive cut churn in the top-risk decile by only **1.6 pp (95.3% → 93.7%)**. https://evaascarza.com/papers/ascarza_18.pdf
4. **Small churn, huge base.** Q2 2026 postpaid churn was **0.99%/mo** (T-Mobile, account level), **0.92%** (Verizon phone) and **0.86%** (AT&T phone). A few basis points matter. SEC filings linked in the table below.
5. *(medium)* At one mobile operator, a churn campaign **raised** churn from 9% to 10%. Targeting only the uplift-selected 30% cut churn to under 8% with 70% less spend. Radcliffe & Surry 2011 (authors sell uplift software), https://stochasticsolutions.com/pdf/sig-based-up-trees.pdf

Not used as headline facts: "5-25x cheaper to retain" (unsourced, not telecom-specific), and the 0.85% T-Mobile Q2'26 phone churn (a CFO remark on the call, not in the filing).

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

## 4. Recommendations
1. **Add a random holdout of 5-10%** of contact-eligible accounts (bigger, 30-50%, for a pilot to learn uplift). Report Qini/uplift curves, not accept rates.
2. **Sensitivity run:** rerun the strategy comparison with all `SAVE_RATE`s cut to ~0.25× (and 0.5×). Show whether "ours" still beats "discount everyone" and "top-10% risk".
3. **Raise `ANNOYANCE` on `right_size`/`variant_switch`** (or add a churn penalty for volatile or declining usage) and revisit `SAME_COVERAGE_RULE`.
4. On the slide, label save rates "simulated; optimistic vs field experiments" and LTV "illustrative estimate".

## 5. Weak-source / unverified list
- T-Mobile Q2'26 phone churn 0.85%: CFO remark on the call, not in the filing.
- T-Mobile Q1'26 phone churn ~0.94%: our inference from a transcript remark ("+3 bp YoY").
- Save-desk rates, all vendor or undated: Foundever 70% (https://foundever.com/case-studies/u-s-telecoms-provider-surpasses-its-customer-retention-targets-in-just-five-months/); InfiniteWatch 61→73% and ~$8.20 per save (https://infinitewatch.ai/resources/ai-voice-agents-telecom-retention); Oriserve/Airtel 14% blended (https://oriserve.com/customers/case-studies/airtel); Qualfon 9.5→24.9% (https://www.qualfon.com/resources/case-studies/telecom-customer-retention-160-percent-improvement/); AOL 18→44% (https://krisschaefferassociates.com/aol).
- Retention credit sizes: Reddit-sourced press and content farms (Android Authority, Droid Life, PhoneArena, The Money Overview).
- "5-25x acquire vs retain" (HBR 2014, unsourced, not telecom) and "+5% retention → +25-95% profit" (Bain, financial services). **Do not use.**
- CPGA figures are 2004-2005, from before the carriers stopped disclosing them.
- Radcliffe & Surry 2011 and the Optimove holdout guidance are vendor-authored.
- Mailchimp/Ascend2 fatigue survey: marketing messages in general, not telecom retention.
