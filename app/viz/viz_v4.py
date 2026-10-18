"""v4 pieces for make_pipeline_viz.py: retro-tech CRT shell, 3D population cloud with dataset switcher
(sandbox 5k / Gaussian-copula 50k / 250k), 3D stacked pipeline layers, Model A what-if toggles.
ALL CUSTOMERS AND NUMBERS ARE SYNTHETIC. Counts are computed from CSVs at build time; nothing is typed in."""
from __future__ import annotations

import html as _html
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

MAGENTA, PINK, INK = "#E20074", "#FF8FBF", "#F7F1EA"
BG, PANEL, EDGE, MUTED, GREY = "#0D0810", "#1A1220", "#3A2C3E", "#B9A9B5", "#5A4A5E"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', 'DejaVu Sans Mono', monospace"
CLOUD_POINTS = 20000
SEED = 2026

ACTION_COLORS = ["#E20074", "#FF8FBF", "#F7F1EA", "#7FD1FF", "#FFD27F", "#8BE0B0", "#C9A0FF", "#F5A97F", "#A0C4FF",
                 "#E0E07F", "#7FFFD4", "#FFB3D9", "#B0E57C"]


# ------------------------------------------------------------------------------------------- datasets
OUT_ROOT = None
FIND = None  # set by make_pipeline_viz: harness/out first, then demo_data


def _read(path: Path, cols=None, out: Path | None = None):
    if FIND is not None and OUT_ROOT is not None:
        try:
            path = FIND(Path(path).relative_to(OUT_ROOT))
        except ValueError:
            pass
    if not path.exists():
        return None
    head = pd.read_csv(path, nrows=0).columns
    use = [c for c in cols if c in head] if cols else None
    return pd.read_csv(path, usecols=use)


def load_datasets(out: Path, d: dict, m: pd.DataFrame, cut: float, alabel) -> list[dict]:
    """Each dataset: key, label, n, cloud df (x,y,z,color group), axis notes, funnel counts, tiles."""
    global OUT_ROOT
    OUT_ROOT = out
    rng = np.random.default_rng(SEED)
    sets = []

    # ---- sandbox 5k (full pipeline)
    fe = d["features"][["account_id", "last_bill_cents", "segment"]]
    up = _read(out / "upgrade_scores.csv", ["account_id", "p_upgrade_90d"])
    lab = _read(out / "labels.csv", ["account_id", "churn_90d", "p_upgrade_90d"])
    df = m[["account_id", "p_churn_90d", "action_code", "flagged", "offered", "messaged"]].merge(fe, on="account_id")
    zsrc = "upgrade model (upgrade_scores.csv)"
    if up is not None:
        df = df.merge(up, on="account_id", how="left")
    elif lab is not None:
        df = df.merge(lab[["account_id", "p_upgrade_90d"]], on="account_id", how="left")
        zsrc = "synthetic generator p_upgrade_90d"
    df["x"], df["y"], df["z"] = df["p_churn_90d"], df["last_bill_cents"] / 100, df["p_upgrade_90d"]
    df["group"] = [alabel(a, dagger=False) for a in df["action_code"]]
    en = d["enrichment"]
    kid = d.get("_sbx", {}).get("kid_lines") or {}
    tiles = [("ACCOUNTS", f"{len(df):,}"), ("MODEL A", "scored (churn_scores.csv)"),
             ("FLAGGED · TOP 10%", f"{int(df['flagged'].sum()):,}"),
             ("OFFERED (WORTH MAKING)", f"{int(df['offered'].sum()):,}"),
             ("DO NOTHING", f"{int((~df['offered']).sum()):,}"),
             ("MESSAGES READY", f"{int(df['messaged'].sum()):,}"),
             ("SIM. CHURNERS (LABELS)", f"{int(lab['churn_90d'].sum()):,}" if lab is not None else "n/a"),
             ("FAMILY PLANS", f"{int(en['is_family_plan'].sum()):,}" if "is_family_plan" in en else "n/a"),
             ("ACCTS WITH KID LINES", f"{kid.get('accounts_with_kid_lines', 0):,}" if kid else "n/a"),
             ("MEAN MONTHLY BILL", f"${df['y'].mean():,.2f}")]
    nf = int(df["flagged"].sum())
    fn = dict(kind="full", n=len(df), flagged=nf,
              off_f=int((df["flagged"] & df["offered"]).sum()), off_r=int((~df["flagged"] & df["offered"]).sum()),
              msg=int(df["messaged"].sum()))
    sets.append(dict(key="5k", label="SANDBOX 5K", long="sandbox 5k (synthetic judge data)", n=len(df), cloud=df,
                     shown=len(df), xlab="p(churn 90d) · Model A", zlab=f"upgrade propensity · {zsrc}",
                     color_note="colour = chosen action (Model B, offers.csv)", tiles=tiles, funnel=fn,
                     note="Full pipeline: Model A scores, Model B offers, validated messages."))

    # ---- Gaussian-copula 50k (Model A scored, offers not run)
    sc = out / "scaled"
    f50 = _read(sc / "features_scaled.csv", ["account_id", "last_bill_cents", "segment"])
    l50 = _read(sc / "labels_scaled.csv", ["account_id", "churn_90d", "p_true_90d", "p_upgrade_90d"])
    h50 = _read(sc / "household_scaled.csv", ["account_id", "is_family_plan", "likely_kid_flag"])
    s50 = _read(out / "scaled_scores" / "churn_scores.csv", ["account_id", "p_churn_90d"])
    if f50 is not None and l50 is not None:
        df = f50.merge(l50, on="account_id")
        has_a = s50 is not None and s50["account_id"].isin(df["account_id"]).mean() > 0.99
        if has_a:
            df = df.merge(s50, on="account_id", how="left")
            c50 = float(df["p_churn_90d"].quantile(0.90))
            df["flagged"] = df["p_churn_90d"] >= c50
            df["x"] = df["p_churn_90d"]
            df["group"] = np.where(df["flagged"], "Model A top 10% (flagged)", "Model A rest")
        else:
            df["x"] = df["p_true_90d"]
            df["group"] = "generator only"
        df["y"], df["z"] = df["last_bill_cents"] / 100, df["p_upgrade_90d"]
        if h50 is not None:
            df = df.merge(h50, on="account_id", how="left")
        n = len(df)
        tiles = [("ACCOUNTS", f"{n:,}"),
                 ("MODEL A", "scored (scaled_scores/, fit on 50k)" if has_a else "not run at this scale"),
                 ("FLAGGED · TOP 10%", f"{int(df['flagged'].sum()):,}" if has_a else "not run"),
                 ("OFFERED", "not run at this scale"), ("DO NOTHING", "not run at this scale"),
                 ("MESSAGES READY", "not run at this scale"),
                 ("SIM. CHURNERS (LABELS)", f"{int(df['churn_90d'].sum()):,}"),
                 ("FAMILY PLANS", f"{int(df['is_family_plan'].sum()):,}" if "is_family_plan" in df else "n/a"),
                 ("ACCTS WITH KID LINES", f"{int(df['likely_kid_flag'].sum()):,}" if "likely_kid_flag" in df else "n/a"),
                 ("MEAN MONTHLY BILL", f"${df['y'].mean():,.2f}")]
        fn = dict(kind="scored" if has_a else "labels", n=n, flagged=int(df["flagged"].sum()) if has_a else None,
                  churners=int(df["churn_90d"].sum()))
        samp = df.sample(min(CLOUD_POINTS, n), random_state=SEED)
        sets.append(dict(key="50k", label="SYNTH 50K", long="Gaussian-copula synthetic 50k", n=n, cloud=samp, shown=len(samp),
                         xlab="p(churn 90d) · Model A fit on 50k" if has_a else "p(churn 90d) · generator",
                         zlab="upgrade propensity · synthetic generator p_upgrade_90d (no upgrade model at 50k)",
                         color_note="colour = Model A top 10% vs rest · offers not run at this scale", tiles=tiles, funnel=fn,
                         note="Copula fitted to the 5,000 regular sandbox accounts (out/scaled/; its FIDELITY.md notes a "
                              "line-count flaw fixed in the 250k set). Model A scored; Model B offers not run."))

    # ---- Gaussian-copula 250k (labels only, Model A + offers not run)
    sc = out / "scaled_250k"
    f250 = _read(sc / "features_scaled.csv", ["account_id", "last_bill_cents", "segment"])
    l250 = _read(sc / "labels_scaled.csv", ["account_id", "churn_90d", "p_true_90d", "p_upgrade_90d"])
    h250 = _read(sc / "household_scaled.csv", ["account_id", "is_family_plan", "likely_kid_flag"])
    if f250 is not None and l250 is not None:
        df = f250.merge(l250, on="account_id")
        if h250 is not None:
            df = df.merge(h250, on="account_id", how="left")
        df["x"], df["y"], df["z"] = df["p_true_90d"], df["last_bill_cents"] / 100, df["p_upgrade_90d"]
        df["group"] = np.where(df["churn_90d"] == 1, "simulated churner (label)", "stayed (label)")
        n = len(df)
        tiles = [("ACCOUNTS", f"{n:,}"), ("MODEL A", "not run at this scale"), ("FLAGGED · TOP 10%", "not run"),
                 ("OFFERED", "not run at this scale"), ("DO NOTHING", "not run at this scale"),
                 ("MESSAGES READY", "not run at this scale"),
                 ("SIM. CHURNERS (LABELS)", f"{int(df['churn_90d'].sum()):,}"),
                 ("FAMILY PLANS", f"{int(df['is_family_plan'].sum()):,}" if "is_family_plan" in df else "n/a"),
                 ("ACCTS WITH KID LINES", f"{int(df['likely_kid_flag'].sum()):,}" if "likely_kid_flag" in df else "n/a"),
                 ("MEAN MONTHLY BILL", f"${df['y'].mean():,.2f}")]
        fn = dict(kind="labels", n=n, churners=int(df["churn_90d"].sum()))
        samp = df.sample(min(CLOUD_POINTS, n), random_state=SEED)
        sets.append(dict(key="250k", label="SYNTH 250K", long="Gaussian-copula synthetic 250k", n=n, cloud=samp, shown=len(samp),
                         xlab="p(churn 90d) · synthetic generator (Model A not run at 250k)",
                         zlab="upgrade propensity · synthetic generator p_upgrade_90d",
                         color_note="colour = simulated churn label · Model A and offers not run at this scale",
                         tiles=tiles, funnel=fn,
                         note="Copula fitted to the sandbox (out/scaled_250k/). Labels from the same labels.py recipe. "
                              "Neither Model A nor Model B has been run on it, so axes use the generator's probabilities."))
    return sets


