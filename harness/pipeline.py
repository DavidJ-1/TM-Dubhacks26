"""End-to-end pipeline summary: data -> features -> Model A -> EV offer engine -> message.  ALL SYNTHETIC.

Reuses the other lanes' code without editing it:
  features   harness/features.py (tm-data)            -> features.csv
  Model A    harness/churn_model.py (tm-churn)        -> churn_scores.csv
  EV engine  harness/offers.py + offer_detectors.py   -> offers.csv, offer_candidates.csv   (tm-offers; canonical
             for these two files; the console's engine.py builds its own in-memory view and is not used here)
  messages   app/messages.py render_message (tm-ui)   -> SMS text per chosen action (en/es)

Writes out/pipeline_stages.json (schema shared with the team):
  {synthetic, caveat, generated_at, data_source, label, segment_key, excluded_personas,
   stages: [accounts, scored, flagged, offered, wait, messaged]  each {id, label, count, by_segment, ...extras},
   trace: {account_id, signals[{name, value, source}], score{p_churn_90d, percentile, risk_reasons, stay_reasons},
           offer{candidates[{action, ev, eligible}], chosen}, message{language, text}}}
Invariant: offered + wait == flagged. The is_persona demo accounts are excluded from every stage count
(excluded_personas reports how many) but any account, persona or not, can be traced. Trace signals are plain
English (plan names from the sandbox plans table, never SKUs or column names); 'signals' = the ~8 behind the
chosen offer and Model A's reasons, 'all_signals' = the full list. Messages: app/messages.py templates (tm-ui
owns the copy); the source used is recorded on the messaged stage and on trace.message.  A stage whose source is unavailable gets count null and a 'note'.

Modes:
  default   summarise the lanes' latest outputs in harness/out/ (no recomputation, nothing overwritten)
  --run     recompute every stage into an isolated folder harness/out/pipeline_run/<data_source>/ (features.build(),
            churn_model.py --out-dir, offers.py with TM_OUT_DIR), then summarise that folder. Labels for training
            Model A are read (never written) from tm-data's labels file.
CLI: python harness/pipeline.py [--run] [--data sandbox_5k|scaled_50k] [--segment risk_band|family_plan]
                                [--trace ACC-PERSONA-22] [--lang en|es]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = Path(os.environ.get("MH_OUT_DIR", HERE / "out"))
CAVEAT = ("All customers, labels and numbers are SYNTHETIC / SIMULATED (judge sandbox stub data + simulated "
          "labels). Counts show how the pipeline behaves, not real T-Mobile results.")
DATA_SOURCES = {
    "sandbox_5k": {"features": "features.csv", "labels": "labels.csv"},
    "scaled_50k": {"features": "scaled/features_scaled.csv", "labels": "scaled/labels_scaled.csv"},
}
FLAG_TOP_FRAC = 0.10
FLAG_RULE = "top 10% churn risk or an upgrade moment"
STAGE_LABELS = [("accounts", "Customers"), ("scored", "Scored by Model A"), ("flagged", "Flagged this week"),
                ("offered", "Offer beats waiting"), ("wait", "Do nothing"), ("messaged", "Message drafted")]
# Signal -> source grouping, copied from tm-ui's app/streamlit_app.py SIGNALS (a UI choice: commerce =
# plan/bill/device/financing, customer = profile + support history, live = latest signals snapshot).
SIGNALS = {
    "plan_sku": "commerce", "n_lines": "commerce", "last_bill_cents": "commerce", "bill_change_3m_pct": "commerce",
    "promo_expired_recent": "commerce", "installment_ended_recent": "commerce",
    "min_financing_months_left_financed": "commerce", "max_device_age_months": "commerce",
    "n_lines_over_cap_3m": "commerce",
    "segment": "customer", "tenure_months": "customer", "language": "customer", "contact_preference": "customer",
    "autopay": "customer", "support_90d": "customer", "unresolved_90d": "customer", "avg_sentiment_90d": "customer",
    "network_contacts_90d": "customer", "cancel_inquiries_270d": "customer",
    "competitor_research_score": "live", "port_out_inquiry": "live", "app_sessions_30d": "live",
    "data_growth_pct": "live",
}
FAMILY_PLAN_COLS = ("family_plan", "is_family_plan", "household_type")   # tm-data household fields (future)


def _py() -> str:
    return sys.executable


def _clean(v):
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if math.isnan(float(v)) else float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def _action_key(off: pd.DataFrame, aid: str) -> str:
    """tm-offers' machine code (action_code, e.g. care_credit_fix_first) when present, else the display label;
    app/messages.py understands the codes but not every combined display label."""
    if "action_code" in off.columns and isinstance(off.at[aid, "action_code"], str):
        return off.at[aid, "action_code"]
    return str(off.at[aid, "action"])


def _messages_module():
    sys.path.insert(0, str(REPO / "app"))
    try:
        import messages  # type: ignore  (tm-ui, app/messages.py)
        return messages
    except Exception:  # noqa: BLE001
        return None


# ============================================================================================ --run (recompute)
def run_stages(data_source: str, run_dir: Path) -> dict:
    """Recompute features -> Model A -> offers into run_dir (isolated; canonical out/ untouched)."""
    run_dir.mkdir(parents=True, exist_ok=True)
    log = {}
    feats = run_dir / "features.csv"
    if data_source == "sandbox_5k":
        sys.path.insert(0, str(HERE))
        import features as tmdata_features  # tm-data, read-only sandbox
        tmdata_features.build().to_csv(feats, index=False)
        log["features"] = "features.build() (sandbox read-only)"
    else:
        src = OUT / DATA_SOURCES[data_source]["features"]  # scaled: tm-data's file, copied into the run folder
        pd.read_csv(src).to_csv(feats, index=False)
        log["features"] = f"copied {src}"
    labels = OUT / DATA_SOURCES[data_source]["labels"]
    r = subprocess.run([_py(), str(HERE / "churn_model.py"), "--features", str(feats), "--labels", str(labels),
                        "--out-dir", str(run_dir)], capture_output=True, text=True, cwd=REPO)
    log["model_a"] = "ok" if r.returncode == 0 else f"failed: {r.stderr[-400:]}"
    if data_source == "sandbox_5k" and r.returncode == 0:
        env = dict(os.environ, TM_OUT_DIR=str(run_dir))
        r2 = subprocess.run([_py(), str(HERE / "offers.py")], capture_output=True, text=True, cwd=REPO, env=env)
        log["offers"] = "ok" if r2.returncode == 0 else f"failed: {r2.stderr[-400:]}"
    else:
        log["offers"] = "skipped: the EV engine needs sandbox account facts (scaled SYN-* accounts are not in the sandbox)"
    return log


# ============================================================================================ summary
DATA_FILES = {  # data_source -> (features, scores, offers dir candidates, household)
    "sandbox_5k": {"features": "features.csv", "scores": "churn_scores.csv", "household": "enrichment.csv"},
    "scaled_50k": {"features": "scaled/features_scaled.csv", "scores": "scaled_scores/churn_scores.csv",
                   "household": "scaled/household_scaled.csv"},
}
OFFERS_COLS = {"account_id", "action", "upgrade_moment"}
CAND_COLS = {"account_id", "action", "eligible", "expected_value", "is_chosen"}


def _read(path: Optional[Path]) -> Optional[pd.DataFrame]:
    return pd.read_csv(path) if path is not None and path.exists() else None


def _mtime(path: Optional[Path]) -> Optional[str]:
    return (datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
            if path is not None and path.exists() else None)


def _header(path: Path) -> set:
    try:
        return set(pd.read_csv(path, nrows=0).columns)
    except Exception:  # noqa: BLE001
        return set()


def _find_offers(src_dir: Path, data_source: str):
    """offers.csv / offer_candidates.csv for this data source. sandbox: src_dir/offers.csv. scaled: any
    offers*.csv under src_dir whose schema matches tm-offers' and whose ids are SYN-* (tm-offers' 50k trial)."""
    if data_source == "sandbox_5k":
        o, c = src_dir / "offers.csv", src_dir / "offer_candidates.csv"
        return (o if o.exists() else None), (c if c.exists() else None)
    for o in sorted(src_dir.rglob("offers*.csv")):
        if "pipeline_run" in o.parts or not OFFERS_COLS <= _header(o):
            continue
        try:
            first = str(pd.read_csv(o, nrows=1)["account_id"].iloc[0])
        except Exception:  # noqa: BLE001
            continue
        if first.startswith("SYN-"):
            c = o.with_name(o.name.replace("offers", "offer_candidates"))
            return o, (c if c.exists() and CAND_COLS <= _header(c) else None)
    return None, None


def _segments(ids: pd.Index, seg: Optional[pd.Series]) -> dict:
    if seg is None:
        return {}
    return {str(k): int(v) for k, v in seg.reindex(ids).fillna("unknown").value_counts().sort_index().items()}


# ---------------------------------------------------------------------------------- plain-English signals
def _plan_names() -> dict:
    """SKU -> plan name from the judge sandbox's plans table (opened read-only); {} if unavailable."""
    import sqlite3
    try:
        from harness.features import find_db
    except ImportError:  # run as a script from harness/
        from features import find_db  # type: ignore
    try:
        dbs = [find_db()]
    except FileNotFoundError:
        dbs = []
    for db in dbs:
        if db.exists():
            try:
                con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
                try:
                    return {k: v for k, v in con.execute("select sku, name from plans")}
                finally:
                    con.close()
            except Exception:  # noqa: BLE001
                return {}
    return {}


