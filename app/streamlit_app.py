"""T-Mobile churn + upsell: lean demo app (tm-ui lane). ALL CUSTOMERS AND NUMBERS ARE SYNTHETIC.

Run:  streamlit run app/streamlit_app.py
Tabs: Four customers · How it decides · Pipeline visual. (Customer journey tab hidden: its numbers were stale.)
Data: TM_OUT_DIR -> demo_data/ -> harness/out/ -> app/mock/ (mock is flagged with a banner). See app/data.py.
One churn number everywhere: churn_scores.csv p_churn_90d. On screen: "Churn risk model" / "Offer engine",
no file paths, SKUs or codenames (provenance sits in a collapsed expander).
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

APP = Path(__file__).resolve().parent
REPO = APP.parent
sys.path.insert(0, str(APP))
from data import clean_stays, is_mock, load_all, merged, persona_titles  # noqa: E402
from messages import action_label, normalize_action  # noqa: E402

MAGENTA = "#E20074"
import plotly.graph_objects as _go  # noqa: E402
import plotly.io as _pio  # noqa: E402
_t = _go.layout.Template(_pio.templates["plotly_white"])
_t.layout.update(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                 font=dict(family="Inter, sans-serif", color="#15111A", size=12),
                 colorway=["#15111A", "#A39DA6", "#D6CEC4"],
                 xaxis=dict(showgrid=False, zeroline=False), yaxis=dict(showgrid=False, zeroline=False))
_pio.templates["tm_light"] = _t
# How-it-decides tab: show app/charts/06_upgrade_or_wait.png only once tm-strategy signs off on its post-8:50 figures.
SHOW_UPGRADE_WAIT = False
import itertools as _it  # noqa: E402
_orig_container, _cc = st.container, _it.count()


def _card_container(*a, **k):  # tag bordered containers so the dark card CSS can target them (visual only)
    if k.get("border") and "key" not in k:
        k["key"] = f"tmcard_{next(_cc)}"
    return _orig_container(*a, **k)


st.container = _card_container
st.set_page_config(page_title="T-Mobile Next Best Moment (synthetic)", page_icon="📱", layout="wide")
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Inter+Tight:wght@500;600&display=swap');
:root {{--paper:#F6F3EE; --card:#FFFFFF; --line:#E6E0D8; --ink:#15111A; --muted:#6E6873; --faint:#A39DA6; --mag:{MAGENTA}}}
html, body, [data-testid="stAppViewContainer"], .stApp {{background:var(--paper) !important; color:var(--ink)}}
.stApp, .stApp p, .stApp li, .stApp label, .stApp span, .stApp div, .stApp td, .stApp th, .stApp input {{font-family:'Inter',system-ui,sans-serif}}
.stApp [data-testid="stIconMaterial"] {{font-family:'Material Symbols Rounded' !important}}
.stApp h1, .stApp h2, .stApp h3, .stApp h4 {{font-family:'Inter Tight','Inter',sans-serif !important; font-weight:600 !important;
  letter-spacing:-0.025em; color:var(--ink)}}
.stApp h3 {{font-size:28px !important; margin:48px 0 8px !important}}
.stApp h4 {{font-size:20px !important; margin:40px 0 16px !important}}
#MainMenu, footer, [data-testid="stDecoration"], [data-testid="stStatusWidget"], [data-testid="stToolbar"] {{display:none !important}}
header[data-testid="stHeader"] {{display:none !important}}
.block-container {{padding:0 40px 64px !important; max-width:1360px}}
[data-testid="stCaptionContainer"], .stCaption, [data-testid="stCaptionContainer"] p {{color:var(--muted) !important; font-size:13px}}
/* app shell */
.tm-head {{position:sticky; top:0; z-index:50; display:flex; justify-content:space-between; align-items:center; height:64px;
  margin:0 -40px 0; padding:0 40px; background:rgba(246,243,238,.92); backdrop-filter:blur(8px); border-bottom:1px solid var(--line)}}
.tm-brand {{display:flex; align-items:center; gap:12px; font-weight:600; font-size:15px; letter-spacing:-0.01em; color:var(--ink)}}
.tm-logo {{width:24px; height:24px; border-radius:6px; background:var(--mag); display:inline-flex; align-items:center;
  justify-content:center; font-weight:600; color:white; font-size:12px}}
.tm-sub {{color:var(--faint); font-size:13px; font-weight:400; padding-left:12px; border-left:1px solid var(--line)}}
.tm-syn {{display:inline-flex; gap:8px; align-items:center; color:var(--ink); background:var(--card); border:1px solid var(--line);
  border-radius:999px; padding:6px 14px; font-size:12px; font-weight:500}}
.tm-syn small {{color:var(--muted); font-weight:400; font-size:12px}}
/* tabs as segmented nav */
[data-testid="stTabs"] [role="tablist"] {{gap:24px; border-bottom:1px solid var(--line) !important; margin:16px 0 0}}
[data-testid="stTabs"] button[role="tab"] {{background:transparent !important; padding:12px 0 !important; margin:0 !important; border:none !important; box-shadow:none !important}}
[data-testid="stTabs"] button[role="tab"] p {{font-size:14px !important; font-weight:500; color:var(--muted)}}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] p {{color:var(--ink) !important}}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {{background:var(--mag) !important; height:2px !important; display:block !important}}
[data-testid="stTabs"] [data-baseweb="tab-border"] {{display:none !important}}
div[class*="st-key-tmcard_"] h4 {{margin:4px 0 0 !important; padding:0 !important; font-size:22px !important}}
div[class*="st-key-tmcard_"] [data-testid="stMetric"], div[class*="st-key-tmcard_"] .risk-card {{margin-top:0}}
div[class*="st-key-tmcard_"] .pill {{margin-bottom:2px}}
/* bento */
.bento {{display:grid; grid-template-columns:repeat(12,1fr); grid-auto-rows:minmax(150px,auto); gap:16px; margin:8px 0 8px}}
.tile {{background:var(--card); border:1px solid var(--line); border-radius:16px; padding:24px; min-width:0}}
.bento .t1 {{grid-column:span 4; grid-row:span 2; display:flex; flex-direction:column}}
.bento .t1 .rows {{margin-top:auto}}
.bento .t2 {{grid-column:span 4}} .bento .t3 {{grid-column:span 4}}
.bento .t4 {{grid-column:span 5}} .bento .t5 {{grid-column:span 3}}
.tile.dark {{background:var(--ink); border-color:var(--ink)}}
.tile.dark .big {{color:#F6F3EE}} .tile.dark .step, .tile.dark .sub, .tile.dark .note {{color:#A39DA6}}
.trow {{display:grid; grid-template-columns:96px 1fr; gap:8px; align-items:baseline; padding:8px 0; border-top:1px solid var(--line); font-size:14px}}
.note {{font-size:13px; color:var(--muted); margin-top:16px}}
.brow {{display:flex; justify-content:space-between; gap:8px; font-size:13px; color:var(--ink); margin-top:12px}}
.brow span {{overflow:hidden; text-overflow:ellipsis; white-space:nowrap}} .brow b {{font-weight:600}}
.bbar {{height:4px; background:#ECE7E0; border-radius:2px; margin-top:6px}} .bbar i {{display:block; height:4px; border-radius:2px}}
.follow {{display:grid; grid-template-columns:1.4fr .9fr 1.3fr 1fr 1.4fr; gap:16px; margin:8px 0 24px}}
.follow .tile {{padding:20px}}
.ft {{padding:6px 0; font-size:13px; line-height:1.45; color:var(--ink)}} .ft .pill {{margin-bottom:4px}}
.fw {{font-size:18px; font-weight:600; letter-spacing:-0.01em; color:var(--ink); margin-bottom:4px}}
.fq {{font-size:14px; line-height:1.4; color:var(--ink); margin-bottom:12px}}
.bubble.sm {{font-size:12px; padding:10px 12px; background:var(--ink); color:#F6F3EE}}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {{white-space:normal !important; overflow:visible !important; text-overflow:clip !important}}
[data-testid="stMetricLabel"] p {{letter-spacing:.02em !important}}
/* hero */
.hero {{padding:48px 0 32px}}
.hero-eyebrow {{font-size:12px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); font-weight:500; margin-bottom:16px}}
.hero h1 {{font-size:56px !important; line-height:1.04 !important; max-width:980px; margin:0 0 40px !important; padding:0 !important}}
.hero h1 em {{font-style:normal; color:var(--mag)}}
.hero-stats {{display:grid; grid-template-columns:repeat(4,1fr); border-top:1px solid var(--line)}}
.hero-stat {{padding:24px 24px 0 0}}
.hero-stat + .hero-stat {{padding-left:24px; border-left:1px solid var(--line)}}
.hero-num {{font-family:'Inter Tight',sans-serif; font-size:64px; font-weight:600; letter-spacing:-0.04em; line-height:1; color:var(--ink)}}
.hero-lbl {{font-size:13px; color:var(--muted); margin-top:8px}}
/* cards */
div[class*="st-key-tmcard_"] {{background:var(--card) !important; border:1px solid var(--line) !important; border-radius:16px !important;
  box-shadow:none !important; padding:24px !important; transition:border-color .15s ease}}
div[class*="st-key-tmcard_"]:hover {{border-color:#D6CEC4 !important}}
.kicker {{color:var(--muted); font-weight:500; letter-spacing:.08em; text-transform:uppercase; font-size:11px}}
.badge {{display:inline-block; color:var(--muted); border:1px solid var(--line); border-radius:999px; padding:2px 10px; font-size:11px;
  font-weight:500; margin-left:8px; text-transform:none; letter-spacing:0; background:var(--paper)}}
.cid {{font-size:13px; color:var(--faint)}}
.why {{font-family:'Inter Tight','Inter',sans-serif; font-size:30px; line-height:1.15; font-weight:600; color:var(--ink);
  letter-spacing:-0.025em; margin:8px 0 16px; max-width:820px}}
.decision {{display:inline-block; background:var(--mag); color:white; font-weight:500; border-radius:8px; padding:6px 12px; font-size:13px}}
.decision i {{font-weight:400; opacity:.85}}
.chip {{display:grid; grid-template-columns:96px 16px 1fr; align-items:baseline; padding:12px 0; border-bottom:1px solid var(--line);
  font-size:15px; color:var(--ink)}}
.chip .mk {{color:var(--faint); font-size:10px}}
.chip.risk .mk {{color:var(--mag)}}
.pill {{display:inline-block; font-size:11px; font-weight:500; padding:1px 8px; border:1px solid var(--line); border-radius:999px;
  color:var(--muted) !important; background:var(--paper) !important; margin-right:6px; width:fit-content; letter-spacing:.01em}}
.legend {{font-size:12px; color:var(--faint); margin:16px 0 4px}} .legend .pill {{margin-left:8px}}
/* phone */
.phone {{width:280px; margin:8px auto 0; border-radius:44px; background:#15111A; min-height:480px; padding:44px 16px 24px; position:relative;
  box-shadow:0 0 0 1px #2A2430, 0 24px 48px -24px rgba(21,17,26,.35)}}
.phone::before {{content:""; position:absolute; top:14px; left:50%; transform:translateX(-50%); width:88px; height:24px;
  background:#000; border-radius:14px}}
.sender {{text-align:center; font-size:11px; color:#A39DA6; margin:0 0 16px; padding-bottom:12px; border-bottom:1px solid #2A2430}}
.bubble {{background:#2A2430; color:#F6F3EE; border-radius:18px 18px 18px 4px; padding:12px 14px; font-size:14px; line-height:1.4}}
.nomsg {{text-align:center; color:#A39DA6; margin-top:136px; font-size:14px}}
.whatif {{border:1px solid var(--line); border-radius:10px; padding:12px 16px; background:var(--paper); font-size:14px; color:var(--ink)}}
.how {{background:var(--card); border-radius:12px; padding:8px 16px; font-size:15px; color:var(--ink)}}
.how b {{color:var(--ink)}}
/* bento pipeline */
.step {{color:var(--muted); font-weight:500; font-size:11px; letter-spacing:.08em; text-transform:uppercase; margin-bottom:16px}}
.big {{font-family:'Inter Tight',sans-serif; font-size:44px; font-weight:600; letter-spacing:-0.035em; line-height:1; color:var(--ink); margin:0 0 8px}}
.sub {{font-size:13px; color:var(--muted); margin-bottom:4px; line-height:1.45}}
.arrow {{color:var(--faint); text-align:center; margin-top:88px; font-size:14px}}
/* risk */
.risk-lbl {{color:var(--muted); font-size:11px; letter-spacing:.08em; text-transform:uppercase; font-weight:500}}
.risk-num {{font-family:'Inter Tight',sans-serif; font-size:48px; font-weight:600; letter-spacing:-0.04em; color:var(--mag); line-height:1; margin:8px 0 16px}}
.risk-bar {{height:4px; background:#ECE7E0; border-radius:2px; position:relative}}
.risk-bar span {{position:absolute; left:0; top:0; bottom:0; background:var(--mag); border-radius:2px}}
.risk-scale {{display:flex; justify-content:space-between; color:var(--faint); font-size:11px; margin-top:8px}}
.risk-was {{color:var(--muted); font-size:13px; margin-top:8px}}
.risk-syn {{display:inline-block; margin-left:8px; padding:1px 7px; border:1px solid var(--line); border-radius:999px; color:var(--muted); font-size:10px; letter-spacing:.04em; text-transform:lowercase; vertical-align:1px}}
/* metrics */
[data-testid="stMetric"] {{background:var(--card) !important; border:1px solid var(--line) !important; border-radius:16px !important; padding:24px !important;
  box-shadow:none !important; border-left:1px solid var(--line) !important}}
[data-testid="stMetricLabel"] p {{color:var(--muted) !important; font-size:11px !important; letter-spacing:.04em; text-transform:uppercase; font-weight:500}}
[data-testid="stMetricValue"] {{font-family:'Inter Tight',sans-serif; font-size:40px !important; font-weight:600; letter-spacing:-0.035em; color:var(--ink)}}
/* options table */
table.opts {{width:100%; border-collapse:collapse; font-size:14px; margin:8px 0 16px; color:var(--ink); border:none}}
table.opts th, table.opts td {{border:none !important; border-bottom:1px solid var(--line) !important}}
table.opts th {{text-align:left; color:var(--faint); font-weight:500; font-size:11px; letter-spacing:.06em; text-transform:uppercase; padding:8px 12px 8px 0}}
table.opts td {{padding:12px 12px 12px 0; vertical-align:top; white-space:normal}}
table.opts tr.won td {{font-weight:600}}
table.opts tr.won td:first-child {{box-shadow:inset 3px 0 0 var(--mag); padding-left:12px}}
table.opts tr.blocked td {{color:var(--faint)}}
table.opts td:nth-child(1) {{width:19%}} table.opts td:nth-child(2) {{width:8%; white-space:nowrap}}
table.opts td:nth-child(3) {{width:15%}} table.opts td:nth-child(4) {{width:11%; white-space:nowrap}}
table.opts td:nth-child(5) {{width:7%; white-space:nowrap}}
/* widgets */
.stButton button {{border-radius:8px; border:1px solid var(--line); background:var(--card); color:var(--ink); font-weight:500; font-size:13px}}
.stButton button:hover {{border-color:var(--ink); color:var(--ink)}}
[data-baseweb="select"] > div {{background:var(--card) !important; border:1px solid var(--line) !important; border-radius:10px !important}}
[data-testid="stExpander"] details {{background:var(--card); border:1px solid var(--line) !important; border-radius:12px}}
[data-testid="stAlert"] {{background:var(--paper) !important; border:1px solid var(--line) !important; border-radius:10px; color:var(--ink)}}
[data-testid="stWidgetLabel"] p {{font-size:13px; color:var(--muted)}}
</style>
""", unsafe_allow_html=True)
st.markdown("<div class='tm-head'><div class='tm-brand'><span class='tm-logo'>T</span>Next Best Moment"
            "<span class='tm-sub'>churn risk model + offer engine</span></div>"
            "<div class='tm-syn'>⚠️ All customers are synthetic <small>· T-Mobile judge sandbox data with simulated "
            "scores. Not real customers.</small></div></div>", unsafe_allow_html=True)