def dataset_stats(sets):
    return {s["key"]: {"label": s["long"], "n": s["n"], "points_shown": s["shown"], "tiles": dict(s["tiles"]),
                       "funnel": s["funnel"], "x_axis": s["xlab"], "z_axis": s["zlab"], "colour": s["color_note"],
                       "note": s["note"]} for s in sets}


# ------------------------------------------------------------------------------------------- figures
def _scene(xlab, zlab):
    ax = dict(backgroundcolor=BG, gridcolor="#2A1E30", zerolinecolor=EDGE, showbackground=True, color=MUTED,
              tickfont=dict(family=MONO, size=10, color=MUTED), titlefont=dict(family=MONO, size=11, color=INK))
    return dict(
        xaxis=dict(title=dict(text=xlab.split(" · ")[0], font=dict(family=MONO, size=11, color=INK)), type="log", **{k: v for k, v in ax.items() if k != "titlefont"}),
        yaxis=dict(title=dict(text="monthly bill ($)", font=dict(family=MONO, size=11, color=INK)), **{k: v for k, v in ax.items() if k != "titlefont"}),
        zaxis=dict(title=dict(text="upgrade propensity", font=dict(family=MONO, size=11, color=INK)), **{k: v for k, v in ax.items() if k != "titlefont"}),
        bgcolor=BG, camera=dict(eye=dict(x=1.7, y=1.0, z=0.8)), aspectmode="cube")


