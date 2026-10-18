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
.o-know-sm .o-kv{padding:3px 10px;font-size:13px}.o-know-sm .o-kv span:last-child{font-size:12px}
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
.o-mix div{border-right:1px solid #111;display:flex;min-width:78px;flex-shrink:0;align-items:center;padding-left:8px;font:400 11px 'SM';white-space:nowrap;overflow:hidden}
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
[class*="st-key-orbit_money"] label p{font:400 11px 'SM'!important;letter-spacing:.08em;text-transform:uppercase;color:#111;white-space:nowrap}
[class*="st-key-orbit_money"]{padding-bottom:8px}
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


def render_hero(df: pd.DataFrame, *, show_money: bool = True) -> None:
    """show_money: the hero shows no money of ours either way (bills on hover are the customer's own); kept for a uniform API."""
    scored, flagged = len(df), int(df.flagged.sum())
    messaged, texts = int(df.messaged.sum()), int((df.channel == "text").sum())
    st.markdown(f"<div class='o-strip'><span><b>Churn + upsell board</b> · this week</span><span>{scored:,} customers scored</span>"
                f"<span>01 / 05</span></div>", unsafe_allow_html=True)
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


# ============================================================== act 2 — how we pick the deal
CSS_DEAL = f"""
.o-flow{{display:flex;align-items:stretch;margin:6px 0 10px}}
.o-flow .bx{{flex:1 1 0;border:1px solid {INK};padding:12px 14px 14px;background:{BG};min-height:118px}}
.o-flow .bx .no{{font:400 11px 'SM';letter-spacing:.08em;color:{MUTED}}}
.o-flow .bx .t{{font:500 17px/1.2 'SG';margin:6px 0 6px}}
.o-flow .bx .d{{font:400 13px/1.35 'SG';color:#333}}
.o-flow .bx.end{{border-color:{MAG};box-shadow:inset 0 0 0 1px {MAG}}}
.o-flow .ln{{flex:0 0 22px;align-self:center;border-top:1px solid {INK}}}
.o-cards{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:12px 0 10px}}
.o-card{{border:1px solid {INK};padding:10px 12px 12px;background:{BG};min-height:112px;display:flex;flex-direction:column;gap:6px}}
.o-card .nm{{font:500 14px/1.25 'SG'}}
.o-card .bar{{font:400 10px 'SM';letter-spacing:.08em;text-transform:uppercase;color:{MUTED}}}
.o-card .pill{{align-self:flex-start;font:400 10px 'SM';letter-spacing:.08em;text-transform:uppercase;border:1px solid {INK};padding:2px 6px}}
.o-card .rs{{font:400 12px/1.35 'SG';color:#333}}
.o-card .nt{{margin-top:auto;font:400 12px 'SM'}}
.o-card.win{{border:2px solid {MAG};padding:9px 11px 11px}}
.o-card.win .pill{{border-color:{MAG};background:{MAG};color:#fff}}
.o-card.out{{border-color:#B9B2A7;color:#8C877D}}
.o-card.out .nm{{text-decoration:line-through;color:#8C877D}}
.o-card.out .rs,.o-card.out .pill{{color:#8C877D;border-color:#B9B2A7}}
.o-pickline{{font:400 18px/1.4 'SG';border-top:1px solid {INK};padding:12px 0 4px}}
"""


def _deal_stats(options, candidates=None) -> tuple[float, float, str] | None:
    """(options weighed per customer, ruled out per customer, source) averaged over every account."""
    try:
        if options is not None and len(options) and {"account_id", "verdict"} <= set(options.columns):
            g = options.groupby("account_id")
            ruled = options.verdict.astype(str).str.lower().str.replace("_", " ").eq("ruled out").groupby(options.account_id).sum()
            return float(g.size().mean()), float(ruled.mean()), "options"
        if candidates is not None and len(candidates) and "account_id" in candidates:
            g = candidates.groupby("account_id")
            ok = candidates.eligible.astype(str).str.lower().isin(["true", "1"]) if "eligible" in candidates else None
            ruled = (~ok).groupby(candidates.account_id).sum().mean() if ok is not None else float("nan")
            return float(g.size().mean()), float(ruled), "candidates"
    except Exception:  # noqa: BLE001
        return None
    return None


def _pick_sentence(r, d, o) -> str:
    """'Picked: X, sent by Y, because Z.' from decisions (else df)."""
    def low(t):
        t = _cap(t).rstrip(".")
        return t[:1].lower() + t[1:]
    lang = {"EN": "English", "ES": "Spanish"}.get(str(r.get("language", "")).upper(), "")
    dec = _sv(d, "decision") if d is not None else ("message" if bool(r.get("messaged")) else ("receipt_only" if _sv(r, "receipt_line_en") else "silent"))
    ch = (_sv(d, "channel") if d is not None else _sv(r, "channel")).lower()
    reason = (_sv(d, "decision_reason") if d is not None else _sv(r, "reason_line")) or ""
    if dec == "message":
        label = _sv(d, "offer_label") if d is not None else ""
        if not label and o is not None and (o.verdict == "picked").any():
            label = str(o[o.verdict == "picked"].option_label.iloc[0])
        how = CHANNEL_PHRASE.get(ch, "as a message").replace("as an agent call", "an agent call").replace("in the app", "in-app message").replace("by ", "")
        return (f"Picked: <b>{esc(label or 'one message')}</b>, sent by <b>{esc(how)}</b>{(' in ' + lang) if lang else ''}, "
                f"because {esc(low(reason.split(':', 1)[-1] if ':' in reason[:40] else reason))}.")
    if dec == "receipt_only":
        sav = _sv(d, "customer_saves_usd_mo") if d is not None else _sv(r, "receipt_saving_mo")
        saves = f" (saves them ${float(sav):,.0f}/mo)" if sav and float(sav) > 0 else ""
        return (f"Picked: <b>a cheaper plan{esc(saves)}</b>, shown <b>on the bill and in the app</b>{(' in ' + lang) if lang else ''}, "
                f"because a plan change is never sent as a message.")
    return f"Picked: <b>do nothing</b>, nothing is sent, because {esc(low(reason) or 'no option beats doing nothing')}."


def render_deal_engine(df: pd.DataFrame, account_id: str, options: pd.DataFrame | None = None,
                       decisions: pd.DataFrame | None = None, show_money: bool = True, *,
                       candidates: pd.DataFrame | None = None, demo_ids: list[str] | None = None, key: str = "orbit") -> str:
    """Act 2 'How we pick the deal': five-box flow, then a live example for one demo customer.
    options: options.csv (account_id, option_label, verdict picked/not_sent/ruled_out, reason, net_mid_usd; do nothing first).
    decisions: decisions.csv (decision, channel, offer_label, decision_reason) for the closing sentence.
    candidates (optional, every account): fallback for the per-customer averages when options is missing.
    demo_ids: account ids for the small picker (default: the demo accounts in df); account_id is the default pick.
    show_money=False: no net figures; weighing is described without cost. Returns the account shown."""
    st.markdown(f"<style>{CSS_DEAL}</style>", unsafe_allow_html=True)
    _act("04 / 05", "How we pick the deal", "the same five steps for every customer")
    weigh = ("The chance it keeps them, against what it costs us and how much it bugs them (team estimate)." if show_money
             else "How likely it helps vs how much it bugs them (team estimate).")
    boxes = [("Every option on the table", "Do nothing is always first: every offer has to beat it."),
             ("Eligibility rules", "The real promotion rules cross out what this customer can't get."),
             ("Open issue?", "Fix it first. With an open support issue, the only message is a fix."),
             ("Weigh each option", weigh),
             ("The pick", "One decision, plus the channel and the language.")]
    flow = "<div class='ln'></div>".join(f"<div class='bx {'end' if i == 4 else ''}'><div class='no'>{i + 1:02d}</div><div class='t'>{esc(t)}</div>"
                                         f"<div class='d'>{esc(d)}</div></div>" for i, (t, d) in enumerate(boxes))
    stt = _deal_stats(options, candidates)
    cap = ""
    if stt and stt[2] == "options":
        cap = f"Each customer: {stt[0]:.0f} options weighed, {stt[1]:.0f} ruled out by real promotion rules on average."
    elif stt:
        cap = f"{stt[0]:.0f} options weighed per customer" + (f", {stt[1]:.0f} ruled out on average." if stt[1] == stt[1] else ".")
    st.markdown(f"<div class='o-flow'>{flow}</div>" + (f"<div class='o-lbl' style='margin-bottom:22px'>{esc(cap)}</div>" if cap else ""),
                unsafe_allow_html=True)

    ids = demo_ids or list(df[df.is_demo].account_id)
    ids = [a for a in ids if a in set(df.account_id)]
    pk = f"{key}_deal_pick"
    if ids:
        if st.session_state.get(pk) not in ids:
            st.session_state[pk] = account_id if account_id in ids else ids[0]
        a, _ = st.columns([2, 3])
        a.segmented_control("Live example", ids, key=pk, format_func=lambda x: f"Customer {cid(x)}")
        acc = st.session_state.get(pk) or account_id
    else:
        acc = account_id
    if acc not in set(df.account_id):
        return acc
    r = df[df.account_id == acc].iloc[0]
    o = _opts_for(options, acc)
    d = _drow(decisions, acc)
    cards = ""
    if o is not None:
        for i, x in enumerate(o.itertuples()):
            v = x.verdict
            is_dn = str(x.option_label).strip().lower() == "do nothing"
            cls = "win" if v == "picked" else ("out" if v == "ruled out" else "")
            reason = x.reason
            if v == "picked" and reason.strip().lower() in ("sent.", "sent"):
                reason = "Won: worth sending at realistic save rates and passed every outreach rule."
            elif v == "picked" and reason.lower().startswith("no message:"):
                reason = "Won: " + _cap(reason)
            nt = getattr(x, "net_mid_usd", None)
            net = (f"<div class='nt'>{'net at 10% · ' + _signed(float(nt)) if not is_dn else 'net $0 · the baseline'}</div>"
                   if show_money and nt is not None and not pd.isna(nt) else "")
            cards += (f"<div class='o-card {cls}'>" + ("<div class='bar'>the bar to beat</div>" if is_dn else "")
                      + f"<div class='nm'>{esc(str(x.option_label))}</div><span class='pill'>{esc(v)}</span>"
                      f"<div class='rs'>{esc(reason)}</div>{net}</div>")
    st.markdown((f"<div class='o-cards'>{cards}</div>" if cards else "")
                + f"<div class='o-pickline'>{_pick_sentence(r, d, o)}</div>", unsafe_allow_html=True)
    return acc


# ============================================================== act 3 — one customer, six steps
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


def _tower(base, top, rest, overlap, p_now, key, hl: str | None = None, hl_old: float | None = None,
           hl_delta: float | None = None) -> go.Figure:
    """hl (optional): feature whose block moved (the 'Other' block when it isn't in the top): drawn solid magenta at its
    new height, a dashed grey outline at its old height (hl_old pts), and a callout with the signal's own change this
    event (hl_delta, points; 'new' when it contributed nothing before). The total risk change is the header chip's."""
    cols = [("Typical customer", "base", base, 0.0)]
    cum = base
    hl_i = None
    for _, t in top.iterrows():
        if hl is not None and t.feat == hl:
            hl_i = len(cols)
        cols.append((t.label, t.lane, t.pts, cum))
        cum += t.pts
    if abs(rest + overlap) >= 0.005:
        if hl is not None and hl_i is None:
            hl_i = len(cols)
        cols.append(("Other small signals + overlap", "Other", rest + overlap, cum))
    cols.append(("This customer", "total", p_now, 0.0))
    lane_y = {"Commerce": 0, "Customer": 1, "Live": 2, "Other": 1, "base": 1, "total": 1}
    fig, W = go.Figure(), 0.36
    ex, ey, ez, ann = [], [], [], []
    hx, hy, hz = [], [], []
    for i, (lab, lane, v, z0) in enumerate(cols):
        x, y = float(i), lane_y[lane]
        lo, hi = ((0.0, v) if lane in ("base", "total") else ((z0, z0 + v) if v >= 0 else (z0 + v, z0)))
        hi = max(hi, lo + 0.012)
        color = {"base": "#D9D3C9", "total": INK, "Other": BG}.get(lane, MAG if v > 0 else "#FFFFFF")
        if i == hl_i:
            color = MAG
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
            if i == hl_i and hl_old is not None:   # dashed grey outline: the same block at its old height
                g = 0.04
                OX = [x - W - g, x + W + g, x + W + g, x - W - g] * 2
                OY = [y - W - g, y - W - g, y + W + g, y + W + g] * 2
                olo, ohi = (z0, z0 + hl_old) if hl_old >= 0 else (z0 + hl_old, z0)
                OZ = [olo] * 4 + [max(ohi, olo + 0.012)] * 4
                hx += [OX[a], OX[b], None]; hy += [OY[a], OY[b], None]; hz += [OZ[a], OZ[b], None]
        if i == hl_i and hl_delta is not None:
            ann.append(dict(x=x, y=y, z=hi, text=f"<b>{'new' if hl_old is not None and abs(hl_old) < 0.005 else 'moved'} this event</b> · {hl_delta:+.2f} pts", showarrow=True, arrowhead=0, arrowwidth=1,
                            arrowcolor=MAG, ax=40, ay=-30, font=dict(family="SM", size=10, color=MAG), bgcolor="#fff",
                            bordercolor=MAG, borderwidth=1, borderpad=3))
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
    if hx:
        fig.add_trace(go.Scatter3d(x=hx, y=hy, z=hz, mode="lines", line=dict(color=MUTED, width=2, dash="dash"), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter3d(x=cx, y=cy, z=cz, mode="lines", line=dict(color=INK, width=1.4, dash="dash"), hoverinfo="skip", showlegend=False))
    for n in range(min(3, len(top))):
        t, i = top.loc[n], n + 1
        ann.append(dict(x=i, y=lane_y[t.lane], z=cols[i][3] + max(t.pts, 0), text=f"<b>{n + 1}</b>  {esc(t.label)}<br>{t.pts:+.2f} pts",
                        showarrow=True, arrowhead=0, arrowwidth=1, arrowcolor=MAG if t.pts > 0 else INK,
                        ax=[-50, 30, 140][n], ay=[-34, -80, -126][n], font=dict(family="SM", size=10, color=INK),
                        bgcolor="#fff", bordercolor=INK, borderwidth=1, borderpad=4))
    for ln, y in (("COMMERCE", 0), ("CUSTOMER", 1), ("LIVE", 2)):
        ann.append(dict(x=len(cols) - 0.35, y=y, z=0, text=ln, showarrow=False, xanchor="left", font=dict(family="SM", size=10, color=MUTED)))
    zmax = max(max(c[3] + max(c[2], 0) for c in cols), p_now, base) * 1.7
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
    plan = (str(r.get("plan_name")) if pd.notna(r.get("plan_name")) and str(r.get("plan_name", "")).strip() else
            " ".join(str(r.get(c, "")).title() for c in ("plan_family", "plan_tier") if pd.notna(r.get(c))))
    g = {
        "Commerce": [("Plan", plan or None), ("Plan price / mo", money("plan_price_cents")), ("Last bill", money("last_bill_cents")),
                     ("Bill vs prior 3 mo", num("bill_change_3m_pct", "{:+.0f}%", 100)), ("Promo just ended", yes("promo_expired_recent")),
                     ("Lines", num("n_lines")), ("Phone age, months", num("max_device_age_months")),
                     ("Financing months left", num("max_financing_months_remaining")), ("Home Internet", yes("has_home_internet"))],
        "Customer": [("Months with us", num("tenure_months")), ("Account type", str(r.get("segment", "")).title() or None),
                     ("Support contacts, 90 days", num("support_90d")), ("Unresolved, 90 days", num("unresolved_90d")),
                     ("Unhappy contacts, 90 days", num("negative_contacts_90d")), ("Asked about cancelling, 270 days", num("cancel_inquiries_270d")),
                     ("Prefers", PREF_WORDS.get(str(r.get("contact_preference", "")).strip().lower(), str(r.get("contact_preference", ""))) or None), ("Language", str(r.get("language", "")).upper() or None)],
        "Live": [("Comparing carriers (0-1)", num("competitor_research_score", "{:.2f}")), ("Asked about transferring number", yes("port_out_inquiry")),
                 ("App sessions, 30 days", num("app_sessions_30d")), ("Data use vs 3 mo ago", num("data_growth_pct", "{:+.0f}%", 100)),
                 ("Data per month, GB", num("data_gb_3m_avg", "{:.1f}"))],
    }
    return {k: [(a, b) for a, b in v if b not in (None, "", "Nan")] for k, v in g.items()}


def _v(r, c):
    v = r.get(c)
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else v


def _yn(r, c):
    v = _v(r, c)
    return None if v is None else ("yes" if float(v) > 0 else "no")


def _fmt(r, c, f):
    v = _v(r, c)
    return None if v is None else f(v)


INPUT_VALUES: dict[str, Callable] = {  # considerations item -> this customer's value (None = not in this view)
    "Bill increase": lambda r: _fmt(r, "bill_increase_pct", lambda v: f"{float(v) * 100:+.0f}%"),
    "Promo ended recently": lambda r: _yn(r, "promo_expired_recent"),
    "Plan misfit": lambda r: _fmt(r, "plan_misfit_share", lambda v: f"{float(v) * 100:.0f}% of lines"),
    "Phone age": lambda r: _fmt(r, "max_device_age_months", lambda v: f"{float(v):.0f} months"),
    "Bring-your-own-phone account": lambda r: None if _v(r, "n_byod_lines") is None else f"{int(r.n_byod_lines)} of {int(_n(r, 'n_lines'))} lines",
    "Phone payoff within 3 months": lambda r: _yn(r, "financing_ends_within_3m"),
    "Home Internet on the account": lambda r: _yn(r, "has_home_internet"),
    "Plan, family and price": lambda r: (f"{_v(r, 'plan_name')} · ${_n(r, 'plan_price_cents') / 100:,.0f}/mo" if _v(r, "plan_name") else None
        if _v(r, "plan_family") is None else
        f"{str(r.plan_family).replace('_', ' ').title()} {str(_v(r, 'plan_tier') or '').replace('_', ' ').title()} · ${_n(r, 'plan_price_cents') / 100:,.0f}/mo".replace("  ", " ")),
    "Last bill": lambda r: _fmt(r, "last_bill_cents", lambda v: f"${float(v) / 100:,.0f}"),
    "Bill change reason": lambda r: _fmt(r, "bill_change_reason", lambda v: str(v).replace("_", " ")),
    "Phone financing and trade-in value": lambda r: _fmt(r, "max_financing_months_remaining", lambda v: f"{int(v)} months left" if float(v) > 0 else "nothing financed"),
    "Add-ons and streaming perk": lambda r: None if _v(r, "n_account_addons") is None else
        f"{int(r.n_account_addons)} add-ons · streaming {'included' if _n(r, 'has_streaming_addon') > 0 else 'no'}",
    "Connected lines (watch, tablet)": lambda r: _fmt(r, "n_connected_lines", lambda v: f"{int(v)}"),
    "AutoPay": lambda r: _yn(r, "autopay"),
    "Tenure": lambda r: _fmt(r, "tenure_months", lambda v: f"{int(v)} months"),
    "Lines on the account": lambda r: _fmt(r, "n_lines", lambda v: f"{int(v)}"),
    "Cancellation inquiries": lambda r: _fmt(r, "cancel_inquiries_270d", lambda v: f"{int(v)} in 270 days"),
    "Segment and discount group": lambda r: None if _v(r, "segment") is None else
        f"{str(r.segment).title()} · {str(_v(r, 'discount_group') or 'none').replace('_', ' ')}",
    "Credit tier": lambda r: _fmt(r, "credit_tier", lambda v: str(v)),
    "Language": lambda r: _fmt(r, "language", lambda v: str(v).upper()),
    "Contact preference": lambda r: _fmt(r, "contact_preference", lambda v: str(v)),
    "Total support contacts in 90 days": lambda r: _fmt(r, "support_90d", lambda v: f"{int(v)}"),
    "Unresolved support contacts (90 days)": lambda r: _fmt(r, "unresolved_90d", lambda v: f"{int(v)}"),
    "Unhappy support contacts (90 days)": lambda r: _fmt(r, "negative_contacts_90d", lambda v: f"{int(v)}"),
    "Negative sentiment": lambda r: _fmt(r, "avg_sentiment_90d", lambda v: f"{float(v):+.2f} avg, 90 days"),
    "Troubled (4+ contacts and one bad)": lambda r: None if _v(r, "support_90d") is None else
        ("yes" if _n(r, "support_90d") >= 4 and (_n(r, "unresolved_90d") > 0 or _n(r, "negative_contacts_90d") > 0) else "no"),
    "Comparing carriers": lambda r: _fmt(r, "competitor_research_score", lambda v: f"{float(v):.2f} of 1"),
    "Asked about transferring their number": lambda r: _yn(r, "port_out_inquiry"),
    "App use": lambda r: _fmt(r, "app_sessions_30d", lambda v: f"{int(v)} sessions, 30 days"),
    "Recent usage": lambda r: _fmt(r, "data_gb_3m_avg", lambda v: f"{float(v):.1f} GB/mo · {_n(r, 'streaming_hours_3m_avg'):.0f} h streaming"),
    "Open issue topic": lambda r: _fmt(r, "open_issue_topic", lambda v: str(v)),
}


def _inputs_html(r, inputs: pd.DataFrame, was: dict | None = None) -> tuple[str, int, int]:
    """was (optional): {item: previous shown value}; those rows get a magenta left hairline and a grey 'was X'."""
    cols, shown, total = "", 0, 0
    for g, x in inputs.groupby("group", sort=False):
        name = re.sub(r"^\w+\.\s*(Inputs:\s*)?", "", str(g)).strip().title()
        rows = ""
        for it in x.itertuples():
            fn = INPUT_VALUES.get(str(it.item))
            val = fn(r) if fn else None
            total += 1
            shown += val is not None
            w = (was or {}).get(str(it.item))
            if w is not None and val is not None:
                a_, b_ = str(val).split(" ", 1) + [""], str(w).split(" ", 1) + [""]
                nv_, ov_ = (a_[0], b_[0]) if a_[1] and a_[1] == b_[1] else (str(val), str(w))   # '−0.20 was −0.13'
                nv_, ov_ = nv_.replace("-", "−"), ov_.replace("-", "−")
                rows += (f"<div class='o-kv o-chg' style='border-left:2px solid {MAG};padding-left:8px;margin:3px 0'><span>{esc(str(it.item))}</span>"
                         f"<span><span class='nv' style='color:{MAG}'>{esc(nv_)}</span> <span class='wv' style='color:{MUTED};font-size:12px'>was {esc(ov_)}</span></span></div>")
                continue
            rows += (f"<div class='o-kv'><span>{esc(str(it.item))}</span><span>{esc(str(val)) if val is not None else '<i style=\"color:#6B675F\">not in this view</i>'}</span></div>")
        cols += f"<div class='col'><div class='gh'>{esc(name)} · {len(x)}</div>{rows}</div>"
    return cols, shown, total


def _nice_date(x) -> str:
    """'2026-12-03' -> 'Dec 3, 2026'; the input unchanged if it isn't a date."""
    try:
        t = pd.Timestamp(x)
        return f"{t.strftime('%b')} {t.day}, {t.year}"
    except Exception:  # noqa: BLE001
        return str(x)


def _pref_lang(r) -> str:
    """'ES' when the customer prefers Spanish (language column), else 'EN'."""
    return "ES" if str(r.get("language", "") or "").strip().lower() == "es" else "EN"


def _msg_es(r, d=None) -> str:
    return (_sv(d, "message_es") if d is not None else "") or str(r.get("message_es", "") or "").strip()


def _message_html(r, d=None, lang: str = "EN") -> str:
    """Step 5: the message as the customer receives it, in its channel's look. Empty string when there is nothing to show.
    d (optional decisions row): receipt_line / customer_saves_usd_mo fill in when df lacks them; receipt_kind 'tradeoff'
    adds the receipt_tradeoff_line under the bill row as "but you'd lose: ..."; timing 'wait' + wait_until puts the
    scheduled date in the preview header. lang 'ES' shows message_es (decisions row, else df) when there is one."""
    msg = str(r.get("message_en", "") or "").strip()
    if lang == "ES" and msg and _msg_es(r, d):
        msg = _msg_es(r, d)
    wait = _sv(d, "wait_until") if d is not None and _sv(d, "timing").lower() == "wait" else ""
    when = f"scheduled {_nice_date(wait)}" if wait else "now"
    ch = r.get("channel")
    bill = str(r.get("receipt_line_en", "") or "").strip() or (_sv(d, "receipt_line") if d is not None else "")
    trade = _sv(d, "receipt_tradeoff_line") if d is not None and _sv(d, "receipt_kind").lower() == "tradeoff" else ""
    mm = re.search(r"(?:,\s*)?\bbut you'?d lose:?\s*(.*)$", trade, flags=re.I)
    lose = mm.group(1).strip().rstrip(".") if mm else trade
    if not bill and trade:
        bill = (trade[:mm.start()] if mm else trade).strip().rstrip(".")
    if bill:
        lines = [s.strip() for s in bill.split("|") if s.strip()]
        sav = r.get("receipt_saving_mo")
        if (sav is None or pd.isna(sav)) and d is not None and _sv(d, "customer_saves_usd_mo"):
            sav = float(d.get("customer_saves_usd_mo")) or None
        rows = "".join(
            f"<div class='row {'mark' if i == 0 else ''}'><span>{esc(s)}"
            + (f"<br><span style='font:400 11px SM;color:#6B675F'>but you'd lose: {esc(lose)}</span>" if i == 0 and lose else "")
            + f"</span><span class='amt'>{('−$' + format(float(sav), ',.0f') + '/mo') if i == 0 and sav is not None and not pd.isna(sav) else ''}</span></div>"
            for i, s in enumerate(sorted(lines, key=lambda s: not s.lower().startswith("same features"))))
        bill_html = f"<div class='o-bill'><div class='h'><span>Your monthly bill · notes</span><span>printed on the bill</span></div>{rows}</div>"
    else:
        bill_html = ""
    if not msg:
        return bill_html
    body = esc(msg)
    if ch == "text":
        m = f"<div class='o-sms'><div class='top'>Text message · {esc(when)}</div><div class='b'>{body}</div></div>"
    elif ch == "in_app":
        first, _, rest = msg.partition(". ")
        m = (f"<div class='o-app'><span class='bell'>&#x1F514;&#xFE0E;</span><span class='t'>{esc(first)}.</span>"
             f"<span class='b'>{esc(rest)}</span><span class='m'>app notification · {esc(when)}</span></div>")
    elif ch == "email":
        subj = "About your open support request"
        m = (f"<div class='o-mail'><div class='h'>From: Customer Care</div><div class='h'>Subject: {subj}</div>"
             + (f"<div class='h'>Sends: {esc(when)}</div>" if wait else "") +
             f"<div class='body'>{body}</div></div>")
    elif ch == "call":
        s = re.sub(r"^\[(?:Call script|Guion de llamada)\]\s*", "", msg)
        ask = ""
        for kw in ("Ask:", "Pregunte:"):
            if kw in s:
                s, _, ask = s.partition(kw)
                break
        parts = [p.strip() for p in re.split(r"(?<=[.?!])\s+", s.strip()) if p.strip()]
        items = "".join(f"<li>{'<span class=say>Say:</span> ' if i == 0 else ''}{esc(p)}</li>" for i, p in enumerate(parts))
        if ask:
            q, _, tail = ask.strip().partition("?")
            items += f"<li><span class='say'>Ask:</span> {esc(q)}?</li>" + (f"<li>{esc(tail.strip())}</li>" if tail.strip() else "")
        m = f"<div class='o-call'><div class='h'><span>&#x260E;&#xFE0E; Agent call script</span><span>read aloud{(' · ' + esc(when)) if wait else ''}</span></div><ol>{items}</ol></div>"
    else:
        m = f"<div class='o-app'><span class='bell'></span><span class='b'>{body}</span></div>"
    return m + (("<div style='height:12px'></div>" + bill_html) if bill_html else "")


DN_REASON = {"happy": "nothing is going wrong on this account", "open_ticket": "there's an open ticket to fix first",
             "wait_payoff": "it's better to wait until their phone is paid off"}


def _bill_rule_pass(r, d=None) -> str:
    """Rule 4's line when it doesn't stop us, from the same fields step 1 shows (bill_increase_pct, bill_change_reason,
    unresolved_90d) and the decision's guardrail_note."""
    inc = _v(r, "bill_increase_pct")
    rose = (inc is not None and round(float(inc) * 100) > 0) or bool(_sv(r, "bill_change_reason"))
    if not rose:
        return "Bill didn't go up."
    if _n(r, "unresolved_90d") > 0:
        return "Bill went up, but fixing their open issue is still allowed."
    if "offset" in (_sv(d, "guardrail_note") if d is not None else "").lower():
        return "Bill went up, but the message comes with a credit that offsets it."
    if "new phone" in _sv(r, "bill_change_reason").lower() or _sv(r, "bill_change_reason").lower() == "device_installment":
        return "Bill went up for a new phone they chose, so a message is still allowed."
    if not _sv(r, "bill_change_reason"):
        return "Bill went up, but not from a promo ending or a phone payment, so it doesn't hold a message back."
    return "Bill went up, but this message is still allowed."


PREF_WORDS = {"sms": "text", "text": "text", "app": "the app", "in_app": "the app", "email": "email", "call": "a phone call"}


def outreach_rules(r, channel: str | None = None, d=None) -> list[tuple[str, str, str]]:
    """The outreach rules (from the outreach playbook), in order; the first one that stops us decides, and if none
    does we send. Returns (rule, status, detail) with status 'stop' (decides: no message), 'pass', 'info' (also true:
    shapes the message), 'na' (doesn't apply), 'note' (noted) or 'skip' (not reached).
    Uses optional columns: action_code, do_nothing_reason, policy_selected, block_reason, bill_increase_pct,
    bill_change_reason, unresolved_90d, contact_preference; d (optional decisions row) for guardrail_note."""
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
            st_ = {"info": "info" if applies else "na", "note": "note"}.get(kind, "pass")
            out.append((rule, st_, detail_pass if not applies else detail_stop))
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
        (br == "bill_change_no_fix") if "block_reason" in r else None, "Bill went up and we have no offer that lowers it.", _bill_rule_pass(r, d))
    un = _n(r, "unresolved_90d")
    add("With an open support issue, the only message allowed is a fix, never an offer.", un > 0,
        f"{int(un)} unresolved support contact{'s' if un != 1 else ''}: "
        + ("we'll call to help fix their open issue." if (channel or "") == "call" else "we'll help fix their open issue."), "No open support issue.", kind="info")
    pref = sv("contact_preference")
    if pref:
        add("We reach people the way they asked to be reached.", True, f"Prefers {PREF_WORDS.get(pref.strip().lower(), pref)}.", "", kind="note")
    add("One proactive message per account at most.", True, "At most one message this run.", "", kind="note")
    return out


def _cap(t) -> str:
    t = str(t or "").removeprefix("No message: ").strip()
    return t[:1].upper() + t[1:]


TODAY_LABEL = {"check_in": "a free check-in", "variant_switch": "a cheaper version of their plan", "right_size": "a right-sized plan",
               "care_credit_fix_first": "a $25 credit plus a fix-first callback", "fix_first": "a fix-first callback",
               "care_credit": "a $25 care credit", "loyalty_credit": "a loyalty credit", "perk_reminder": "a perk reminder",
               "bill_shock_price_lock": "bill-shock relief", "step_up": "a step-up plan", "family_upgrade": "a family upgrade",
               "home_internet_bundle": "a Home Internet bundle", "do_nothing": "do nothing"}
CHANNEL_PHRASE = {"in_app": "in the app", "text": "by text", "email": "by email", "call": "as an agent call"}


def _sv(r, c) -> str:
    v = r.get(c) if hasattr(r, "get") else None
    return "" if v is None or (isinstance(v, float) and math.isnan(v)) else str(v).strip()


def _drow(decisions, acc):
    try:
        if decisions is None or not len(decisions) or "account_id" not in decisions:
            return None
        d = decisions[decisions.account_id == acc]
        return d.iloc[0] if len(d) else None
    except Exception:  # noqa: BLE001
        return None


def _next_version(r, decisions=None) -> dict:
    """The next-version decision for one account: from decisions.csv when given, else from the outreach columns on df."""
    d = _drow(decisions, r.account_id)
    nv = {"net": None}
    if d is not None:
        nets = [d.get(f"net_{k}_usd") for k in ("low", "mid", "high")]
        try:
            nv["net"] = tuple(float(x) for x in nets) if all(x is not None and not pd.isna(x) for x in nets) else None
        except (TypeError, ValueError):
            nv["net"] = None
        nv["net_why"] = _sv(d, "why_mid") or _sv(d, "net_mid_why") or _sv(d, "net_why")
    if d is not None and not any(c in d.index for c in ("channel", "decision", "receipt_line", "offer_label")):
        dd, d = d, None   # money/timing-only ledger: the pick itself comes from df
    else:
        dd = d
    if d is not None:
        ch = _sv(d, "channel").lower().replace("-", "_").replace(" ", "_")
        ch = {"in_app_message": "in_app", "agent_call": "call", "phone_call": "call", "sms": "text", "none": ""}.get(ch, ch)
        if _sv(d, "receipt_line") or _sv(d, "decision") == "receipt_only" or ch == "bill":
            kind, ch = "bill", ""
        elif ch:
            kind = "message"
        else:
            kind = "quiet"
        reason = _sv(d, "decision_reason") or _sv(d, "guardrail_note")
        label = _sv(d, "offer_label") or _sv(d, "decision")
        code = None
    else:
        ch = r.get("channel") if isinstance(r.get("channel"), str) else ""
        kind = "message" if bool(r.get("messaged")) else ("bill" if _sv(r, "receipt_line_en") else "quiet")
        reason = _cap(_sv(r, "reason_line"))
        label = ""
        code = (_sv(r, "policy_action") or None) if kind == "message" else (
            (_sv(r, "action_code") if _sv(r, "action_code") in ("variant_switch", "right_size") else "variant_switch") if kind == "bill" else "do_nothing")
    low = reason[:1].lower() + reason[1:] if reason else ""
    if kind == "quiet":
        nv.update(headline="Stay quiet.", sentence=f"we'd stay quiet, because {low.rstrip('.')}." if low else "we'd stay quiet.")
    elif kind == "bill":
        nv.update(headline="Cheaper plan on the bill. No message.", sentence=f"we'd show the cheaper plan on the bill instead of messaging. {reason}".strip())
    else:
        nv.update(headline=f"Reach out {CHANNEL_PHRASE.get(ch, 'with a message')}" + (f": {label}." if label else "."),
                  sentence=f"we'd reach out {CHANNEL_PHRASE.get(ch, 'with one message')}. {reason}".strip())
    if dd is not None and _sv(dd, "already_leaving").lower() in ("true", "1", "yes"):
        nv["leaving"] = _leaving(_sv(dd, "already_leaving_note")) if _sv(dd, "already_leaving_note") else LEAVING_DEFAULT
    nv.update(kind=kind, channel=ch, code=code, label=label, reason=reason,
              timing=_sv(dd, "timing").lower() if dd is not None else "", wait_until=_sv(dd, "wait_until") if dd is not None else "")
    return nv


def _money_bar(nv) -> str:
    if not nv.get("net"):
        return ""
    lo, mid, hi = nv["net"]
    span = max(abs(lo), abs(hi), 1)
    def x(v):
        return 50 + 50 * v / span
    return (f"<div class='o-lbl' style='margin-top:10px'>Net value, low / mid / high save rate</div>"
            f"<div style='position:relative;height:22px;border-bottom:1px solid #111;margin-top:4px'>"
            f"<div style='position:absolute;left:50%;top:0;bottom:0;border-left:1px dashed #111'></div>"
            f"<div style='position:absolute;left:{min(x(lo), x(hi)):.1f}%;width:{abs(x(hi) - x(lo)):.1f}%;top:8px;height:6px;background:#111'></div>"
            f"<div style='position:absolute;left:{x(mid):.1f}%;top:2px;width:2px;height:18px;background:{MAG}'></div></div>"
            f"<div style='display:flex;justify-content:space-between;font:400 12px SM;margin-top:4px'><span>{_signed(lo)}</span>"
            f"<span style='color:{MAG}'>{_signed(mid)}</span><span>{_signed(hi)}</span></div>"
            + (f"<div class='o-lbl' style='text-transform:none;margin-top:4px'>{esc(nv.get('net_why', ''))}</div>" if nv.get("net_why") else ""))


LEAVING_DEFAULT = "Asked us about moving their number. We still reach out because fixing their open issue is worth it."


def _leaving(note: str) -> str:
    """'Already leaving' always means the customer asked us about leaving; never claim we saw them try to leave."""
    t = str(note or "").strip()
    if not t or re.search(r"\b(tr(y|ied|ying) to leave|caught|saw them|seen leaving|detected)\b", t, re.I):
        return "They asked us about leaving."
    t = re.sub(r",\s*so this account is counted\b.*$", ".", t)   # headline split is pending: no 'counted on its own line'
    return t


EVENT_WORDS = {"billing": "billing", "device": "phone", "network": "coverage", "plan_change": "plan change",
               "cancellation_inquiry": "cancelling", "promo_expired": "a promo ended", "device_installment": "a new phone payment",
               "installment_ended": "a phone was paid off"}


def _event_text(e) -> str:
    t = _sv(e, "event_text")
    if t:
        t = _leaving(t) if "leav" in t.lower() else t
        return t[:1].upper() + t[1:]
    et = _sv(e, "event_type").lower()
    parts = et.split(":")
    if parts[0] == "support" and len(parts) > 1:
        topic, extra = parts[1], (parts[2] if len(parts) > 2 else "")
        if topic == "cancellation_inquiry":
            return "Asked us about leaving"
        return f"Contacted support about {EVENT_WORDS.get(topic, topic.replace('_', ' '))}" + (", still open" if extra == "unresolved" else "")
    if parts[0] == "bill" and len(parts) > 1:
        why, amt = parts[1], (parts[2] if len(parts) > 2 else "")
        try:
            a = float(amt) / 100
            head = f"Bill {'up' if a > 0 else 'down'} ${abs(a):,.0f}"
        except ValueError:
            head = "Bill changed"
        return f"{head}: {EVENT_WORDS.get(why, why.replace('_', ' '))}"
    return et.replace("_", " ").capitalize()


def _events_for(acc, events=None, decisions=None) -> pd.DataFrame:
    src = events if events is not None else decisions
    try:
        if src is None or not len(src) or not {"account_id", "event_date"} <= set(src.columns):
            return pd.DataFrame()
        e = src[src.account_id == acc].copy()
        e = e[e.event_date.astype(str).str.strip().ne("") & e.event_date.notna()]
        return e.sort_values("event_date", ascending=False).head(3)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def _strip_html(e: pd.DataFrame, nv: dict, live: bool = False) -> str:
    if e is None or not len(e):
        return ""
    def d(x):
        try:
            return pd.Timestamp(x).strftime("%b %d").upper()
        except Exception:  # noqa: BLE001
            return str(x)
    items = "".join(f"<span style='margin-right:26px'><span style='font:700 11px SM'>{esc(d(x.event_date))}</span>&nbsp;&nbsp;"
                    f"<span style='font:400 14px SG'>{esc(_event_text(x._asdict() if hasattr(x, '_asdict') else x))}</span></span>"
                    for x in e.itertuples(index=False))
    timing = (_sv(e.iloc[0], "timing") or nv.get("timing", "")).lower()
    wait = _sv(e.iloc[0], "wait_until") or nv.get("wait_until", "")
    tag = (f"<span style='font:700 11px SM;color:{MAG};letter-spacing:.06em;text-transform:uppercase'>wait until {esc(d(wait))}</span>"
           if timing == "wait" and wait else "<span class='o-lbl'>now</span>")
    if nv.get("kind") not in ("message", "bill"):
        tag = ""
    return (f"<div style='display:flex;align-items:baseline;gap:12px;border-bottom:1px solid #111;padding:7px 0'>"
            f"<span class='o-lbl' style='min-width:150px'>Latest on the account</span><span style='flex:1'>{items}</span>{tag}</div>"
            f"<div style='text-align:right;font:400 10px SM;color:{MUTED};padding:3px 0 2px'>{"what if this happens next" if live else "latest events, refreshed each run"}</div>")


def _why_when(r, nv, e) -> str:
    if nv.get("timing") == "wait" or (e is not None and len(e) and _sv(e.iloc[0], "timing").lower() == "wait"):
        wait = nv.get("wait_until") or (_sv(e.iloc[0], "wait_until") if e is not None and len(e) else "")
        why = _sv(e.iloc[0], "wait_reason") if e is not None and len(e) else ""
        return f"<b>Why wait:</b> {esc(why or ('the better moment is ' + _nice_date(wait) if wait else 'the timing is better later'))}."
    if nv["kind"] == "bill":
        return "<b>Why now:</b> it goes on their next bill, where they already look; nothing is sent."
    if nv["kind"] == "quiet" or e is None or not len(e):
        return ""
    top = e.iloc[0]
    return f"<b>Why now:</b> {esc(_event_text(top))} on {esc(pd.Timestamp(top.event_date).strftime('%b %d') if _sv(top, 'event_date') else '')}."


def _opts_for(options, acc) -> pd.DataFrame | None:
    """This account's rows of options.csv (option_label, verdict, reason[, net_mid_usd]), verdicts normalised; None if absent."""
    try:
        if options is None or not len(options) or not {"account_id", "option_label", "verdict"} <= set(options.columns):
            return None
        o = options[options.account_id == acc].copy()
        if not len(o):
            return None
        o["verdict"] = o.verdict.astype(str).str.replace("_", " ").str.strip().str.lower()
        o["reason"] = o.get("reason", pd.Series("", index=o.index)).fillna("").astype(str)
        return o
    except Exception:  # noqa: BLE001
        return None


def _options_html(r, candidates, nv, stop, options=None) -> str:
    """Every option with one verdict: from options.csv (option_label, verdict, reason) when given, else derived."""
    o = _opts_for(options, r.account_id)
    if o is not None:
        rows, n = "", {"picked": 0, "not sent": 0, "ruled out": 0}
        for x in o.itertuples():
            v = x.verdict
            n[v] = n.get(v, 0) + 1
            col = f"color:{MAG};font-weight:700" if v == "picked" else ""
            rows += (f"<div class='o-opt {'off' if v == 'ruled out' else ''}' style='grid-template-columns:1fr 120px 1.8fr;padding:5px 0'>"
                     f"<span>{esc(str(x.option_label))}</span><span style='font:400 12px SM;{col}'>{esc(v)}</span><span class='why'>{esc(x.reason)}</span></div>")
        head = (f"<div class='o-lbl' style='margin:12px 0 4px'>Every option weighed · {n.get('picked', 0)} picked · {n.get('not sent', 0)} not sent · "
                f"{n.get('ruled out', 0)} ruled out</div>")
        return head + f"<div style='max-height:180px;overflow:auto;border-top:1px solid #111;margin-bottom:16px'>{rows}</div>"
    if candidates is None or not len(candidates):
        return ""
    c = candidates.copy()
    c["ok"] = c.eligible.astype(str).str.lower().isin(["true", "1"])
    dn = c.action_code.eq("do_nothing") if "action_code" in c else c.action.eq("do nothing")
    c = pd.concat([c[dn], c[~dn & c.ok], c[~dn & ~c.ok]])
    opt = None
    try:
        if options is not None and len(options) and {"account_id", "option_label", "verdict"} <= set(options.columns):
            opt = options[options.account_id == r.account_id].copy()
            opt["k"] = opt.option_label.astype(str).str.lower().str.strip()
            opt = opt.drop_duplicates("k").set_index("k")
    except Exception:  # noqa: BLE001
        opt = None
    pick = str(nv.get("code") or "").split("|")
    rows, n = "", {"picked": 0, "not sent": 0, "ruled out": 0}
    for x in c.itertuples():
        k = str(x.action).lower().strip()
        if opt is not None and k in opt.index:
            v, w = _sv(opt.loc[k], "verdict") or "—", _sv(opt.loc[k], "reason")
        elif not x.ok:
            v, w = "ruled out", str(x.blocked_or_ineligible_reason or "")
        elif getattr(x, "action_code", "") in pick:
            v, w = "picked", ("on the bill" if nv["kind"] == "bill" else CHANNEL_PHRASE.get(nv["channel"], ""))
        else:
            v, w = "not sent", stop or (f"we send one message only: {nv['label']}" if nv["kind"] == "message" and nv.get("label") else
                                        "we send one message only" if nv["kind"] == "message" else "")
        n[v] = n.get(v, 0) + 1
        col = f"color:{MAG};font-weight:700" if v == "picked" else ""
        rows += (f"<div class='o-opt {'off' if v == 'ruled out' else ''}' style='grid-template-columns:1fr 120px 1.8fr;padding:5px 0'>"
                 f"<span>{esc(str(x.action))}</span><span style='font:400 12px SM;{col}'>{esc(v)}</span><span class='why'>{esc(w)}</span></div>")
    head = (f"<div class='o-lbl' style='margin:12px 0 4px'>Every option weighed · {n.get('picked', 0)} picked · {n.get('not sent', 0)} not sent · "
            f"{n.get('ruled out', 0)} ruled out</div>")
    return head + f"<div style='max-height:180px;overflow:auto;border-top:1px solid #111;margin-bottom:16px'>{rows}</div>"


CSS_LIVE = """
.o-live{border:1px solid var(--ink);background:#fff;margin:4px 0 14px}
.o-live .hd{display:flex;justify-content:space-between;align-items:baseline;border-bottom:1px solid var(--ink);padding:10px 14px}
.o-live .chips{display:flex;flex-wrap:wrap;gap:8px;padding:12px 14px;border-bottom:1px solid var(--ink);min-height:52px;align-items:center}
.o-live .chip{border:1px solid var(--ink);padding:5px 10px;font:400 13px 'SM'}
.o-live .chip.new{background:var(--ink);color:#fff}
.o-live .chip.todo{border-style:dashed;color:var(--muted);border-color:var(--muted)}
.o-live .row{display:grid;grid-template-columns:1fr 1.25fr 1.5fr}
.o-live .cell{padding:12px 14px;border-right:1px solid var(--ink)}
.o-live .cell:last-child{border-right:0}
.o-live .num{font:500 44px/1 'SG';letter-spacing:-.02em}
.o-live .num small{font-size:20px}
.o-live .delta{font:400 13px 'SM';color:var(--muted);margin-top:6px}
.o-live .delta.up{color:var(--mag)}
.o-live .txt{font:400 17px/1.35 'SG';margin-top:6px}
.o-live .card{padding:0}
.o-live .card .pk{font:500 26px/1.1 'SG';padding:12px 14px 6px}
.o-live .card .pk.flip{background:var(--mag);color:#fff;padding:14px 14px 10px}
.o-live .card .ws{font:400 15px/1.35 'SG';padding:6px 14px 12px}
.o-live .ft{border-top:1px solid var(--ink);padding:8px 14px;font:400 12px 'SM';color:var(--muted)}
"""


def _live_go(state_key: str, i: int) -> None:
    st.session_state[state_key] = i


def render_live(rows: pd.DataFrame, *, show_money: bool = True, key: str = "orbit") -> None:
    """'What if this happens next': a manual Next event / Reset strip over precomputed rows (one per event). Each press
    adds one event; the risk, the reason that moved and the pick come from the rows as given (no math here)."""
    rows = rows.sort_values("step").reset_index(drop=True)
    acc = str(rows.account_id.iloc[0])
    sk = f"{key}_live_{acc}"
    n = len(rows) - 1
    i = max(0, min(int(st.session_state.get(sk, 0)), n))
    cur, first = rows.iloc[i], rows.iloc[0]
    prev = rows.iloc[i - 1] if i > 0 else cur
    st.markdown(f"<style>{CSS_LIVE}</style>", unsafe_allow_html=True)
    chips = "".join(f"<span class='chip{' new' if j == i else ''}'>{j:02d} · {esc(str(rows.event_label[j]))}</span>"
                    for j in range(1, i + 1))
    chips += "".join(f"<span class='chip todo'>{j:02d} · ?</span>" for j in range(i + 1, n + 1))
    r_now, r_prev = float(cur.risk) * 100, float(prev.risk) * 100
    d = r_now - r_prev
    delta = ("starting point" if i == 0 else f"{'+' if d >= 0 else '−'}{abs(d):.1f} pts vs before · was {pct(float(first.risk) * 100)} at the start")
    if i == 0:
        what = "Nothing new yet. Press Next event to see what happens."
        moved = "Today's top reason: " + str(cur.reason_1 or "")
    else:
        what = str(cur.event_line or "")
        moved = str(cur.reason_changed or "") or "No single reason stands out."
    flipped = str(cur.pick) != str(first.pick)
    pick = "Do nothing. No message is sent." if str(cur.pick) == "silent" else f"Send a {esc(str(cur.pick_label))}."
    ev = ""
    if show_money and str(cur.pick) == "message" and pd.notna(cur.get("policy_ev_usd")):
        ev = f"<div class='ws' style='padding-top:0;color:{MUTED};font-size:13px'>Expected value, this customer only: +${float(cur.policy_ev_usd):,.2f}</div>"
    note = ("This customer only: the week's totals above don't change."
            if not show_money else "This customer only: the week's message count and dollars above don't change.")
    st.markdown(f"""<div class='o-live'><div class='hd'><span class='o-ph' style='margin:0'>What if this happens next</span>
<span class='o-lbl'>event {i} of {n}</span></div>
<div class='chips'>{chips}</div>
<div class='row'>
<div class='cell'><div class='o-lbl'>90-day churn risk</div><div class='num'>{pct(r_now)[:-1]}<small>%</small></div>
<div class='delta {"up" if d > 0 else ""}'>{esc(delta)}</div></div>
<div class='cell'><div class='o-lbl'>{"What happened" if i else "Right now"}</div><div class='txt'>{esc(what)}</div>
<div class='o-lbl' style='margin-top:10px'>{"Reason that moved" if i else "Why they score this"}</div><div class='txt'>{esc(moved)}</div></div>
<div class='cell card'><div class='o-lbl' style='padding:12px 14px 0'>{"Decision flipped" if flipped else "What we'd do"}</div>
<div class='pk{" flip" if flipped else ""}'>{pick}</div><div class='ws'>{esc(str(cur.why or ""))}</div>{ev}</div>
</div><div class='ft'>{esc(note)}</div></div>""", unsafe_allow_html=True)
    with st.container(key=f"orbit_live_nav_{key}"):
        a, b, _ = st.columns([1.2, 1, 5])
        a.button("Next event →", key=f"{sk}_next", disabled=i >= n, on_click=_live_go, args=(sk, i + 1), width="stretch",
                 type="primary")
        b.button("Reset", key=f"{sk}_reset", disabled=i == 0, on_click=_live_go, args=(sk, 0), width="stretch")


def _go(state_key: str, i: int) -> None:
    st.session_state[state_key] = i


def render_customer(df: pd.DataFrame, account_id: str, *, contributions_fn: Callable | None = None,
                    candidates: pd.DataFrame | None = None, inputs: pd.DataFrame | None = None,
                    decisions: pd.DataFrame | None = None, options: pd.DataFrame | None = None,
                    events: pd.DataFrame | None = None, show_money: bool = True, key: str = "orbit",
                    live: pd.DataFrame | None = None, tick: dict | None = None) -> None:
    """Act 2. contributions_fn(account_id, edits) -> (intercept_logit, contributions Series, p, standardized-values Series or None).
    candidates: every option row for this account (action, eligible, expected_value, blocked_or_ineligible_reason, is_chosen).
    events (optional): account_id, event_date, event_type[, event_text, timing, wait_until] for the 'Latest on the account' strip
    (read from decisions when not given; strip hidden when there are none).
    decisions / options (optional, engine output): when given they drive step 3's verdicts, step 4's pick, reason
    and money bar; otherwise the outreach columns on df are used. Missing columns degrade quietly.
    inputs: the engine-input rows of the considerations table (groups 1a-1c: group, item); step 1 lists this customer's value for each.
    show_money=False hides step 4's net-value bar; the customer's own savings (bill lines) stay.
    live (optional): precomputed 'what if this happens next' rows (step, event_label, event_line, risk, reason_changed,
    pick, pick_label, why, policy_ev_usd) for the one account they belong to; renders the Next event / Reset strip.
    tick (optional, 'the account ticks'): {risk (0-1), chip, was {item: old value}, hl (feature), reasons [(text, is_new)],
    rail (callable drawing the event rail)}; the header, step 1 and step 2 then show that event's state."""
    _act("02 / 05", "One customer, step by step", "why this score · why this action")
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
    if tick and tick.get("risk") is not None:
        p_now = float(tick["risk"]) * 100
    base = bd[0] if bd else None

    was = f"<div class='was'>(what-if, was {pct(p_orig)})</div>" if edits and bd else ""
    lines = int(_n(r, "n_lines"))
    if tick and tick.get("chip"):
        was = f"<div class='was o-tk-chip' style='color:{MAG}'>{esc(tick['chip'])}</div>"
    if tick and callable(tick.get("rail")):
        tick["rail"]()
    sub = (f"typical customer {pct(base)} · " if base else "") + (f"risk rank {int(r.risk_rank):,} of {len(df):,}" if "risk_rank" in r and not (tick and "step" in tick) else "")
    sub = sub.rstrip(" ·")
    an = (tick or {}).get("anim", "")   # CSS hook: set only on the run right after a Next event press
    st.markdown(f"""<div class='o-cust'><div><div class='o-lbl'>Customer {esc(cid(account_id))}</div>
<div class='name'>{esc(str(r.get('segment', '')).title())} account · {(str(int(_n(r, 'tenure_months')) // 12) + ' yrs') if _n(r, 'tenure_months') >= 12 else (str(int(_n(r, 'tenure_months'))) + ' months')} with us · {lines} line{'s' if lines != 1 else ''}</div>
<div class='sub'>{sub}</div></div>
<div class='{an}'><div class='risk o-tk-risk'>{pct(p_now)[:-1]}<small>%</small></div><div class='rl'>90-DAY CHURN RISK</div>{was}</div></div>""", unsafe_allow_html=True)

    events_df = _events_for(account_id, events, decisions)
    strip = _strip_html(events_df, _next_version(r, decisions), live=bool(tick and "step" in tick))
    if strip:
        st.markdown(strip, unsafe_allow_html=True)
    if live is not None and len(live) and account_id in set(live.account_id):
        render_live(live[live.account_id == account_id], show_money=show_money, key=key)
    with st.container(key=f"orbit_rail_{key}"):
        rc = st.columns(len(STEPS))
        for i, (c, name) in enumerate(zip(rc, STEPS)):
            c.button(f"{i + 1:02d}  {name}", key=f"{key}_rail_{i}", type="primary" if i == step else "secondary",
                     width="stretch", on_click=_go, args=(sk, i))

    panel = st.container()
    with panel:
        if step == 0:
            if inputs is not None and len(inputs):
                cols, shown, total = _inputs_html(r, inputs, (tick or {}).get("was"))
                st.markdown(f"<div class='o-ph'>Every input the engine uses, and this customer's value<small>{total} inputs</small></div>"
                            f"<div class='o-know o-know-sm {an}' style='margin-bottom:16px'>{cols}</div>", unsafe_allow_html=True)
            else:
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
                    tk = tick or {}
                    st.plotly_chart(_tower(b, top, rest, overlap, pn, key, tk.get("hl"), tk.get("hl_old_pts"), tk.get("hl_delta")),
                                    width="stretch", theme=None, config=CFG3D, key=f"{key}_tower")
                    st.markdown("<div class='o-hint'>drag to rotate · hover a block</div>", unsafe_allow_html=True)
                with z:
                    hlf = (tick or {}).get("hl")
                    rows = "".join(f"<div class='o-drv'><span class='n'>{i + 1:02d}</span><span>{esc(t.label)} <span class='g'>· {t.lane}</span>"
                                   + (f" <b style='color:{MAG};font:500 11px SM'>MOVED</b>" if hlf and t.feat == hlf else "") + "</span>"
                                   f"<span class='g' style='text-align:right'>{'raises' if t.pts > 0 else 'lowers'}</span>"
                                   f"<span class='p {'up' if t.pts > 0 else ''}'>{t.pts:+.2f} pts</span></div>" for i, t in top.iterrows())
                    rows += (f"<div class='o-drv'><span class='n'>··</span><span>Other small signals + overlap</span><span></span>"
                             f"<span class='p'>{rest + overlap:+.2f} pts</span></div>")
                    if hlf and not any(t.feat == hlf for _, t in top.iterrows()):
                        rows += f"<div class='o-lbl' style='margin-top:6px;color:{MAG}'>moved: inside other small signals</div>"
                    if tick and tick.get("reasons"):
                        same = bool(tick.get("same_signal"))
                        tag = "new · moved" if same else "new reason"
                        rows = "".join(f"<div class='o-drv'><span class='n'>{i + 1:02d}</span><span>{esc(t_)}</span><span></span>"
                                       f"<span class='p up'>{tag if nw else ''}</span></div>" for i, (t_, nw) in enumerate(tick["reasons"])) \
                            + ("" if same or not any(nw for _, nw in tick["reasons"]) else
                               f"<div class='o-lbl' style='margin:6px 0 0'>The new reason is worded by reason group; the block marked moved is the single signal that changed most.</div>") \
                            + "<div class='o-lbl' style='margin:14px 0 4px'>Biggest signals</div>" + rows
                    st.markdown(f"<div class='o-ph'>Typical {pct(b)} → this customer {pct(pn)}</div>{rows}", unsafe_allow_html=True)
        elif step == 2:
            nv = _next_version(r, decisions)
            rl = outreach_rules(r, (nv or {}).get("channel") if isinstance(nv, dict) else None, _drow(decisions, account_id))
            decide = f"<span style='color:{MAG};font-weight:700'>DECIDES</span>"
            mark = {"stop": f"<span style='color:{MAG};font-weight:700'>STOPS HERE</span>", "pass": "passes", "info": "also true",
                    "na": "doesn't apply", "note": "noted", "skip": "not reached"}
            chg = set((tick or {}).get("rules_changed") or [])   # live mode: the rule whose verdict changed this event

            def _rrow(n, rule, s_, det, win=False):
                hi = rule in chg
                return (f"<div class='o-opt {'win' if win or s_ == 'stop' else ''} {'off' if s_ == 'skip' else ''}' style='grid-template-columns:1.4fr 1.2fr 110px;padding:5px 0"
                        + (f";border-left:3px solid {MAG};padding-left:8px;background:#fff" if hi else "") + "'>"
                        f"<span>{n}{esc(rule)}" + (f" <b style='color:{MAG};font:500 11px SM'>CHANGED</b>" if hi else "")
                        + f"</span><span class='why'>{esc(det)}</span><span class='v'>{decide if win else mark[s_]}</span></div>")
            rrows, sent_row = "", not any(s_ == "stop" for _, s_, _ in rl) and nv.get("kind") == "message"
            for i, (rule, s_, det) in enumerate(rl):
                if sent_row and s_ in ("info", "na", "note"):   # once, right after the last rule that could stop us
                    sent_row = False
                    rrows += _rrow("→ ", "No rule above stopped us, so we send one message.",
                                   "", nv.get("headline", "").rstrip("."), win=True)
                rrows += _rrow(f"{i + 1}. ", rule, s_, det)
            st.markdown(f"<div class='o-ph'>The rules, in order<small>the first one that stops us decides · if none does, we send</small></div>{rrows}",
                        unsafe_allow_html=True)
            if (candidates is not None and len(candidates)) or _opts_for(options, account_id) is not None:
                stop = next((d for _, s_, d in rl if s_ == "stop"), "")
                st.markdown(_options_html(r, candidates, nv, stop, options), unsafe_allow_html=True)
        elif step == 3:
            nv = _next_version(r, decisions)
            reason = nv.get("reason", "")
            if nv["kind"] == "quiet":
                big = "<div class='big hero'>Do nothing.<br>No text is sent.</div>"
            elif nv["kind"] == "bill":
                big = "<div class='big'>Cheaper plan on the bill.<br>No message is sent.</div>"
            else:
                big = f"<div class='big'>{esc(nv['headline'])}</div>"
            head = "Why we're reaching out" if nv["kind"] == "message" else "Why we're not reaching out"
            why = (f"<div class='o-lbl' style='padding:10px 14px 0;border-top:1px solid #111'>{head}</div>"
                   f"<div class='why' style='border-top:0'>{esc(reason)}</div>") if reason else ""
            wl = _why_when(r, nv, events_df)
            when = f"<div style='border-top:1px solid #111;padding:10px 14px;font:400 15px/1.4 SG'>{wl}</div>" if wl else ""
            money = f"<div style='border-top:1px solid #111;padding:6px 14px 14px'>{_money_bar(nv)}</div>" if nv.get("net") and show_money else ""
            if nv.get("leaving"):
                when += (f"<div style='border-top:1px solid #111;padding:10px 14px'><div style='border:1px solid #111;padding:8px 12px'>"
                         f"<div class='o-lbl'>Asked us about leaving</div><div style='font:400 14px/1.4 SG;margin-top:4px'>{esc(nv['leaving'])}</div></div></div>")
            tk = tick or {}
            if tk.get("pick_note"):
                ch_ = tk.get("flip_at") is not None and tk.get("step", 0) >= tk["flip_at"]
                big = (f"<div class='o-lbl' style='padding:10px 14px 0;color:{MAG if ch_ else MUTED}'>{esc(tk['pick_note'])}</div>"
                       + (big if ch_ else "<div class='big hero'>Still doing nothing.<br>No text is sent.</div>"))
                if tk.get("ev"):
                    money += f"<div style='border-top:1px solid #111;padding:8px 14px;font:400 13px SM;color:{MUTED}'>{esc(tk['ev'])}</div>"
            flipc = " o-tk-flip" if (tk.get("is_flip") and an) else ""
            st.markdown(f"<div class='o-dec{flipc}' style='max-width:780px'><div class='hd'><span class='o-lbl'>What we picked</span></div>{big}{why}{when}{money}</div>",
                        unsafe_allow_html=True)
            if nv["kind"] in ("message", "bill"):
                m = _message_html(r, _drow(decisions, account_id), st.session_state.get(f"{key}_lang_{account_id}") or _pref_lang(r))
                if m:
                    lab = "On the bill:" if nv["kind"] == "bill" else f"Sent {CHANNEL_PHRASE.get(nv['channel'], 'as a message')}:"
                    slide = " o-tk-slide" if ((tick or {}).get("is_flip") and an) else ""
                    st.markdown(f"<div class='o-lbl' style='margin:12px 0 6px'>{esc(lab)}</div><div class='{slide}'>{m}</div>", unsafe_allow_html=True)
        elif step == 4:
            drow = _drow(decisions, account_id)
            lk = f"{key}_lang_{account_id}"
            lang = _pref_lang(r)
            if r.messaged and str(r.get("message_en", "") or "").strip() and _msg_es(r, drow):
                st.session_state.setdefault(lk, lang)
                lc, _ = st.columns([1, 5])
                lc.segmented_control("Message language", ["EN", "ES"], key=lk,
                                     format_func=lambda x: f"{x} · preferred" if x == lang else x)
            lang = st.session_state.get(lk) or lang
            m = _message_html(r, drow, lang)
            reason = str(r.get("reason_line", "") or "")
            head = "Why we're reaching out" if r.messaged else "Why we're not reaching out"
            top = f"<div class='o-lbl'>{head}</div><div class='o-ph'>{esc(_cap(reason))}</div>" if reason else ""
            slide = " o-tk-slide" if ((tick or {}).get("is_flip") and an) else ""
            st.markdown(top + (f"<div class='{slide}'>{m}</div>" if m else ""), unsafe_allow_html=True)
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


SAVED_VALUE_LINE = ("We value a saved account at its own monthly margin times 19.3 months (how long an average saved customer stays): "
                    "about $1,500 for an average account, about $2,000 for the ones we message.")


def _net_mid(df: pd.DataFrame, decisions: pd.DataFrame | None) -> float | None:
    """Sum of net_mid_usd over messaged accounts, from decisions/ledger. None when not available."""
    try:
        if decisions is None or "net_mid_usd" not in decisions or "account_id" not in decisions:
            return None
        msg = set(df.loc[df.messaged, "account_id"])
        v = pd.to_numeric(decisions[decisions.account_id.isin(msg)].net_mid_usd, errors="coerce").dropna()
        return float(v.sum()) if len(v) else None
    except Exception:  # noqa: BLE001
        return None


def _pct2(v: float) -> str:
    """Percent with up to two decimals, as given: 5.17, 4.8."""
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _band(lo: float, mid: float | None, hi: float, p_ahead: float | None) -> str:
    """Hairline band for the 95% range of the total, on its own dollar scale with a zero tick."""
    span_lo, span_hi = min(lo, 0), max(hi, 0)
    w = (span_hi - span_lo) or 1
    def x(v):
        return (v - span_lo) / w * 100
    mid_mark = (f"<div style='position:absolute;left:{x(mid):.2f}%;top:-4px;width:2px;height:9px;background:{MAG}'></div>" if mid is not None else "")
    ahead = f" · ahead in {p_ahead * 100:.0f}% of re-runs" if p_ahead is not None else ""
    return (f"<div style='margin:0 0 22px auto;width:46%'><div class='o-lbl' style='display:flex;justify-content:space-between'>"
            f"<span>95% range at our central assumption{ahead}</span></div>"
            f"<div style='position:relative;height:1px;background:#111;margin:10px 0 6px'>"
            f"<div style='position:absolute;left:0;top:-4px;height:9px;border-left:1px solid #111'></div>"
            f"<div style='position:absolute;right:0;top:-4px;height:9px;border-left:1px solid #111'></div>"
            f"<div style='position:absolute;left:{x(0):.2f}%;top:-3px;height:7px;border-left:1px dashed #111'></div>{mid_mark}</div>"
            f"<div style='position:relative;height:14px;font:400 11px SM'><span style='position:absolute;left:0'>{_signed(lo)}</span>"
            f"<span style='position:absolute;left:{x(0):.2f}%;transform:translateX(-50%)'>$0</span>"
            f"<span style='position:absolute;right:0'>{_signed(hi)}</span></div></div>")


def _signed(v: float) -> str:
    return f"{'+' if v >= 0 else '−'}${abs(v):,.0f}"


def _meter(breakeven: float, net: float | None, counts: list[tuple[str, int]], needle: float = 0.10,
           band: tuple | None = None) -> str:
    be, nd, top = breakeven * 100, needle * 100, 20.0
    ticks = "".join(f"<div style='position:absolute;left:{t / top * 100:.2f}%;bottom:0;height:{10 if t % 5 == 0 else 5}px;border-left:1px solid #111'></div>"
                    + (f"<div style='position:absolute;left:{t / top * 100:.2f}%;top:46px;transform:translateX(-50%);font:400 10px SM'>{t}%</div>" if t % 5 == 0 and t != round(nd) else "")
                    for t in range(0, 21))
    money = (f"<div style='position:absolute;left:{nd / top * 100:.2f}%;top:-24px;margin-left:8px;font:500 20px SG;color:{MAG}'>"
             f"{'+' if net >= 0 else '−'}${abs(net):,.0f} at {nd:.0f}%</div>") if net is not None else ""
    cnt = "".join(f"<div><b style='font:300 34px SG'>{v:,}</b><div class='o-lbl'>{esc(k)}</div></div>" for k, v in counts)
    return (f"<div style='border:1px solid #111;border-top:0;padding:14px 16px 18px'><div class='o-lbl'>Save-rate ruler · share of messaged customers we keep</div>"
            f"<div style='position:relative;height:40px;border-bottom:1px solid #111;margin:30px 0 40px'>{ticks}"
            f"<div style='position:absolute;left:0;width:{be / top * 100:.2f}%;bottom:0;height:12px;background:repeating-linear-gradient(90deg,#111 0 1px,transparent 1px 5px)'></div>"
            f"<div style='position:absolute;left:{be / top * 100:.2f}%;bottom:0;height:34px;border-left:1px dashed #111'></div>"
            f"<div style='position:absolute;left:{be / top * 100:.2f}%;top:-22px;transform:translateX(-50%);font:400 11px SM'>break-even {_pct2(be)}%</div>"
            f"<div style='position:absolute;left:{nd / top * 100:.2f}%;bottom:-18px;height:64px;border-left:2px solid {MAG}'></div>{money}"
            f"<div style='position:absolute;left:{nd / top * 100:.2f}%;top:46px;transform:translateX(-50%);font:700 10px SM;color:{MAG};white-space:nowrap;"
            f"letter-spacing:.06em;text-transform:uppercase'>{nd:.0f}% · our central assumption</div></div>"
            + (_band(*band) if band else "")
            + f"<div style='display:flex;gap:48px;margin-top:6px'>{cnt}</div></div>")


def _bill_kinds(decisions) -> tuple[int, int] | None:
    """(clean, trade-off) bill-line counts from decisions.receipt_kind; None when the column is absent."""
    try:
        if decisions is None or "receipt_kind" not in decisions:
            return None
        k = decisions.receipt_kind.astype(str).str.lower().str.strip()
        return int(k.eq("clean").sum()), int(k.eq("tradeoff").sum())
    except Exception:  # noqa: BLE001
        return None


def _dec_bill(decisions) -> tuple[int, float | None] | None:
    """(bill-line-only accounts, their total monthly saving) from decisions.csv, or None without a decision column."""
    try:
        if decisions is None or "decision" not in decisions:
            return None
        b = decisions[decisions.decision.astype(str).eq("receipt_only")]
        if "receipt_kind" in b:
            b = b[b.receipt_kind.astype(str).str.lower().eq("clean")]
        sav = float(pd.to_numeric(b.customer_saves_usd_mo, errors="coerce").sum()) if "customer_saves_usd_mo" in b else None
        return len(b), sav
    except Exception:  # noqa: BLE001
        return None


def _bill_count(df, decisions) -> int:
    d = _dec_bill(decisions)
    if d is not None:
        return d[0]
    return int((df.receipt_line_en.astype(str).str.strip().ne("") & ~df.messaged).sum()) if "receipt_line_en" in df else 0


def _decision_counts(scored: int, ch: pd.Series, bill: int, messaged: int, kinds: tuple[int, int] | None = None) -> str:
    """Money-off stand-in for the meter: one decision per account, as a flat proportional bar plus counts."""
    quiet = max(scored - messaged - (sum(kinds) if kinds else bill), 0)
    order = [k for k in ("text", "in-app", "email", "call") if k in ch.index]
    bills = [("bill line", kinds[0], "#8C877D"), ("bill line with a trade-off", kinds[1], "#B9B2A7")] if kinds else [("bill line", bill, "#8C877D")]
    segs = [(f"{k}", int(ch[k]), MAG if k == "text" else INK) for k in order] + bills + [("quiet", quiet, "#D9D3C8")]
    bar = "".join(f"<div title='{esc(k)} {v:,}' style='flex:{v} 1 0;min-width:{3 if v else 0}px;background:{c};border-right:1px solid {BG}'></div>" for k, v, c in segs)
    chs = " · ".join(f"{k} {int(ch[k])}" for k in order)
    def col(n, lab, sub):
        return (f"<div style='border-left:1px solid #111;padding:2px 0 0 14px'><b style='font:300 44px/1 SG'>{n:,}</b>"
                f"<div class='o-lbl' style='margin-top:6px'>{esc(lab)}</div><div class='o-lbl' style='text-transform:none;letter-spacing:0;color:#6B675F'>{esc(sub)}</div></div>")
    return (f"<div style='border:1px solid #111;border-top:0;padding:14px 16px 18px'>"
            f"<div style='display:flex;justify-content:space-between'><span class='o-lbl'>What every account gets this week · one decision each</span>"
            f"<span class='o-lbl'>{scored:,} accounts</span></div>"
            f"<div style='display:flex;height:22px;margin:16px 0 18px;border:1px solid #111'>{bar}</div>"
            f"<div style='display:grid;grid-template-columns:repeat({4 if kinds else 3},1fr);gap:0'>"
            + col(messaged, "messaged", chs)
            + (col(kinds[0], "bill line", "same features, lower price, no message") + col(kinds[1], "bill line with a trade-off", "cheaper, but they'd lose something")
               if kinds else col(bill, "bill line only", "cheaper plan on the bill, no message"))
            + col(quiet, "stay quiet", "no message, nothing on the bill")
            + "</div></div>")


def render_dashboard(df: pd.DataFrame, economics: dict | None = None, *, typical_risk: float | None = None,
                     decisions: pd.DataFrame | None = None, breakeven: float = 0.048, value_note: str | None = None,
                     summary: dict | None = None, show_money: bool = True, key: str = "orbit") -> str | None:
    """economics: {'breakeven_sr': float (0-1), 'receipt_lines': int, 'receipt_monthly': float}. Missing keys are skipped.
    Money comes only from decisions['net_mid_usd'] (summed over messaged accounts); without it no dollar figure is shown.
    breakeven: default used when economics has no 'breakeven_sr'. value_note: optional line shown under the meter.
    summary (optional, ledger summary): breakeven_save_rate (break-even mark), total_mid (checked against the
    decisions sum), range95_low/range95_high (hairline band on the meter only), p_net_pos_at_10.
    show_money=False: no net value, break-even, ruler or value note; the meter's place shows decision counts instead.
    Customers' own savings (savings lines on the bill) stay.
    Returns the account_id clicked in the riskiest-ten table (or None)."""
    e = economics or {}
    _act("03 / 05", "The whole book, at a glance", "this week")
    scored, flagged = len(df), int(df.flagged.sum())
    messaged = int(df.messaged.sum())
    ch = df[df.messaged].channel.map(CHANNEL_LABEL).value_counts()
    mix = "".join(f"<div style='flex:{v} 1 0;{'background:' + MAG + ';color:#fff' if k == 'text' else ''}'>"
                  f"{k.upper()} {v}</div>" for k, v in ch.items())
    med = float(df.p_churn_90d.median() * 100)
    cells = [f"<div class='o-cell'><span class='o-lbl'>Customers scored</span><span class='v'>{scored:,}</span><span class='s'>every account, every week</span></div>",
             f"<div class='o-cell warn'><span class='o-lbl'>Flagged at risk · top 10%</span><span class='v'>{flagged}</span><span class='s'>cut at {pct(df.attrs.get('flag_cut', 0) * 100)} 90-day risk</span></div>",
             f"<div class='o-cell w2'><span class='o-lbl'>Messages this week · by channel</span><span class='v'>{messaged}</span>"
             f"<div class='o-mix'>{mix}</div></div>"]
    dec_bill = _dec_bill(decisions)
    kinds0 = _bill_kinds(decisions)
    if kinds0 is not None and dec_bill is not None:
        dec_bill = (kinds0[0], dec_bill[1])
    if dec_bill is not None:
        e = {**e, "receipt_lines": dec_bill[0], **({"receipt_monthly": dec_bill[1]} if dec_bill[1] is not None else {})}
    if "receipt_lines" in e:
        cells.append(f"<div class='o-cell{'' if show_money else ' w2'}'><span class='o-lbl'>Savings lines on the bill</span><span class='v'>{int(e['receipt_lines']):,}</span>"
                     f"<span class='s'>same features, lower price{(' · $' + format(e['receipt_monthly'], ',.0f') + '/mo if all switch') if 'receipt_monthly' in e else ''}</span></div>")
    sm = summary or {}
    net = _net_mid(df, decisions)
    if net is None and sm.get("total_mid") is not None:
        net = float(sm["total_mid"])
    be_v = float(sm.get("breakeven_save_rate", e.get("breakeven_sr", breakeven)))
    band = ((float(sm["range95_low"]), net, float(sm["range95_high"]), sm.get("p_net_pos_at_10"))
            if sm.get("range95_low") is not None and sm.get("range95_high") is not None else None)
    if not show_money:
        pass
    elif net is not None:
        cells.append(f"<div class='o-cell'><span class='o-lbl'>Net value at a 10% save rate</span><span class='v'>{'+' if net >= 0 else '−'}"
                     f"<small>$</small>{abs(net):,.0f}</span><span class='s'>over {messaged} messages · break-even {_pct2(be_v * 100)}%</span></div>")
    else:
        cells.append(f"<div class='o-cell'><span class='o-lbl'>Break-even save rate</span><span class='v'>{_pct2(be_v * 100)}<small>%</small></span>"
                     f"<span class='s'>below this, messaging costs more than it keeps</span></div>")
    if typical_risk is not None:
        cells.append(f"<div class='o-cell'><span class='o-lbl'>Typical customer risk</span><span class='v'>{pct(typical_risk)[:-1]}<small>%</small></span><span class='s'>90-day churn · model baseline</span></div>")
    cells.append(f"<div class='o-cell'><span class='o-lbl'>Median customer risk</span><span class='v'>{med:.2f}<small>%</small></span><span class='s'>half the book is below this</span></div>")
    st.markdown("<div class='o-grid'>" + "".join(cells) + "</div>", unsafe_allow_html=True)
    bill = _bill_count(df, decisions)
    kinds = _bill_kinds(decisions)
    quiet_n = scored - messaged - (sum(kinds) if kinds else bill)
    counts = ([("messaged", messaged), ("bill line", kinds[0]), ("bill line with a trade-off", kinds[1]), ("stay quiet", quiet_n)] if kinds
              else [("messaged", messaged), ("cheaper plan on the bill, no message", bill), ("stay quiet", quiet_n)])
    if show_money:
        st.markdown(_meter(be_v, net, counts, band=band), unsafe_allow_html=True)
    else:
        st.markdown(_decision_counts(scored, ch, bill, messaged, kinds), unsafe_allow_html=True)
    if value_note and show_money:
        st.markdown(f"<div class='o-lbl' style='text-transform:none;letter-spacing:0;font-size:12px;margin-top:8px'>{esc(value_note)}</div>", unsafe_allow_html=True)

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
                        "Top reason": t.get("risk_reason_1", ""), "What we do": t.reason_line.map(_cap),
                        "Channel": t.channel.map(CHANNEL_LABEL).fillna("none")})
    ev = st.dataframe(tab, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key=f"{key}_riskiest",
                      column_config={"Customer": st.column_config.TextColumn(width="small"), "Risk": st.column_config.TextColumn(width="small"),
                                     "Channel": st.column_config.TextColumn(width="small")})
    rows = (ev.selection.rows if ev is not None and hasattr(ev, "selection") else []) or []
    return t.iloc[rows[0]].account_id if rows else None