_PLAN_NAMES: Optional[dict] = None
_FAMILY_TEXT = {"essentials": "Essentials", "experience_more": "Experience More", "experience_beyond": "Experience Beyond"}


def _plan_text(sku, row) -> Optional[str]:
    global _PLAN_NAMES
    if _PLAN_NAMES is None:
        _PLAN_NAMES = _plan_names()
    if isinstance(sku, str) and sku in _PLAN_NAMES:
        return _PLAN_NAMES[sku]
    fam = row.get("plan_family") if hasattr(row, "get") else None
    return _FAMILY_TEXT.get(fam) if isinstance(fam, str) else None    # never a raw SKU


def _yn(v):
    return None if v is None else ("Yes" if float(v) else "No")


def _pct(v):
    return None if v is None else f"{float(v) * 100:+.0f}%"


def _money_c(v):
    return None if v is None else f"${float(v) / 100:,.2f}"


def _int(v, unit=None):
    if v is None:
        return None
    n = int(round(float(v)))
    return f"{n}" if unit is None else f"{n} {unit}{'' if n == 1 else 's'}"


_SEG = {"family": "Family", "single": "Single person", "couple": "Couple", "student": "Student",
        "smb": "Small business", "senior": "Senior"}
_LANG = {"en": "English", "es": "Spanish", "other": "Another language"}
_CONTACT = {"app": "T-Life app", "sms": "Text message", "email": "Email", "call": "Phone call"}


