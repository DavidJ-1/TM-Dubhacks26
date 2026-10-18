"""Orbit sections: a long-scroll board in four acts, ready to lift into the real app.

API (all data is passed in; this module never reads repo files except its own fonts in orbit_assets/):
    load_css()                                   inject fonts + page CSS once per run
    orbit_frame(merged, outreach=None, ...)      add flagged / messaged / channel / reason columns
    render_hero(df)                              act 1: every customer in 3D + funnel headline
    render_customer(df, account_id, ...)         act 2: six-step walk-through for one account
    render_dashboard(df, economics)              act 3: hairline stat grid, two charts, riskiest-ten (returns clicked id)
    render_considered(df_considerations)         act 4: what we considered (renders nothing for None)
"""
from __future__ import annotations

import base64
import html
import math
import re
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ASSETS = Path(__file__).resolve().parent / "orbit_assets"
BG, INK, MUTED, MAG, DOT = "#F6F3EE", "#111111", "#6B675F", "#E20074", "#B9B2A7"
FLAT = dict(ambient=1, diffuse=0, specular=0, fresnel=0, roughness=1)
CFG3D = {"displayModeBar": False, "scrollZoom": False}
PERSONA_PREFIX = "ACC-PERSONA-"
esc = html.escape


# ============================================================== theme
@st.cache_resource(show_spinner=False)
def _font_css() -> str:
    def b(f):
        return base64.b64encode((ASSETS / f).read_bytes()).decode()
    return (f"@font-face{{font-family:'SG';src:url(data:font/woff2;base64,{b('SpaceGrotesk-Variable-latin.woff2')}) format('woff2');font-weight:300 700}}"
            f"@font-face{{font-family:'SM';src:url(data:font/woff2;base64,{b('SpaceMono-Regular-latin.woff2')}) format('woff2');font-weight:400}}"
            f"@font-face{{font-family:'SM';src:url(data:font/woff2;base64,{b('SpaceMono-Bold-latin.woff2')}) format('woff2');font-weight:700}}")