# ============================================================== act 4 — what we considered
CSS4 = """
.o-cg{display:grid;grid-template-columns:repeat(4,1fr);border-left:1px solid #111;border-top:1px solid #111;align-items:start}
.o-cg details{border-right:1px solid #111;border-bottom:1px solid #111;margin:0}
.o-cg summary{list-style:none;cursor:pointer;padding:12px 14px 14px;display:flex;flex-direction:column;justify-content:space-between;min-height:120px}
.o-cg summary::-webkit-details-marker{display:none}
.o-cg summary .n{font:300 54px/0.95 'SG';letter-spacing:-.03em}
.o-cg summary .g{font:400 14px/1.25 'SG'}
.o-cg summary .h{font:400 10px 'SM';letter-spacing:.08em;text-transform:uppercase;color:#6B675F}
.o-cg details[open] summary{background:#111;color:#F6F3EE}
.o-cg details[open] summary .h{color:#F6F3EE}
.o-cg .it{padding:8px 14px;border-top:1px solid rgba(17,17,17,.25);font:400 13px/1.35 'SG'}
.o-cg .it b{display:block;font-weight:600;margin-bottom:2px}
.o-cg .it span{color:#6B675F}
"""


_SIM = re.compile(r"\s*\((?:simulated|synthetic)\)", re.I)
_MSG_RESULT = re.compile(r"^(\d[\d,]*) messages come out [+-]?\$[\d,]+ ahead\b[^.]*\.?\s*(.*)$")
_BOOT = re.compile(r"^(\d[\d,]*) account resamples\b.*$")
_EARLIER = re.compile(r"^The earlier engine\b[^.]*-\$[\d,]+[^.]*\.\s*(.*)$")
_HALF = re.compile(r"at 5% it is -?\$[\d,]+ ahead")
SAVED_VALUE_PLAIN = "We value a saved account by its own monthly margin and how long an average saved customer stays (19.3 months)."
_PLAIN_OFF = [(r"It is priced at \$0 and every", "It is always on the table and every"),
              (r"^A fix-first callback costs \$15, a check-in \$2, plus an annoyance cost of \$2 to \$6 per contact\.$",
               "Every contact has a cost, plus an annoyance cost; an offer has to cover both."),
              (r"\s*\(-?\$[\d,]+\)", ""),
              (r"at a \$0 device margin", "with no margin on the device")]