def _sentiment(v):
    if v is None:
        return None
    v = float(v)
    word = "Negative" if v <= -0.2 else ("Positive" if v >= 0.2 else "Neutral")
    return f"{word} ({v:+.2f} on a -1 to +1 scale)"


def _shopping(v):
    if v is None:
        return None
    v = float(v)
    word = "High" if v >= 0.5 else ("Some" if v >= 0.3 else "Low")
    return f"{word} ({v:.2f} on a 0 to 1 scale)"


# column -> (plain label, formatter(value, row))
SIGNAL_TEXT = {
    "plan_sku": ("Plan", lambda v, r: _plan_text(v, r)),
    "n_lines": ("Lines on the account", lambda v, r: _int(v)),
    "last_bill_cents": ("Latest monthly bill", lambda v, r: _money_c(v)),
    "bill_change_3m_pct": ("Bill change vs prior 3 months", lambda v, r: _pct(v)),
    "promo_expired_recent": ("Promo credit ended recently", lambda v, r: _yn(v)),
    "installment_ended_recent": ("Phone just paid off", lambda v, r: _yn(v)),
    "min_financing_months_left_financed": ("Months until next phone payoff",
                                           lambda v, r: "No phone payments" if v is not None and float(v) == 0 else _int(v, "month")),
    "max_device_age_months": ("Age of oldest phone", lambda v, r: _int(v, "month")),
    "n_lines_over_cap_3m": ("Lines that went over their data cap (3 months)", lambda v, r: _int(v)),
    "segment": ("Account type", lambda v, r: _SEG.get(v, str(v).replace("_", " ").capitalize() if v else None)),
    "tenure_months": ("Customer for", lambda v, r: None if v is None else
                      (f"{int(v) // 12} years" if float(v) >= 24 else _int(v, "month"))),
    "language": ("Preferred language", lambda v, r: _LANG.get(v, v)),
    "contact_preference": ("Preferred contact", lambda v, r: _CONTACT.get(v, v)),
    "autopay": ("On AutoPay", lambda v, r: _yn(v)),
    "support_90d": ("Support contacts (last 90 days)", lambda v, r: _int(v)),
    "unresolved_90d": ("Unresolved support issues (last 90 days)", lambda v, r: _int(v)),
    "avg_sentiment_90d": ("Tone of recent support contacts", lambda v, r: _sentiment(v)),
    "network_contacts_90d": ("Network complaints (last 90 days)", lambda v, r: _int(v)),
    "cancel_inquiries_270d": ("Cancellation questions (last 9 months)", lambda v, r: _int(v)),
    "competitor_research_score": ("Shopping other carriers", lambda v, r: _shopping(v)),
    "port_out_inquiry": ("Asked about moving their number", lambda v, r: _yn(v)),
    "app_sessions_30d": ("T-Life app visits (last 30 days)", lambda v, r: _int(v)),
    "data_growth_pct": ("Change in data use", lambda v, r: _pct(v)),
}
# keywords in Model A's reason text -> the signal behind it (used to rank signals for the trace)
REASON_KEYWORDS = {
    "plan_sku": ["plan"], "n_lines": ["line"], "last_bill_cents": ["bill"], "bill_change_3m_pct": ["bill up", "bill"],
    "promo_expired_recent": ["promo"], "installment_ended_recent": ["paid off", "payoff"],
    "min_financing_months_left_financed": ["financ", "payment", "owes"], "max_device_age_months": ["phone (", "phone old", "newer phone", "older phone", "months old", "years old"],
    "n_lines_over_cap_3m": ["cap", "data"], "segment": ["account", "family", "student", "senior"],
    "tenure_months": ["customer", "tenure", "yrs", "years"], "autopay": ["autopay"],
    "support_90d": ["support contact"], "unresolved_90d": ["unresolved"], "avg_sentiment_90d": ["unhappy", "sentiment", "tone"],
    "network_contacts_90d": ["network", "coverage"], "cancel_inquiries_270d": ["cancel"],
    "competitor_research_score": ["carrier", "shopping", "competitor"], "port_out_inquiry": ["port-out", "port out", "switching", "moving their number"],
    "app_sessions_30d": ["app"], "data_growth_pct": ["data use", "usage"],
}
# signals each EV-engine action is built on (tm-offers detectors / OFFERS_README)
ACTION_SIGNALS = {
    "$25 care credit": ["promo_expired_recent", "bill_change_3m_pct", "last_bill_cents"],
    "fix-first callback": ["unresolved_90d", "network_contacts_90d", "avg_sentiment_90d", "support_90d"],
    "$25 care credit + fix-first callback": ["promo_expired_recent", "bill_change_3m_pct", "unresolved_90d",
                                             "avg_sentiment_90d", "network_contacts_90d"],
    "loyalty credit": ["tenure_months", "competitor_research_score", "port_out_inquiry"],
    "keep-your-phone credit": ["installment_ended_recent", "min_financing_months_left_financed"],
    "right-size plan": ["plan_sku", "last_bill_cents", "data_growth_pct"],
    "step-up plan": ["plan_sku", "n_lines_over_cap_3m", "data_growth_pct"],
    "device upgrade": ["max_device_age_months", "min_financing_months_left_financed"],
}
TRACE_TOP_N = 8