CSS = """
:root{--bg:#F6F3EE;--ink:#111;--muted:#6B675F;--mag:#E20074}
html,body,[data-testid="stAppViewContainer"],[data-testid="stApp"]{background:var(--bg)!important;color:var(--ink);font-family:'SG',sans-serif}
[data-testid="stHeader"],[data-testid="stToolbar"],footer,#MainMenu,[data-testid="stDecoration"],[data-testid="stStatusWidget"]{display:none!important}
.block-container{max-width:1480px!important;padding:0 40px 80px!important}
.o-strip{display:flex;justify-content:space-between;border-bottom:1px solid var(--ink);padding:14px 0 10px;font:400 11px 'SM';letter-spacing:.08em;text-transform:uppercase}
.o-strip b{font-weight:700}
.o-lbl{font:400 11px 'SM';letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.o-act{display:grid;grid-template-columns:120px 1fr auto;align-items:end;border-top:1px solid var(--ink);border-bottom:1px solid var(--ink);padding:18px 0 14px;margin:48px 0 10px}
.o-act .no{font:400 12px 'SM';letter-spacing:.08em}
.o-act h2{font:300 44px/1 'SG';margin:0;padding:0;letter-spacing:-.02em;color:var(--ink)}
.o-act .tag{font:400 11px 'SM';letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.o-hero-num{font:300 210px/0.82 'SG';letter-spacing:-.06em;margin-top:10px}
.o-funnel{display:grid;grid-template-columns:repeat(4,auto);border-top:1px solid var(--ink);margin-top:26px}
.o-funnel div{padding:8px 12px 0 0;border-right:1px solid var(--ink);margin-right:12px}
.o-funnel div:last-child{border-right:0}
.o-funnel b{display:block;font:400 30px 'SG'}
.o-funnel span{font:400 10px 'SM';color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.o-funnel .arrow{font:400 10px 'SM';color:var(--muted)}
.o-cue{text-align:center;font:400 11px 'SM';letter-spacing:.12em;margin:4px 0 0}
.o-hint{text-align:right;font:400 10px 'SM';letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-top:-6px}
.o-cust{display:grid;grid-template-columns:1fr auto;border-bottom:1px solid var(--ink);padding:4px 0 12px;align-items:end}
.o-cust .name{font:400 28px/1.1 'SG';letter-spacing:-.01em}
.o-cust .sub{font:400 12px 'SM';color:var(--muted);margin-top:6px}
.o-cust .risk{font:300 84px/0.9 'SG';letter-spacing:-.04em;text-align:right}
.o-cust .risk small{font-size:30px}
.o-cust .rl{font:400 11px 'SM';text-align:right;color:var(--muted);letter-spacing:.04em}
.o-cust .was{color:var(--mag);font:700 13px 'SM';text-align:right;margin-top:4px}
.o-panel{min-height:300px;max-height:520px;overflow:hidden}
.o-ph{font:400 22px/1.2 'SG';margin:6px 0 12px}
.o-ph small{font:400 11px 'SM';color:var(--muted);letter-spacing:.06em;text-transform:uppercase;margin-left:10px}
.o-know{display:grid;grid-template-columns:repeat(3,1fr);border-top:1px solid #111;border-left:1px solid #111}
.o-know .col{border-right:1px solid #111;border-bottom:1px solid #111}
.o-know .gh{font:700 11px 'SM';letter-spacing:.08em;text-transform:uppercase;padding:8px 12px;border-bottom:1px solid #111}
.o-kv{display:flex;justify-content:space-between;gap:12px;padding:6px 12px;border-bottom:1px solid rgba(17,17,17,.18);font:400 14px 'SG'}
.o-kv:last-child{border-bottom:0}
.o-kv span:last-child{font:400 13px 'SM';text-align:right}
.o-drv{display:grid;grid-template-columns:30px 1fr 60px 80px;border-bottom:1px solid #111;padding:7px 0;font:400 14px 'SG';align-items:baseline}
.o-drv:first-child{border-top:1px solid #111}
.o-drv .n{font:700 11px 'SM'}
.o-drv .g{font:400 10px 'SM';letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.o-drv .p{font:400 13px 'SM';text-align:right}
.o-drv .p.up{color:var(--mag);font-weight:700}
.o-opt{display:grid;grid-template-columns:1.2fr 1.6fr 100px;gap:12px;padding:7px 0;border-bottom:1px solid #111;font:400 14px 'SG';align-items:baseline}
.o-opt.hd{border-top:1px solid #111}
.o-opt .v{font:400 13px 'SM';text-align:right}
.o-opt .why{font:400 13px 'SG';color:var(--muted)}
.o-opt.win{font-weight:600}
.o-opt.win .v{color:var(--mag);font-weight:700}
.o-opt.off{color:var(--muted)}
.o-dec{border:1px solid var(--ink);background:#fff}
.o-dec .hd{display:flex;justify-content:space-between;border-bottom:1px solid var(--ink);padding:10px 14px}
.o-dec .big{font:400 36px/1.08 'SG';letter-spacing:-.015em;padding:18px 14px 8px}
.o-dec .big.hero{background:var(--mag);color:#fff;font-size:48px;padding:26px 14px 22px;font-weight:500}
.o-dec .ev{font:400 13px 'SM';padding:0 14px 16px;color:var(--muted)}
.o-dec .why{font:400 17px/1.4 'SG';padding:12px 14px 16px;border-top:1px solid var(--ink)}
.o-sms{max-width:380px;border:1px solid #111;border-radius:22px;padding:14px;background:#fff}
.o-sms .top{font:400 10px 'SM';text-align:center;color:var(--muted);letter-spacing:.06em;text-transform:uppercase;margin-bottom:10px}
.o-sms .b{background:#ECE7DF;border-radius:16px 16px 16px 4px;padding:10px 12px;font:400 15px/1.4 'SG'}
.o-app{max-width:460px;border:1px solid #111;background:#fff;padding:12px 14px;display:grid;grid-template-columns:28px 1fr;gap:4px 10px}
.o-app .bell{font:400 18px 'SM';grid-row:span 2}
.o-app .t{font:700 15px 'SG'}
.o-app .b{font:400 14px/1.4 'SG'}
.o-app .m{grid-column:2;font:400 10px 'SM';color:var(--muted);letter-spacing:.06em;text-transform:uppercase}
.o-mail{max-width:560px;border:1px solid #111;background:#fff}
.o-mail .h{font:400 12px 'SM';padding:6px 14px;border-bottom:1px solid #111}
.o-mail .body{padding:12px 14px;font:400 15px/26px 'SG';background:repeating-linear-gradient(#fff 0 25px,rgba(17,17,17,.14) 25px 26px)}
.o-call{max-width:560px;border:1px solid #111;background:#fff}
.o-call .h{display:flex;justify-content:space-between;font:700 11px 'SM';letter-spacing:.08em;text-transform:uppercase;padding:8px 14px;border-bottom:1px solid #111}
.o-call ol{margin:0;padding:10px 14px 12px 40px;font:400 13px/1.55 'SM'}
.o-call li{padding:2px 0}
.o-call .say{font-weight:700;color:var(--mag)}
.o-bill{max-width:620px;border:1px solid #111;background:#fff;font:400 13px 'SM'}
.o-bill .h{display:flex;justify-content:space-between;padding:8px 14px;border-bottom:1px solid #111;font-weight:700;letter-spacing:.06em;text-transform:uppercase;font-size:11px}
.o-bill .row{display:grid;grid-template-columns:1fr 110px;gap:16px;padding:10px 14px;border-bottom:1px dashed #111}
.o-bill .row:last-child{border-bottom:0}
.o-bill .row.mark{border-left:4px solid var(--mag)}
.o-bill .amt{text-align:right}
.o-none{border:1px dashed #111;padding:22px 14px;text-align:center;font:500 22px 'SG';max-width:560px}
.o-grid{display:grid;grid-template-columns:repeat(4,1fr);border-left:1px solid #111;border-top:1px solid #111}
.o-cell{border-right:1px solid #111;border-bottom:1px solid #111;padding:14px 16px 16px;min-height:150px;display:flex;flex-direction:column;justify-content:space-between}
.o-cell.w2{grid-column:span 2}
.o-cell .v{font:300 68px/0.95 'SG';letter-spacing:-.03em}
.o-cell .v small{font-size:28px}
.o-cell .s{font:400 12px 'SM';color:var(--muted)}
.o-cell.warn{background:var(--mag);color:#fff}
.o-cell.warn .o-lbl,.o-cell.warn .s{color:#fff}
.o-mix{display:flex;height:34px;border:1px solid #111;margin-top:10px}
.o-mix div{border-right:1px solid #111;display:flex;align-items:center;padding-left:8px;font:400 11px 'SM';white-space:nowrap;overflow:hidden}
.o-mix div:last-child{border-right:0}
.o-ch{border-top:1px solid #111;padding:10px 0 2px;display:flex;justify-content:space-between}
.o-ledger{columns:2;column-gap:48px}
.o-ledger .grp{break-inside:avoid;margin-bottom:18px}
.o-ledger .gh{font:700 11px 'SM';letter-spacing:.08em;text-transform:uppercase;border-bottom:1px solid #111;padding:6px 0}
.o-ledger .it{display:grid;grid-template-columns:1fr 1.3fr;gap:16px;padding:7px 0;border-bottom:1px solid rgba(17,17,17,.25);font:400 14px/1.35 'SG'}
.o-ledger .it span:last-child{color:var(--muted)}
.o-foot{border-top:1px solid #111;margin-top:40px;padding:12px 0;font:400 11px 'SM';letter-spacing:.06em;text-transform:uppercase;display:flex;justify-content:space-between}
/* step rail + nav: real buttons, restyled */
[class*="st-key-orbit_rail"] button{border-radius:0!important;border:0!important;border-top:2px solid #111!important;background:transparent!important;color:#111!important;font:400 11px 'SM'!important;justify-content:flex-start!important;padding:6px 0 0!important;min-height:0!important;box-shadow:none!important}
[class*="st-key-orbit_rail"] button p{font:400 11px 'SM'!important;letter-spacing:.06em;text-transform:uppercase;text-align:left}
[class*="st-key-orbit_rail"] button[kind="primary"]{border-top-color:var(--mag)!important;color:var(--mag)!important}
[class*="st-key-orbit_rail"] button[kind="primary"] p{color:var(--mag)!important;font-weight:700!important}
[class*="st-key-orbit_nav"] button{border-radius:0!important;border:1px solid #111!important;background:transparent!important;font:400 12px 'SM'!important;color:#111!important}
[class*="st-key-orbit_nav"] button p{font:400 12px 'SM'!important}
[data-testid="stBaseButton-segmented_control"],[data-testid="stBaseButton-segmented_controlActive"]{font-family:'SM'!important;border-radius:0!important;border-color:#111!important}
[data-testid="stWidgetLabel"] p{font:400 11px 'SM'!important;letter-spacing:.08em;text-transform:uppercase;color:#6B675F}
[data-testid="stTextInput"] input{border-radius:0!important;font-family:'SM'!important;background:#fff}
"""


def load_css() -> None:
    st.markdown(f"<style>{_font_css()}{CSS}</style>", unsafe_allow_html=True)


def _act(no: str, title: str, tag: str = "") -> None:
    st.markdown(f"<div class='o-act'><span class='no'>{no}</span><h2>{esc(title)}</h2><span class='tag'>{esc(tag)}</span></div>",
                unsafe_allow_html=True)


def _axes(title: str, **kw) -> dict:
    return dict(title=dict(text=title, font=dict(family="SM", size=11, color=INK)), backgroundcolor=BG, showbackground=True,
                gridcolor="rgba(17,17,17,0.35)", gridwidth=1, zerolinecolor=INK, linecolor=INK, linewidth=1, showspikes=False,
                tickfont=dict(family="SM", size=10, color=MUTED), **kw)


def pct(x: float) -> str:
    return f"{x:.1f}%" if x >= 1 else f"{x:.2f}%"


def cid(acc: str) -> str:
    return acc[len(PERSONA_PREFIX):] if acc.startswith(PERSONA_PREFIX) else acc.replace("ACC-", "#")


# ============================================================== data shaping (pure; inputs passed in)
CHANNELS = {"text": "text", "in-app message": "in_app", "email": "email", "agent call": "call"}
CHANNEL_LABEL = {"in_app": "in-app", "text": "text", "email": "email", "call": "call"}


