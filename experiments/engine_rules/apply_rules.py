"""Post-process the engine's per-account offers with the three engine rules and join the result on account_id.
Does NOT edit or import-patch harness/offers.py (tm-offers owns it); it reads the engine's outputs read-only.
ALL NUMBERS SYNTHETIC (comment only; no emitted value carries that label).

Adds: contact_ok, block_reason, why_line (rule 1), timing, wait_until (rule 2), holdout, holdout_note (rule 3),
and text_send = when a text actually goes out ('now', an ISO date for a wait, or '' = no text).

Run from the repo root:
    python3 -m experiments.engine_rules.apply_rules                         # shipped demo_data, scratch-parity mode
    python3 -m experiments.engine_rules.apply_rules --engine-dir $TM_OUT_DIR --policy engine --save-rate-scale 1 --value-scale 1 --tag v2engine
Writes experiments/engine_rules/out/<tag>/{offers_with_rules.csv, guardrail.csv, guardrail_detail.csv, summary.json}.
"""
from __future__ import annotations
import argparse, json, os, sqlite3, sys
from datetime import date
from pathlib import Path
import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2])); __package__ = "experiments.engine_rules"
from . import guardrail_rule as GR, timing_rule as TR, holdout_rule as HR

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RULE_COLS = ["contact_ok", "block_reason", "why_line", "timing", "wait_until", "holdout", "holdout_note", "text_send"]


def _db_path(arg=None):
    for c in (arg, os.environ.get("DUBHACKS_DB"), os.environ.get("TM_SANDBOX_DB"),
              REPO / "vendor" / "dubhacks" / "data" / "sandbox.db", REPO.parent / "dubhacks" / "data" / "sandbox.db"):
        if c and Path(c).is_file():
            return str(Path(c).resolve())
    raise FileNotFoundError("sandbox.db not found; set DUBHACKS_DB")


def connect_ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)     # never writes sandbox.db


def _read(d: Path, name):
    for n in (name, name + ".gz"):
        if (d / n).exists():
            return pd.read_csv(d / n)
    raise FileNotFoundError(d / name)


