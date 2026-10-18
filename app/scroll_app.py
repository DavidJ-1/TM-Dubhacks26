"""Scroll page: the churn + upsell board as one long page (built from the design team's orbit mock).

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
dec = D.offer_decisions(df)   # next-version decisions (offers team's decisions.csv; ledger fallback)

# ---- one selected customer. Pending row clicks are applied before the chart so the highlight matches.
# A new chart click updates the selection and reruns once, before the walk-through and the deal draw.
_ids = set(df.account_id)
st.session_state.setdefault("acc", f"{D.PERSONA}38")
if "customer_pick" not in st.session_state:
    D.apply_shared_selection(st.session_state, st.session_state["acc"])
if st.session_state.get("seg") not in D.QUICK_IDS:
    st.session_state["seg"] = st.session_state["acc"] if st.session_state["acc"] in D.QUICK_IDS else None
pending = st.session_state.pop("_pending_acc", None)
if pending and pending in _ids:
    D.apply_shared_selection(st.session_state, pending)
    if st.session_state.get("_seen_dot") not in (None, pending):
        st.session_state["_chart_gen"] = int(st.session_state.get("_chart_gen", 0)) + 1
        st.session_state["_seen_dot"] = None

_hero_points = _call(O.render_hero, df, selected=st.session_state.get("acc"), marks=D.quick_marks()) or []
dot = D.account_from_point_selection(_hero_points)
if dot and dot in _ids and dot != st.session_state.get("acc"):
    D.apply_shared_selection(st.session_state, dot)
    st.session_state["_seen_dot"] = dot
    st.rerun()
st.session_state["_seen_dot"] = dot or None

_menu_ids = D.customers_by_risk(df)
_menu_labels = {
    a: D.customer_menu_label(a, p, b)
    for a, p, b in zip(df.account_id, df.p_churn_90d, df["last_bill_cents"] if "last_bill_cents" in df.columns else [None] * len(df))
}
if st.session_state["acc"] not in _menu_labels and len(_menu_ids):
    D.apply_shared_selection(st.session_state, _menu_ids[0])


def _forget_dot():
    """A picker changed the customer, so the chart's last click should not win on the next run."""
    st.session_state["_chart_gen"] = int(st.session_state.get("_chart_gen", 0)) + 1
    st.session_state["_seen_dot"] = None


def _from_seg():
    v = st.session_state.get("seg")
    if v:
        D.apply_shared_selection(st.session_state, v)
        _forget_dot()


def _from_pick():
    v = st.session_state.get("customer_pick")
    if v:
        D.apply_shared_selection(st.session_state, v)
        _forget_dot()


def _on_quick(account_id: str):
    """Deal quick pick: write the shared customer before the deal section draws."""
    if account_id:
        D.apply_shared_selection(st.session_state, account_id)
        _forget_dot()


def _from_live():
    """Open the scripted account (#02363) through the same selection as the dropdown."""
    D.apply_shared_selection(st.session_state, D.LIVE_ACC)
    _forget_dot()


st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
_qlabel = {q["id"]: D.quick_button(q) for q in D.QUICK}
st.segmented_control("Quick picks", list(D.QUICK_IDS), key="seg",
                     format_func=lambda i: _qlabel.get(i, D.customer_cid(i)), on_change=_from_seg)
st.selectbox("Find a customer", _menu_ids, key="customer_pick", format_func=lambda i: _menu_labels.get(i, i), on_change=_from_pick)
st.markdown("<div class='o-lbl' style='text-transform:none;letter-spacing:0;margin:6px 0 0'>Scroll the list or type to search. "
            "Highest risk is first. A chart dot, a table row, the walk-through, and the deal below all follow this customer.</div>",
            unsafe_allow_html=True)
live = D.live_events()   # the event rail in the customer section is the entry point (no separate button)
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
            f".o-tick .lab{{margin:0 8px 0 4px;white-space:nowrap;font-size:11px}}.o-tick .lab.now{{color:{O.MAG}}}.o-tick .lab.fut{{color:{O.MUTED}}}"
            f".st-key-{TICK_KEY}_open button{{white-space:nowrap}}"
            f".o-tickline{{font:400 16px/1.35 'SG';margin-top:4px;padding-bottom:10px;border-bottom:1px solid {O.INK}}}"
            # ---- animations: plain CSS, transform/opacity/box-shadow only (no layout change, no page jump), ease-out,
            # under 600ms, no overshoot. The 'tka' class is set only on the run right after a Next event press, so each
            # plays once per press; React swaps the element (its markup changes), which restarts the animation.
            "@keyframes tkUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}"
            "@keyframes tkIn{from{opacity:0;transform:translateX(16px)}to{opacity:1;transform:none}}"
            f"@keyframes tkRing{{from{{box-shadow:0 0 0 0 {O.MAG}}}to{{box-shadow:0 0 0 9px rgba(226,0,116,0)}}}}"
            "@keyframes tkLine{from{transform:scaleX(0)}to{transform:scaleX(1)}}"
            f"@keyframes tkFade{{from{{opacity:1;color:{O.INK}}}to{{opacity:.75;color:{O.MUTED}}}}}"
            "@keyframes tkFlip{from{transform:perspective(900px) rotateX(-90deg);opacity:.2}to{transform:perspective(900px) rotateX(0);opacity:1}}"
            ".tka .o-tk-risk{animation:tkUp .45s ease-out both}"
            ".tka .o-tk-chip{animation:tkIn .45s ease-out .1s both}"
            ".o-tick .dot.now.tka{animation:tkRing .55s ease-out 1}"
            f".tka .o-chg{{position:relative}}.tka .o-chg::after{{content:'';position:absolute;left:0;right:0;bottom:-1px;height:1px;"
            f"background:{O.MAG};transform-origin:left;animation:tkLine .5s ease-out both}}"
            ".tka .o-chg .wv{animation:tkFade .55s ease-out both}"
            ".o-tk-flip{animation:tkFlip .5s ease-out both;transform-origin:top center}"
            ".o-tk-slide{animation:tkUp .45s ease-out .15s both}</style>")


