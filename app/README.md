# Demo UI (tm-ui lane)

All customers are synthetic (judge sandbox + simulated scores).

```bash
pip install -r app/requirements.txt
streamlit run app/streamlit_app.py            # http://localhost:8501
TM_USE_MOCK=1 streamlit run app/streamlit_app.py   # force mock data
```

Data: reads `harness/out/{churn_scores,offers,features,labels}.csv` (LANES.md contracts) and falls back per file to
`app/mock/*.csv` (regenerate with `python app/mock/make_mocks.py`). If `offers.csv` is real but `churn_scores.csv`
isn't, it uses tm-offers' `harness/out/mock_churn_scores.csv` so scores and offers match. Sidebar shows which source is live.

Screens: Insights, Who's at risk this week, Customer card (commerce/customer/live signals, reasons, offer or do nothing,
en/es phone mockup). Messages are deterministic templates in `app/messages.py`.