def cloud_fig(s):
    df = s["cloud"].copy()
    df["x"] = df["x"].clip(lower=1e-4)
    groups = df["group"].value_counts().index.tolist()
    # put "do nothing"/rest groups first (drawn underneath) and dim them
    dim = {"Do nothing", "do nothing", "Model A rest", "stayed (label)", "generator only"}
    groups = [g for g in groups if g in dim] + [g for g in groups if g not in dim]
    traces = []
    ci = 0
    for g in groups:
        sub = df[df["group"] == g]
        if g in dim:
            col, size, op = "#6A5A6E", 1.6, 0.35
        else:
            col = ACTION_COLORS[ci % len(ACTION_COLORS)] if s["key"] == "5k" else MAGENTA
            ci += 1
            size, op = 3.2, 0.9
        traces.append(go.Scatter3d(
            x=sub["x"].round(5), y=sub["y"].round(2), z=sub["z"].round(5), mode="markers", name=f"{g} · {len(sub):,}",
            marker=dict(size=size, color=col, opacity=op, line=dict(width=0)),
            customdata=sub[["account_id"]].values if s["key"] == "5k" else None,
            hovertemplate=(("%{customdata[0]}<br>" if s["key"] == "5k" else "") + g +
                           "<br>p(churn) %{x:.2%}<br>bill $%{y:,.0f}<br>upgrade %{z:.1%}<extra>synthetic</extra>")))
    lay = go.Layout(
        height=760, paper_bgcolor=BG, plot_bgcolor=BG, font=dict(family=MONO, color=INK, size=11),
        margin=dict(l=0, r=0, t=10, b=0), scene=_scene(s["xlab"], s["zlab"]), uirevision=s["key"],
        legend=dict(x=0.0, y=0.98, bgcolor="rgba(13,8,16,0.75)", bordercolor=EDGE, borderwidth=1,
                    font=dict(family=MONO, size=11, color=INK), itemsizing="constant",
                    title=dict(text=s["color_note"].split(" · ")[0].upper(), font=dict(family=MONO, size=10, color=PINK))))
    return go.Figure(data=traces, layout=lay)


def mini_funnel_fig(s):
    """Compact Sankey per dataset; stages that were not run are shown as grey 'not run' nodes."""
    f, n = s["funnel"], s["funnel"]["n"]
    lab, src, tgt, val, ncol, lcol = [], [], [], [], [], []

    def node(t, c):
        lab.append(t); ncol.append(c)
        return len(lab) - 1

    def link(a, b, v, c):
        src.append(a); tgt.append(b); val.append(v); lcol.append(c)

    a = node(f"ALL {n:,}", "#8A7B84")
    if f["kind"] == "full":
        fl, rest = node(f"FLAGGED {f['flagged']:,}", MAGENTA), node(f"NOT FLAGGED {n - f['flagged']:,}", GREY)
        link(a, fl, f["flagged"], "rgba(226,0,116,.45)"); link(a, rest, n - f["flagged"], "rgba(138,123,132,.25)")
        o1 = node(f"RETENTION OFFER {f['off_f']:,}", MAGENTA); o2 = node(f"UPGRADE / FIX OFFER {f['off_r']:,}", PINK)
        dn = node(f"DO NOTHING {n - f['off_f'] - f['off_r']:,}", EDGE)
        link(fl, o1, f["off_f"], "rgba(226,0,116,.45)"); link(fl, dn, f["flagged"] - f["off_f"], "rgba(90,74,94,.35)")
        link(rest, o2, f["off_r"], "rgba(255,143,191,.35)"); link(rest, dn, n - f["flagged"] - f["off_r"], "rgba(90,74,94,.35)")
        ms = node(f"MESSAGE READY {f['msg']:,}", INK)
        link(o1, ms, f["off_f"], "rgba(226,0,116,.40)"); link(o2, ms, f["off_r"], "rgba(255,143,191,.35)")
    elif f["kind"] == "scored":
        fl, rest = node(f"FLAGGED {f['flagged']:,}", MAGENTA), node(f"NOT FLAGGED {n - f['flagged']:,}", GREY)
        link(a, fl, f["flagged"], "rgba(226,0,116,.45)"); link(a, rest, n - f["flagged"], "rgba(138,123,132,.25)")
        nr = node("OFFERS · NOT RUN AT THIS SCALE", "#2A1E30")
        link(fl, nr, f["flagged"], "rgba(90,74,94,.25)"); link(rest, nr, n - f["flagged"], "rgba(90,74,94,.18)")
    else:
        ch, st = node(f"SIM. CHURNERS {f['churners']:,}", MAGENTA), node(f"STAYED {n - f['churners']:,}", GREY)
        link(a, ch, f["churners"], "rgba(226,0,116,.45)"); link(a, st, n - f["churners"], "rgba(138,123,132,.25)")
        nr = node("MODEL A + OFFERS · NOT RUN", "#2A1E30")
        link(ch, nr, f["churners"], "rgba(90,74,94,.25)"); link(st, nr, n - f["churners"], "rgba(90,74,94,.18)")
    tr = go.Sankey(arrangement="snap", node=dict(label=lab, color=ncol, pad=18, thickness=12, line=dict(width=0),
                                                 hovertemplate="%{label}<extra>synthetic</extra>"),
                   link=dict(source=src, target=tgt, value=val, color=lcol,
                             hovertemplate="%{value:,} accounts<extra>synthetic</extra>"),
                   textfont=dict(family=MONO, size=10, color=INK))
    return go.Figure(data=[tr], layout=go.Layout(height=300, paper_bgcolor=BG, margin=dict(l=4, r=4, t=6, b=6),
                                                 font=dict(family=MONO, color=INK)))


