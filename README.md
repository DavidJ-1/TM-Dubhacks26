# Retention Console

DubHacks '26, T-Mobile track. A Python console that ranks who is likely to leave, explains why in plain language, and picks one eligible promotion or does nothing.

**All sandbox data is synthetic.** Customers, prices, devices, and promotions come from the T-Mobile hackathon sandbox. Nothing in this repo is a real customer or an official T-Mobile offer.

## Run

```bash
make setup && .venv/bin/streamlit run app/scroll_app.py --server.port 8501
```

On Windows, from the repo root:

```bat
.venv\Scripts\pip install -r requirements.txt -r app/requirements.txt
.venv\Scripts\streamlit run app/scroll_app.py
```

This is the app: the scroll page at <http://localhost:8501> (money shown; add `?money=0` to hide company dollars). `make setup` creates a virtualenv, installs the Python dependencies and clones the judge sandbox if it is not already in `vendor/dubhacks`. `make run` starts the same scroll page.

The older chart page (`app/streamlit_app.py`) is retired; its figures are out of date. The Retention Console (`app/console_app.py`) is still in the repo.

```bash
make test
```

Python 3.11 or newer. The stack is pandas, scikit-learn, and Streamlit. There is no JavaScript frontend.

## Live what-if (this branch)

Open the scroll page and press **Live what-if** (customer #02363). Each **Next event** press adds one scripted event
(app login, dropped call with an open coverage chat, carrier-shopping score rising, asked to move their number); **Reset**
clears it. The risk, the reason that moved and the decision come from `data/live_events/live_events.csv`, precomputed
offline by `scripts/live_events.py`: the same Model A rescoring the app uses, the offer engine rerun on the edited row,
and the do-not-contact guardrail rerun over the whole book with only this customer swapped (save-rate scale frozen, so
no other account moves; the week's 184 messages and dollars stay as they are). Rebuild with
`DUBHACKS_DB=vendor/dubhacks/data/sandbox.db python3 scripts/live_events.py --write` (sandbox opened read-only).

## Where the data comes from

`make setup` clones <https://github.com/mageshkumarj/dubhacks> into `vendor/dubhacks` (gitignored). The console reads `vendor/dubhacks/data/sandbox.db` directly. It does not need the sandbox API process.

The same database backs that repo's FastAPI server (`./run.sh`, docs at `localhost:8000/docs`). This app reimplements the promotion rules in Python so a demo does not depend on a running server or on carts, which the sandbox keeps in memory and wipes on restart.

Override the file with `DUBHACKS_DB=/path/to/sandbox.db` if you already have a copy.

Rules the code follows:

- Money is stored in cents and shown as dollars.
- The dataset is as of 2026-10-01.
- Financing runs 24 months. Upgrade eligibility is 12 or more months owned.
- Trading in a phone that is not paid off charges the remaining balance today.
- Only one device promotion is applied. Three of the 21 promotions are retention offers (`source = stub`).
- The sandbox does not subtract promo savings from cart totals. When we show a net, we subtract that one promo ourselves.
- The trade-in curve is good condition.
- There is no battery health and no future phone release date. Battery is estimated from phone age and labeled as a model. A "wait" that is not the 12-month rule or the remaining installment is labeled as a modeled assumption.
- Support-contact counts are `COUNT(*)` on `support_interactions`. They are not a score we made up.

## What the four screens do

1. **Overview.** Expected 90-day churn on the public sandbox score, for the 5,000 non-persona accounts. Concentration of that expected churn, and the drivers that actually move it (support contacts, competitor research, bill jumps, port-out). Autopay and Home Internet are shown because they barely move.
2. **At-risk queue.** Ranked by Model A, a logistic regression. Selecting an account shows the score plus three reasons to leave and three reasons to stay. Each reason is a coefficient times a standardized value, written out from the real fields.
3. **Next best action.** Model B picks one promotion the account can have with an empty cart (care credit, loyalty credit, or the student credit), or **do nothing** when nothing scores above zero. An upgrade-moment detector (paid off, usage over the cap, phone 36 months or older) adds a separate timing recommendation and at most one device promo.
4. **Projections.** Labeled **Projected, illustrative assumptions**. Sliders for acceptance and upgrade take-up redraw the arithmetic. The offer list does not change, and nothing on this screen is a measured response.

## Models

The sandbox has no observed churn outcomes. Judges score a private model that is not in this repository.

- **Sandbox score** on the Overview is the public reference formula shipped in the judge repo (`support_90d`, negative sentiment, bill increase, competitor research, port-out, tenure, plan misfit). Persona accounts are left out of the population rates.
- **Model A** draws one label per non-persona account from that probability (seed 2026) and fits a standardized logistic regression on those same fields. Holdout AUC is against the draw, not against real churn. Reason codes are the contributions from that fit.
- **Model B** ranks an eligible offer as `risk × fit × 25% acceptance × 24 months of the latest bill − offer cost − $5 contact cost`. The 25% is an assumption used for ranking. Fit is a written rule (a care credit matches frustrated support; it is a poor match for a happy frequent caller or a network complaint with a stable bill). Accounts under a 15% risk floor, near the sandbox base rate, are not offered a credit. Do nothing wins at or below zero.

## Not in this build

- No offer-outcome feedback loop and no retraining on imagined acceptances.
- No scraped or online "what people want to upgrade to" data.
- No simulated before/after presented as a real result. The projection screen is labeled as an assumption.
- Photon messaging is not included. There is no Python send path in this demo.

## Layout

```
app/streamlit_app.py     Streamlit screens
harness/                 load, Model A, offers, upgrade moments, projections
tests/test_engine.py     checks against sandbox.db
vendor/dubhacks/         cloned judge sandbox (not committed)
```

## Secrets

API keys do not belong in this repo. `.env.example` lists names only. The console does not call an external API.