data = load_all()
MOCK = is_mock(data)
if MOCK:
    bad = ", ".join(f"{k}.csv" for k in ("churn_scores", "offers", "features", "labels") if data[k].source != "real")
    st.error("🧪 MOCK DATA: the saved sandbox run wasn't found, so this app shows a 48-account placeholder mock, "
             "not the real 5,000-account run.")
PERSONAS = persona_titles()
df = merged(data)
if "action_code" in df:
    df["action_key"] = df["action_code"].fillna(df.get("action")).map(normalize_action)
elif "action" in df:
    df["action_key"] = df["action"].map(normalize_action)
NONP = df[~df.account_id.astype(str).str.startswith("ACC-PERSONA")]


def fmt_prob(p) -> str:
    """One format everywhere: 19.7% / 5.4% / 0.32%."""
    try:
        p = float(p)
    except (TypeError, ValueError):
        return "n/a"
    if p >= 0.01:
        return f"{p:.1%}"
    return f"{p * 100:.2f}%" if p >= 0.0001 else "<0.01%"


def money(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    return "—" if pd.isna(v) else f"${v:,.0f}"


SHOW_PIPELINE_TAB = False  # hidden for tonight: its message count predates the current engine run
if SHOW_PIPELINE_TAB:
    tab2, tab3 = st.tabs(["How it decides · four customers", "Pipeline visual"])
else:
    tab2, tab3 = st.container(), None
# Customer journey tab hidden: its embedded HTML (app/viz/customer_journey.html) carries stale counts
# (504 flagged / 1,123 contacted vs 505 / 1,314 on the main page). Re-add only after regenerating it.

TOP10_CLAIM = ("The top 10% catches {pct} of leavers in held-out synthetic data, close to the 64.2% best possible, "
               "because it recovers the patterns built into the synthetic data (synthetic).")

# ---------------- TAB 2: Four customers ----------------
CARDS = [  # account, story we intend, action codes that fit the story (demo script v2 order)
    ("ACC-PERSONA-38", "Save them money", {"variant_switch", "right_size", "right_size_plan"}),
    ("ACC-PERSONA-04", "Fix it first", {"care_credit_fix_first", "fix_first", "fix_first_callback"}),
    ("ACC-PERSONA-21", "A check-in, not a discount", {"check_in"}),
    ("ACC-PERSONA-24", "Restraint: do nothing", {"do_nothing"}),
]
BADGES = {  # challenge direction each card demonstrates
    "ACC-PERSONA-38": "Account plan fit · cheaper best-fit plan",
    "ACC-PERSONA-04": "Next Best Moment · proportionate fix + credit",
    "ACC-PERSONA-21": "Next Best Moment · live re-decide",
    "ACC-PERSONA-24": "Next Best Moment · doing nothing is allowed",
}


def clean_text(t) -> str:
    """No SKUs, raw driver tags or EV formulas on screen: map to plain words."""
    t = str(t or "")
    t = re.sub(r"TMO-STUB-PLAN-([A-Z0-9-]+)", lambda m: m.group(1).replace("-", " ").title() + " plan", t)
    t = re.sub(r"TMO-STUB-[A-Z0-9-]+", "a plan", t)
    t = re.sub(r"PROMO-STUB-([A-Z0-9-]+)", lambda m: m.group(1).replace("-", " ").lower() + " promo", t)
    t = re.sub(r"enrichment\([^)]*\)(\[[^\]]*\])?:?[^;,.]*[;,]?\s*", "", t)
    t = re.sub(r"\s*EV\s*=.*?(\(synthetic\)\.?|$)", "", t)
    t = re.sub(r"\bEV\b", "expected value", t)
    t = t.replace("Model A + EV engine", "churn risk model + offer engine").replace("Model A", "churn risk model")
    t = t.replace("expected value engine", "offer engine").replace("Model B", "offer engine")
    t = re.sub(r"(?i)\b(live:)?port_out_inquiry\b", "Asked us about transferring their number", t)
    t = re.sub(r"(?i)\bno port-out inquir(y|ies)\b", "hasn't asked us about transferring their number", t)
    t = re.sub(r"(?i)\bport-out inquir(y|ies)\b", "asked us about transferring their number", t)
    t = re.sub(r"(?i)\basked about porting out\b", "asked us about transferring their number", t)
    t = re.sub(r"(?i)\basked (us )?about porting (their |the |a )?number( out)?\b", "Asked us about transferring their number", t)
    t = re.sub(r"(?i)\bport(ing)?[- ]out\b", "number transfer", t)
    t = re.sub(r"(?i)\bporting\b", "transferring", t)
    t = re.sub(r"no-income upgrade model('|&#x27;)s top", r"simulated upgrade score\1s top", t)
    return t.strip()


def signal_type(text: str) -> str:
    """Commerce (plan/price/bill/device/financing) · Customer (support, sentiment, tenure) · Real-time (number transfer, carriers, app)."""
    t = str(text).lower()
    if any(w in t for w in ("porting", "port-out", "transferring their number", "number transfer", "shopping", "carriers", "app user", "uses the app", "sessions")):
        return "Real-time"
    if any(w in t for w in ("support", "unresolved", "unhappy", "complaint", "positive experiences",
                            "long-time", "new customer", "cancel")):
        return "Customer"
    return "Commerce"


_REASON_CATS = [
    (r"unresolved support contact", "Unresolved support contacts (90 days)"),
    (r"unhappy support contact", "Unhappy support contacts (90 days)"),
    (r"promo ended, bill up|promo recently ended", "Promo ended, bill went up"),
    (r"^bill up", "Bill went up vs prior months"),
    (r"^new customer", "New customer"),
    (r"^phone is \d+ months old", "Older phone"),
    (r"shopping other carriers", "Shopping other carriers"),
    (r"rarely uses the app", "Rarely uses the app"),
    (r"porting|transferring their number", "Asked us about transferring their number"),
    (r"asked about cancelling", "Asked about cancelling"),
]


def reason_category(t) -> str:
    """Plain label for a risk reason with the numbers removed (for counts across customers)."""
    t = str(t or "").strip()
    for pat, lab in _REASON_CATS:
        if re.search(pat, t, re.I):
            return lab
    return clean_text(t)


PILL = {"Commerce": "p-com", "Customer": "p-cus", "Real-time": "p-rt"}


def chip(text: str, kind: str) -> str:
    stype = signal_type(text)
    return (f"<div class='chip {kind}'><span class='pill {PILL[stype]}'>{stype}</span>"
            f"<span class='mk'>{'▲' if kind == 'risk' else '●'}</span> {html.escape(clean_text(text))}</div>")


LEGEND = ("<div class='legend'><span class='pill p-com'>Commerce</span>plan, price, bill, device, financing "
          "<span class='pill p-cus'>Customer</span>support, sentiment, tenure "
          "<span class='pill p-rt'>Real-time</span>transfer questions, comparing carriers, app use "
          "&nbsp;·&nbsp; ▲ risk &nbsp;● reason to stay</div>")
TOGGLES = [  # key, label, relevant-if, edits applied to features.csv / engine row
    # Toggles start ON (the fact as it is in the data); switching one OFF removes that fact and re-decides.
    ("tickets", "Open support tickets", lambda r: float(r.get("unresolved_90d", 0) or 0) > 0
     or float(r.get("negative_contacts_90d", 0) or 0) > 0,
     {"unresolved_90d": 0, "unresolved_270d": 0, "negative_contacts_90d": 0, "network_contacts_90d": 0}),
    ("port", "Asked us about transferring their number", lambda r: float(r.get("port_out_inquiry", 0) or 0) > 0, {"port_out_inquiry": 0}),
    ("comp", "Comparing carriers", lambda r: float(r.get("competitor_research_score", 0) or 0) >= 0.3,
     {"competitor_research_score": 0.0}),
]


def phone(msg: str | None, lang: str) -> str:
    if msg:
        inner = f"<div class='bubble'>{html.escape(msg)}</div>"
    else:
        inner = ("<div class='nomsg'>🤫<br><b>" + ("No se envía mensaje" if lang == "es" else "No message sent")
                 + "</b><br>" + ("Decidimos esperar." if lang == "es" else "We decided to wait.") + "</div>")
    return f"<div class='phone'><div class='sender'>T-Mobile · Text Message</div>{inner}</div>"


def _monthly_from_text(t: str) -> str:
    t = str(t or "")
    m = re.search(r"saves? \$(\d+(?:\.\d+)?)/mo", t)
    if m:
        return f"saves ${float(m.group(1)):,.0f}/mo"
    m = re.search(r"\$(\d+(?:\.\d+)?)/mo(?:nth)? more", t)
    if m:
        return f"pays ${float(m.group(1)):,.0f}/mo more"
    return "—"


def options_table(acc: str, cands: pd.DataFrame | None = None, msg_en: str | None = None) -> tuple[pd.DataFrame, str]:
    oc = data["offer_candidates"].df if cands is None else cands
    c = oc[oc.account_id == acc].copy() if len(oc) else oc
    if not len(c):
        return pd.DataFrame(), ""
    chosen_col = "is_winner" if "is_winner" in c else "is_chosen"
    c["_chosen"] = c[chosen_col].astype(str).str.lower().isin(("true", "1"))
    c["_elig"] = c["eligible"].astype(str).str.lower().isin(("true", "1"))
    elig, inel = c[c._elig], c[~c._elig]
    c = pd.concat([elig.sort_values("rank"), inel.head(max(3, 7 - len(elig)))])
    evcol = "ev" if "ev" in c else "expected_value"
    win = c[c._chosen]
    win_name = (action_label(win.iloc[0]["action_code"]) if normalize_action(win.iloc[0]["action_code"]) in _KNOWN
                else str(win.iloc[0].get("action", ""))) if len(win) else ""
    win_ev = float(win.iloc[0][evcol]) if len(win) and pd.notna(win.iloc[0][evcol]) else 0.0
    rows, tips = [], []
    msg_prices = None
    om = df[df.account_id == acc]
    if msg_en is None and len(om) and isinstance(om.iloc[0].get("message_en"), str):
        msg_en = om.iloc[0]["message_en"]
    if isinstance(msg_en, str):
        m = re.search(r"\$(\d+(?:\.\d+)?)/month instead of \$(\d+(?:\.\d+)?)", msg_en)
        if m:
            msg_prices = (float(m.group(1)), float(m.group(2)))
    for _, r in c.iterrows():
        code = r["action_code"]
        name = action_label(code) if normalize_action(code) in _KNOWN else str(r.get("action", code))
        cost = r["cost_to_tmobile"] if "cost_to_tmobile" in c else r.get("offer_cost")
        if "customer_monthly_delta" in c and pd.notna(r.get("customer_monthly_delta")):
            d = float(r["customer_monthly_delta"])
            cust = "no change" if d == 0 else (f"saves ${-d:,.0f}/mo" if d < 0 else f"pays ${d:,.0f}/mo more")
        else:  # plain plan-price change (never the model's customer_benefit estimate)
            cust = "no change" if code == "do_nothing" else _monthly_from_text(r.get("reason"))
            if r._chosen and msg_prices:
                new, old = msg_prices
                txt = f"saves ${old - new:,.0f}/mo (${old:,.0f} → ${new:,.0f})" if old > new else f"pays ${new - old:,.0f}/mo more"
                if cust not in ("—", txt.split(" (")[0]):
                    txt += " ⚠ text/engine differ"
                cust = txt
        evv = r.get(evcol)
        if r._chosen:
            res_, why = "✅ Won", "Our pick: the highest net value for this customer"
        elif not r._elig:
            res_, why = "Blocked", "Not eligible: " + str(r.get("blocked_or_ineligible_reason") or "rule not met")
        else:
            gap = win_ev - (float(evv) if pd.notna(evv) else 0.0)
            res_, why = "Lost", f"Lost to {win_name} by ${gap:,.2f}"
            if "why_not_chosen" in c and isinstance(r.get("why_not_chosen"), str) and r["why_not_chosen"]:
                why += f": {r['why_not_chosen']}"
            elif "below zero" in str(r.get("reason", "")):
                why += ": costs more than it's likely to save"
        why = clean_text(why)
        rows.append({"Option": clean_text(name), "Cost to T-Mobile": money(cost) if r._elig else "—",
                     "Customer": cust if r._elig else "—",
                     "Net value to us (simulated)": (f"${float(evv):,.2f}" if (r._elig and pd.notna(evv)) else "—"),
                     "Result": res_, "Reason": why})
        if r._elig and pd.notna(evv):
            tips.append(f"{name}: expected value {money(evv)}")
    return pd.DataFrame(rows), "Expected value per option (synthetic, internal only): " + "; ".join(tips)


_KNOWN = set(__import__("messages").ACTION_LABELS)


@st.cache_resource(show_spinner="Loading the offer engine (one time, ~6 s)…")
def engine():
    """tm-offers' engine frame for the demo accounts, built exactly as harness/offers.py main() does (synthetic)."""
    import numpy as np
    for p in (str(REPO), str(REPO / "harness")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import offer_detectors as det
    import offers as O
    conn = det.connect_ro()
    cat = det.load_catalog(conn)
    facts = det.build_account_facts(conn)
    facts, _ = det.apply_features_csv(facts, O.OUT_DIR / "features.csv")
    facts, _ = det.apply_enrichment(facts, O.OUT_DIR / "enrichment.csv")
    churn, _src = O.load_churn_scores(facts)
    d = facts.merge(churn, on="account_id", how="left")
    d = d[d.account_id.isin([a for a, _s, _c in CARDS])].copy()
    plans = cat["plans"]
    d["all_low_use_premium_any"] = d["um_plan_overpay"]
    d["um_plan_overpay"] = [bool(r["um_plan_overpay"] or O.right_size_option(r, plans) is not None
                                 or O.variant_option(r, plans) is not None) for _, r in d.iterrows()]
    d["upgrade_moment"] = d[det.UPGRADE_MOMENT_COLS].any(axis=1)
    gs = None
    if O.CONFIG.get("UPGRADE_GATE"):
        import upgrade_gate as ug
        gs = ug.load()
    if gs is not None:
        d = d.merge(gs[["account_id", "upgrade_pct", "in_top15"]], on="account_id", how="left")
        d["in_top15"] = d["in_top15"].fillna(False).astype(bool)
    else:
        d["upgrade_pct"], d["in_top15"] = np.nan, True
    d["upgrade_candidate"] = d["upgrade_moment"] & d["in_top15"]
    lt = pd.read_csv(O.OUT_DIR / "line_tradein.csv")
    tv = lt[(lt["net_now_cents"] > 0) | ((lt["financing_balance_cents"] == 0) & (lt["tradein_value_now_cents"] > 0))]
    d["n_tradein_value_lines"] = d["account_id"].map(tv.groupby("account_id").size()).fillna(0).astype(int)
    return O, cat, d.set_index("account_id")


@st.cache_resource(show_spinner=False)
def offer_api():
    """tm-offers' per-account chooser (harness/offer_api.py: prepared_row + choose_offer). Read-only, synthetic."""
    import os
    if data["offers"].source == "real":  # engine reads the same run the cards show (offers.OUT_DIR honours TM_OUT_DIR)
        os.environ.setdefault("TM_OUT_DIR", str(Path(data["offers"].path).parent))
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from harness import offer_api as api
    api.prepared_row(CARDS[0][0])  # warm the engine cache once
    return api


@st.cache_resource(show_spinner=False)
def prewarm() -> bool:
    """Load the scorer + offer engine once at startup so the first toggle flip is instant. No choose_offer, no sends."""
    try:
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from harness.churn_scorer import score_account
        f = data["features"].df
        for acc in ("ACC-PERSONA-21",):
            if (f.account_id == acc).any():
                score_account(f[f.account_id == acc].iloc[0].to_dict())
        api = offer_api()
        api.prepared_row("ACC-PERSONA-21")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[tm-ui] prewarm skipped: {type(e).__name__}: {e}")
        return False


def _demo_phone():
    """harness.phone_push (ntfy via notify.py; dry run unless TM_SEND_LIVE=1 + NTFY_TOPIC), or None."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    try:
        from harness import phone_push
        return phone_push
    except Exception:  # noqa: BLE001
        return None


def sms_state() -> str:
    """'dry' | 'real' | 'off' for the caption under the phone (harness.phone_push.mode())."""
    dp = _demo_phone()
    if dp is None:
        return "off"
    return "real" if dp.mode()[0] == "live" else "dry"


def what_if(acc: str, edits: dict) -> dict:
    """Re-score with Model A (score_account), re-pick with tm-offers' real chooser. Never raises."""
    out = {"p": None, "risks": [], "action": None, "why": None, "via": None, "error": None, "res": None}
    try:
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from harness.churn_scorer import score_account
        f = data["features"].df
        row = f[f.account_id == acc].iloc[0].to_dict()
        row.update(edits)
        out["p"], out["risks"], _stays = score_account(row)
    except Exception as e:  # noqa: BLE001
        print(f"[tm-ui] re-score unavailable: {type(e).__name__}: {e}")
        out["error"] = "Live re-score isn't available on this machine (saved model inputs missing)."
        return out
    try:
        api = offer_api()
        er = api.prepared_row(acc)
        for k, v in edits.items():
            if k in er.index:
                er[k] = v
        res = api.choose_offer(er, out["p"])
        out.update(res=res, action=res["action_code"], why=res.get("why_this_offer"), via="harness.offer_api.choose_offer")
    except Exception as e:  # noqa: BLE001
        try:  # older engine without offer_api: same chooser functions, called directly
            O, cat, frame = engine()
            er = frame.loc[acc].copy()
            er["account_id"] = acc
            for k, v in edits.items():
                if k in er.index:
                    er[k] = v
            er["p_churn_90d"] = out["p"]
            ev = O.evaluate_account(er, cat["promotions"], cat["plans"])
            a = O.pick(ev["res"])[0]
            out.update(action=a, why=O.why_this_offer(a, er, ev), via="offers.evaluate_account + pick")
        except Exception as e2:  # noqa: BLE001
            print(f"[tm-ui] re-decide unavailable: {type(e).__name__}: {e} / {type(e2).__name__}: {e2}")
            out["error"] = "Live re-decide isn't available on this machine."
    return out


def key_facts(r, edits=None) -> str:
    """Verifiable facts straight from features.csv (synthetic), so the why-line can be checked on screen."""
    edits = edits or {}
    def n(c):
        try:
            return float(r.get(c))
        except (TypeError, ValueError):
            return float("nan")
    bits = []
    if pd.notna(n("support_270d")):
        sent = n("avg_sentiment")
        s90 = n("support_90d")
        sup = (f"{int(s90)} support contacts in 90 days ({int(n('support_270d'))} in 270)" if pd.notna(s90)
               else f"{int(n('support_270d'))} support contacts in 270 days")
        bits.append(f"{sup}, {int(n('unresolved_270d') or 0)} unresolved"
                    + (f", avg sentiment {sent:+.2f}" if pd.notna(sent) and n("support_270d") > 0 else ""))
    if pd.notna(n("port_out_inquiry")):
        bits.append("asked us about transferring their number" if n("port_out_inquiry") > 0 else "hasn't asked about transferring their number")
    if pd.notna(n("competitor_research_score")):
        bits.append("not comparing carriers" if "competitor_research_score" in edits
                    else f"shopping score {n('competitor_research_score'):.2f}")
    if pd.notna(n("bill_change_3m_pct")):
        bits.append(f"bill {n('bill_change_3m_pct'):+.0%} vs prior 3 mo")
    return "Facts: " + " · ".join(bits) + " (synthetic)" if bits else ""


FEATURE_LABELS = {  # churn model column -> (plain label, signal type)
    "extra_lines": ("Extra lines on the account", "Commerce"), "tenure_capped60": ("Time with T-Mobile", "Customer"),
    "app_sessions_30d": ("App use, last 30 days", "Real-time"), "financing_ends_within_3m": ("Phone paid off within 3 months", "Commerce"),
    "is_byod": ("Bring-your-own phone", "Commerce"), "neg_sentiment": ("Negative support sentiment", "Customer"),
    "cancel_inquiries_270d": ("Asked about cancelling", "Customer"), "short_history": ("Short account history", "Customer"),
    "has_home_internet": ("Home Internet bundle", "Commerce"), "low_app_use": ("Rarely uses the app", "Real-time"),
    "plan_misfit_share": ("Plan doesn't fit usage", "Commerce"), "port_out_inquiry": ("Asked us about transferring their number", "Real-time"),
    "early_tenure": ("First year with us", "Customer"), "promo_expired_recent": ("Promo just ended", "Commerce"),
    "max_device_age_months": ("Phone age", "Commerce"), "troubled_4plus": ("4+ support contacts", "Customer"),
    "bill_increase_pct": ("Bill went up", "Commerce"), "unresolved_90d": ("Unresolved support, 90 days", "Customer"),
    "competitor_research_score": ("Comparing carriers", "Real-time"),
    "negative_contacts_90d": ("Unhappy support contacts, 90 days", "Customer"),
}
TYPE_COLOR = {"Commerce": "#6E6873", "Customer": "#6E6873", "Real-time": "#6E6873"}


@st.cache_resource(show_spinner=False)
def _live_contributions():
    """Fallback when churn_contributions.csv isn't in the data folder: the scorer's own logistic regression."""
    import numpy as np  # noqa: F401
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from harness import churn_scorer as cs
    from harness.churn_features import prepare
    stt = cs._load()
    m, feats = stt["model"], stt["feats"]
    X = prepare(feats)
    C = m.contributions(X)
    C.insert(0, "intercept_logit", m.intercept_)
    C.index = feats["account_id"].values
    return C


def contributions_for(acc: str):
    cc = data["churn_contributions"]
    if cc.source == "real" and len(cc.df):
        row = cc.df[cc.df.account_id == acc]
        if len(row):
            return row.iloc[0].drop(labels=["account_id"]).astype(float), "saved"
    try:
        C = _live_contributions()
        if acc in C.index:
            return C.loc[acc].astype(float), "live"
    except Exception as e:  # noqa: BLE001
        print(f"[tm-ui] explanation unavailable: {type(e).__name__}: {e}")
    return None, None


def score_panel(acc: str, p_now: float, kp: str = ""):
    import numpy as np
    import plotly.graph_objects as go
    st.markdown("**Why this score?** How each signal pushes this customer's churn risk up or down",
                help="The churn risk model is a logistic regression. Each bar = how much risk changes if that one "
                     "signal were at the typical customer's level instead (coefficient × standardized value, "
                     "shown in percentage points). Synthetic.")
    cr, src = contributions_for(acc)
    if cr is None:
        st.caption("Explanation unavailable on this machine.")
        return
    b0 = float(cr.pop("intercept_logit"))
    logit = b0 + float(cr.sum())
    sig = lambda z: 1 / (1 + np.exp(-z))  # noqa: E731
    p = sig(logit)
    d = pd.DataFrame({"feat": cr.index, "c": cr.values})
    d["pts"] = [(p - sig(logit - c)) * 100 for c in d.c]
    d = d.reindex(d.pts.abs().sort_values(ascending=False).index).head(6)
    d = d[d.pts.abs() >= 0.005]
    d["label"] = [f"{FEATURE_LABELS.get(f, (f.replace('_', ' '), 'Commerce'))[0]}  ·  "
                  f"{FEATURE_LABELS.get(f, ('', 'Commerce'))[1]}" for f in d.feat]
    d["type"] = [FEATURE_LABELS.get(f, ("", "Commerce"))[1] for f in d.feat]
    d = d.iloc[::-1]
    fig = go.Figure(go.Bar(x=d.pts, y=d.label, orientation="h",
                           marker_color=[(MAGENTA if v > 0 else "#A39DA6") for v in d.pts],
                           text=[f"{v:+.2f} pts" for v in d.pts], textposition="outside", cliponaxis=False))
    fig.add_vline(x=0, line_color="#D6CEC4", line_width=1)
    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', template="tm_light", height=60 + 34 * max(1, len(d)), margin=dict(l=8, r=60, t=4, b=4),
                      xaxis_title="change in 90-day churn risk, percentage points (synthetic)", yaxis_title=None,
                      font=dict(size=12))
    st.plotly_chart(fig, use_container_width=True, theme=None, key=f"{kp}why_{acc}")
    st.caption(f"Typical customer: {fmt_prob(sig(b0))} · this customer: {fmt_prob(p_now)}. "
               "Magenta raises risk, grey lowers it. Tags: Commerce / Customer / Real-time. Synthetic.")


def send_button(body: str, key: str):
    """'Send to my phone': one click = one call. Body is the exact engine text shown on the phone mockup.
    harness.phone_push dry-runs unless TM_SEND_LIVE=1 and NTFY_TOPIC are set; topic is masked on screen.
    The app never passes a customer number, address or topic."""
    dp = _demo_phone()
    if dp is None:
        st.button("📲 Send to my phone", key=f"send_{key}", disabled=True)
        return
    live = dp.mode()[0] == "live"
    clicked = st.button("📲 Send to my phone" + ("" if live else " (dry run)"), key=f"send_{key}")
    if clicked:  # st.button is True only on the rerun triggered by this click
        acc, _, lang = key.rpartition("_")
        res = dp.send_to_my_phone(body, account_id=acc.split("_", 1)[-1], lang=lang)
        st.session_state[f"sent_{key}"] = res
    res = st.session_state.get(f"sent_{key}")
    if res is None:
        return
    if res.get("sent"):
        st.success("Sent to the demo phone")
    elif res.get("ok"):
        st.info("Dry run: nothing was sent. This is exactly what would go out.")
    else:
        st.error(str(res.get("detail") or "Send failed"))
    pv = res.get("preview")
    if pv:
        with st.expander("What goes to the phone", expanded=not res.get("sent")):
            st.markdown(f"**To:** ntfy push, topic {pv['topic_masked']} (demo phone only)  \n"
                        f"**Length:** {pv['chars']} chars, plain text")
            st.code(pv["text"], language=None, wrap_lines=True)
            st.caption(str(res.get("detail", "")))


def ring(p, caption: str = "") -> str:
    """Churn risk as a plain number + thin bar on a 0-20% scale (so low risks stay visible)."""
    try:
        w = max(1.5, min(100.0, float(p) / 0.20 * 100))
    except (TypeError, ValueError):
        w = 0.0
    return (f"<div class='risk-card'><div class='risk-lbl'>Churn risk, 90 days <span class='risk-syn'>synthetic</span></div>"
            f"<div class='risk-num'>{fmt_prob(p)}</div>"
            f"<div class='risk-bar'><span style='width:{w:.1f}%'></span></div>"
            f"<div class='risk-scale'><span>0%</span><span>10%</span><span>20%+</span></div>"
            + (f"<div class='risk-was'>{html.escape(caption)}</div>" if caption else "") + "</div>")


def card(acc: str, story, fits: set, idx: int, kp: str = "", allow_send: bool = True):
    if acc not in set(df.account_id):
        st.warning(f"{acc} is not in the loaded data.")
        return
    r = df[df.account_id == acc].iloc[0]
    k = r.get("action_key", "do_nothing")
    title = PERSONAS.get(acc, "")
    badge = BADGES.get(acc, "")
    st.markdown(f"<div class='kicker'>Customer {idx} · {html.escape(story)}"
                + (f"<span class='badge'>{html.escape(badge)}</span>" if badge else "") + "</div>", unsafe_allow_html=True)
    h1, h2 = st.columns([3, 1])
    num = acc.rsplit("-", 1)[-1] if acc.startswith("ACC-PERSONA") else acc.replace("ACC-", "")
    h1.markdown(f"#### {html.escape(title) or 'Customer #' + num}  \n<span class='cid'>Customer #{num} (synthetic) · "
                f"{r.get('segment', '')} · "
                f"{int(r.get('tenure_months', 0) or 0) // 12} yrs with us</span>", unsafe_allow_html=True)
    risk_ph = h2.empty()
    risk_ph.markdown(ring(r.p_churn_90d), unsafe_allow_html=True,
                     help="Churn risk model: the single churn number used on every screen (synthetic).")
    why_ph = st.empty()
    warn_ph = st.empty()
    left, right = st.columns([2.4, 1])
    with left:
        dec_ph = st.empty()
        chips_ph = st.empty()
        facts_ph = st.empty()
        opt_hdr, tbl_ph = st.empty(), st.empty()
        st.markdown("**What if?** Switch a fact off and our models re-decide live.")
        rel = [(key, lab, ed) for key, lab, cond, ed in TOGGLES if cond(r)]
        if not rel:
            st.caption("Nothing to switch off: no open tickets, hasn't asked about transferring their number, not comparing carriers.")
        edits = {}
        cols = st.columns(max(1, len(rel)))
        for (key, lab, ed), c in zip(rel, cols):
            if not c.toggle(lab, value=True, key=f"{kp}t_{acc}_{key}"):
                edits.update(ed)
        w = what_if(acc, edits) if edits else None
        res = (w or {}).get("res") or None
        if w is not None:
            if w["p"] is None:
                st.markdown(f"<div class='whatif'>{html.escape(w['error'])}</div>", unsafe_allow_html=True)
            else:
                risk_ph.markdown(ring(w["p"], f"(what-if, was {fmt_prob(r.p_churn_90d)})"), unsafe_allow_html=True,
                                 help="What-if: re-scored live by the churn risk model with the switched-off facts removed (synthetic).")
                line = f"Risk {fmt_prob(r.p_churn_90d)} → <b>{fmt_prob(w['p'])}</b>"
                if w["action"]:
                    na = normalize_action(w["action"])
                    line += f" · decision {'flips to' if na != normalize_action(k) else 'stays'} <b>{html.escape(action_label(na))}</b>"
                else:
                    line += f" · {html.escape(w['error'] or '')}"
                st.markdown(f"<div class='whatif'>{line}</div>", unsafe_allow_html=True)
                st.caption("Live: the churn risk model re-scores, then the offer engine re-decides. Synthetic.")
    # fill the placeholders from the live result if a toggle is on, else from offers.csv
    risks = [r.get(f"risk_reason_{i}") for i in (1, 2, 3)]
    stays, _dropped = clean_stays(r)
    if w and w.get("p") is not None and w.get("risks"):
        risks = w["risks"]
        rr = r.copy()
        for kk, vv in edits.items():
            rr[kk] = vv
        for i in (1, 2, 3):
            rr[f"risk_reason_{i}"] = risks[i - 1] if i <= len(risks) else None
        stays, _dropped = clean_stays(rr)
    rr_now = r.copy()
    for kk, vv in edits.items():
        rr_now[kk] = vv
    facts_ph.caption(key_facts(rr_now, edits))
    if "port_out_inquiry" in edits:
        risks = [x for x in risks if not (isinstance(x, str) and re.search(r"porting|transferring their number", x, re.I))]
        stays = ["Hasn't asked about transferring their number"] + [x for x in stays if "transferring" not in str(x)]
    if "competitor_research_score" in edits:
        risks = [x for x in risks if not (isinstance(x, str) and re.search(r"shopping other carriers|comparing carriers", x, re.I))]
        stays = ["Not comparing carriers"] + [x for x in stays if "shopping" not in str(x).lower() and "comparing" not in str(x).lower()]
    chips = "".join(chip(x, "risk") for x in risks if isinstance(x, str) and x)
    chips += "".join(chip(x, "stay") for x in stays)
    chips_ph.markdown(chips + LEGEND, unsafe_allow_html=True)
    k_now = normalize_action(w["action"]) if (w and w.get("action")) else k
    why = (w.get("why") if (w and w.get("why")) else
           (r.get("why_this_offer") if isinstance(r.get("why_this_offer"), str) else str(r.get("reason", ""))))
    why_ph.markdown(f"<div class='why'>{html.escape(clean_text(why))}</div>", unsafe_allow_html=True)
    if fits and not edits and normalize_action(k) not in {normalize_action(x) for x in fits}:
        warn_ph.error(f"Engine picked **{action_label(k)}**, which doesn't match this card's story ({story}).")
    dec_ph.markdown(f"<span class='decision'>Decision: {html.escape(action_label(k_now))}"
                    + (" <i>(what-if)</i>" if edits and w and w.get("action") else "") + "</span>", unsafe_allow_html=True)
    if res is not None:
        cand = res["candidates"].copy()
        cand["account_id"] = acc
        tbl, tip = options_table(acc, cand, res.get("message_en"))
    else:
        tbl, tip = options_table(acc)
    opt_hdr.markdown("**Why this offer? Every option we considered**" + ("  _(what-if)_" if res is not None else ""),
                     help="Net value to us = simulated saved margin − cost − annoyance, using our assumed acceptance "
                          "rates. Synthetic.")
    if len(tbl):
        # HTML table so long "Why not" text wraps instead of being cut off
        _t = tbl.rename(columns={"Cost to T-Mobile": "Cost to us", "Customer": "Customer saves / pays"})
        _h = _t.to_html(index=False, escape=True, classes="opts", border=0)
        _rows = _h.split("<tr>")
        _h = _rows[0] + "".join(("<tr class='won'>" if "✅ Won" in x else "<tr class='blocked'>" if "<td>Blocked</td>" in x else "<tr>") + x
                                for x in _rows[1:])
        tbl_ph.markdown(_h, unsafe_allow_html=True)
    else:
        tbl_ph.caption("Option list not available.")
    with right:
        lang_default = "es" if str(r.get("language", "en")) == "es" else "en"
        lang = st.radio("Text language", ["en", "es"], index=["en", "es"].index(lang_default), horizontal=True,
                        format_func=lambda x: {"en": "English", "es": "Español"}[x], key=f"{kp}lang_{acc}")
        msg = res.get(f"message_{lang}") if res is not None else r.get(f"message_{lang}")
        msg = msg.strip() if (k_now != "do_nothing" and isinstance(msg, str) and msg.strip()) else None
        st.markdown(phone(msg, lang), unsafe_allow_html=True)
        if msg and allow_send and res is None:
            send_button(msg, f"{kp}{acc}_{lang}")
        elif not msg:
            st.info("No text is sent to this customer: the offer engine chose to wait." if k_now == "do_nothing"
                    else "No text is sent to this customer.", icon="🤫")
        st.caption(("What-if text from the offer engine." if res is not None else "The exact text the offer engine wrote.")
                   + " " + {"dry": "Rehearsal mode: the button shows what would be sent, nothing is sent.",
                            "real": "Live: sends this exact text to the demo phone.",
                            "off": "Phone sending not set up."}[sms_state()])
    sp, _gap = st.columns([2.4, 1])
    with sp:
        score_panel(acc, float(r.p_churn_90d), kp)


with tab2:
    top_c = st.container()
    st.markdown("### Four customers, four different right answers")
    st.caption("Same pipeline, different decision for each customer, including staying silent. All synthetic.")
    for i, (acc, story, fits) in enumerate(CARDS, 1):
        with st.container(border=True):
            card(acc, story, fits, i)
    with st.expander("More account plan fits (synthetic)"):
        mcols = st.columns(2)
        for mc, macc in zip(mcols, ("ACC-PERSONA-05",)):
            mr = df[df.account_id == macc]
            if not len(mr):
                continue
            mr = mr.iloc[0]
            with mc, st.container(border=True):
                num = macc.rsplit("-", 1)[-1]
                st.markdown(f"**{html.escape(PERSONAS.get(macc, 'Customer #' + num))}**  \n"
                            f"<span class='cid'>Customer #{num} (synthetic) · {action_label(mr.get('action_key'))}</span>",
                            unsafe_allow_html=True)
                st.markdown(f"<div class='why' style='font-size:1.1rem'>{html.escape(clean_text(mr.get('why_this_offer', '')))}</div>",
                            unsafe_allow_html=True)
                me = str(mr.get("message_en") or "")
                m1 = re.search(r"\$(\d+)/month instead of \$(\d+)", me)
                m2 = re.search(r"pay \$(\d+)/month less", me)
                if m1:
                    st.markdown(f"Saves **${int(m1.group(2)) - int(m1.group(1))}/mo** (${m1.group(2)} → ${m1.group(1)})")
                elif m2:
                    st.markdown(f"Saves **${m2.group(1)}/mo**")
                st.markdown(phone(me.strip() or None, "en"), unsafe_allow_html=True)
                if me.strip() and mr.get("action_key") != "do_nothing" and macc != "ACC-PERSONA-39":
                    send_button(me.strip(), f"mx_{macc}_en")

    st.markdown("### Open any customer")
    _lk = df.sort_values("risk_rank")
    _labels = {a: f"Customer {a.rsplit('-', 1)[-1] if a.startswith('ACC-PERSONA') else a.replace('ACC-', '').lstrip('0')}"
                  f"{' (test persona)' if a.startswith('ACC-PERSONA') else ''} · {seg} · risk {fmt_prob(p)}"
               for a, seg, p in zip(_lk.account_id, _lk.get("segment", pd.Series("", index=_lk.index)), _lk.p_churn_90d)}
    SHORTLIST = ["ACC-PERSONA-38", "ACC-PERSONA-04", "ACC-PERSONA-21", "ACC-PERSONA-24", "ACC-PERSONA-05"]
    full = st.checkbox(f"Search all {len(_labels):,}", key="lookup_all")
    opts = list(_labels) if full else [a for a in SHORTLIST if a in _labels]
    pick = st.selectbox("Customer (type to filter by number, segment or risk)", [None] + opts,
                        format_func=lambda a: "Pick a customer…" if a is None else _labels[a],
                        key="lookup_full" if full else "lookup_short")
    if pick:
        with st.container(border=True):
            if pick not in SHORTLIST:
                st.caption("Not pre-checked for the demo (synthetic).")
            card(pick, "Customer lookup", set(), 0, kp="lk_", allow_send=pick in SHORTLIST)
    bottom_c = st.container()

# ---------------- How it decides: band (top of first tab) + across-all charts (end) ----------------
with top_c:
    import plotly.express as px
    import plotly.graph_objects as go
    D = df.copy()
    nonp_p = NONP.p_churn_90d
    cut = float(nonp_p.quantile(0.90)) if len(nonp_p) else 1.0
    D["flagged"] = D.p_churn_90d >= cut
    D["contact"] = D.get("action_key", pd.Series("do_nothing", index=D.index)) != "do_nothing"
    has_msg = D.get("message_en", pd.Series("", index=D.index)).fillna("").astype(str).str.strip() != ""
    D["msg"] = D.contact & has_msg
    n_acc, n_flag, n_msg = len(D), int(D.flagged.sum()), int(D.msg.sum())
    n_dn = int((~D.contact).sum())
    n_msg_nonflag = int((D.msg & ~D.flagged).sum())
    lab = data["labels"].df
    catch, auc, catch_src = None, None, ""
    if len(lab) and "churn_90d" in lab:
        oof = data["churn_oof_pred"]
        src = oof.df if oof.source == "real" else NONP[["account_id", "p_churn_90d"]]
        catch_src = "held-out (out-of-fold)" if oof.source == "real" else "in-sample"
        j = src.merge(lab[["account_id", "churn_90d"]], on="account_id")
        j = j[~j.account_id.astype(str).str.startswith("ACC-PERSONA")].sort_values("p_churn_90d", ascending=False)
        catch = j.head(int(len(j) * 0.10)).churn_90d.sum() / max(1, j.churn_90d.sum())
        try:
            from sklearn.metrics import roc_auc_score
            auc = roc_auc_score(j.churn_90d, j.p_churn_90d)
        except Exception:  # noqa: BLE001
            auc = None
    # ================= End-to-end process band (one screen explains the pipeline) =================
    n_contact = int(D.contact.sum())
    st.markdown(
        "<div class='hero'><div class='hero-eyebrow'>Next Best Moment · churn risk model + offer engine · synthetic</div>"
        "<h1>One engine decides who gets a text, what it says, and <em>when to stay silent</em>.</h1>"
        "<div class='hero-stats'>"
        f"<div class='hero-stat'><div class='hero-num'>{n_acc:,}</div><div class='hero-lbl'>synthetic accounts scored</div></div>"
        f"<div class='hero-stat'><div class='hero-num'>{n_flag:,}</div><div class='hero-lbl'>flagged at risk (top 10%)</div></div>"
        f"<div class='hero-stat'><div class='hero-num'>{n_msg:,}</div><div class='hero-lbl'>texts ready, English/Spanish</div></div>"
        f"<div class='hero-stat'><div class='hero-num'>{n_dn:,}</div><div class='hero-lbl'>left alone on purpose</div></div>"
        "</div></div>", unsafe_allow_html=True)
    st.markdown("#### How it works, end to end")
    _rr = NONP[NONP.p_churn_90d >= cut].risk_reason_1.fillna("").map(reason_category)
    top_drv = _rr[_rr != ""].value_counts().head(3)
    mix_top = D[D.contact].action_key.map(action_label).value_counts().head(4) if "action_key" in D else pd.Series(dtype=int)

    def _mini_bar(series, color, key):  # noqa: ARG001 (HTML bars so long labels stay readable)
        if not len(series):
            return
        mx = float(series.max()) or 1.0
        st.markdown("".join(
            f"<div class='sub' style='margin:3px 0 0'>{html.escape(str(lbl))} <b>{int(v):,}</b></div>"
            f"<div style='background:{color}; height:7px; border-radius:4px; width:{max(4, 100 * v / mx):.0f}%'></div>"
            for lbl, v in series.items()), unsafe_allow_html=True)

    def _bars(series, color):
        if not len(series):
            return ""
        mx = float(series.max()) or 1.0
        return "".join(f"<div class='brow'><span>{html.escape(str(lbl))}</span><b>{int(v):,}</b></div>"
                       f"<div class='bbar'><i style='width:{max(3, 100 * v / mx):.0f}%; background:{color}'></i></div>"
                       for lbl, v in series.items())
    catch_txt = TOP10_CLAIM.format(pct=f"{catch:.0%}") if catch is not None else ""
    st.markdown(
        "<div class='bento'>"
        "<div class='tile t1'><div class='step'>01 · Customer data</div>"
        f"<div class='big'>{n_acc:,}</div><div class='sub'>synthetic accounts</div>"
        "<div class='rows'><div class='trow'><span class='pill p-com'>Commerce</span><span>plan, bill, device</span></div>"
        "<div class='trow'><span class='pill p-cus'>Customer</span><span>support, sentiment, tenure</span></div>"
        "<div class='trow'><span class='pill p-rt'>Real-time</span><span>transfer questions, comparing carriers, app use</span></div></div></div>"
        "<div class='tile t2'><div class='step'>02 · Churn risk score</div>"
        f"<div class='big'>{n_flag:,}</div><div class='sub'>flagged: top 10% most likely to leave in 90 days</div>"
        f"<div class='note'>{html.escape(catch_txt)}</div></div>"
        "<div class='tile t3'><div class='step'>03 · Why this score</div><div class='sub'>Top drivers among flagged customers</div>"
        f"{_bars(top_drv, '#15111A')}</div>"
        "<div class='tile t4'><div class='step'>04 · Offer engine</div>"
        f"<div class='big'>{n_contact:,}</div><div class='sub'>get a text · {n_dn:,} left alone</div>{_bars(mix_top.head(3), '#A39DA6')}</div>"
        "<div class='tile t5 dark'><div class='step'>05 · Why this offer → message</div>"
        f"<div class='big'>0</div><div class='sub'>actually sent: this is a demo</div>"
        f"<div class='note'>{n_msg:,} English/Spanish texts ready</div></div>"
        "</div>", unsafe_allow_html=True)
    st.caption("Every eligible action is weighed, including doing nothing. Each ready text carries a plain-language reason. "
               "All numbers synthetic.")

    # ---- follow one customer through it ----
    FOLLOW = ["ACC-PERSONA-38", "ACC-PERSONA-04", "ACC-PERSONA-21", "ACC-PERSONA-24", "ACC-PERSONA-05"]
    FOLLOW = [a for a in FOLLOW if a in set(df.account_id)]
    if FOLLOW:
        fa = st.selectbox("Follow one customer through it", FOLLOW, index=0, key="follow",
                          format_func=lambda a: f"Customer #{a.rsplit('-', 1)[-1]} · {PERSONAS.get(a, '')} (synthetic)")
        fr = df[df.account_id == fa].iloc[0]

        def _v(c, kind="int"):
            v = fr.get(c)
            try:
                v = float(v)
            except (TypeError, ValueError):
                return "n/a"
            if pd.isna(v):
                return "n/a"
            return {"int": f"{int(round(v))}", "pct": f"{v:+.0%}", "f2": f"{v:.2f}", "usd": f"${v / 100:,.0f}",
                    "yn": "yes" if v > 0 else "no"}[kind]
        plan = str(fr.get("plan_sku", "")).replace("TMO-STUB-PLAN-", "").replace("-", " ").title()
        f1 = ("<div class='ft'><span class='pill p-com'>Commerce</span>"
              f"<div>{html.escape(plan)} · {_v('n_lines')} lines · bill {_v('last_bill_cents', 'usd')} ({_v('bill_change_3m_pct', 'pct')}) · phone {_v('max_device_age_months')} mo</div></div>"
              "<div class='ft'><span class='pill p-cus'>Customer</span>"
              f"<div>{_v('support_270d')} support contacts (270d), {_v('unresolved_270d')} unresolved · sentiment {_v('avg_sentiment', 'f2')} · {_v('tenure_months')} mo tenure</div></div>"
              "<div class='ft'><span class='pill p-rt'>Real-time</span>"
              f"<div>asked about transferring number: {_v('port_out_inquiry', 'yn')} · comparing carriers {_v('competitor_research_score', 'f2')} · {_v('app_sessions_30d')} app sessions/30d</div></div>")
        flagged = float(fr.p_churn_90d) >= cut
        f2 = (f"<div class='big' style='color:{MAGENTA}'>{fmt_prob(fr.p_churn_90d)}</div><div class='sub'>90-day churn risk · rank "
              f"#{int(fr.risk_rank):,} of {n_acc:,} · {'flagged' if flagged else 'not flagged'}</div>")
        cr, _src = contributions_for(fa)
        if cr is not None:
            import numpy as np
            b0 = float(cr.pop("intercept_logit")); lg = b0 + float(cr.sum()); sg = lambda z: 1 / (1 + np.exp(-z))  # noqa: E731,E702
            pts = pd.Series({f: (sg(lg) - sg(lg - c)) * 100 for f, c in cr.items()})
            top = pts.reindex(pts.abs().sort_values(ascending=False).index).head(3)
            f3 = "".join(
                f"<div class='ft'><span class='pill {PILL[FEATURE_LABELS.get(f, ('', 'Commerce'))[1]]}'>{FEATURE_LABELS.get(f, ('', 'Commerce'))[1]}</span>"
                f"<div>{html.escape(FEATURE_LABELS.get(f, (f, ''))[0])} <b style='color:{MAGENTA if v > 0 else '#6E6873'}'>{v:+.2f} pts</b></div></div>"
                for f, v in top.items()) + f"<div class='sub'>vs typical customer {fmt_prob(sg(b0))}</div>"
        else:
            f3 = "".join(chip(x, "risk") for x in [fr.get(f"risk_reason_{i}") for i in (1, 2, 3)] if isinstance(x, str) and x)
        f4 = ""
        tbl_f, _tip = options_table(fa)
        if len(tbl_f):
            won = tbl_f[tbl_f.Result.str.contains("Won")]
            n_el = int((tbl_f.Result != "Blocked").sum())
            lost = tbl_f[tbl_f.Result == "Lost"].head(1)
            f4 = (f"<div class='fw'>{html.escape(won.Option.iloc[0] if len(won) else action_label(fr.get('action_key')))}</div><div class='sub'>wins"
                  + (f" · net value to us {won['Net value to us (simulated)'].iloc[0]} (simulated)" if len(won) else "") + "</div>"
                  + f"<div class='sub'>{n_el} eligible options weighed"
                  + (f"; runner-up {html.escape(lost.Option.iloc[0])}" if len(lost) else "") + "</div>")
        m_ = fr.get("message_es" if str(fr.get("language")) == "es" else "message_en")
        f5 = f"<div class='fq'>{html.escape(clean_text(fr.get('why_this_offer', '')))}</div>"
        if fr.get("action_key") != "do_nothing" and isinstance(m_, str) and m_.strip():
            f5 += f"<div class='bubble sm'>{html.escape(m_.strip())}</div>"
        else:
            f5 += "<div class='sub'>🤫 No message sent: we decided to wait.</div>"
        st.markdown("<div class='follow'>" + "".join(
            f"<div class='tile'><div class='step'>{lab}</div>{body}</div>" for lab, body in
            (("Data", f1), ("Score", f2), ("Why", f3), ("Decision", f4), ("Message", f5))) + "</div>", unsafe_allow_html=True)
    st.markdown("<div style='text-align:center;font-size:1.05rem;margin:.4rem 0 1rem'>⬇ <b>Step 5 in full:</b> "
                "Customer #38's card is right below, then three more customers (synthetic).</div>", unsafe_allow_html=True)
with bottom_c:
    st.divider()
    st.markdown(f"#### Across all {n_acc:,} customers")
    k = st.columns(6)
    k[0].metric("Accounts", f"{n_acc:,}", help="Judge sandbox accounts incl. 42 personas (synthetic).")
    k[1].metric("Flagged at-risk", f"{n_flag:,}", help=f"Churn risk ≥ {fmt_prob(cut)}: the top 10% of regular accounts (synthetic).")
    k[2].metric("Top-10% catch", f"{catch:.0%}" if catch is not None else "n/a",
                help=(TOP10_CLAIM.format(pct=f"{catch:.0%}") if catch is not None else "")
                     + f" Scores: {catch_src}, against simulated outcomes. Not a measure of real-world accuracy.")
    k[3].metric("Messages ready", f"{n_msg:,}", help="Accounts with an action and an EN/ES text ready (synthetic).")
    k[4].metric("Do nothing", f"{n_dn:,}", help="Accounts we deliberately leave alone (synthetic).")
    k[5].metric("Texts, not at risk", f"{n_msg_nonflag:,}",
                help="Customers below the risk flag who still get a text: money-saving, fix-first, or a plan upgrade (synthetic).")
    try:
        from streamlit_extras.metric_cards import style_metric_cards
        style_metric_cards(border_left_color="#E6E0D8", background_color="#FFFFFF", border_color="#E6E0D8", border_radius_px=16, box_shadow=False)
    except Exception:  # noqa: BLE001
        pass

    g1, g2 = st.columns(2)
    with g1, st.container(border=True):
        st.markdown("**From 5,000+ accounts to a handful of texts**")
        STEP = {"step_up", "step_up_plan"}
        D["upsell_nf"] = ~D.flagged & D.action_key.isin(STEP) if "action_key" in D else False
        fo = int((D.flagged & D.contact).sum()); fd = int((D.flagged & ~D.contact).sum())
        su = int(D.upsell_nf.sum())
        # "usage-based" only if EVERY step-up to a not-at-risk customer states a usage reason in offers.csv `reason`
        _usage_re = r"data cap|hotspot|near (?:their|the) (?:data )?(?:limit|cap)|over (?:the |their )?(?:plan )?(?:data )?cap|usage|\bGB\b"
        _ur = D.loc[D.upsell_nf, "reason"].fillna("").astype(str) if "reason" in D else pd.Series(dtype=str)
        UPS = "Plan upgrades, usage-based" if su and _ur.str.contains(_usage_re, case=False, regex=True).all() else "Plan upgrades"
        no = int((~D.flagged & D.contact & ~D.upsell_nf).sum()); nd = int((~D.flagged & ~D.contact).sum())
        m3 = int((D.msg & ~D.upsell_nf).sum()); m4 = int((D.msg & D.upsell_nf).sum())
        mo = m3 + m4
        labels_ = [f"All accounts {n_acc:,}", f"Flagged at-risk {n_flag:,}", f"Not flagged {n_acc - n_flag:,}",
                   f"Offer / contact {fo + no:,}", f"{UPS} {su:,}", f"Do nothing {fd + nd:,}",
                   f"Text ready {mo:,}"]
        fig = go.Figure(go.Sankey(
            node=dict(label=labels_, pad=18, thickness=16,
                      color=["#A39DA6", "#D6CEC4", "#A39DA6", "#A39DA6", "#D6CEC4", "#D6CEC4", MAGENTA]),
            link=dict(source=[0, 0, 1, 1, 2, 2, 2, 3, 4], target=[1, 2, 3, 5, 3, 4, 5, 6, 6],
                      value=[n_flag, n_acc - n_flag, fo, fd, no, su, nd, m3, m4],
                      color=["rgba(21,17,26,.08)"] * 9)))
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', template="tm_light", height=380, margin=dict(l=8, r=8, t=8, b=8), font=dict(size=13, color="#15111A"))
        st.plotly_chart(fig, use_container_width=True, theme=None)
        st.caption(f"Why more texts ({mo:,}) than flags ({n_flag:,}): customers who aren't at risk still get a text when "
                   f"it helps them: {no:,} money-saving or fix-first contacts, plus {su:,} {UPS.lower()}"
                   + (" (near their data cap or using hotspot)" if "usage" in UPS else "")
                   + f". {fd:,} flagged customers get nothing because no offer is worth it. Synthetic.")
    with g2, st.container(border=True):
        st.markdown("**What we decided for each account**")
        if "action_key" in D:
            D["mix_label"] = D.action_key.map(action_label)
            D.loc[D.upsell_nf, "mix_label"] = f"{UPS} (not at risk)"
            mix = D.groupby("mix_label").size().reset_index(name="accounts").rename(columns={"mix_label": "action"})
            mix["kind"] = mix.action.map(lambda a: "Do nothing" if a == action_label("do_nothing")
                                         else ("Upsell" if a.startswith("Plan upgrades") else "Contact"))
            fig = px.bar(mix.sort_values("accounts"), x="accounts", y="action", orientation="h", color="kind",
                         color_discrete_map={"Do nothing": "#D6CEC4", "Contact": "#15111A", "Upsell": "#6E6873"}, template="tm_light",
                         text="accounts")
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=380, margin=dict(l=8, r=40, t=8, b=8), showlegend=False,
                              xaxis_title="accounts (synthetic)", yaxis_title=None,
                              xaxis=dict(range=[0, float(mix.accounts.max()) * 1.15]))
            fig.update_traces(textposition="outside", cliponaxis=False)
            st.plotly_chart(fig, use_container_width=True, theme=None)
    with st.container(border=True):
        st.markdown("**Same assumptions, different strategies (simulated)**")
        src_dir = Path(data["offers"].path).parent if data["offers"].path else REPO / "demo_data"
        cp = src_dir / "comparison.csv" if (src_dir / "comparison.csv").exists() else None
        same_run, n_ours, n_ours_cmp = True, int(D.contact.sum()), None
        if cp is not None:
            try:
                _c = pd.read_csv(cp)
                _o = _c[_c.strategy.str.contains("Ours") & ~_c.strategy.astype(str).str.match(r"^\s*\d+[a-z]\.")]
                n_ours_cmp = int(_o.contacted.iloc[0]) if len(_o) else None
                same_run = n_ours_cmp is None or n_ours_cmp == n_ours
            except Exception:  # noqa: BLE001
                same_run = False
        if cp is not None and not same_run:
            st.warning(f"comparison pending: it was built from a different engine run "
                       f"({n_ours_cmp:,} contacts for 'Ours') than the decisions shown here ({n_ours:,}). "
                       "Not mixing runs.", icon="⏳")
        elif cp is not None:
            try:
                cmp_ = pd.read_csv(cp)
                cmp_ = cmp_[~cmp_.strategy.astype(str).str.match(r"^\s*\d+[a-z]\.")]  # drop variant rows like 5b
                cmp_["Strategy"] = cmp_.strategy.str.replace(r"^\d+\.\s*", "", regex=True).map(clean_text)
                cmp_["ours"] = cmp_.Strategy.str.startswith("Ours")
                ca, cb = st.columns([1.1, 1])
                with ca:
                    fig = px.bar(cmp_, x="net_value_usd", y="Strategy", orientation="h", template="tm_light",
                                 color="ours", color_discrete_map={True: MAGENTA, False: "#D6CEC4"},
                                 text=cmp_.net_value_usd.map(lambda v: f"${v:,.0f}"))
                    fig.add_vline(x=0, line_color="#D6CEC4", line_width=1)
                    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=300, margin=dict(l=8, r=8, t=8, b=8), showlegend=False,
                                      xaxis_title="simulated net value, $ (synthetic)", yaxis_title=None,
                                      yaxis=dict(autorange="reversed"))
                    fig.update_traces(textposition="inside", insidetextanchor="middle", textfont_color="white")
                    st.plotly_chart(fig, use_container_width=True, theme=None)
                with cb:
                    st.dataframe(pd.DataFrame({
                        "Contacts to low-risk customers": cmp_[next(c for c in ("contacts_to_low_risk", "unneeded_contacts") if c in cmp_)].astype(int),
                        "Credits $": cmp_.credit_spend_usd.map(lambda v: f"${v:,.0f}"),
                        "Strategy": cmp_.Strategy, "Churners reached": cmp_.churners_reached.astype(int),
                        "Net value (simulated)": cmp_.net_value_usd.map(lambda v: f"${v:,.0f}")}),
                        hide_index=True, width="stretch")
                    st.caption("All synthetic. Contacts to low-risk customers = people contacted who weren't going to churn.")
            except Exception as e:  # noqa: BLE001
                st.caption(f"comparison pending ({type(e).__name__})")
        else:
            st.caption("comparison pending")
        st.caption("Scored with our assumed acceptance rates; we don't claim lift until a holdout test.")
    g3, g4 = st.columns(2)
    with g3, st.container(border=True):
        st.markdown("**Churn risk across accounts**")
        h = NONP.assign(pct=NONP.p_churn_90d * 100)
        fig = px.histogram(h, x="pct", nbins=60, template="tm_light", color_discrete_sequence=["#A39DA6"])
        fig.add_vline(x=cut * 100, line_color="#15111A", line_width=2, annotation_text=f"flag: top 10% (≥ {fmt_prob(cut)})",
                      annotation_position="top right", annotation_font_color="#15111A")
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=330, margin=dict(l=8, r=8, t=8, b=8), xaxis_title="90-day churn risk, % (synthetic)",
                          yaxis_title="accounts", bargap=0.05)
        st.plotly_chart(fig, use_container_width=True, theme=None)
        st.caption(f"Most customers are low risk; the average is {fmt_prob(nonp_p.mean())}. Synthetic.")
    with g4, st.container(border=True):
        uw = APP / "charts" / "06_upgrade_or_wait.png"
        if SHOW_UPGRADE_WAIT and uw.exists():
            st.markdown("**Upgrade now or wait?**")
            st.image(str(uw), use_container_width=True)
            st.caption("Trade-in value vs remaining phone balance. Synthetic.")
        else:
            st.markdown("**Top reason each flagged customer is at risk**")
            fl = D[D.flagged & ~D.account_id.astype(str).str.startswith("ACC-PERSONA")]
            rr = fl.risk_reason_1.fillna("").map(reason_category)
            t = rr[rr != ""].value_counts().head(8).reset_index()
            t.columns = ["reason", "accounts"]
            fig = px.bar(t.sort_values("accounts"), x="accounts", y="reason", orientation="h", template="tm_light",
                         color_discrete_sequence=["#15111A"], text="accounts")
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=330, margin=dict(l=8, r=8, t=8, b=8), xaxis_title="flagged accounts (synthetic)", yaxis_title=None)
            fig.update_traces(textposition="outside", cliponaxis=False)
            st.plotly_chart(fig, use_container_width=True, theme=None)
            st.caption("Top risk reason for the flagged top 10%. Synthetic.")

    with st.expander("Explore: drivers of churn and the at-risk list (synthetic)"):

        f, lab = data["features"].df, data["labels"].df
        fn = f[~f.account_id.astype(str).str.startswith("ACC-PERSONA")] if len(f) else f
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Expected 90-day churn", fmt_prob(NONP.p_churn_90d.mean()) if len(NONP) else "n/a",
                  help=f"Mean churn risk over {len(NONP):,} sandbox accounts, test personas excluded (synthetic). "
                       "The judge sandbox's raw toy score averages 14.6%.")
        oof = data["churn_oof_pred"]
        if len(lab) and "churn_90d" in lab:
            src = oof.df if oof.source == "real" else NONP[["account_id", "p_churn_90d"]]
            j = src.merge(lab[["account_id", "churn_90d"]], on="account_id")
            j = j[~j.account_id.astype(str).str.startswith("ACC-PERSONA")].sort_values("p_churn_90d", ascending=False)
            top = j.head(int(len(j) * 0.10))
            cap = top.churn_90d.sum() / max(1, j.churn_90d.sum())
            c2.metric("Churners caught in the riskiest 10%", f"{cap:.0%}",
                      help=("Held-out scores" if oof.source == "real" else "In-sample scores") + " vs simulated churn outcomes. Synthetic.")
        if "cancel_inquiries_270d" in fn:
            c3.metric("Asked about cancelling (270d)", f"{int((fn.cancel_inquiries_270d > 0).sum()):,} accounts",
                      help="Accounts with a cancellation inquiry in 270 days (synthetic)")
        if "promo_expired_recent" in fn:
            c4.metric("Promo expired recently", f"{int((fn.promo_expired_recent > 0).sum()):,} accounts",
                      help="Accounts whose promo credit recently ended (synthetic)")

        if len(fn) and len(lab) and "churn_90d" in lab:
            j = fn.merge(lab[["account_id", "churn_90d"]], on="account_id")
            parts = []
            for name, col, bins, labels in [
                ("Support contacts (90d)", "support_90d", [-1, 0, 2, 4, 999], ["0", "1-2", "3-4", "5+"]),
                ("Competitor research", "competitor_research_score", [-1, 0.25, 0.5, 0.75, 9], ["<0.25", "0.25-0.5", "0.5-0.75", "0.75+"]),
                ("Bill change (3 mo)", "bill_change_3m_pct", [-9, 0.0, 0.05, 99], ["flat / down", "up 0-5%", "up >5%"]),
                ("Asked us about transferring their number", "port_out_inquiry", [-1, 0, 9], ["no", "yes"]),
                ("Tenure", "tenure_months", [-1, 12, 36, 9999], ["<1 yr", "1-3 yrs", "3+ yrs"]),
            ]:
                if col in j:
                    g = j.groupby(pd.cut(j[col], bins, labels=labels), observed=True).churn_90d.agg(["mean", "size"]).reset_index()
                    g.columns = ["group", "rate", "n"]
                    g["driver"], g["churn_pct"] = name, g["rate"] * 100
                    parts.append(g)
            if parts:
                st.markdown("**What drives churn: synthetic 90-day churn rate by bucket**")
                t = pd.concat(parts)
                st.altair_chart(alt.Chart(t).mark_bar(color="#15111A").encode(
                    x=alt.X("churn_pct:Q", title="90-day churn % (synthetic labels)"),
                    y=alt.Y("group:N", title=None, sort=None),
                    row=alt.Row("driver:N", title=None, sort=None, header=alt.Header(labelAngle=0, labelAlign="left")),
                    tooltip=["driver", "group", alt.Tooltip("churn_pct:Q", format=".1f"), "n"]
                ).properties(height=alt.Step(16), width=520).resolve_scale(y="independent"))

        st.markdown("### Who's at risk this week")
        if len(df):
            n = st.slider("Show top", 5, min(200, len(df)), min(20, len(df)))
            v = df.sort_values("risk_rank").head(n)
            st.dataframe(pd.DataFrame({
                "Rank": v.risk_rank.astype(int), "Account": v.account_id, "Segment": v.get("segment", ""),
                "Risk (90d)": v.p_churn_90d.map(fmt_prob), "Top reason": v.risk_reason_1,
                "Decision": v.get("action_key", pd.Series(dtype=str)).map(action_label)}),
                hide_index=True, width="stretch", height=380)
            if "action_key" in df:
                dn = int((df.action_key == "do_nothing").sum())
                st.caption(f"{dn:,} of {len(df):,} accounts get no contact at all. Risk = churn risk model. "
                           "Note: texts also go to customers who aren't high-risk (money-saving and fix-first texts), "
                           "so the message count is not a subset of the flagged at-risk count. Synthetic.")


