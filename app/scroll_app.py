"""Scroll page: the churn + upsell board as one long 3D scroll (built from the design team's orbit mock).

Run: python -m streamlit run app/scroll_app.py
Data loading and every count live in orbit_data.py and here; orbit_sections.py only draws.
"""
import sys
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Churn + upsell board", layout="wide", initial_sidebar_state="collapsed")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import orbit_data as D  # noqa: E402
import orbit_sections as O  # noqa: E402

O.load_css()


@st.cache_data(show_spinner=False)
def frame():
    # flag cut = 90th percentile of risk over regular accounts, applied to all accounts (orbit_frame's flag_share=0.10)
    return O.orbit_frame(D.merged(), D.outreach(), D.receipts(), flag_share=0.10)


df = frame()
O.render_hero(df)

# ---- open a customer: four demo buttons, search, or a click in the riskiest-ten table
st.session_state.setdefault("acc", f"{D.PERSONA}38")
clicked = st.session_state.get("orbit_riskiest")
rows = (clicked or {}).get("selection", {}).get("rows") if isinstance(clicked, dict) else None
if rows is None and clicked is not None and hasattr(clicked, "selection"):
    rows = clicked.selection.rows
if rows and st.session_state.get("_last_click") != rows:
    st.session_state["_last_click"] = rows
    st.session_state["acc"] = df[~df.is_demo].head(10).iloc[rows[0]].account_id
    st.session_state["seg"] = None


def _from_seg():
    v = st.session_state.get("seg")
    if v:
        st.session_state["acc"] = f"{D.PERSONA}{v}"


def _from_search():
    q = str(st.session_state.get("q", "")).strip().upper().lstrip("#")
    if not q:
        return
    ids = set(df.account_id)
    for cand in (q, f"ACC-{q}", f"{D.PERSONA}{q.zfill(2)}", f"ACC-{q.zfill(5)}"):
        if cand in ids:
            st.session_state["acc"] = cand
            st.session_state["seg"] = None
            return


st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
a, b = st.columns([2, 1])
a.segmented_control("Open a customer", D.DEMO, key="seg", format_func=lambda d: f"Customer {d}", on_change=_from_seg)
b.text_input("Find a customer", key="q", placeholder="e.g. 38 or 01607", on_change=_from_search)
acc = st.session_state["acc"]
row = df[df.account_id == acc].iloc[0]
O.render_customer(df, acc, contributions_fn=D.contributions, candidates=D.candidates(acc, D.policy_pick(row)))
O.render_dashboard(df, D.economics(), typical_risk=D.typical_risk())
O.render_considered(D.considerations())