def _signals(row, reasons: list, chosen: Optional[str], n: int = TRACE_TOP_N):
    """(top-n relevant signals, all signals) in plain English. Order: signals behind the chosen offer, then
    behind Model A's reasons (in reason order), then the account's live/commerce rest in SIGNALS order."""
    allsig = []
    for k, src in SIGNALS.items():
        if k not in row.index:
            continue
        label, fmt = SIGNAL_TEXT[k]
        v = _clean(row[k])
        try:
            txt = fmt(v, row) if v is not None else None
        except (TypeError, ValueError):
            txt = None
        if txt is None:
            txt = "Not available"
        allsig.append({"key": k, "name": label, "value": txt, "source": src})
    by_key = {s["key"]: s for s in allsig}
    order = []
    for k in ACTION_SIGNALS.get(chosen or "", []):
        if k in by_key and k not in order:
            order.append(k)
    for rtxt in reasons:
        low = rtxt.lower()
        for k, kws in REASON_KEYWORDS.items():
            if k in by_key and k not in order and any(w in low for w in kws):
                order.append(k)
    order += [k for k in by_key if k not in order]
    strip = lambda s: {kk: vv for kk, vv in s.items() if kk != "key"}  # noqa: E731  (never expose column names)
    return [strip(by_key[k]) for k in order[:n]], [strip(s) for s in allsig]