def stack_fig(stats):
    """3D stacked layers: each plane is a 20x20 dot grid (each dot ≈ N/400 accounts); lit dots pass that stage."""
    f = stats["funnel"]
    n = f["all_accounts"]
    layers = [("[ DATA ]", f"{n:,} accounts · {stats['sandbox']['n_tables_used']} sandbox tables", 1.0),
              ("[ FEATURES ]", f"{stats['features']['n_columns']} features per account", 1.0),
              ("[ MODEL A ]", f"{f['flagged']:,} flagged (top 10%)", f["flagged"] / n),
              ("[ MODEL B ]", f"{f['offered']:,} offers worth making · {f['do_nothing']:,} do nothing", f["offered"] / n),
              ("[ MESSAGE ]", f"{f['messaged']:,} ready (EN/ES) · 0 sent", f["messaged"] / n)]
    g = np.linspace(-1, 1, 20)
    gx, gy = np.meshgrid(g, g)
    gx, gy = gx.ravel(), gy.ravel()
    order = np.argsort(np.hypot(gx, gy))  # lit dots fill from the centre out
    traces = []
    for k, (tag, txt, share) in enumerate(layers):
        z = k * 1.0
        sq = np.array([[-1.15, -1.15], [1.15, -1.15], [1.15, 1.15], [-1.15, 1.15]])
        traces.append(go.Mesh3d(x=sq[:, 0], y=sq[:, 1], z=[z] * 4, i=[0, 0], j=[1, 2], k=[2, 3], color="#1A1220",
                                opacity=0.55, hoverinfo="skip", showscale=False))
        traces.append(go.Scatter3d(x=list(sq[:, 0]) + [sq[0, 0]], y=list(sq[:, 1]) + [sq[0, 1]], z=[z] * 5, mode="lines",
                                   line=dict(color=MAGENTA if k >= 2 else PINK, width=3), hoverinfo="skip", showlegend=False))
        lit = np.zeros(400, bool)
        lit[order[: int(round(share * 400))]] = True
        cols = np.where(lit, MAGENTA if k >= 2 else INK, "#3A2C3E")
        traces.append(go.Scatter3d(x=gx, y=gy, z=[z] * 400, mode="markers", marker=dict(size=2.6, color=cols, line=dict(width=0)),
                                   hovertemplate=f"{tag} {txt}<extra>synthetic</extra>", showlegend=False))
        traces.append(go.Scatter3d(x=[1.25], y=[-1.25], z=[z + 0.08], mode="text", text=[f"<b>{tag}</b>  {txt}"],
                                   textposition="middle right", textfont=dict(family=MONO, size=12, color=INK),
                                   hoverinfo="skip", showlegend=False))
    traces.append(go.Scatter3d(x=[0, 0], y=[0, 0], z=[0, len(layers) - 1], mode="lines", line=dict(color=MAGENTA, width=6),
                               hoverinfo="skip", showlegend=False))
    hid = dict(visible=False, showbackground=False)
    lay = go.Layout(height=640, paper_bgcolor=BG, margin=dict(l=0, r=0, t=0, b=0), font=dict(family=MONO, color=INK),
                    scene=dict(xaxis=hid, yaxis=hid, zaxis=hid, bgcolor=BG, aspectmode="manual",
                               aspectratio=dict(x=1.6, y=1.6, z=1.5), camera=dict(eye=dict(x=1.6, y=-1.5, z=0.7),
                                                                                center=dict(x=0.25, y=0, z=-0.05))),
                    uirevision="stack", showlegend=False)
    return go.Figure(data=traces, layout=lay)


def compute_toggles(repo: Path, d: dict, accounts: list[str], cut: float):
    """Re-score edited feature rows with tm-churn's score_account (1366e72). Action re-pick needs tm-offers'
    choose_offer(); if it is absent we report the risk change only."""
    sys.path.insert(0, str(repo))
    try:
        from harness.churn_scorer import score_account
    except Exception as e:  # noqa: BLE001
        return {"error": f"score_account unavailable: {e}"}, False
    try:
        from harness.offers import choose_offer  # type: ignore  # noqa: F401
        has_choose = True
    except Exception:  # noqa: BLE001
        has_choose = False
    fe = d["features"].set_index("account_id")
    edits = [("baseline", {}),
             ("resolve open tickets", {"unresolved_90d": 0, "unresolved_270d": 0, "negative_contacts_90d": 0}),
             ("remove port-out inquiry", {"port_out_inquiry": 0}),
             ("+20 GB monthly usage", {"data_gb_3m_avg": "+20"}),
             ("stop shopping other carriers", {"competitor_research_score": 0.0})]
    out = {}
    for a in accounts:
        if a not in fe.index:
            continue
        base = fe.loc[a].copy()
        base["account_id"] = a
        rows = []
        for name, ed in edits:
            r = base.copy()
            for k, v in ed.items():
                if k in r.index:
                    r[k] = (float(r[k]) + 20) if v == "+20" else v
            try:
                p, risks, _ = score_account(r)
            except Exception as e:  # noqa: BLE001  (fresh clone without tm-churn training files)
                return {"error": f"score_account failed: {e}"}, has_choose
            rows.append(dict(state=name, p=float(p), flagged=bool(p >= cut), top_risk=risks[0] if risks else "",
                             changed=[k for k, v in ed.items() if k in base.index and
                                      (float(base[k]) != ((float(base[k]) + 20) if v == "+20" else float(v)))]))
        out[a] = rows
    return out, has_choose


def toggles_fig(account, rows, cut, has_choose):
    states = [r["state"] for r in rows][::-1]
    ps = [r["p"] for r in rows][::-1]
    base = rows[0]["p"]
    cols = [MAGENTA if r["flagged"] else (PINK if r["state"] == "baseline" else "#7FD1FF") for r in rows][::-1]
    txt = []
    for r in rows[::-1]:
        if r["state"] == "baseline":
            txt.append(f"{r['p']:.2%}  baseline")
        elif not r["changed"]:
            txt.append(f"{r['p']:.2%}  n/a (already true for this account)")
        else:
            txt.append(f"{r['p']:.2%}  ({(r['p'] - base) * 100:+.2f} pts)" + ("  FLAGGED" if r["flagged"] else ""))
    fig = go.Figure(go.Bar(x=ps, y=states, orientation="h", marker=dict(color=cols, line=dict(width=0)), text=txt,
                           textposition="outside", cliponaxis=False, textfont=dict(family=MONO, size=11, color=INK),
                           hovertemplate="%{y}: %{x:.2%} (synthetic)<extra></extra>"))
    xmax = max(ps + [cut]) * 1.9
    fig.add_vline(x=cut, line=dict(color=MAGENTA, width=1, dash="dot"))
    fig.add_annotation(x=cut, y=1.0, yref="paper", yanchor="bottom", text=f"flag cut {cut:.2%}", showarrow=False,
                       font=dict(family=MONO, size=10, color=MAGENTA))
    note = ("action re-picked by tm-offers choose_offer()" if has_choose else
            "risk only · action re-pick pending (tm-offers choose_offer() not in harness yet)")
    fig.update_layout(height=250, paper_bgcolor=BG, plot_bgcolor=BG, font=dict(family=MONO, color=INK, size=11),
                      margin=dict(l=10, r=30, t=34, b=36),
                      title=dict(text=f"[ WHAT IF · {account} ] Model A re-score (score_account) · {note}", x=0.0,
                                 font=dict(family=MONO, size=12, color=PINK)),
                      xaxis=dict(range=[0, xmax], tickformat=".1%", gridcolor="#2A1E30", color=MUTED, zeroline=False),
                      yaxis=dict(color=INK, automargin=True))
    return fig