# ---------------- TAB 3: Pipeline visual ----------------
def _clean_pipeline_html(h: str) -> str:
    """Display-time wording fixes for the pre-built pipeline page (file itself untouched): honest top-10% claim,
    'account' not 'household', no internal model names / file names / port-out wording on screen."""
    claim = TOP10_CLAIM.format(pct="62%")
    for a, b in (
        ("held-out: top 10% catches 62%\\u003cbr\\u003eof churners (oracle 64%,\\u003cbr\\u003erule 53%) \\u00b7 AUC 0.853",
         "held-out synthetic: top 10% catches 62%\\u003cbr\\u003eof leavers (best possible 64.2%;\\u003cbr\\u003e"
         "recovers patterns built into the data)"),
        ("Held-out Model A: top 10% catches 62% of churners (oracle 64%, 3+ calls rule 53%), AUC 0.853.", claim),
        ("Model A = tm-churn churn_scores.csv (sandbox 5k) and scaled_scores/churn_scores.csv (50k). "
         "Model B = tm-offers offers.csv / offer_candidates.csv.", "All customers and numbers are synthetic."),
        (" // MODEL A = TM-CHURN CHURN_SCORES.CSV // MODEL B = TM-OFFERS OFFERS.CSV", ""),
        ("Model A = tm-churn churn_scores.csv \\u00b7 actions = Model B (tm-offers offers.csv) \\u00b7 "
         "column 4 = features.csv household segment", "Actions = offer engine \\u00b7 column 4 = account type"),
        ("Engine: Model A + Model B (tm-offers). Model A = tm-churn churn_scores.csv; save_rate, offer_cost, "
         "customer_value from offer_candidates.csv \\u002f offers.csv.", "Engine: churn risk model + offer engine."),
        ("Synthetic. Model A = tm-churn churn_scores.csv; flagged", "Synthetic. Flagged"),
        ("Actions = Model B (tm-offers offers.csv).", "Actions = offer engine."),
        ("Model A re-score (score_account) \\u00b7 action re-picked by tm-offers choose_offer()",
         "churn risk model re-scores \\u00b7 offer engine re-picks the action"),
        ("Model B's", "the offer engine's"), ("Model A", "churn risk model"), ("MODEL A", "CHURN RISK MODEL"),
        ("Model B", "offer engine"), ("MODEL B", "OFFER ENGINE"),
        ("HOUSEHOLD (offered)", "ACCOUNT TYPE (offered)"), ("household:", "account:"),
        ("no port-out inquiry", "hasn't asked about transferring their number"),
        ("remove port-out inquiry", "remove number-transfer question"),
        ("port out inquiry", "asked about transferring their number"), ("port-out", "number transfer"),
        ("scored (churn_scores.csv)", "scored"), ("upgrade model (upgrade_scores.csv)", "upgrade model"),
        ("offer engine, offers.csv)", "offer engine)"),
    ):
        h = h.replace(a, b)
    return re.sub(r"(?i)households", "accounts", re.sub(r"(?i)household", "account", h))