def summarize(src_dir: Path, data_source: str = "sandbox_5k", segment_key: str = "risk_band",
              trace_id: str = "ACC-PERSONA-22", lang: Optional[str] = None, label: str = "churn_90d",
              features_path: Optional[Path] = None, scores_path: Optional[Path] = None) -> dict:
    files = DATA_FILES[data_source]
    canonical = src_dir == OUT
    fpath = features_path or (src_dir / (files["features"] if canonical else "features.csv"))
    spath = scores_path or (src_dir / (files["scores"] if canonical else "churn_scores.csv"))
    opath, cpath = _find_offers(src_dir, data_source)
    f = _read(fpath)
    if f is None:
        raise FileNotFoundError(f"features not found at {fpath}")
    f = f.set_index("account_id")
    persona = (f["is_persona"].astype(bool) if "is_persona" in f.columns
               else pd.Series(f.index.str.startswith("ACC-PERSONA-"), index=f.index))
    regular = f.index[~persona.values]
    n_personas = int(persona.sum())
    sc_all = _read(spath)
    sc_all = sc_all.set_index("account_id") if sc_all is not None else None
    sc = sc_all.loc[sc_all.index.intersection(regular)] if sc_all is not None else None
    off = _read(opath)
    off = off.set_index("account_id") if off is not None else None
    cand = _read(cpath)
    msgs = _messages_module()
    msg_source = ("app/messages.py render_message (tm-ui deterministic templates)" if msgs is not None else None)

    # risk rank among regular accounts only (personas excluded from every count)
    rk = sc["p_churn_90d"].rank(ascending=False, method="first") if sc is not None else None

    seg, seg_note = None, None
    if segment_key == "risk_band":
        if sc is not None:
            n = len(sc)
            seg = pd.Series(np.where(rk <= math.ceil(0.10 * n), "high",
                                     np.where(rk <= math.ceil(0.30 * n), "medium", "low")), index=sc.index)
        else:
            seg_note = "risk_band needs Model A scores"
    elif segment_key == "family_plan":
        col = next((c for c in FAMILY_PLAN_COLS if c in f.columns), None)
        fam = lambda v: ("unknown" if pd.isna(v) else  # noqa: E731
                         "family_plan" if str(v) in ("1", "1.0", "True", "true") else "not_family_plan")
        hh = None
        if col is None:   # tm-data: real 5k -> enrichment.csv, scaled 50k -> scaled/household_scaled.csv
            for hp in (src_dir / Path(files["household"]).name, OUT / files["household"]):
                if hp.exists() and "is_family_plan" in _header(hp):
                    hh = pd.read_csv(hp, usecols=["account_id", "is_family_plan"])
                    break
        if col:
            seg = f[col].map(fam)
        elif hh is not None:
            seg = hh.set_index("account_id")["is_family_plan"].map(fam)
        else:
            seg_note = "family_plan: tm-data's household fields (is_family_plan) are not available for this data source"
    else:
        raise ValueError("segment_key must be risk_band or family_plan")

    def stage(sid, count, ids=None, **extra):
        d = {"id": sid, "label": dict(STAGE_LABELS)[sid], "count": count,
             "by_segment": _segments(ids, seg) if (ids is not None and count is not None) else {}}
        if seg_note and count is not None:
            d["segment_note"] = seg_note
        d.update(extra)
        return d

    stages = [stage("accounts", int(len(regular)), regular, source=str(fpath), source_mtime=_mtime(fpath))]
    if sc is not None:
        scored = sc.index[sc["p_churn_90d"].notna()]
        stages.append(stage("scored", int(len(scored)), scored, source=str(spath), source_mtime=_mtime(spath)))
    else:
        stages.append(stage("scored", None, note="Model A scores not available for this data source"))

    flagged = None
    if sc is not None:
        top = set(sc.index[rk <= math.ceil(FLAG_TOP_FRAC * len(sc))])
        if off is not None and "upgrade_moment" in off:
            um = set(off.index[off["upgrade_moment"].astype(bool)]) & set(regular)
            flagged = pd.Index(sorted(top | um))
            stages.append(stage("flagged", int(len(flagged)), flagged, rule=FLAG_RULE, top_risk=len(top),
                                upgrade_moment=len(um), overlap=len(top & um)))
        else:
            topi = pd.Index(sorted(top))
            stages.append(stage("flagged", None, rule=FLAG_RULE, top_risk=len(top),
                                top_risk_by_segment=_segments(topi, seg), upgrade_moment=None,
                                note="only the top-10% churn part is known; upgrade moments come from the EV engine "
                                     "(offers.csv), which has no output for this data source yet"))
    else:
        stages.append(stage("flagged", None, rule=FLAG_RULE, note="needs Model A scores"))

    offered_ids = None
    if flagged is not None and off is not None:
        act = off.reindex(flagged)["action"].astype(str)
        is_wait = act.str.strip().str.lower().isin(["do nothing", "nan"])
        offered_ids, wait_ids = flagged[~is_wait.values], flagged[is_wait.values]
        stages.append(stage("offered", int(len(offered_ids)), offered_ids,
                            by_action={k: int(v) for k, v in act[~is_wait].value_counts().items()},
                            source=str(opath), source_mtime=_mtime(opath)))
        stages.append(stage("wait", int(len(wait_ids)), wait_ids))
    else:
        note = "EV offer engine output (offers.csv) not available for this data source yet"
        stages.append(stage("offered", None, note=note, by_action={}))
        stages.append(stage("wait", None, note=note))

    def acct_lang(aid):
        v = str(f.at[aid, "language"]) if "language" in f.columns and aid in f.index else "en"
        return "es" if v == "es" else "en"

    if offered_ids is not None and msgs is not None:
        texts = {}
        for aid in offered_ids:
            lg = acct_lang(aid)
            t = msgs.render_message(_action_key(off, aid), lg,
                                    _clean(f.at[aid, "tenure_months"]) if aid in f.index else None)
            if t:
                texts[aid] = lg
        ids = pd.Index(list(texts))
        bl = {"en": sum(1 for v in texts.values() if v == "en"), "es": sum(1 for v in texts.values() if v == "es")}
        extra = {"by_language": bl, "message_source": msg_source}
        no_tpl = int(len(offered_ids) - len(ids))
        if no_tpl:
            extra["note"] = f"{no_tpl} offered accounts have no message template for their action"
        stages.append(stage("messaged", int(len(ids)), ids, **extra))
    else:
        stages.append(stage("messaged", None, by_language={"en": None, "es": None}, message_source=msg_source,
                            note="needs offers (EV engine) and app/messages.py"))

    # ---------------------------------------------------------------- trace (any account, personas allowed)
    trace = {"account_id": trace_id}
    score = None
    if sc_all is not None and trace_id in sc_all.index:
        r = sc_all.loc[trace_id]
        p = float(r["p_churn_90d"])
        reg = sc["p_churn_90d"]
        score = {"p_churn_90d": p,
                 "percentile": round(float((reg < p).mean() * 100 + (reg == p).mean() * 50), 1),
                 "risk_reasons": [str(r[c]) for c in ("risk_reason_1", "risk_reason_2", "risk_reason_3")
                                  if c in r and isinstance(r[c], str) and r[c]],
                 "stay_reasons": [str(r[c]) for c in ("stay_reason_1", "stay_reason_2", "stay_reason_3")
                                  if c in r and isinstance(r[c], str) and r[c]]}
    chosen, offer = None, None
    if cand is not None and trace_id in set(cand["account_id"]):
        cc = cand[cand["account_id"] == trace_id]
        ch = cc[cc["is_chosen"].astype(bool)]
        chosen = str(ch["action"].iloc[0]) if len(ch) else None
        offer = {"candidates": [{"action": str(a), "ev": _clean(e), "eligible": bool(el)}
                                for a, e, el in zip(cc["action"], cc["expected_value"], cc["eligible"])],
                 "chosen": chosen}
    if trace_id in f.index:
        reasons = (score["risk_reasons"] + score["stay_reasons"]) if score else []
        top, allsig = _signals(f.loc[trace_id], reasons, chosen)
        trace["signals"], trace["all_signals"] = top, allsig
    else:
        trace["signals"], trace["all_signals"] = [], []
        trace["note"] = f"{trace_id} is not in this data source"
    trace["score"], trace["offer"] = score, offer
    if chosen is not None and msgs is not None:
        lg = lang or acct_lang(trace_id)
        ten = _clean(f.at[trace_id, "tenure_months"]) if trace_id in f.index else None
        key = _action_key(off, trace_id) if off is not None and trace_id in off.index else chosen
        trace["message"] = {"language": lg, "text": msgs.render_message(key, lg, ten), "source": msg_source}
    else:
        trace["message"] = None

    out = {"synthetic": True, "caveat": CAVEAT,
           "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
           "data_source": data_source, "label": label, "segment_key": segment_key,
           "excluded_personas": n_personas, "stages": stages, "trace": trace}
    check_invariants(out)
    return out