# ------------------------------------------------------------------------------------------- shell
CSS = f"""
:root{{--bg:{BG};--panel:{PANEL};--edge:{EDGE};--ink:{INK};--pink:{PINK};--mag:{MAGENTA};--muted:{MUTED}}}
*{{box-sizing:border-box}}
html,body{{margin:0;background:var(--bg);color:var(--ink);font-family:{MONO};font-size:13px}}
body{{background-image:linear-gradient(rgba(226,0,116,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(226,0,116,.035) 1px,transparent 1px);
     background-size:40px 40px}}
body:after{{content:"";position:fixed;inset:0;pointer-events:none;z-index:50;
     background:repeating-linear-gradient(0deg,rgba(0,0,0,.18) 0px,rgba(0,0,0,.18) 1px,transparent 1px,transparent 3px)}}
.wrap{{width:1600px;margin:0 auto;padding:0 0 40px}}
.top{{position:sticky;top:0;z-index:40;background:var(--mag);color:#fff;font-weight:700;letter-spacing:.14em;font-size:12px;
     padding:7px 18px;display:flex;justify-content:space-between;text-transform:uppercase}}
.ticker{{border-bottom:1px solid var(--edge);color:var(--muted);font-size:11px;letter-spacing:.16em;white-space:nowrap;overflow:hidden;padding:6px 0}}
.ticker span{{display:inline-block;padding-left:100%;animation:tick 60s linear infinite}}
@keyframes tick{{to{{transform:translateX(-100%)}}}}
.hero{{padding:16px 30px 8px;border-bottom:1px solid var(--edge)}}
.hero h1{{margin:0;font-size:24px;font-weight:600;letter-spacing:.02em}} .hero h1 b{{color:var(--mag)}}
.hero p{{margin:8px 0 0;color:var(--muted);max-width:1100px;line-height:1.55}}
.sec{{margin:28px 0 0;border-top:1px solid var(--edge);padding-top:12px}}
.sh{{display:flex;align-items:baseline;gap:18px;padding:0 30px 8px}}
.sh .id{{color:var(--mag);font-weight:700;letter-spacing:.14em}} .sh .t{{font-size:15px;letter-spacing:.08em;text-transform:uppercase}}
.sh .s{{color:var(--muted);font-size:11px;letter-spacing:.12em;text-transform:uppercase}}
.btns{{display:flex;gap:8px;padding:4px 30px 10px;flex-wrap:wrap}}
.btn{{background:transparent;color:var(--ink);border:1px solid var(--edge);font-family:{MONO};font-size:12px;letter-spacing:.12em;
     padding:7px 12px;cursor:pointer;text-transform:uppercase}}
.btn:hover{{border-color:var(--pink)}} .btn.on{{border-color:var(--mag);color:#fff;background:rgba(226,0,116,.18)}}
.grid2{{display:grid;grid-template-columns:1fr 380px;gap:0 18px;padding:0 30px}}
.tiles{{border:1px solid var(--edge);background:rgba(26,18,32,.7)}}
.tile{{display:flex;justify-content:space-between;gap:10px;padding:8px 12px;border-bottom:1px solid #22182a;font-size:12px}}
.tile .k{{color:var(--muted);letter-spacing:.1em;font-size:10.5px}} .tile .v{{text-align:right}}
.tile .v.nr{{color:#7A6A7E;font-style:italic}}
.cap{{color:var(--muted);font-size:11px;padding:8px 12px;line-height:1.5}}
.foot{{color:#8A7A8E;font-size:11px;padding:6px 30px;line-height:1.5}}
.dim{{opacity:.8}}
.ds,.cu{{display:none}} .ds.on,.cu.on{{display:block}}
"""

JS = """
function rotator(id, r, z, speed){
  const gd=document.getElementById(id); if(!gd) return; let t=Math.random()*6, on=true, last=0;
  ['mousedown','wheel','touchstart'].forEach(e=>gd.addEventListener(e,()=>{on=false; clearTimeout(gd._rt); gd._rt=setTimeout(()=>{on=true},9000);}));
  function step(ts){ const rc=gd.getBoundingClientRect(); const vis=rc.bottom>0 && rc.top<innerHeight/(parseFloat(document.body.style.zoom)||1);
  if(on && vis && gd.offsetParent!==null && gd._fullLayout && ts-last>70){ last=ts; t+=speed;
      Plotly.relayout(gd,{'scene.camera.eye':{x:r*Math.cos(t),y:r*Math.sin(t),z:z}}); }
    requestAnimationFrame(step);} requestAnimationFrame(step);
}
function pick(group, key){
  document.querySelectorAll('.'+group).forEach(el=>el.classList.toggle('on', el.dataset.k===key));
  document.querySelectorAll('.btn[data-g="'+group+'"]').forEach(b=>b.classList.toggle('on', b.dataset.k===key));
  document.querySelectorAll('.'+group+'.on .js-plotly-plot').forEach(p=>Plotly.Plots.resize(p));
}
function fit(){ if(!document.body) return; document.body.style.zoom = Math.min(1, window.innerWidth/1640).toFixed(3); }
fit(); window.addEventListener('resize', fit); document.addEventListener('DOMContentLoaded', fit);
window.addEventListener('load',()=>{ if(navigator.webdriver) return; ['cloud_5k','cloud_50k','cloud_250k'].forEach(id=>rotator(id,2.1,0.85,0.0045)); rotator('stack',2.3,0.9,0.003); });
"""


def tiles_html(s):
    rows = []
    for k, v in s["tiles"]:
        nr = "not run" in v
        rows.append(f"<div class='tile'><span class='k'>{_html.escape(k)}</span><span class='v{' nr' if nr else ''}'>{_html.escape(v)}</span></div>")
    return "".join(rows)


