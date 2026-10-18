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

# ---- open a customer: four demo buttons, search, or a click in the riskiest-ten table (render_dashboard returns it)
st.session_state.setdefault("acc", f"{D.PERSONA}38")
pending = st.session_state.pop("_pending_acc", None)
if pending:  # a row click from the last run: apply it before the picker widgets exist, then clear them
    st.session_state["acc"] = pending
    st.session_state["seg"] = None
    st.session_state["q"] = ""


def _from_seg():
    v = st.session_state.get("seg")
    if v:
        st.session_state["acc"] = f"{D.PERSONA}{v}"
        st.session_state["q"] = ""


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


def _from_live():
    st.session_state["acc"] = D.LIVE_ACC
    st.session_state["seg"] = None
    st.session_state["q"] = ""


st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
a, b, c = st.columns([2, 1, 0.8])
a.segmented_control("Open a customer", D.DEMO, key="seg", format_func=lambda d: f"Customer {d}", on_change=_from_seg)
b.text_input("Find a customer", key="q", placeholder="e.g. 38 or 01607", on_change=_from_search)
live = D.live_events()
if live is not None and D.LIVE_ACC in set(df.account_id):
    c.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    c.button("Live what-if", key="open_live", on_click=_from_live, width="stretch")
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
# ---- 'the account ticks': for the live account, a thin event rail at the top of the customer section drives the
# whole view (header risk + chip, step 1 inputs, step 2 tower and reasons). Buttons only, no timer. The rest of the
# page stays frozen (it is drawn from df, never from the ticked row).
TICK_KEY = f"tick_{D.LIVE_ACC}"
TICK_CSS = (f"<style>.st-key-orbit_tick{{position:sticky;top:0;z-index:20;background:{O.BG};padding:8px 0 0;margin-bottom:10px}}"
            f".o-tick{{display:flex;align-items:center;gap:0;font:400 12px 'SM';color:{O.INK};height:34px}}"
            f".o-tick .seg{{flex:1;height:1px;background:{O.INK}}}"
            f".o-tick .dot{{width:12px;height:12px;border-radius:50%;border:1.5px solid {O.INK};background:{O.BG};flex:none}}"
            f".o-tick .dot.past{{background:{O.INK}}}.o-tick .dot.now{{background:{O.MAG};border-color:{O.MAG}}}"
            f".o-tick .lab{{margin:0 10px 0 6px;white-space:nowrap}}.o-tick .lab.now{{color:{O.MAG}}}.o-tick .lab.fut{{color:{O.MUTED}}}"
            f".o-tickline{{font:400 16px/1.35 'SG';margin-top:4px;padding-bottom:10px;border-bottom:1px solid {O.INK}}}</style>")


def _tick_go(i: int) -> None:
    st.session_state[TICK_KEY] = i


def _tick_rail(t: dict):
    def draw():
        i, n, labs = t["step"], t["n"], t["labels"]
        with st.container(key="orbit_tick"):
            st.markdown(TICK_CSS, unsafe_allow_html=True)
            a, b, c = st.columns([7, 1.2, 0.8], vertical_alignment="center")
            parts = []
            for j in range(1, n + 1):
                k = "now" if j == i else ("past" if j < i else "fut")
                parts.append(f"<span class='dot {k}'></span><span class='lab {k}'>{j:02d} · {O.esc(labs[j]) if j <= i else '?'}</span>")
            a.markdown(f"<div class='o-tick'><span class='lab'>EVENTS</span>{'<span class=seg></span>'.join(parts)}</div>",
                       unsafe_allow_html=True)
            b.button("Next event →", key=f"{TICK_KEY}_next", disabled=i >= n, on_click=_tick_go, args=(i + 1,),
                     type="primary", width="stretch")
            c.button("Reset", key=f"{TICK_KEY}_reset", disabled=i == 0, on_click=_tick_go, args=(0,), width="stretch")
            line = t["line"] or "Nothing new yet. Press Next event to see what happens."
            st.markdown(f"<div class='o-tickline'>{O.esc(line)}</div>", unsafe_allow_html=True)
    return draw


@st.fragment
def customer_section():
    acc_ = st.session_state["acc"]
    inp = D.engine_inputs()
    t = D.live_tick(df, acc_, int(st.session_state.get(TICK_KEY, 0)), inp) if acc_ == D.LIVE_ACC else None
    view, cfn = df, D.contributions
    if t is not None:
        t["rail"] = _tick_rail(t)
        view, cfn = D.live_row(df, acc_, t["step"]), D.live_contributions(t["step"], acc_)
    _call(O.render_customer, view if SHOW_MONEY else D.strip_money(view), acc_, contributions_fn=cfn, candidates=cand,
          inputs=inp, events=D.events(), decisions=dec, options=opts, tick=t)


customer_section()
clicked = _call(O.render_dashboard, df if SHOW_MONEY else D.strip_money(df), econ, typical_risk=D.typical_risk(),
                decisions=dec, summary=D.dashboard_summary() if SHOW_MONEY else None)
if clicked and clicked != st.session_state.get("_last_row_pick"):
    st.session_state["_last_row_pick"] = clicked
    st.session_state["_pending_acc"] = clicked
    st.rerun()
if not clicked:
    st.session_state["_last_row_pick"] = None
# section 4: how we pick the deal (live example defaults to customer 04); order per David: hero, customer, book, deal, considered
if hasattr(O, "render_deal_engine"):
    allo = D.all_options()
    _call(O.render_deal_engine, df, f"{D.PERSONA}04", options=allo if SHOW_MONEY else D.strip_money(allo),
          decisions=dec_all if SHOW_MONEY else D.strip_money(dec_all))
_call(O.render_considered, D.considerations() if SHOW_MONEY else D.considerations_no_money(D.considerations()),
      summary=D.considered_summary() if SHOW_MONEY else None)