def orbit_frame(merged: pd.DataFrame, outreach: pd.DataFrame | None = None, receipts: pd.DataFrame | None = None,
                flag_share: float = 0.10) -> pd.DataFrame:
    """merged: one row per account (churn scores + features [+ offers]).
    outreach: account_id, outreach_reason, message_en, message_es ('Sent as: <channel>.' at the end of outreach_reason).
    receipts: account_id, receipt_line_en, receipt_saving_mo (optional; plan-move bill lines).
    Flag cut = top `flag_share` of regular accounts (demo accounts excluded), applied to every account."""
    df = merged.copy()
    df["is_demo"] = df.account_id.str.startswith(PERSONA_PREFIX)
    reg = df[~df.is_demo].p_churn_90d.sort_values(ascending=False)
    cut = float(reg.iloc[max(0, int(round(len(reg) * flag_share)) - 1)]) if len(reg) else 1.0
    df["flagged"] = df.p_churn_90d >= cut
    df.attrs["flag_cut"] = cut
    for c in ("outreach_reason", "message_en", "message_es"):
        df[c] = ""
    if outreach is not None and len(outreach):
        o = outreach.reset_index() if "account_id" not in outreach.columns else outreach
        o = o.drop_duplicates("account_id").set_index("account_id")
        for c in ("outreach_reason", "message_en", "message_es"):
            if c in o:
                df[c] = df.account_id.map(o[c]).fillna("").astype(str)
    df["channel"] = df.outreach_reason.str.extract(r"Sent as:\s*([^.]+)", expand=False).str.strip().str.lower().map(CHANNELS)
    df["messaged"] = df.message_en.str.strip().ne("")
    df.loc[~df.messaged, "channel"] = None
    df["reason_line"] = df.outreach_reason.str.replace(r"\s*Sent as:.*$", "", regex=True).str.strip()
    df["receipt_line_en"] = ""
    df["receipt_saving_mo"] = np.nan
    if receipts is not None and len(receipts):
        r = receipts.drop_duplicates("account_id").set_index("account_id")
        for c in ("receipt_line_en", "receipt_saving_mo"):
            if c in r:
                df[c] = df.account_id.map(r[c])
        df["receipt_line_en"] = df.receipt_line_en.fillna("").astype(str)
    if "risk_rank" in df:
        df = df.sort_values("risk_rank")
    return df.reset_index(drop=True)


# ============================================================== act 1 — hero
@st.cache_resource(show_spinner=False, max_entries=4)
def _hero_fig(_df: pd.DataFrame, sig: str) -> go.Figure:
    h = _df
    x = h.p_churn_90d * 100
    y = (h.get("last_bill_cents", pd.Series(0, index=h.index)).fillna(0) / 100)
    z = h.get("tenure_months", pd.Series(0, index=h.index)).fillna(0)
    how = h.channel.map(CHANNEL_LABEL).fillna("no message")
    cd = np.stack([[cid(a) for a in h.account_id], how], axis=1)
    tip = ("Customer %{customdata[0]}<br>90-day churn risk %{x:.2f}%<br>monthly bill $%{y:,.0f}"
           "<br>%{z:.0f} months with us<br>message: %{customdata[1]}<extra></extra>")
    fig = go.Figure()
    for mask, size, col in ((~h.flagged, 2.2, DOT), (h.flagged, 3.4, MAG)):
        fig.add_trace(go.Scatter3d(x=x[mask], y=y[mask], z=z[mask], mode="markers", marker=dict(size=size, color=col, line=dict(width=0)),
                                   customdata=cd[mask.values], hovertemplate=tip, showlegend=False))
    ann = []
    demo = [a for a in (f"{PERSONA_PREFIX}{d}" for d in ("38", "04", "21", "24")) if a in set(h.account_id)]
    offs = [(-70, -70), (-40, -140), (-120, 40), (90, 60)]
    picks = [(a, f"CUSTOMER {cid(a)}", offs[i]) for i, a in enumerate(demo)]
    reg = h[~h.is_demo]
    if len(reg):
        picks.append((reg.iloc[0].account_id, f"RISKIEST · {cid(reg.iloc[0].account_id)}", (110, 10)))
    for acc, title, (ax, ay) in picks:
        i = h.index[h.account_id == acc][0]
        ann.append(dict(x=math.log10(max(x[i], 0.05)), y=y[i], z=z[i], text=f"<b>{title}</b><br>{pct(x[i])} risk · ${y[i]:,.0f}/mo",
                        showarrow=True, arrowhead=0, arrowwidth=1, arrowcolor=INK, ax=ax, ay=ay,
                        font=dict(family="SM", size=10, color=INK), bgcolor=BG, bordercolor=INK, borderwidth=1, borderpad=4))
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG, margin=dict(l=0, r=0, t=0, b=0), height=760, uirevision="orbit-hero",
        font=dict(family="SG", color=INK), hoverlabel=dict(bgcolor="#fff", bordercolor=INK, font=dict(family="SM", size=11, color=INK)),
        scene=dict(xaxis=_axes("90-DAY CHURN RISK (LOG)", type="log", tickvals=[0.3, 1, 3, 10, 30, 70],
                               ticktext=["0.3%", "1%", "3%", "10%", "30%", "70%"]),
                   yaxis=_axes("MONTHLY BILL $"), zaxis=_axes("MONTHS WITH US"),
                   aspectmode="manual", aspectratio=dict(x=1.6, y=1.1, z=0.8),
                   camera=dict(eye=dict(x=1.45, y=-1.35, z=0.6), center=dict(x=0, y=0, z=-0.15)), annotations=ann))
    return fig


def render_hero(df: pd.DataFrame) -> None:
    scored, flagged = len(df), int(df.flagged.sum())
    messaged, texts = int(df.messaged.sum()), int((df.channel == "text").sum())
    st.markdown(f"<div class='o-strip'><span><b>Churn + upsell board</b> · this week</span><span>{scored:,} customers scored</span>"
                f"<span>01 / 04</span></div>", unsafe_allow_html=True)
    left, right = st.columns([0.3, 0.7], gap="small")
    with left:
        st.markdown(f"""<div style='margin-top:28px'><div class='o-lbl'>Messages this week</div>
<div class='o-hero-num'>{messaged}</div>
<div class='o-funnel'>
<div><b>{scored:,}</b><span>scored</span></div>
<div><b><span style='color:{MAG};font-size:30px'>●</span>&nbsp;{flagged}</b><span>flagged</span></div>
<div><b>{messaged}</b><span>messaged</span></div>
<div><b>{texts}</b><span>by text</span></div>
</div>
<div class='o-lbl' style='margin-top:12px'>every dot is one customer · magenta = flagged</div></div>""", unsafe_allow_html=True)
    with right:
        sig = f"{scored}-{flagged}-{messaged}-{float(df.p_churn_90d.sum()):.6f}"
        st.plotly_chart(_hero_fig(df, sig), width="stretch", theme=None, config=CFG3D, key="orbit_hero")
        st.markdown("<div class='o-hint'>drag to rotate · hover a point</div>", unsafe_allow_html=True)
    st.markdown("<div class='o-cue'>↓&nbsp;&nbsp;SCROLL · OPEN ONE CUSTOMER</div>", unsafe_allow_html=True)