def div(fig, id_, include_js=False, cfg=None):
    return pio.to_html(fig, include_plotlyjs="inline" if include_js else False, full_html=False, div_id=id_,
                       config=cfg or dict(displaylogo=False, responsive=True), auto_play=False)


# ------------------------------------------------------------------------------------------- customer cards
FEATURED = [  # (account, intended story, action codes that match that story)
    ("ACC-PERSONA-38", "saves money · 55+ plan", {"variant_switch", "right_size"}),
    ("ACC-PERSONA-04", "fixed first", {"fix_first", "care_credit_fix_first"}),
    ("ACC-PERSONA-21", "check-in", {"check_in"}),
]
AVOID_HAPPY = {"ACC-PERSONA-28", "ACC-PERSONA-10", "ACC-PERSONA-06", "ACC-PERSONA-19"}


def pick_happy(d):
    """Do-nothing account whose 'leave alone' reason is verifiably true. Prefer personas, lowest p_churn."""
    o = d["offers"][["account_id", "action_code", "p_churn_90d"]]
    f = d["features"]
    e = d["enrichment"]
    cols = ["account_id", "is_persona", "support_90d", "unresolved_270d", "port_out_inquiry", "bill_increase_pct",
            "bill_change_3m_pct", "promo_expired_recent"]
    x = o.merge(f[[c for c in cols if c in f.columns]], on="account_id")
    if "promo_months_remaining" in e.columns:
        x = x.merge(e[["account_id", "promo_months_remaining"]], on="account_id", how="left")
    else:
        x["promo_months_remaining"] = 0
    checks = {
        "action is do_nothing": x["action_code"] == "do_nothing",
        "0 support contacts in 90 days": x["support_90d"] == 0,
        "0 unresolved contacts in 270 days": x["unresolved_270d"] == 0,
        "no port-out inquiry": x["port_out_inquiry"] == 0,
        "no recent bill increase (last bill and 3-month change <= 0)": (x["bill_increase_pct"] <= 0) & (x["bill_change_3m_pct"].fillna(0) <= 0),
        "no promo expired recently": x["promo_expired_recent"] == 0,
        "no promo ending within 3 months": (x["promo_months_remaining"].fillna(0) == 0) | (x["promo_months_remaining"] > 3),
        "p_churn_90d < 1%": x["p_churn_90d"] < 0.01,
        "not persona 28/10/06/19 (unstable between runs)": ~x["account_id"].isin(AVOID_HAPPY),
    }
    ok = np.logical_and.reduce(list(checks.values()))
    cand = x[ok].sort_values(["is_persona", "p_churn_90d"], ascending=[False, True])
    if cand.empty:
        return None, {}
    r = cand.iloc[0]
    detail = {
        "account_id": r["account_id"], "p_churn_90d": float(r["p_churn_90d"]), "support_90d": int(r["support_90d"]),
        "unresolved_270d": int(r["unresolved_270d"]), "port_out_inquiry": int(r["port_out_inquiry"]),
        "bill_increase_pct": float(r["bill_increase_pct"]), "bill_change_3m_pct": float(r["bill_change_3m_pct"]),
        "promo_expired_recent": int(r["promo_expired_recent"]), "promo_months_remaining": int(r["promo_months_remaining"] or 0),
        "checks_passed": list(checks.keys()), "n_accounts_passing_all_checks": int(ok.sum()),
    }
    return r["account_id"], detail


def happy_audit(d):
    """How many 'happy' do-nothing labels sit on accounts with unresolved contacts (we display labels as-is)."""
    o, f = d["offers"], d["features"]
    if "why_this_offer" not in o.columns:
        return {}
    x = o[["account_id", "why_this_offer"]].merge(f[["account_id", "unresolved_90d", "unresolved_270d", "support_90d"]], on="account_id")
    hp = x["why_this_offer"].astype(str).str.contains(r"\bhappy\b", case=False) & \
        ~x["why_this_offer"].astype(str).str.contains("unhappy", case=False)
    return {"happy_labels": int(hp.sum()),
            "happy_with_unresolved_90d": int((hp & (x["unresolved_90d"] > 0)).sum()),
            "happy_with_unresolved_270d": int((hp & (x["unresolved_270d"] > 0)).sum()),
            "happy_with_any_support_90d": int((hp & (x["support_90d"] > 0)).sum())}


def _first(df, names):
    return next((c for c in names if c in df.columns), None)


def options_rows(oc_acc: pd.DataFrame, standin_text) -> tuple[list[dict], dict]:
    """Options we considered. Uses tm-offers' new columns when present, else derives from existing ones."""
    c_cost = _first(oc_acc, ["cost_to_tmobile", "cost_to_tmobile_usd", "tmobile_cost", "cost_to_t_mobile"])
    c_cust = _first(oc_acc, ["customer_monthly_change", "customer_monthly_change_usd", "monthly_change_customer",
                             "customer_change_monthly", "customer_monthly_delta"])
    c_win = _first(oc_acc, ["is_winner", "winner", "is_chosen"])
    c_ev = _first(oc_acc, ["ev", "expected_value"])
    c_loss = _first(oc_acc, ["why_not_chosen", "loss_reason", "why_lost", "lost_because", "plain_loss_reason"])
    used = dict(cost=c_cost or "offer_cost (fallback)", customer=c_cust or "customer_benefit / upsell_gain (fallback)",
                winner=c_win, loss=c_loss or "blocked_or_ineligible_reason / EV comparison (fallback)")
    win = oc_acc[oc_acc[c_win] == True] if c_win else oc_acc.iloc[0:0]  # noqa: E712
    win_ev = float(win[c_ev].iloc[0]) if c_ev and len(win) and pd.notna(win[c_ev].iloc[0]) else 0.0
    rows = []
    for _, r in oc_acc.iterrows():
        is_win = bool(r[c_win]) if c_win else False
        elig = bool(r.get("eligible", True)) if pd.notna(r.get("eligible", True)) else False
        ev = r.get(c_ev) if c_ev else None
        if c_cost and pd.notna(r[c_cost]):
            cost = f"${float(r[c_cost]):,.0f}"
        elif pd.notna(r.get("offer_cost")) and elig:
            cost = f"${float(r['offer_cost']):,.0f}"
        else:
            cost = "—"
        if c_cust and pd.notna(r[c_cust]):
            v = float(r[c_cust])
            cust = "no change" if v == 0 else (f"saves ${-v:,.0f}/mo" if v < 0 else f"pays ${v:,.0f}/mo more")
        elif not elig:
            cust = "—"
        elif pd.notna(r.get("customer_benefit")) and float(r.get("customer_benefit") or 0) > 0:
            cust = f"benefit ${float(r['customer_benefit']):,.0f} (model est.)"
        elif pd.notna(r.get("upsell_gain")) and float(r.get("upsell_gain") or 0) > 0:
            cust = "pays more (upgrade)"
        elif "credit" in str(r["action"]).lower():
            cust = "gets a bill credit"
        else:
            cust = "no change"
        if is_win:
            why = "WINNER"
        elif c_loss and pd.notna(r[c_loss]) and str(r[c_loss]).strip():
            why = str(r[c_loss])
        elif not elig:
            why = "not eligible: " + str(r.get("blocked_or_ineligible_reason") or str(r.get("reason", "")).replace("Not eligible: ", ""))
        else:
            why = "scored lower than the winner (hover)"
        tip = str(r.get("reason", "")) if elig else ""
        rows.append(dict(option=standin_text(r["action"]), cost=cost, customer=cust, why=why, win=is_win, elig=elig,
                         ev=None if pd.isna(ev) else float(ev), tip=tip))
    rows.sort(key=lambda x: (not x["win"], not x["elig"], -(x["ev"] if x["ev"] is not None else -1e9)))
    return rows, used


