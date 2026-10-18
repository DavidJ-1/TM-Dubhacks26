# Strategy comparison

**All customers are from the judges' sandbox; none of this is real T-Mobile customer data. Every money figure depends on the save rate it names.**

The strategy table that used to be here described the earlier offer engine and is out of date, so it has been
removed. Rerunning `harness/compare_strategies.py` regenerates it for that earlier engine.

## Current headline (next version of the engine)

At a 10% save rate, our central assumption: of 5,042 accounts scored, 505 are flagged and 184 get a message. Those 184
messages come out +$3,938 ahead, with a 95% range of −$3,186 to +$13,148, an 80% chance of coming out ahead (41% at a
5% save rate), and break-even at a 5.17% save rate. For the other 4,858 accounts, doing nothing wins. Source: the
Devpost draft in `docs/strategy/DEVPOST.md`.

## Churn model score

| measured against | AUC | note |
|---|---:|---|
| the judges' public example model's churn probabilities (out-of-fold) | **0.797** | comparable with the judges' figures; their README puts the best possible at about 0.825 |
| our own stand-in labels (out-of-fold) | 0.853 | not comparable: the labels are built from the same fields the model uses |

Against our own labels, the model puts 62% of leavers in its riskiest 10% (6.2x lift), vs 54% for ranking by support
calls (AUC 0.834) and 10% at random. Recompute the first row with `python scripts/predict.py`.

## Reproducibility (inputs used)

- Input dir: `demo_data`
- offers.csv: `demo_data/offers.csv`, mtime 2026-10-17 21:34:44 PDT, 5,042 rows
