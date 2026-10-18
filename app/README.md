# Demo UI

All customers are synthetic (judge sandbox + simulated scores).

```bash
pip install -r app/requirements.txt
streamlit run app/streamlit_app.py            # http://localhost:8501
TM_USE_MOCK=1 streamlit run app/streamlit_app.py   # force mock data
```

Data: reads `harness/out/{churn_scores,offers,features,labels}.csv` (LANES.md contracts) and falls back per file to
`app/mock/*.csv` (regenerate with `python app/mock/make_mocks.py`). If `offers.csv` is real but `churn_scores.csv`
isn't, it uses the offer engine's `harness/out/mock_churn_scores.csv` so scores and offers match. Sidebar shows which source is live.

Screens: Insights, Who's at risk this week, Customer card (commerce/customer/live signals, reasons, offer or do nothing,
en/es phone mockup). Messages are deterministic templates in `app/messages.py`.

## Charts
`python app/charts/make_charts.py` regenerates slide-ready 1600x900 PNGs in `app/charts/` from `harness/out/` (also shown on
the in-app **Charts** screen, with a Regenerate button). Model C charts read `harness/model_c_artifacts/` (doubly-robust
policy values, IPW Qini curves) and are final by default; `TM_MODELC_PLACEHOLDER=1` forces placeholders. The learning curve reads
`harness/bench/out/learning_curve_long.csv` (target == churn_90d). The phone mockup shows offers.csv `message_en`/`message_es`
verbatim when present, otherwise the `app/messages.py` templates.