def options_html(rows):
    h = ["<table class='opt'><thead><tr><th>option</th><th>cost to T-Mobile</th><th>customer saves / pays</th>"
         "<th>why it lost</th></tr></thead><tbody>"]
    for r in rows:
        cls = "win" if r["win"] else ("in" if not r["elig"] else "")
        tip = _html.escape(r["tip"] + (f"  [EV ${r['ev']:,.2f}]" if r["ev"] is not None else ""), quote=True)
        h.append(f"<tr class='{cls}' title=\"{tip}\"><td>{'&#9656; ' if r['win'] else ''}{_html.escape(r['option'])}</td>"
                 f"<td>{_html.escape(r['cost'])}</td><td>{_html.escape(r['customer'])}</td><td>{_html.escape(r['why'])}</td></tr>")
    h.append("</tbody></table>")
    return "".join(h)


def phone_html(story):
    en, es = story.get("message_en", ""), story.get("message_es", "")
    if not en:
        body = ("<div class='nomsg'>NO MESSAGE<br><span>leave alone · nothing is sent</span></div>")
    else:
        lang = story.get("language", "en")
        body = (f"<div class='lt'>ENGLISH{' · their language' if lang == 'en' else (' · English default' if lang not in ('en', 'es') else '')}</div>"
                f"<div class='bub'>{_html.escape(en)}</div>"
                f"<div class='lt'>ESPAÑOL{' · their language' if lang == 'es' else ''}</div><div class='bub'>{_html.escape(es)}</div>")
    return (f"<div class='phone'><div class='pbar'></div><div class='phd'>T-Mobile<span>text message · synthetic</span></div>"
            f"{body}<div class='pbar b'></div></div>")


CARD_CSS = """
.cardwrap{padding:0 30px}
.card{display:grid;grid-template-columns:1fr 340px;gap:22px;border:1px solid var(--edge);background:rgba(26,18,32,.55);padding:18px 20px}
.ctag{color:var(--mag);letter-spacing:.14em;font-size:12px;font-weight:700}
.why{font-size:21px;line-height:1.4;margin:10px 0 12px;color:var(--ink)}
.meta{display:flex;flex-wrap:wrap;gap:6px 18px;color:var(--muted);font-size:11.5px;letter-spacing:.06em;margin-bottom:12px}
.meta b{color:var(--ink);font-weight:600}
.chips{margin:4px 0 12px}.chip{display:inline-block;border:1px solid var(--edge);padding:2px 6px;margin:0 6px 6px 0;font-size:10.5px;color:var(--muted)}
.chip i{font-style:normal;color:var(--pink)}
.warn{color:#FFD27F;font-size:11px;margin:0 0 10px}
table.opt{width:100%;border-collapse:collapse;font-size:11.5px}
table.opt th{text-align:left;color:var(--muted);font-weight:400;letter-spacing:.1em;text-transform:uppercase;font-size:10px;border-bottom:1px solid var(--edge);padding:5px 6px}
table.opt td{padding:5px 6px;border-bottom:1px solid #22182a;vertical-align:top}
table.opt tr.win td{color:#fff;background:rgba(226,0,116,.22);border-bottom:1px solid var(--mag)}
table.opt tr.in td{color:#7A6A7E}
table.opt tr:hover td{background:rgba(255,143,191,.08)}
.phone{width:320px;background:#1A1220;border-radius:28px;padding:14px 14px 10px;border:2px solid #3A2C3E;box-shadow:0 0 0 1px #000,0 18px 40px rgba(0,0,0,.5)}
.pbar{height:8px;width:96px;border-radius:8px;background:#3A2C3E;margin:0 auto 12px}.pbar.b{margin:12px auto 0;width:110px;height:5px}
.phd{text-align:center;color:var(--pink);font-weight:700;margin-bottom:10px}.phd span{display:block;color:var(--muted);font-weight:400;font-size:10px}
.lt{color:var(--muted);font-size:10px;letter-spacing:.12em;margin:8px 2px 4px}
.bub{background:#F7F1EA;color:#1A1220;border-radius:16px 16px 16px 4px;padding:10px 12px;font-size:12.5px;line-height:1.45}
.nomsg{color:var(--muted);text-align:center;padding:90px 0;letter-spacing:.18em}.nomsg span{font-size:10px;letter-spacing:.08em}
"""