def run(engine_dir=REPO / "demo_data", policy="retention10", save_rate_scale="auto", rule="new",
        value_scale=GR.V_SCALE_1478, db=None, weekly=None, churn_oof=None, holdout_share=HR.HOLDOUT_SHARE):
    engine_dir = Path(engine_dir)
    offers = _read(engine_dir, "offers.csv").set_index("account_id")
    cand = _read(engine_dir, "offer_candidates.csv")
    feats = _read(engine_dir if (engine_dir / "features.csv").exists() else REPO / "demo_data", "features.csv") \
        .set_index("account_id").reindex(offers.index)
    con = connect_ro(_db_path(db))
    sandbox = GR.load_sandbox(con); con.close()
    as_of = date.fromisoformat(str(sandbox[0].date()))
    pc = HERE / "proactive_contacts.csv"
    G, gsum = GR.run_guardrail(feats, offers, cand, sandbox,
                               GR.GuardrailConfig(rule=rule, value_scale=value_scale,
                                                  save_rate_scale=save_rate_scale, policy=policy),
                               proactive_contacts=pd.read_csv(pc) if pc.exists() else None)
    # timing (rule 2): moments decision inputs; unscored accounts (42 personas) are 'silent'
    weekly = pd.read_csv(TR.DATA / "weekly_candidates_12w.csv.gz") if weekly is None else weekly
    churn_oof = pd.read_csv(REPO / "demo_data" / "churn_oof_pred.csv") if churn_oof is None else churn_oof
    acct = TR.decision_accounts(churn_oof, offers, feats)
    T = TR.run_timing(weekly, acct, offers.index, as_of)
    R = G.merge(T, on="account_id", how="left", validate="1:1")
    R["holdout"] = HR.assign_holdout(R.account_id, R.contact_ok, share=holdout_share).values
    R["holdout_note"] = R.holdout.map({True: HR.HOLDOUT_NOTE, False: ""})
    # a text goes out only for contact_ok, not held out; default now, a dated wait if the timing rule says so
    send = R.contact_ok & ~R.holdout
    R["text_send"] = ""
    R.loc[send, "text_send"] = R.loc[send].apply(lambda r: r.wait_until if r.timing == "wait" else "now", axis=1)
    assert not (R.holdout & (R.text_send != "")).any(), "a held-out account would get a text"
    assert not (R.holdout & ~R.contact_ok).any()
    # the engine's own data_note column carries a data label; David's rule keeps it out of product output, so it
    # is dropped here (offers.csv itself is tm-offers' file and is left as is)
    drop = [c for c in RULE_COLS + ["data_note"] if c in offers.columns]
    out_offers = offers.reset_index().drop(columns=drop) \
        .merge(R[["account_id"] + RULE_COLS], on="account_id", how="left", validate="1:1")
    # engine text columns (e.g. reason "... = $665.05 (synthetic).") carry the data label; strip it from our output
    for c in out_offers.columns:
        if out_offers[c].dtype == object or str(out_offers[c].dtype).startswith("str"):
            v = out_offers[c].astype("string")
            if v.str.contains("synthetic", case=False, na=False).any():
                out_offers[c] = v.str.replace(r"\s*\([^()]*synthetic[^()]*\)", "", regex=True, case=False) \
                                 .str.replace(r"(?i)\s*synthetic(/simulated)?", "", regex=True).astype(object)
    ok = R[R.contact_ok]
    summary = dict(guardrail=gsum,
                   timing={k: int(v) for k, v in R.timing.value_counts().items()},
                   timing_scored_accounts=int(R.timing_scored.sum()),
                   timing_wait_by_action={k: int(v) for k, v in R[R.timing == "wait"].timing_action.value_counts().items()},
                   timing_wait_dates={k: int(v) for k, v in R[R.timing == "wait"].wait_until.value_counts().items()},
                   timing_among_contact_ok={k: int(v) for k, v in ok.timing.value_counts().items()},
                   holdout_share=holdout_share, holdout_seed=HR.SEED, holdout=int(R.holdout.sum()),
                   texts_sent=int((R.text_send != "").sum()),
                   text_send={k: int(v) for k, v in R[R.text_send != ""].text_send.value_counts().items()},
                   engine_dir=str(engine_dir), as_of=str(as_of))
    return out_offers, R, summary


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine-dir", default=str(REPO / "demo_data"))
    ap.add_argument("--policy", default="retention10", choices=["retention10", "engine"])
    ap.add_argument("--save-rate-scale", default="auto")
    ap.add_argument("--rule", default="new", choices=["new", "old"])
    ap.add_argument("--value-scale", type=float, default=GR.V_SCALE_1478,
                    help="1.0 when the engine's customer_value_usd is already on the $1,478 basis (tm-offers a20b2dd+)")
    ap.add_argument("--db", default=None)
    ap.add_argument("--tag", default="demo")
    a = ap.parse_args(argv)
    srs = a.save_rate_scale if a.save_rate_scale == "auto" else float(a.save_rate_scale)
    O, R, S = run(a.engine_dir, a.policy, srs, a.rule, value_scale=a.value_scale, db=a.db)
    out = HERE / "out" / a.tag; out.mkdir(parents=True, exist_ok=True)
    O.to_csv(out / "offers_with_rules.csv", index=False)
    R[["account_id"] + RULE_COLS].to_csv(out / "guardrail.csv", index=False)   # names read by tm-offers guardrail_join
    R.to_csv(out / "guardrail_detail.csv", index=False)
    (out / "summary.json").write_text(json.dumps(S, indent=1, default=str))
    print(json.dumps(S, indent=1, default=str))


if __name__ == "__main__":
    main()
