"""Scroll page: the churn + upsell board as one long 3D scroll (built from the design team's orbit mock).

Run: python -m streamlit run app/scroll_app.py
Data loading and every count live in orbit_data.py and here; orbit_sections.py only draws.
"""
import inspect
import sys
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Churn + upsell board", layout="wide", initial_sidebar_state="collapsed")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import orbit_data as D  # noqa: E402
import orbit_sections as O  # noqa: E402

O.load_css()

# ---- 'Show money': on by default, ?money=0 starts it off. The visible toggle (and keeping ?money in sync) lives in
# the sections module once it ships; until then the URL param alone decides. Off = show_money=False to every render_*
# that accepts it, plus company-dollar fields stripped from the data as a backstop.
SHOW_MONEY = str(st.query_params.get("money", "1")).strip() != "0"
if hasattr(O, "show_money_state"):  # sections-module helper, if present, owns the toggle state
    try:
        SHOW_MONEY = bool(O.show_money_state())
    except Exception:  # noqa: BLE001
        pass


def _call(fn, *args, **kw):
    """Call a render_* with show_money= only if its signature accepts it."""
    if "show_money" in inspect.signature(fn).parameters:
        kw["show_money"] = SHOW_MONEY
    return fn(*args, **kw)


@st.cache_data(show_spinner=False)
def frame():
    # flag cut = 90th percentile of risk over regular accounts, applied to all accounts (orbit_frame's flag_share=0.10)
    return D.apply_offer_text(O.orbit_frame(D.merged(), D.outreach(), D.receipts(), flag_share=0.10))


df = frame()
_call(O.render_hero, df)

dec = D.offer_decisions(df)   # next-version decisions (offers team's decisions.csv; ledger fallback)

# ---- one selected customer. The dropdown, a quick pick, a table row, and (later) a chart dot all write
# st.session_state["acc"] through D.apply_shared_selection, before the widgets are created.
st.session_state.setdefault("acc", f"{D.PERSONA}38")
if "customer_pick" not in st.session_state:
    D.apply_shared_selection(st.session_state, st.session_state["acc"])
pending = st.session_state.pop("_pending_acc", None)
if pending and pending in set(df.account_id):
    D.apply_shared_selection(st.session_state, pending)

_menu_ids = D.customers_by_risk(df)
_menu_labels = {
    a: D.customer_menu_label(a, p, b)
    for a, p, b in zip(df.account_id, df.p_churn_90d, df["last_bill_cents"] if "last_bill_cents" in df.columns else [None] * len(df))
}
if st.session_state["acc"] not in _menu_labels and len(_menu_ids):
    D.apply_shared_selection(st.session_state, _menu_ids[0])


def _from_seg():
    v = st.session_state.get("seg")
    if v:
        D.apply_shared_selection(st.session_state, f"{D.PERSONA}{v}")


def _from_pick():
    v = st.session_state.get("customer_pick")
    if v:
        D.apply_shared_selection(st.session_state, v)


st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
a, b = st.columns([1, 2])
a.segmented_control("Quick picks", D.DEMO, key="seg", format_func=lambda d: f"Customer {d}", on_change=_from_seg)
b.selectbox("Find a customer", _menu_ids, key="customer_pick", format_func=lambda i: _menu_labels.get(i, i), on_change=_from_pick)
st.markdown("<div class='o-lbl' style='text-transform:none;letter-spacing:0;margin:6px 0 0'>Scroll the list or type to search. "
            "Highest risk is first. The walk-through and the deal below follow this customer.</div>", unsafe_allow_html=True)
acc = st.session_state["acc"]
# the walk-through: decisions/options from the offers team's files (ledger/outreach fallbacks), today's candidates for eligibility
opts = D.offer_options(df, acc)
cand = D.candidates_for(acc, opts)
econ = D.economics()
if opts is None:
    opts = D.options_for(df, acc, cand)
dec_all = dec
if not SHOW_MONEY:   # backstop: no company dollars in anything handed to the sections module
    cand, econ, dec, opts = D.strip_money(cand), D.economics_no_money(econ), D.strip_money(dec), D.strip_money(opts)
_call(O.render_customer, df if SHOW_MONEY else D.strip_money(df), acc, contributions_fn=D.contributions, candidates=cand,
      inputs=D.engine_inputs(), events=D.events(), decisions=dec, options=opts)
clicked = _call(O.render_dashboard, df if SHOW_MONEY else D.strip_money(df), econ, typical_risk=D.typical_risk(),
                decisions=dec, summary=D.dashboard_summary() if SHOW_MONEY else None)
if clicked and clicked != st.session_state.get("_last_row_pick"):
    st.session_state["_last_row_pick"] = clicked
    st.session_state["_pending_acc"] = clicked
    st.rerun()
if not clicked:
    st.session_state["_last_row_pick"] = None
# section 4: how we pick the deal, for the same customer selected above. Demo personas are quick picks only.
if hasattr(O, "render_deal_engine"):
    allo = D.all_options()
    _call(O.render_deal_engine, df, acc, options=allo if SHOW_MONEY else D.strip_money(allo),
          decisions=dec_all if SHOW_MONEY else D.strip_money(dec_all),
          demo_ids=[f"{D.PERSONA}{d}" for d in D.DEMO])
_call(O.render_considered, D.considerations() if SHOW_MONEY else D.considerations_no_money(D.considerations()),
      summary=D.considered_summary() if SHOW_MONEY else None)