def card_html(story, rows, title, mismatch, drivers):
    meta = [("p(churn 90d)", f"{story['p']:.2%}"), ("rank", f"{story['rank']:,} of {story['n']:,}"),
            ("Model A flag", "FLAGGED (top 10%)" if story["flagged"] else "not flagged"),
            ("action", story["chosen"]), ("segment", story.get("segment_label") or "—"),
            ("language", story["language"].upper()), ("channel", story["contact_pref"])]
    chips = "".join(f"<span class='chip'><i>{_html.escape(g)}</i> {_html.escape(s.replace('_', ' '))}</span>" for g, s in drivers)
    why = story.get("why") or story["reason"].split(" EV =")[0]
    return (f"<div class='card'><div><div class='ctag'>[ {story['account_id']} ] {_html.escape(title.upper())}</div>"
            + (f"<div class='warn'>NOTE: {_html.escape(mismatch)}</div>" if mismatch else "")
            + f"<div class='why'>{_html.escape(why)}</div>"
            + "<div class='meta'>" + "".join(f"<span>{_html.escape(k)} <b>{_html.escape(v)}</b></span>" for k, v in meta) + "</div>"
            + (f"<div class='chips'>{chips}</div>" if chips else "")
            + "<div class='ctag' style='margin:6px 0 6px'>[ OPTIONS WE CONSIDERED ]  <span style='color:var(--muted);font-weight:400'>hover a row for the details</span></div>"
            + options_html(rows) + "</div>"
            + f"<div>{phone_html(story)}</div></div>")


def page(parts: dict, sets, cards, stats) -> str:
    f = stats["funnel"]
    ticker = (" // ".join([
        "ALL CUSTOMERS AND NUMBERS ARE SYNTHETIC", f"{f['all_accounts']:,} SANDBOX ACCOUNTS",
        f"{f['flagged']:,} FLAGGED BY MODEL A", f"{f['offered']:,} OFFERS WORTH MAKING", f"{f['do_nothing']:,} LEFT ALONE",
        f"{f['messaged']:,} MESSAGES READY · 0 SENT"] + [f"{s['label']}: {s['n']:,} ROWS" for s in sets]
        + ["MODEL A = TM-CHURN CHURN_SCORES.CSV", "MODEL B = TM-OFFERS OFFERS.CSV", "POLICY DOLLARS PROVISIONAL"]) + " // ") * 2
    ds_btns = "".join(f"<button class='btn{' on' if i == 0 else ''}' data-g='ds' data-k='{s['key']}' onclick=\"pick('ds','{s['key']}')\">[ {s['label']} ]</button>"
                      for i, s in enumerate(sets))
    ds_blocks = "".join(
        f"<div class='ds{' on' if i == 0 else ''}' data-k='{s['key']}'><div class='grid2'><div>{parts['cloud_' + s['key']]}</div>"
        f"<div><div class='tiles'><div class='tile'><span class='k'>DATASET</span><span class='v'>{_html.escape(s['long'])}</span></div>"
        f"{tiles_html(s)}<div class='cap'>{_html.escape(s['note'])}<br><br>x: {_html.escape(s['xlab'])}<br>y: monthly bill (last_bill_cents)"
        f"<br>z: {_html.escape(s['zlab'])}<br>{_html.escape(s['color_note'])}<br>points drawn: {s['shown']:,} of {s['n']:,} (counts use all rows)</div></div>"
        f"{parts['mini_' + s['key']]}</div></div></div>" for i, s in enumerate(sets))
    cu_btns = "".join(f"<button class='btn{' on' if i == 0 else ''}' data-g='cu' data-k='{c['key']}' onclick=\"pick('cu','{c['key']}')\">[ {c['btn']} ]</button>"
                      for i, c in enumerate(cards))
    cu_blocks = "".join(f"<div class='cu{' on' if i == 0 else ''}' data-k='{c['key']}'><div class='cardwrap'>{c['html']}</div>"
                        f"<div style='padding:10px 30px 0'>{parts['tog_' + c['key']]}</div>"
                        "<div class='foot'>Live toggles and re-picks are in the Streamlit app; these are precomputed (risk only).</div></div>"
                        for i, c in enumerate(cards))

    def sec(i, t, sub, body):
        return f"<div class='sec'><div class='sh'><span class='id'>[ {i:02d} ]</span><span class='t'>{t}</span><span class='s'>{sub}</span></div>{body}</div>"

    return f"""<!doctype html><html><head><meta charset="utf-8"><title>TM retention pipeline v4 (synthetic)</title>
<meta name="viewport" content="width=device-width"><style>{CSS}{CARD_CSS}</style>{parts['js']}</head><body>
<div class="top"><span>ALL CUSTOMERS AND NUMBERS ARE SYNTHETIC</span><span>[ TM RETENTION PIPELINE · v4 ]</span><span>NOTHING IS SENT</span></div>
<div class="ticker"><span>{_html.escape(ticker)}</span></div>
<div class="wrap">
<div class="hero"><h1>WHO WE TEXT, <b>WHAT</b> WE OFFER, AND WHY WE LEAVE MOST PEOPLE ALONE</h1>
<p>Judge sandbox data → features → Model A (churn risk + reasons) → Model B (weighs every eligible option against doing nothing) → a plain message in the customer's language. Every count is computed from the team's synthetic CSVs at build time.</p></div>
{sec(1, "Funnel", "sandbox 5k · press play", parts['funnel'])}
{sec(2, "Four customers, four answers", "why first · options we considered · the text they get", "<div class='btns'>" + cu_btns + "</div>" + cu_blocks)}
{sec(3, "Population cloud", "drag to orbit · scroll to zoom · switch dataset", "<div class='btns'>" + ds_btns + "</div>" + ds_blocks)}
{sec(4, "Pipeline stack", "each plane = 400 dots ≈ 13 accounts each · lit = passes that stage", parts['stack'])}
{sec(5, "What if X% accept", "projected, illustrative assumption (synthetic)", parts['whatif'])}
{sec(6, "Future: consented data (simulated, not used)", "never feeds decisions or text", "<div class='dim'>" + parts['future'] + "</div>")}
{sec(7, "Slide", "static export: app/viz/pipeline_flow.png", parts['slide'])}
<div class="foot">Model A = tm-churn churn_scores.csv (sandbox 5k) and scaled_scores/churn_scores.csv (50k). Model B = tm-offers offers.csv / offer_candidates.csv.
† judge-provided stand-in credit (sandbox promotions.source = 'stub'). Held-out Model A: top 10% catches 62% of churners (oracle 64%, 3+ calls rule 53%), AUC 0.853. Policy dollars PROVISIONAL.</div>
</div></body></html>"""