# ============================================================== act 2 — one customer, six steps
# model column -> (wording when this customer is ABOVE typical, wording when BELOW typical, group)
SIGNALS = {
    "extra_lines": ("More lines than typical", "Fewer lines than typical", "Commerce"),
    "tenure_capped60": ("Longer with T-Mobile than typical", "Newer to T-Mobile than typical", "Customer"),
    "app_sessions_30d": ("Uses the app more than typical", "Uses the app less than typical", "Live"),
    "financing_ends_within_3m": ("Phone paid off within 3 months", "No phone payoff coming up", "Commerce"),
    "is_byod": ("Brought their own phone", "Phone bought from us", "Commerce"),
    "neg_sentiment": ("More negative with support than typical", "Less negative with support than typical", "Customer"),
    "cancel_inquiries_270d": ("Asked about cancelling", "Hasn't asked about cancelling", "Customer"),
    "short_history": ("Short account history", "Full account history", "Customer"),
    "has_home_internet": ("Has Home Internet with us", "No Home Internet with us", "Commerce"),
    "low_app_use": ("Rarely uses the app", "Uses the app regularly", "Live"),
    "plan_misfit_share": ("Plan doesn't fit their usage", "Plan fits their usage", "Commerce"),
    "port_out_inquiry": ("Asked about transferring their number", "Hasn't asked about transferring their number", "Live"),
    "early_tenure": ("In their first year with us", "Past their first year", "Customer"),
    "promo_expired_recent": ("A promo just ended", "No promo ended recently", "Commerce"),
    "max_device_age_months": ("Older phone than typical", "Newer phone than typical", "Commerce"),
    "troubled_4plus": ("4+ support contacts", "Fewer than 4 support contacts", "Customer"),
    "bill_increase_pct": ("Bill went up more than typical", "Bill rose less than typical", "Commerce"),
    "unresolved_90d": ("More unresolved support issues than typical", "Fewer unresolved support issues than typical", "Customer"),
    "competitor_research_score": ("Comparing carriers more than typical", "Comparing carriers less than typical", "Live"),
    "negative_contacts_90d": ("More unhappy support contacts than typical", "Fewer unhappy support contacts than typical", "Customer"),
}
TOGGLES = [  # what-if switches (fact ON as in the data; OFF removes it and re-scores)
    ("tickets", "Open support tickets", lambda r: _n(r, "unresolved_90d") > 0 or _n(r, "negative_contacts_90d") > 0,
     {"unresolved_90d": 0, "unresolved_270d": 0, "negative_contacts_90d": 0, "network_contacts_90d": 0}),
    ("port", "Asked about transferring their number", lambda r: _n(r, "port_out_inquiry") > 0, {"port_out_inquiry": 0}),
    ("comp", "Comparing carriers", lambda r: _n(r, "competitor_research_score") >= 0.3, {"competitor_research_score": 0.0}),
]
STEPS = ["What we know", "How the score adds up", "Rules and options", "What we picked", "The message", "What if?"]


def _n(r, c, d=0.0) -> float:
    try:
        v = float(r.get(c, d))
        return d if math.isnan(v) else v
    except (TypeError, ValueError):
        return d


def _sig(z: float) -> float:
    return 1 / (1 + math.exp(-z))


def breakdown(b0: float, C: pd.Series, p: float, Z: pd.Series | None = None, k: int = 7):
    """Honest additive breakdown in percentage points: typical (sigmoid of intercept) + top-k signals + rest + overlap = p."""
    logit = b0 + float(C.sum())
    d = pd.DataFrame({"feat": C.index, "c": C.values})
    d["pts"] = [(_sig(logit) - _sig(logit - c)) * 100 for c in d.c]
    d = d.loc[d.pts.abs().sort_values(ascending=False).index]
    d = d[d.pts.abs() >= 0.005]
    top, rest = d.head(k).copy(), float(d.iloc[k:].pts.sum())
    base = _sig(b0) * 100
    overlap = p * 100 - base - float(top.pts.sum()) - rest

    def word(f):
        hi, lo, g = SIGNALS.get(f, (f.replace("_", " "), f.replace("_", " "), "Commerce"))
        if Z is not None and f in Z.index and not pd.isna(Z[f]):
            return (hi if Z[f] > 0 else lo), g
        return hi, g
    top["label"], top["lane"] = zip(*[word(f) for f in top.feat]) if len(top) else ([], [])
    return base, top.reset_index(drop=True), rest, overlap, p * 100