def _tick_go(i: int) -> None:
    st.session_state[TICK_KEY] = i
    st.session_state["_tick_anim"] = i > 0   # animate the run right after a Next event press (not on Reset)


def _tick_open() -> None:   # the rail as entry point: from any other customer, Next event opens the live account
    D.apply_shared_selection(st.session_state, D.LIVE_ACC)
    _forget_dot()
    st.session_state[TICK_KEY] = 1
    st.session_state["_tick_anim"] = True
    st.session_state["_tick_full"] = True
    st.session_state["_tick_switched"] = True


def _tick_rail(t: dict):
    def draw():
        i, n, labs = t["step"], t["n"], t["labels"]
        with st.container(key="orbit_tick"):
            st.markdown(TICK_CSS, unsafe_allow_html=True)
            a, b, c = st.columns([7, 1.2, 0.8], vertical_alignment="center")
            parts = []
            for j in range(1, n + 1):
                k = "now" if j == i else ("past" if j < i else "fut")
                lab = f"{j:02d} · {O.esc(labs[j])}" if j <= i else f"{j:02d}"
                parts.append(f"<span class='dot {k} {t.get('anim', '') if j == i else ''}'></span><span class='lab {k}'>{lab}</span>")
            a.markdown(f"<div class='o-tick'><span class='lab'>WHAT IF THIS HAPPENS NEXT</span>{'<span class=seg></span>'.join(parts)}</div>",
                       unsafe_allow_html=True)
            b.button("Next event →", key=f"{TICK_KEY}_next", disabled=i >= n, on_click=_tick_go, args=(i + 1,),
                     type="primary", width="stretch")
            c.button("Reset", key=f"{TICK_KEY}_reset", disabled=i == 0, on_click=_tick_go, args=(0,), width="stretch")
            line = t["line"] or "Nothing new yet. Press Next event to see what happens."
            st.markdown(f"<div class='o-tickline'>{O.esc(line)}</div>", unsafe_allow_html=True)
    return draw


def _entry_rail():
    """For any other customer: a slim rail whose Next event opens the account that ticks."""
    who = O.cid(D.LIVE_ACC)
    with st.container(key="orbit_tick"):
        st.markdown(TICK_CSS, unsafe_allow_html=True)
        a, b = st.columns([1.3, 1], vertical_alignment="center")
        a.markdown(f"<div class='o-tick'><span class='lab'>EVENTS</span><span class='lab fut'>"
                   f"Live events demo follows customer {O.esc(who)}</span></div>",
                   unsafe_allow_html=True)
        b.button(f"Next event → switches to customer {who}", key=f"{TICK_KEY}_open", on_click=_tick_open,
                 type="primary", width="stretch")


@st.fragment
def customer_section():
    if st.session_state.pop("_tick_full", False):   # opened from the entry rail: redraw the picker too
        st.rerun()
    if st.session_state.pop("_tick_switched", False):
        st.toast(f"Now showing {O.cid(D.LIVE_ACC)} for live events")
    acc_ = st.session_state["acc"]
    inp = D.engine_inputs()
    t = D.live_tick(df, acc_, int(st.session_state.get(TICK_KEY, 0)), inp) if acc_ == D.LIVE_ACC else None
    view, cfn, dec_v, opt_v = df, D.contributions, dec, opts
    if t is not None:
        t = D.live_tick_more(t, df, acc_, show_money=SHOW_MONEY)
        t["anim"] = "tka" if st.session_state.pop("_tick_anim", False) else ""
        t["rail"] = _tick_rail(t)
        view, cfn = D.live_row(df, acc_, t["step"]), D.live_contributions(t["step"], acc_)
        dec_v = D.live_decisions(dec, acc_, t["step"], show_money=SHOW_MONEY)
        opt_v = D.live_options(acc_, t["step"], show_money=SHOW_MONEY)
    elif live is not None:
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
    _call(O.render_customer, view if SHOW_MONEY else D.strip_money(view), acc_, contributions_fn=cfn, candidates=cand,
          inputs=inp, events=D.events(), decisions=dec_v, options=opt_v, tick=t if t is not None else
          ({"rail": _entry_rail, "risk": None} if live is not None else None))


customer_section()
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
          quick=[(q["id"], D.quick_button(q)) for q in D.QUICK], on_quick=_on_quick)
_call(O.render_considered, D.considerations() if SHOW_MONEY else D.considerations_no_money(D.considerations()),
      summary=D.considered_summary() if SHOW_MONEY else None)