def check_invariants(d: dict) -> None:
    s = {x["id"]: x for x in d["stages"]}
    assert [x["id"] for x in d["stages"]] == [i for i, _ in STAGE_LABELS], "stage order"
    o, w, fl = s["offered"]["count"], s["wait"]["count"], s["flagged"]["count"]
    if None not in (o, w, fl):
        assert o + w == fl, f"offered {o} + wait {w} != flagged {fl}"
    if s["messaged"]["count"] is not None and o is not None:
        assert s["messaged"]["count"] <= o


def main(argv=None):
    ap = argparse.ArgumentParser(description="End-to-end pipeline summary (SYNTHETIC) -> out/pipeline_stages.json")
    ap.add_argument("--run", action="store_true", help="recompute all stages into out/pipeline_run/<data>/")
    ap.add_argument("--data", choices=list(DATA_SOURCES), default="sandbox_5k")
    ap.add_argument("--segment", choices=["risk_band", "family_plan"], default="risk_band")
    ap.add_argument("--trace", default="ACC-PERSONA-22")
    ap.add_argument("--lang", choices=["en", "es"], default=None, help="trace message language (default: account's)")
    ap.add_argument("--out", default=str(OUT / "pipeline_stages.json"))
    a = ap.parse_args(argv)
    if a.run:
        rd = OUT / "pipeline_run" / a.data
        log = run_stages(a.data, rd)
        print("run:", json.dumps(log, indent=1))
        d = summarize(rd, a.data, a.segment, a.trace, a.lang, features_path=rd / "features.csv",
                      scores_path=rd / "churn_scores.csv")
    else:
        d = summarize(OUT, a.data, a.segment, a.trace, a.lang)
    Path(a.out).write_text(json.dumps(d, indent=2, ensure_ascii=False))
    for s in d["stages"]:
        print(f"{s['id']:<9} {s['label']:<20} {s['count']!s:>6}  {s.get('note', '')}")
    print(f"wrote {a.out}  [SYNTHETIC]")
    return d


if __name__ == "__main__":
    main()