if tab3 is not None:
  with tab3:
      st.markdown('### Pipeline visual')
      viz = APP / "viz" / "pipeline_flow.html"
      st.caption("The whole system on one page: sandbox data → churn risk → every eligible action priced, "
                 "with do nothing as a real option → a text in their language. All synthetic.")
      if viz.exists():
          components.html(_clean_pipeline_html(viz.read_text(encoding="utf-8", errors="replace")), height=900, scrolling=True)
      else:
          st.info("Pipeline visual loading…")

st.divider()


def _run_label() -> str:
    """Plain-words run time for the provenance note (from the saved comparison notes, else the file time)."""
    import datetime as _dt
    src = Path(data["offers"].path).parent if data["offers"].path else None
    if src is not None and (src / "COMPARISON.md").exists():
        m = re.search(r"offers\.csv.*?mtime (\d{4}-\d{2}-\d{2} \d{2}:\d{2})", (src / "COMPARISON.md").read_text())
        if m:
            return _dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").strftime("%-I:%M %p") + " run"
    if data["offers"].path:
        return _dt.datetime.fromtimestamp(Path(data["offers"].path).stat().st_mtime).strftime("%-I:%M %p") + " run"
    return "no run loaded"


with st.expander("Data provenance", expanded=False):
    kind = "placeholder mock data" if MOCK else "synthetic sandbox data"
    st.markdown(f"**{kind.capitalize()}, {_run_label()}.** Judge-provided sandbox (5,000 synthetic accounts "
                "plus 42 test personas), our churn risk model and offer engine. No real customer data.")
    for n, lab_ in (("churn_scores", "Churn risk"), ("offers", "Decisions and texts"), ("features", "Customer signals"),
                    ("labels", "Simulated outcomes"), ("offer_candidates", "Options considered")):
        l = data[n]
        st.caption(f"{lab_}: " + {"real": "saved sandbox run", "mock": "placeholder mock", "missing": "not loaded"}[l.source])
st.caption("All customers and numbers are synthetic.")

# warm the live what-if path after the page has rendered (cached; runs once per server)
prewarm()