def _tower(base, top, rest, overlap, p_now, key) -> go.Figure:
    cols = [("Typical customer", "base", base, 0.0)]
    cum = base
    for _, t in top.iterrows():
        cols.append((t.label, t.lane, t.pts, cum))
        cum += t.pts
    if abs(rest + overlap) >= 0.005:
        cols.append(("Other small signals + overlap", "Other", rest + overlap, cum))
    cols.append(("This customer", "total", p_now, 0.0))
    lane_y = {"Commerce": 0, "Customer": 1, "Live": 2, "Other": 1, "base": 1, "total": 1}
    fig, W = go.Figure(), 0.36
    ex, ey, ez, ann = [], [], [], []
    for i, (lab, lane, v, z0) in enumerate(cols):
        x, y = float(i), lane_y[lane]
        lo, hi = ((0.0, v) if lane in ("base", "total") else ((z0, z0 + v) if v >= 0 else (z0 + v, z0)))
        hi = max(hi, lo + 0.012)
        color = {"base": "#D9D3C9", "total": INK, "Other": BG}.get(lane, MAG if v > 0 else "#FFFFFF")
        X = [x - W, x + W, x + W, x - W] * 2
        Y = [y - W, y - W, y + W, y + W] * 2
        Z = [lo] * 4 + [hi] * 4
        unit = "%" if lane in ("base", "total") else " pts"
        fig.add_trace(go.Mesh3d(x=X, y=Y, z=Z, i=[0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 3, 3], j=[1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 0, 4],
                                k=[2, 3, 6, 7, 5, 4, 6, 5, 7, 6, 4, 7], color=color, opacity=1, flatshading=True, lighting=FLAT,
                                hovertemplate=f"{esc(lab)}<br>{v:+.2f}{unit}<extra></extra>" if unit == " pts" else
                                f"{esc(lab)}<br>{v:.2f}%<extra></extra>", showscale=False))
        for a, b in [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]:
            ex += [X[a], X[b], None]; ey += [Y[a], Y[b], None]; ez += [Z[a], Z[b], None]
        if lane in ("base", "total"):
            ann.append(dict(x=x, y=y, z=hi, text=f"<b>{'TYPICAL' if lane == 'base' else 'THIS CUSTOMER'}</b><br>{pct(v)}",
                            showarrow=True, arrowhead=0, arrowwidth=1, arrowcolor=INK, ax=0, ay=-40,
                            font=dict(family="SM", size=10, color=INK), bgcolor=BG, bordercolor=INK, borderwidth=1, borderpad=3))
    cx, cy, cz, run = [], [], [], base
    for i in range(len(cols) - 2):
        lane, v = cols[i + 1][1], cols[i + 1][2]
        cx += [i + W, i + 1 - W, None]; cy += [lane_y[cols[i][1]], lane_y[lane], None]; cz += [run, run, None]
        run += v
    fig.add_trace(go.Scatter3d(x=ex, y=ey, z=ez, mode="lines", line=dict(color=INK, width=1.6), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter3d(x=cx, y=cy, z=cz, mode="lines", line=dict(color=INK, width=1.4, dash="dash"), hoverinfo="skip", showlegend=False))
    for n in range(min(3, len(top))):
        t, i = top.loc[n], n + 1
        ann.append(dict(x=i, y=lane_y[t.lane], z=cols[i][3] + max(t.pts, 0), text=f"<b>{n + 1}</b>  {esc(t.label)}<br>{t.pts:+.2f} pts",
                        showarrow=True, arrowhead=0, arrowwidth=1, arrowcolor=MAG if t.pts > 0 else INK,
                        ax=-50 + 40 * n, ay=-36 - 40 * n, font=dict(family="SM", size=10, color=INK),
                        bgcolor="#fff", bordercolor=INK, borderwidth=1, borderpad=4))
    for ln, y in (("COMMERCE", 0), ("CUSTOMER", 1), ("LIVE", 2)):
        ann.append(dict(x=len(cols) - 0.35, y=y, z=0, text=ln, showarrow=False, xanchor="left", font=dict(family="SM", size=10, color=MUTED)))
    zmax = max(max(c[3] + max(c[2], 0) for c in cols), p_now, base) * 1.5
    fig.update_layout(paper_bgcolor=BG, plot_bgcolor=BG, margin=dict(l=0, r=0, t=0, b=0), height=430, showlegend=False,
                      uirevision="orbit-tower", hoverlabel=dict(bgcolor="#fff", bordercolor=INK, font=dict(family="SM", size=11, color=INK)),
                      scene=dict(xaxis=_axes("", showticklabels=False, range=[-0.7, len(cols) + 1.0]),
                                 yaxis=_axes("", showticklabels=False, range=[-0.7, 2.7]),
                                 zaxis=_axes("RISK, %", range=[0, zmax], nticks=5),
                                 aspectmode="manual", aspectratio=dict(x=2.2, y=0.8, z=0.95),
                                 camera=dict(eye=dict(x=0.35, y=-1.75, z=0.85), center=dict(x=0, y=0, z=-0.2)), annotations=ann))
    return fig


def _facts(r) -> dict[str, list[tuple[str, str]]]:
    """Step 1: every input we use, grouped. Only columns that exist are shown."""
    def money(c, div=100):
        v = r.get(c)
        return None if v is None or pd.isna(v) else f"${float(v) / div:,.0f}"

    def yes(c):
        v = r.get(c)
        return None if v is None or pd.isna(v) else ("yes" if float(v) > 0 else "no")

    def num(c, fmt="{:,.0f}", scale=1.0):
        v = r.get(c)
        return None if v is None or pd.isna(v) else fmt.format(float(v) * scale)
    plan = " ".join(str(r.get(c, "")).title() for c in ("plan_family", "plan_tier") if pd.notna(r.get(c)))
    g = {
        "Commerce": [("Plan", plan or None), ("Plan price / mo", money("plan_price_cents")), ("Last bill", money("last_bill_cents")),
                     ("Bill vs prior 3 mo", num("bill_change_3m_pct", "{:+.0f}%", 100)), ("Promo just ended", yes("promo_expired_recent")),
                     ("Lines", num("n_lines")), ("Phone age, months", num("max_device_age_months")),
                     ("Financing months left", num("max_financing_months_remaining")), ("Home Internet", yes("has_home_internet"))],
        "Customer": [("Months with us", num("tenure_months")), ("Account type", str(r.get("segment", "")).title() or None),
                     ("Support contacts, 90 days", num("support_90d")), ("Unresolved, 90 days", num("unresolved_90d")),
                     ("Unhappy contacts, 90 days", num("negative_contacts_90d")), ("Asked about cancelling, 270 days", num("cancel_inquiries_270d")),
                     ("Prefers", str(r.get("contact_preference", "")) or None), ("Language", str(r.get("language", "")).upper() or None)],
        "Live": [("Comparing carriers (0-1)", num("competitor_research_score", "{:.2f}")), ("Asked about transferring number", yes("port_out_inquiry")),
                 ("App sessions, 30 days", num("app_sessions_30d")), ("Data use vs 3 mo ago", num("data_growth_pct", "{:+.0f}%", 100)),
                 ("Data per month, GB", num("data_gb_3m_avg", "{:.1f}"))],
    }
    return {k: [(a, b) for a, b in v if b not in (None, "", "Nan")] for k, v in g.items()}


def _message_html(r) -> str:
    """Step 5: the message as the customer receives it, in its channel's look. Empty string when there is nothing to show."""
    msg = str(r.get("message_en", "") or "").strip()
    ch = r.get("channel")
    bill = str(r.get("receipt_line_en", "") or "").strip()
    if bill:
        lines = [s.strip() for s in bill.split("|") if s.strip()]
        sav = r.get("receipt_saving_mo")
        rows = "".join(
            f"<div class='row {'mark' if i == 0 else ''}'><span>{esc(s)}</span>"
            f"<span class='amt'>{('−$' + format(float(sav), ',.0f') + '/mo') if i == 0 and sav is not None and not pd.isna(sav) else ''}</span></div>"
            for i, s in enumerate(sorted(lines, key=lambda s: not s.lower().startswith("same features"))))
        bill_html = f"<div class='o-bill'><div class='h'><span>Your monthly bill · notes</span><span>printed on the bill</span></div>{rows}</div>"
    else:
        bill_html = ""
    if not msg:
        return bill_html
    body = esc(msg)
    if ch == "text":
        m = f"<div class='o-sms'><div class='top'>Text message · now</div><div class='b'>{body}</div></div>"
    elif ch == "in_app":
        first, _, rest = msg.partition(". ")
        m = (f"<div class='o-app'><span class='bell'>&#x1F514;&#xFE0E;</span><span class='t'>{esc(first)}.</span>"
             f"<span class='b'>{esc(rest)}</span><span class='m'>app notification · now</span></div>")
    elif ch == "email":
        subj = "About your open support request"
        m = (f"<div class='o-mail'><div class='h'>From: Customer Care</div><div class='h'>Subject: {subj}</div>"
             f"<div class='body'>{body}</div></div>")
    elif ch == "call":
        s = re.sub(r"^\[Call script\]\s*", "", msg)
        ask = ""
        if "Ask:" in s:
            s, _, ask = s.partition("Ask:")
        parts = [p.strip() for p in re.split(r"(?<=[.?!])\s+", s.strip()) if p.strip()]
        items = "".join(f"<li>{'<span class=say>Say:</span> ' if i == 0 else ''}{esc(p)}</li>" for i, p in enumerate(parts))
        if ask:
            q, _, tail = ask.strip().partition("?")
            items += f"<li><span class='say'>Ask:</span> {esc(q)}?</li>" + (f"<li>{esc(tail.strip())}</li>" if tail.strip() else "")
        m = f"<div class='o-call'><div class='h'><span>&#x260E;&#xFE0E; Agent call script</span><span>read aloud</span></div><ol>{items}</ol></div>"
    else:
        m = f"<div class='o-app'><span class='bell'></span><span class='b'>{body}</span></div>"
    return m + (("<div style='height:12px'></div>" + bill_html) if bill_html else "")


DN_REASON = {"happy": "nothing is going wrong on this account", "open_ticket": "there's an open ticket to fix first",
             "wait_payoff": "it's better to wait until their phone is paid off"}


def outreach_rules(r) -> list[tuple[str, str, str]]:
    """The outreach rules (from the outreach playbook), in order; the first that applies decides.
    Returns (rule, status, detail) with status 'stop' (decides: no message), 'pass', 'info' or 'skip' (not reached).
    Uses optional columns: action_code, do_nothing_reason, policy_selected, block_reason, unresolved_90d, contact_preference."""
    out, stopped = [], False

    def sv(c):
        v = r.get(c)
        return "" if v is None or (isinstance(v, float) and math.isnan(v)) else str(v)

    def add(rule, applies, detail_stop, detail_pass, kind="stop"):
        nonlocal stopped
        if stopped:
            out.append((rule, "skip", "")); return
        if applies is None:
            return
        if applies and kind == "stop":
            stopped = True
            out.append((rule, "stop", detail_stop))
        else:
            out.append((rule, "info" if kind == "info" else "pass", detail_pass if not applies else detail_stop))
    ac = sv("action_code")
    add("If our engine finds nothing worth doing, we stay silent.", (ac == "do_nothing") if ac else None,
        "Engine says do nothing: " + DN_REASON.get(sv("do_nothing_reason"), "no action applies") + ".", "Engine found something worth weighing.")
    br = sv("block_reason")
    add("A cheaper plan with the same features goes on the bill, never in a message.", (br == "receipt_only_plan_move") if br or "block_reason" in r else None,
        "Cheaper plan found: shown on the bill and in the app only.", "No plan move for this account.")
    ps = r.get("policy_selected")
    add("Only offers that still pay off at a realistic 10% save rate get a message.", (not bool(ps)) if ps is not None and not pd.isna(ps) else None,
        "Nothing here pays off at a realistic save rate.", "This action pays off even at a 10% save rate.")
    add("If their bill just went up, we only reach out with a credit that offsets it, or to fix an open issue.",
        (br == "bill_change_no_fix") if "block_reason" in r else None, "Bill went up and we have no offer that lowers it.", "No blocking bill increase.")
    un = _n(r, "unresolved_90d")
    add("With an open support issue, the only message allowed is a fix, never an offer.", un > 0,
        f"{int(un)} unresolved support contact{'s' if un != 1 else ''}: message is a fix callback.", "No open support issue.", kind="info")
    pref = sv("contact_preference")
    if pref:
        add("We reach people the way they asked to be reached.", True, f"Prefers {pref}.", "", kind="info")
    add("One proactive message per account at most.", True, "At most one message this run.", "", kind="info")
    return out


def _go(state_key: str, i: int) -> None:
    st.session_state[state_key] = i


def render_customer(df: pd.DataFrame, account_id: str, *, contributions_fn: Callable | None = None,
                    candidates: pd.DataFrame | None = None, rules: dict[str, str] | None = None, key: str = "orbit") -> None:
    """Act 2. contributions_fn(account_id, edits) -> (intercept_logit, contributions Series, p, standardized-values Series or None).
    candidates: every option row for this account (action, eligible, expected_value, blocked_or_ineligible_reason, is_chosen).
    rules: optional {action_code: plain-language rule} shown in step 3."""
    _act("02 / 04", "One customer, step by step", "why this score · why this action")
    if account_id not in set(df.account_id):
        st.markdown(f"<div class='o-lbl'>No customer {esc(account_id)} in this data.</div>", unsafe_allow_html=True)
        return
    r = df[df.account_id == account_id].iloc[0]
    sk = f"{key}_step"
    if st.session_state.get(f"{key}_last_acc") != account_id:
        st.session_state[f"{key}_last_acc"] = account_id
        st.session_state[sk] = 0
    step = int(st.session_state.get(sk, 0))

    # what-if edits persist across steps (switches live in step 6)
    edits = {}
    for k, _lab, cond, ed in TOGGLES:
        if cond(r) and st.session_state.get(f"{key}_t_{account_id}_{k}") is False:
            edits.update(ed)
    p_orig = float(r.p_churn_90d) * 100
    bd = None
    if contributions_fn is not None:
        try:
            b0, C, p, Z = contributions_fn(account_id, edits or None)
            bd = breakdown(b0, C, p, Z)
        except Exception as e:  # noqa: BLE001
            print(f"[orbit] breakdown unavailable: {type(e).__name__}: {e}")
    p_now = bd[4] if bd else p_orig
    base = bd[0] if bd else None

    was = f"<div class='was'>(what-if, was {pct(p_orig)})</div>" if edits and bd else ""
    lines = int(_n(r, "n_lines"))
    sub = (f"typical customer {pct(base)} · " if base else "") + (f"risk rank {int(r.risk_rank):,} of {len(df):,}" if "risk_rank" in r else "")
    st.markdown(f"""<div class='o-cust'><div><div class='o-lbl'>Customer {esc(cid(account_id))}</div>
<div class='name'>{esc(str(r.get('segment', '')).title())} account · {int(_n(r, 'tenure_months')) // 12} yrs with us · {lines} line{'s' if lines != 1 else ''}</div>
<div class='sub'>{sub}</div></div>
<div><div class='risk'>{pct(p_now)[:-1]}<small>%</small></div><div class='rl'>90-DAY CHURN RISK</div>{was}</div></div>""", unsafe_allow_html=True)

    with st.container(key=f"orbit_rail_{key}"):
        rc = st.columns(len(STEPS))
        for i, (c, name) in enumerate(zip(rc, STEPS)):
            c.button(f"{i + 1:02d}  {name}", key=f"{key}_rail_{i}", type="primary" if i == step else "secondary",
                     width="stretch", on_click=_go, args=(sk, i))

    panel = st.container()
    with panel:
        if step == 0:
            g = _facts(r)
            cols = "".join(f"<div class='col'><div class='gh'>{k}</div>" + "".join(
                f"<div class='o-kv'><span>{esc(a)}</span><span>{esc(str(b))}</span></div>" for a, b in v) + "</div>" for k, v in g.items())
            st.markdown(f"<div class='o-ph'>Everything the models see for this account<small>{sum(len(v) for v in g.values())} inputs</small></div>"
                        f"<div class='o-know'>{cols}</div>", unsafe_allow_html=True)
        elif step == 1:
            if not bd:
                st.markdown("<div class='o-lbl'>Score breakdown unavailable here.</div>", unsafe_allow_html=True)
            else:
                b, top, rest, overlap, pn = bd
                a, z = st.columns([1.5, 1], gap="large")
                with a:
                    st.plotly_chart(_tower(b, top, rest, overlap, pn, key), width="stretch", theme=None, config=CFG3D,
                                    key=f"{key}_tower")
                    st.markdown("<div class='o-hint'>drag to rotate · hover a block</div>", unsafe_allow_html=True)
                with z:
                    rows = "".join(f"<div class='o-drv'><span class='n'>{i + 1:02d}</span><span>{esc(t.label)} <span class='g'>· {t.lane}</span></span>"
                                   f"<span class='g' style='text-align:right'>{'raises' if t.pts > 0 else 'lowers'}</span>"
                                   f"<span class='p {'up' if t.pts > 0 else ''}'>{t.pts:+.2f} pts</span></div>" for i, t in top.iterrows())
                    rows += (f"<div class='o-drv'><span class='n'>··</span><span>Other small signals + overlap</span><span></span>"
                             f"<span class='p'>{rest + overlap:+.2f} pts</span></div>")
                    st.markdown(f"<div class='o-ph'>Typical {pct(b)} → this customer {pct(pn)}</div>{rows}", unsafe_allow_html=True)
        elif step == 2:
            rl = outreach_rules(r)
            mark = {"stop": f"<span style='color:{MAG};font-weight:700'>STOPS HERE</span>", "pass": "passes", "info": "applies", "skip": "not reached"}
            rrows = "".join(f"<div class='o-opt {'win' if s_ == 'stop' else ''} {'off' if s_ == 'skip' else ''}' style='grid-template-columns:1.4fr 1.2fr 110px'>"
                            f"<span>{i + 1}. {esc(rule)}</span><span class='why'>{esc(det)}</span><span class='v'>{mark[s_]}</span></div>"
                            for i, (rule, s_, det) in enumerate(rl))
            st.markdown(f"<div class='o-ph'>The rules, in order: the first one that applies decides</div>{rrows}", unsafe_allow_html=True)
            if candidates is not None and len(candidates):
                c = candidates.copy()
                c["ok"] = c.eligible.astype(str).str.lower().isin(["true", "1"])
                c = pd.concat([c[c.ok].sort_values("expected_value", ascending=False), c[~c.ok]])
                rows = ""
                for x in c.itertuples():
                    why = ("picked" if x.is_chosen else "allowed, not picked") if x.ok else str(x.blocked_or_ineligible_reason or "")
                    v = f"${x.expected_value:,.2f}" if x.ok and not pd.isna(x.expected_value) else "—"
                    rows += (f"<div class='o-opt {'win' if x.is_chosen else ''} {'' if x.ok else 'off'}'><span>{esc(str(x.action))}</span>"
                             f"<span class='why'>{esc(why)}</span><span class='v'>{v}</span></div>")
                st.markdown(f"<div class='o-lbl' style='margin:14px 0 4px'>Every option weighed · {int(c.ok.sum())} allowed · {int((~c.ok).sum())} ruled out · "
                            f"expected value at the engine's own save rates</div><div style='max-height:190px;overflow:auto;border-top:1px solid #111'>{rows}</div>",
                            unsafe_allow_html=True)
        elif step == 3:
            messaged, bill = bool(r.messaged), str(r.get("receipt_line_en", "") or "").strip()
            reason = esc(str(r.get("reason_line", "") or "").removeprefix("No message: "))
            if messaged:
                big = f"<div class='big'>Reach out by {esc(CHANNEL_LABEL.get(r.channel, 'message'))}.</div>"
                head = "Why we're reaching out"
            elif bill:
                big = "<div class='big'>Put the cheaper plan on the bill.<br>No message is sent.</div>"
                head = "Why we're not reaching out"
            else:
                big = "<div class='big hero'>Do nothing.<br>No message is sent.</div>"
                head = "Why we're not reaching out"
            why = f"<div class='o-lbl' style='padding:10px 14px 0;border-top:1px solid #111'>{head}</div><div class='why' style='border-top:0'>{reason}</div>" if reason else ""
            st.markdown(f"<div class='o-dec' style='max-width:760px'><div class='hd'><span class='o-lbl'>What we picked</span></div>{big}{why}</div>",
                        unsafe_allow_html=True)
        elif step == 4:
            m = _message_html(r)
            reason = str(r.get("reason_line", "") or "")
            head = "Why we're reaching out" if r.messaged else "Why we're not"
            top = f"<div class='o-lbl'>{head}</div><div class='o-ph'>{esc(reason.removeprefix('No message: '))}</div>" if reason else ""
            st.markdown(top + m, unsafe_allow_html=True)
        else:
            rel = [(k, lab) for k, lab, cond, _ in TOGGLES if cond(r)]
            st.markdown("<div class='o-ph'>Switch a fact off and the risk model re-scores live</div>", unsafe_allow_html=True)
            if not rel:
                st.markdown("<div class='o-lbl'>Nothing to switch off: no open tickets, no number-transfer question, not comparing carriers.</div>",
                            unsafe_allow_html=True)
            for k, lab in rel:
                st.toggle(lab, value=True, key=f"{key}_t_{account_id}_{k}")
            if edits and bd:
                st.markdown(f"<div class='o-ph' style='margin-top:10px'>Risk {pct(p_orig)} → <b style='color:{MAG}'>{pct(p_now)}</b></div>",
                            unsafe_allow_html=True)

    with st.container(key=f"orbit_nav_{key}"):
        a, _, b = st.columns([1, 6, 1])
        a.button("← Back", key=f"{key}_back", disabled=step == 0, on_click=_go, args=(sk, max(0, step - 1)), width="stretch")
        b.button("Next →", key=f"{key}_next", disabled=step == len(STEPS) - 1, on_click=_go, args=(sk, min(len(STEPS) - 1, step + 1)),
                 width="stretch")


# ============================================================== act 3 — dashboard
def _flat2d(f: go.Figure, h: int) -> go.Figure:
    f.update_layout(paper_bgcolor=BG, plot_bgcolor=BG, height=h, margin=dict(l=64, r=16, t=10, b=48), showlegend=False,
                    font=dict(family="SM", size=11, color=INK), bargap=0.08,
                    hoverlabel=dict(bgcolor="#fff", bordercolor=INK, font=dict(family="SM", size=11)))
    f.update_xaxes(automargin=True, showgrid=False, linecolor=INK, linewidth=1, ticks="outside", tickcolor=INK, zeroline=False)
    f.update_yaxes(automargin=True, gridcolor="rgba(17,17,17,0.18)", gridwidth=1, linecolor=INK, zeroline=False)
    return f


def render_dashboard(df: pd.DataFrame, economics: dict | None = None, *, typical_risk: float | None = None,
                     key: str = "orbit") -> str | None:
    """economics: {'net_10': float, 'breakeven_sr': float (0-1), 'receipt_lines': int, 'receipt_monthly': float}. Missing keys are skipped.
    Returns the account_id clicked in the riskiest-ten table (or None)."""
    e = economics or {}
    _act("03 / 04", "The whole book, at a glance", "this week")
    scored, flagged = len(df), int(df.flagged.sum())
    messaged = int(df.messaged.sum())
    ch = df[df.messaged].channel.map(CHANNEL_LABEL).value_counts()
    mix = "".join(f"<div style='width:{v / max(1, messaged) * 100:.1f}%;{'background:' + MAG + ';color:#fff' if k == 'text' else ''}'>"
                  f"{k.upper()} {v}</div>" for k, v in ch.items())
    med = float(df.p_churn_90d.median() * 100)
    cells = [f"<div class='o-cell'><span class='o-lbl'>Customers scored</span><span class='v'>{scored:,}</span><span class='s'>every account, every week</span></div>",
             f"<div class='o-cell warn'><span class='o-lbl'>Flagged at risk · top 10%</span><span class='v'>{flagged}</span><span class='s'>cut at {pct(df.attrs.get('flag_cut', 0) * 100)} 90-day risk</span></div>",
             f"<div class='o-cell w2'><span class='o-lbl'>Messages this week · by channel</span><span class='v'>{messaged}</span>"
             f"<div class='o-mix'>{mix}</div></div>"]
    if "receipt_lines" in e:
        cells.append(f"<div class='o-cell'><span class='o-lbl'>Savings lines on the bill</span><span class='v'>{int(e['receipt_lines']):,}</span>"
                     f"<span class='s'>same features, lower price{(' · $' + format(e['receipt_monthly'], ',.0f') + '/mo if all switch') if 'receipt_monthly' in e else ''}</span></div>")
    if "net_10" in e:
        be = f" · break-even about {e['breakeven_sr'] * 100:.1f}%" if "breakeven_sr" in e else ""
        cells.append(f"<div class='o-cell'><span class='o-lbl'>Net value at a 10% save rate</span><span class='v'>{'+' if e['net_10'] >= 0 else '−'}"
                     f"<small>$</small>{abs(e['net_10']):,.0f}</span><span class='s'>{be.strip(' ·')}</span></div>")
    if typical_risk is not None:
        cells.append(f"<div class='o-cell'><span class='o-lbl'>Typical customer risk</span><span class='v'>{pct(typical_risk)[:-1]}<small>%</small></span><span class='s'>90-day churn · model baseline</span></div>")
    cells.append(f"<div class='o-cell'><span class='o-lbl'>Median customer risk</span><span class='v'>{med:.2f}<small>%</small></span><span class='s'>half the book is below this</span></div>")
    st.markdown("<div class='o-grid'>" + "".join(cells) + "</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns([1.35, 1], gap="large")
    with c1:
        st.markdown("<div class='o-ch'><span class='o-lbl'>Risk distribution · every customer</span><span class='o-lbl'>magenta = flagged</span></div>", unsafe_allow_html=True)
        edges = np.logspace(np.log10(0.2), np.log10(80), 44)
        cut = float(df.attrs.get("flag_cut", 1.0)) * 100
        cnt, _ = np.histogram(df.p_churn_90d * 100, bins=edges)
        mids = np.sqrt(edges[:-1] * edges[1:])
        f1 = go.Figure(go.Bar(x=mids, y=cnt, width=np.diff(edges) * 0.92, marker=dict(color=[MAG if m >= cut else DOT for m in mids], line=dict(width=0)),
                              hovertemplate="risk ≈ %{x:.2f}%<br>%{y} customers<extra></extra>"))
        f1.add_vline(x=cut, line=dict(color=INK, width=1, dash="dash"))
        f1.add_annotation(x=math.log10(cut), y=max(cnt) * 0.9, text=f"top 10% starts at {pct(cut)}", showarrow=False, xanchor="left", xshift=8,
                          font=dict(family="SM", size=11, color=INK), bgcolor=BG)
        _flat2d(f1, 330).update_xaxes(type="log", tickvals=[0.3, 1, 3, 10, 30], ticktext=["0.3%", "1%", "3%", "10%", "30%"],
                                      title=dict(text="90-day churn risk (log scale)", font=dict(size=11)))
        f1.update_yaxes(title=dict(text="customers", font=dict(size=11)))
        st.plotly_chart(f1, width="stretch", theme=None, config={"displayModeBar": False}, key=f"{key}_dist")
    with c2:
        st.markdown("<div class='o-ch'><span class='o-lbl'>Who hears from us, and how</span><span class='o-lbl'>customers</span></div>", unsafe_allow_html=True)
        order = [k for k in ("in-app", "text", "email", "call") if k in ch.index]
        ys = order + ["no message"]
        xs = [int(ch[k]) for k in order] + [scored - messaged]
        f2 = go.Figure(go.Bar(y=ys[::-1], x=xs[::-1], orientation="h", marker=dict(color=[DOT if y == "no message" else (MAG if y == "text" else INK) for y in ys[::-1]], line=dict(width=0)),
                              text=[f"{v:,}" for v in xs[::-1]], textposition="outside", cliponaxis=False, textfont=dict(family="SM", size=11),
                              hovertemplate="%{y}: %{x:,}<extra></extra>"))
        _flat2d(f2, 330).update_xaxes(type="log", showticklabels=False, ticks="", showline=False)
        f2.update_yaxes(gridcolor="rgba(0,0,0,0)", showline=False)
        f2.update_layout(margin=dict(l=110, r=60, t=10, b=10))
        st.plotly_chart(f2, width="stretch", theme=None, config={"displayModeBar": False}, key=f"{key}_chan")
        st.markdown("<div class='o-lbl'>log scale: most customers get no message on purpose</div>", unsafe_allow_html=True)

    st.markdown("<div class='o-ch' style='margin-top:18px'><span class='o-lbl'>Riskiest ten this week · click a row to open it</span><span class='o-lbl'></span></div>", unsafe_allow_html=True)
    t = df[~df.is_demo].head(10)
    tab = pd.DataFrame({"Customer": [cid(a) for a in t.account_id], "Risk": [pct(v * 100) for v in t.p_churn_90d],
                        "Top reason": t.get("risk_reason_1", ""), "What we do": t.reason_line.str.removeprefix("No message: "),
                        "Channel": t.channel.map(CHANNEL_LABEL).fillna("none")})
    ev = st.dataframe(tab, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key=f"{key}_riskiest",
                      column_config={"Customer": st.column_config.TextColumn(width="small"), "Risk": st.column_config.TextColumn(width="small"),
                                     "Channel": st.column_config.TextColumn(width="small")})
    rows = (ev.selection.rows if ev is not None and hasattr(ev, "selection") else []) or []
    return t.iloc[rows[0]].account_id if rows else None


# ============================================================== act 4 — what we considered
def render_considered(dc: pd.DataFrame | None) -> None:
    """dc columns: group, item, how_handled[, source]. source is never shown. Renders nothing for None/empty."""
    if dc is None or not len(dc):
        return
    _act("04 / 04", "What we considered", "and how each one is handled")
    groups = "".join(
        f"<div class='grp'><div class='gh'>{esc(str(g))} · {len(x)}</div>" + "".join(
            f"<div class='it'><span>{esc(str(i.item))}</span><span>{esc(str(i.how_handled))}</span></div>" for i in x.itertuples()) + "</div>"
        for g, x in dc.groupby("group", sort=False))
    st.markdown(f"<div style='display:flex;align-items:baseline;gap:18px;margin:6px 0 18px'><span class='o-hero-num' style='font-size:120px'>{len(dc)}</span>"
                f"<span class='o-lbl'>things checked</span></div><div class='o-ledger'>{groups}</div>", unsafe_allow_html=True)
    st.markdown("<div class='o-foot'><span>Churn + upsell board</span><span>design mockup</span></div>", unsafe_allow_html=True)
