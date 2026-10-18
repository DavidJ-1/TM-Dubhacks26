# demo_data/: precomputed demo outputs (SYNTHETIC)

**All customers and numbers here are synthetic.** They come from the judge sandbox's stub data
(mageshkumarj/dubhacks, opened read-only) plus our simulated labels and enrichment. No real T-Mobile customer data.

`harness/out/` is gitignored, so these are tracked copies of the 5,000-account sandbox run, letting a fresh clone
show real output without rerunning the pipeline. The 50k/250k scaled sets are left out on purpose.

| File | Made by |
|---|---|
| `features.csv` | `harness/features.py` |
| `enrichment.csv` | `harness/enrichment.py` |
| `labels.csv` | `harness/labels.py` |
| `churn_scores.csv` | `harness/churn_model.py` (Model A) |
| `offers.csv`, `line_tradein.csv` | `harness/offers.py` (Model B) |
| `offer_candidates.csv.gz` | `harness/offers.py` (gzipped, ~16 MB raw; `pd.read_csv` reads `.gz` directly) |

## Refresh

Rebuild `harness/out/` (`features.py` → `enrichment.py` → `labels.py` → `churn_model.py` → `offers.py`, with
`DUBHACKS_DB` pointing at the sandbox or the `make setup` clone in `vendor/`), then:

```bash
python demo_data/refresh.py
```