_CUSTOMER_DOLLARS = re.compile(r"\$\d+ (?:care |one-time )?credit|\$[\d,]+(?:/mo| a month)|\$0 early termination", re.I)


def _drop_our_money(t: str) -> str:
    """Keep only sentences whose dollar figures are the customer's own (credits, savings a month, $0 termination fee)."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", str(t).strip())
    keep = [p for p in parts if "$" not in _CUSTOMER_DOLLARS.sub("", p)]
    return " ".join(keep)


_DROP_ITEMS = {"simulated data only"}
SAVES_STICK = "If a saved customer stays as risky as before, most of the money disappears. That's the first thing a real rollout tests."
_BLANKET = re.compile(r"^A (?:flat )?(\$\d+) credit to (.+?) is -?\$[\d,]+ at \d+%.*$")


def _money(v: float) -> str:
    return f"{'-' if v < 0 else ''}${abs(v):,.0f}"


def _considered_text(t: str, summary: dict | None) -> str:
    """Drop simulated notes; swap stale money results for data-driven ones, or for plain sentences."""
    t = _SIM.sub("", t).strip()
    s = summary or {}
    m = _MSG_RESULT.match(t)
    if m:
        n = f"{int(s['contacts']):,}" if s.get("contacts") is not None else m.group(1)
        net = s.get("net_usd")
        rest = (" " + m.group(2).strip()) if m.group(2).strip() else ""
        if net is None:
            return f"{n} messages come out ahead at our central assumption.{rest}"
        word = "ahead" if net >= 0 else "behind"
        return f"{n} messages come out {_signed(net) if net >= 0 else _money(abs(net))} {word} at our central assumption.{rest}"
    m = _BOOT.match(t)
    if m:
        lo, hi = s.get("range_low_usd"), s.get("range_high_usd")
        out = f"We re-ran the money {m.group(1)} times on resampled accounts to get a range."
        if lo is not None and hi is not None:
            out += f" At our central assumption it runs from {_money(lo)} to {_money(hi)}."
        return out
    m = _EARLIER.match(t)
    if m:
        rest = (m.group(1) or "").strip()
        return "Our earlier engine lost money on the same accounts." + (f" {rest}" if rest else "")
    m = _BLANKET.match(t)
    if m:
        net = s.get("blanket_net_usd")
        if net is None:
            return f"A flat {m.group(1)} credit to {m.group(2)} loses money at the same assumption."
        verb = f"loses {_money(abs(net))}" if net < 0 else f"comes out {_money(net)} ahead"
        return f"A flat {m.group(1)} credit to {m.group(2)} {verb} at the same assumption."
    return t


def render_considered(dc: pd.DataFrame | None, summary: dict | None = None, *, show_money: bool = True) -> None:
    """dc columns: group, item, how_handled[, source]. source is never shown. Renders nothing for None/empty.
    summary (optional, from decisions=/ledger): {"net_usd": total net over messaged accounts at the central
    assumption, "blanket_net_usd": the blanket-credit comparison, "net_low_usd": net at half the central
    assumption (the half-rate item shows only when this is passed and positive), "range_low_usd"/"range_high_usd":
    the resampled range}.
    show_money=False: summary is ignored, our dollar figures become plain sentences, the resampled-range row is dropped;
    customer-side amounts ($25 credit, savings a month, $0 termination fee) stay. Without it, stale dollar results become plain sentences."""
    if dc is None or not len(dc):
        return
    st.markdown(f"<style>{CSS4}</style>", unsafe_allow_html=True)
    _act("05 / 05", "What we considered", "and how each one is handled")
    dc = dc.copy()
    flat = dc.item.astype(str).str.contains(r"\$1,478|per save", regex=True) | dc.how_handled.astype(str).str.contains(r"flat \$?1,478|\$1,478 per save", regex=True)
    dc.loc[flat, "item"] = "Value of a saved account"
    dc.loc[flat, "how_handled"] = SAVED_VALUE_LINE
    dc = dc[~dc.item.astype(str).str.strip().str.lower().isin(_DROP_ITEMS)]
    stick = dc.item.astype(str).str.strip().str.lower().eq("do saves stick?")
    if stick.any():
        lim = [g for g in dc.group.astype(str).unique() if "known limits" in g.lower()]
        dc.loc[stick, "how_handled"] = SAVES_STICK
        dup = dc.how_handled.astype(str).str.strip().eq(SAVES_STICK) & ~stick
        if lim and not dup.any():
            dc.loc[stick, "group"] = lim[0]
            order = list(dict.fromkeys(dc.group.astype(str)))
            dc = dc.assign(_g=dc.group.astype(str).map({g: i for i, g in enumerate(order)})).sort_values("_g", kind="stable").drop(columns="_g")
    half = dc.how_handled.astype(str).str.contains(_HALF)
    if not show_money:
        summary = None
        dc = dc[~dc.how_handled.astype(str).str.match(_BOOT)]
        dc.loc[dc.how_handled.astype(str).eq(SAVED_VALUE_LINE) | dc.how_handled.astype(str).str.contains("19.3 months", regex=False),
               "how_handled"] = SAVED_VALUE_PLAIN
        for pat, new in _PLAIN_OFF:
            dc["how_handled"] = dc.how_handled.astype(str).str.replace(pat, new, regex=True)
    net_low = (summary or {}).get("net_low_usd")
    if net_low is not None and net_low > 0:
        dc.loc[half, "item"] = "Half our central assumption"
        dc.loc[half, "how_handled"] = f"Still ahead at half our central assumption ({_money(net_low)})."
    else:
        dc = dc[~half]
    dc = dc.copy()
    dc["group"] = dc.group.astype(str).map(lambda t: _SIM.sub("", t).strip())
    dc["item"] = dc.item.astype(str).map(lambda t: _considered_text(t, summary))
    dc["how_handled"] = dc.how_handled.astype(str).map(lambda t: _considered_text(t, summary))
    if not show_money:   # any sentence still carrying our own dollars goes; a row left empty goes too
        dc["how_handled"] = dc.how_handled.map(_drop_our_money)
        dc = dc[dc.how_handled.str.strip().ne("")]
    groups = list(dc.groupby("group", sort=False))
    cells = ""
    for g, x in groups:
        name = re.sub(r"^\w+\.\s*", "", str(g)).strip()
        items = "".join(f"<div class='it'><b>{esc(str(i.item))}</b><span>{esc(str(i.how_handled))}</span></div>" for i in x.itertuples())
        cells += (f"<details><summary><span class='h'>{esc(str(g).split('.')[0])}</span><span class='n'>{len(x)}</span>"
                  f"<span class='g'>{esc(name)}</span></summary>{items}</details>")
    st.markdown(f"<div style='margin:8px 0 6px'><span class='o-hero-num' style='font-size:150px'>{len(dc)}</span></div>"
                f"<div class='o-ph' style='font-size:30px;margin-top:4px'>things we checked</div>"
                f"<div class='o-lbl' style='margin:-4px 0 16px'>{len(groups)} groups · open any group to see each item and how it's handled</div>"
                f"<div class='o-cg'>{cells}</div>", unsafe_allow_html=True)
    st.markdown("<div class='o-foot'><span>Churn + upsell board</span><span>Every account, every week</span></div>", unsafe_allow_html=True)
