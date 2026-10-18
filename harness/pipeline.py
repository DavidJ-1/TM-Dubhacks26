"""End-to-end pipeline summary: data -> features -> Model A -> EV offer engine -> message.  ALL SYNTHETIC.

Reuses the other lanes' code without editing it:
  features   harness/features.py (tm-data)            -> features.csv
  Model A    harness/churn_model.py (tm-churn)        -> churn_scores.csv
  EV engine  harness/offers.py + offer_detectors.py   -> offers.csv, offer_candidates.csv   (tm-offers; canonical
             for these two files; the console's engine.py builds its own in-memory view and is not used here)
  messages   app/messages.py render_message (tm-ui)   -> SMS text per chosen action (en/es)

Writes out/pipeline_stages.json (schema shared with the team):
  {synthetic, caveat, generated_at, data_source, label, segment_key,
   stages: [accounts, scored, flagged, offered, wait, messaged]  each {id, label, count, by_segment, ...extras},
   trace: {account_id, signals[{name, value, source}], score{p_churn_90d, percentile, risk_reasons, stay_reasons},
           offer{candidates[{action, ev, eligible}], chosen}, message{language, text}}}
Invariant: offered + wait == flagged.  A stage whose source is unavailable gets count null and a 'note'.

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
        src = OUT / DATA_SOURCES[data_source]["features"]
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
def _read(path: Path) -> Optional[pd.DataFrame]:
    return pd.read_csv(path) if path.exists() else None


def _mtime(path: Path) -> Optional[str]:
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds") if path.exists() else None


def _segments(ids: pd.Index, seg: Optional[pd.Series]) -> dict:
    if seg is None:
        return {}
    return {str(k): int(v) for k, v in seg.reindex(ids).fillna("unknown").value_counts().sort_index().items()}


def summarize(src_dir: Path, data_source: str = "sandbox_5k", segment_key: str = "risk_band",
              trace_id: str = "ACC-PERSONA-22", lang: Optional[str] = None, label: str = "churn_90d",
              features_path: Optional[Path] = None) -> dict:
    fpath = features_path or (src_dir / ("features.csv" if src_dir != OUT else DATA_SOURCES[data_source]["features"]))
    spath, opath, cpath = src_dir / "churn_scores.csv", src_dir / "offers.csv", src_dir / "offer_candidates.csv"
    if data_source != "sandbox_5k" and src_dir == OUT:
        # canonical out/ only has Model A scores / offers for the 5k sandbox
        spath, opath, cpath = src_dir / "_none_", src_dir / "_none_", src_dir / "_none_"
    f = _read(fpath)
    if f is None:
        raise FileNotFoundError(f"features not found at {fpath}")
    f = f.set_index("account_id")
    sc = _read(spath)
    sc = sc.set_index("account_id") if sc is not None else None
    off = _read(opath)
    off = off.set_index("account_id") if off is not None else None
    cand = _read(cpath)
    msgs = _messages_module()

    # segments
    seg, seg_note = None, None
    if segment_key == "risk_band":
        if sc is not None:
            n = len(sc)
            rk = sc["risk_rank"] if "risk_rank" in sc else sc["p_churn_90d"].rank(ascending=False, method="first")
            seg = pd.Series(np.where(rk <= math.ceil(0.10 * n), "high",
                                     np.where(rk <= math.ceil(0.30 * n), "medium", "low")), index=sc.index)
        else:
            seg_note = "risk_band needs Model A scores"
    elif segment_key == "family_plan":
        col = next((c for c in FAMILY_PLAN_COLS if c in f.columns), None)
        if col:
            seg = f[col].astype(str)
        else:
            seg_note = "family_plan: tm-data's household fields are not in features.csv yet"
    else:
        raise ValueError("segment_key must be risk_band or family_plan")

    def stage(sid, count, ids=None, **extra):
        lab = dict(STAGE_LABELS)[sid]
        d = {"id": sid, "label": lab, "count": count,
             "by_segment": _segments(ids, seg) if (ids is not None and count is not None) else {}}
        if seg_note and count is not None:
            d["segment_note"] = seg_note
        d.update(extra)
        return d

    stages = []
    all_ids = f.index
    stages.append(stage("accounts", int(len(all_ids)), all_ids, source=str(fpath), source_mtime=_mtime(fpath)))
    if sc is not None:
        scored = sc.index[sc["p_churn_90d"].notna()]
        stages.append(stage("scored", int(len(scored)), scored, source=str(spath), source_mtime=_mtime(spath)))
    else:
        scored = None
        stages.append(stage("scored", None, note="Model A scores (churn_scores.csv) not available for this data source"))

    flagged = None
    if sc is not None:
        n = len(sc)
        rk = sc["risk_rank"] if "risk_rank" in sc else sc["p_churn_90d"].rank(ascending=False, method="first")
        top = set(sc.index[rk <= math.ceil(FLAG_TOP_FRAC * n)])
        if off is not None and "upgrade_moment" in off:
            um = set(off.index[off["upgrade_moment"].astype(bool)])
            flagged = pd.Index(sorted(top | um))
            stages.append(stage("flagged", int(len(flagged)), flagged, rule=FLAG_RULE, top_risk=len(top),
                                upgrade_moment=len(um), overlap=len(top & um)))
        else:
            stages.append(stage("flagged", None, rule=FLAG_RULE,
                                note="upgrade moments come from the EV engine (offers.csv), not available here"))
    else:
        stages.append(stage("flagged", None, rule=FLAG_RULE, note="needs Model A scores"))

    offered_ids = None
    if flagged is not None and off is not None:
        act = off.loc[flagged, "action"].astype(str)
        is_wait = act.str.strip().str.lower().eq("do nothing")
        offered_ids, wait_ids = flagged[~is_wait.values], flagged[is_wait.values]
        stages.append(stage("offered", int(len(offered_ids)), offered_ids,
                            by_action={k: int(v) for k, v in act[~is_wait].value_counts().items()},
                            source=str(opath), source_mtime=_mtime(opath)))
        stages.append(stage("wait", int(len(wait_ids)), wait_ids))
    else:
        note = "EV offer engine output (offers.csv) not available for this data source"
        stages.append(stage("offered", None, note=note, by_action={}))
        stages.append(stage("wait", None, note=note))

    def acct_lang(aid):
        v = str(f.at[aid, "language"]) if "language" in f.columns and aid in f.index else "en"
        return "es" if v == "es" else "en"

    if offered_ids is not None and msgs is not None:
        texts = {}
        for aid in offered_ids:
            lg = acct_lang(aid)
            t = msgs.render_message(_action_key(off, aid), lg, _clean(f.at[aid, "tenure_months"]) if aid in f.index else None)
            if t:
                texts[aid] = lg
        ids = pd.Index(list(texts))
        bl = {"en": sum(1 for v in texts.values() if v == "en"), "es": sum(1 for v in texts.values() if v == "es")}
        no_tpl = int(len(offered_ids) - len(ids))
        extra = {"by_language": bl, "source": "app/messages.py render_message (deterministic templates)"}
        if no_tpl:
            extra["note"] = f"{no_tpl} offered accounts have no message template for their action"
        stages.append(stage("messaged", int(len(ids)), ids, **extra))
    else:
        stages.append(stage("messaged", None, by_language={"en": None, "es": None},
                            note="needs offers (EV engine) and app/messages.py"))

    # ---------------------------------------------------------------- trace
    trace = {"account_id": trace_id}
    if trace_id in f.index:
        row = f.loc[trace_id]
        trace["signals"] = [{"name": k, "value": _clean(row[k]), "source": s} for k, s in SIGNALS.items() if k in f.columns]
    else:
        trace["signals"] = []
        trace["note"] = f"{trace_id} not in this data source"
    if sc is not None and trace_id in sc.index:
        r = sc.loc[trace_id]
        reg = sc.loc[~sc.index.str.startswith("ACC-PERSONA-"), "p_churn_90d"]
        p = float(r["p_churn_90d"])
        trace["score"] = {"p_churn_90d": p,
                          "percentile": round(float((reg < p).mean() * 100 + (reg == p).mean() * 50), 1),
                          "risk_reasons": [str(r[c]) for c in ("risk_reason_1", "risk_reason_2", "risk_reason_3")
                                           if c in r and isinstance(r[c], str) and r[c]],
                          "stay_reasons": [str(r[c]) for c in ("stay_reason_1", "stay_reason_2", "stay_reason_3")
                                           if c in r and isinstance(r[c], str) and r[c]]}
    else:
        trace["score"] = None
    chosen = None
    if cand is not None and trace_id in set(cand["account_id"]):
        cc = cand[cand["account_id"] == trace_id]
        chosen_rows = cc[cc["is_chosen"].astype(bool)]
        chosen = str(chosen_rows["action"].iloc[0]) if len(chosen_rows) else None
        trace["offer"] = {"candidates": [{"action": str(a), "ev": _clean(e), "eligible": bool(el)}
                                         for a, e, el in zip(cc["action"], cc["expected_value"], cc["eligible"])],
                          "chosen": chosen}
    else:
        trace["offer"] = None
    if chosen is not None and msgs is not None:
        lg = lang or acct_lang(trace_id)
        ten = _clean(f.at[trace_id, "tenure_months"]) if trace_id in f.index else None
        key = _action_key(off, trace_id) if off is not None and trace_id in off.index else chosen
        trace["message"] = {"language": lg, "text": msgs.render_message(key, lg, ten)}
    else:
        trace["message"] = None

    out = {"synthetic": True, "caveat": CAVEAT,
           "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
           "data_source": data_source, "label": label, "segment_key": segment_key,
           "stages": stages, "trace": trace}
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
        d = summarize(rd, a.data, a.segment, a.trace, a.lang, features_path=rd / "features.csv")
    else:
        d = summarize(OUT, a.data, a.segment, a.trace, a.lang)
    Path(a.out).write_text(json.dumps(d, indent=2, ensure_ascii=False))
    for s in d["stages"]:
        print(f"{s['id']:<9} {s['label']:<20} {s['count']!s:>6}  {s.get('note', '')}")
    print(f"wrote {a.out}  [SYNTHETIC]")
    return d


if __name__ == "__main__":
    main()
