"""Tests for the three engine rules on the shipped demo_data (counts are synthetic; see README.md)."""
import os, sys
from pathlib import Path
import numpy as np, pandas as pd, pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO)); os.environ.setdefault("OMP_NUM_THREADS", "1")
from experiments.engine_rules import apply_rules as A, holdout_rule as HR, timing_rule as TR, events as EV


@pytest.fixture(scope="module")
def run():
    return A.run()


def test_guardrail_counts_match_scratch(run):
    _, R, S = run
    assert len(R) == 5042 and R.account_id.is_unique
    assert S["guardrail"]["contact_ok"] == 184
    assert S["guardrail"]["block_reasons"] == {"not_worth_contacting": 4041, "receipt_only_plan_move": 499,
                                               "bill_change_no_fix": 318, "(contact ok)": 184}
    assert S["guardrail"]["blocking_accounts"] == 562 and S["guardrail"]["bill_change_accounts"] == 1412
    assert abs(S["guardrail"]["contacted_ev"] - 4109.34) < 0.5


def test_guardrail_new_rule_exemptions(run):
    _, R, _ = run
    ok = R[R.contact_ok]
    # fix-only contacts are never blocked by a bill change
    assert not ((R.policy_action == "fix_first") & (R.block_reason == "bill_change_no_fix")).any()
    # a new-phone-only increase never blocks
    assert not ((R.bill_change_reason == "device_installment") & ~R.blocking_bill_change
                & (R.block_reason == "bill_change_no_fix")).any()
    assert set(ok.block_reason) == {""} and (R.contact_ok == (R.block_reason == "")).all()
    assert not ok.policy_action.isin(["right_size", "variant_switch"]).any()      # plan moves: receipt only


def test_why_lines_clean(run):
    _, R, _ = run
    assert (R.why_line.str.len() <= 140).all() and (R.why_line.str.len() > 0).all()
    assert not R.why_line.str.contains(r"income|kid|persona|synthetic|simulated|ACC-|sandbox", case=False).any()


def test_no_synthetic_label_in_emitted_values(run):
    O, R, _ = run
    for df in (O, R[["account_id"] + A.RULE_COLS]):
        for c in df.columns:
            assert not df[c].astype(str).str.contains("synthetic", case=False).any(), c


def test_timing_counts_match_moments_run(run):
    _, R, S = run
    sc = R[R.timing_scored]
    assert len(sc) == 5000
    assert sc.timing.value_counts().to_dict() == {"silent": 4123, "now": 866, "wait": 11}
    assert (R[~R.timing_scored].timing == "silent").all()            # 42 persona accounts have no churn score
    w = R[R.timing == "wait"]
    assert (w.wait_until != "").all() and (R[R.timing != "wait"].wait_until == "").all()
    assert w.wait_until.value_counts().to_dict() == {"2026-11-05": 9, "2026-12-03": 2}
    assert w.timing_action.value_counts().to_dict() == {"care_credit_fix_first": 9, "care_credit": 1, "family_upgrade": 1}


def test_timing_default_is_now_and_caps_hold():
    # toy: account a has only a week-0 option; account b gets a better offer at week 4 (wait); c only negatives
    W = pd.DataFrame([("a", 0, "fix_first", .2, 15., 2., 0., 0.), ("b", 0, "fix_first", .02, 15., 2., 0., 0.),
                      ("b", 4, "care_credit_fix_first", .5, 40., 2., 0., 0.), ("c", 0, "check_in", .0, 5., 2., 0., 0.)],
                     columns=["account_id", "week", "action_code", "save_rate", "cost", "annoyance", "gain", "benefit"])
    acct = pd.DataFrame({"p": [.5, .5, .5], "uq": [.04] * 3, "V0": [80.] * 3, "upsell_blocked": [False] * 3},
                        index=["a", "b", "c"])
    from datetime import date
    T = TR.run_timing(W, acct, ["a", "b", "c", "d"], date(2026, 10, 1)).set_index("account_id")
    assert T.timing.to_dict() == {"a": "now", "b": "wait", "c": "silent", "d": "silent"}
    assert T.wait_until["b"] == "2026-10-29"
    opts = TR.build_options(W, acct, TR.ScheduleConfig())
    assert TR.check_caps(TR.solve(opts, weekly_cap=1))
    with pytest.raises(AssertionError):
        TR.check_caps(pd.concat([opts, opts]))


def test_events_real_fields_only():
    E = EV.build_events(A._db_path(), 12)
    assert (E.simulated == 0).all()
    fwd = E[E.week >= 0].groupby("event_type").size().to_dict()
    assert fwd["payoff"] == 244 and fwd["tenure_6m"] == 201


def test_holdout_deterministic_and_sized(run):
    _, R, S = run
    ids = [f"X-{i:06d}" for i in range(100_000)]
    h = HR.assign_holdout(ids, [True] * len(ids))
    assert abs(h.mean() - 0.20) < 0.005
    assert HR.assign_holdout(ids[::-1], [True] * len(ids)).reindex(ids).equals(h)       # order-free
    assert HR.hash_uniform("ACC-00037") == HR.hash_uniform("ACC-00037")
    assert HR.hash_uniform("ACC-00037", 2026) != HR.hash_uniform("ACC-00037", 2027)
    _, R2, _ = A.run()
    assert R2.holdout.equals(R.holdout)                                                  # rerun-stable
    assert S["holdout"] == int(R.holdout.sum()) == 30 and S["holdout_seed"] == 2026


def test_holdout_only_among_contact_ok_and_never_texted(run):
    O, R, S = run
    assert not (R.holdout & ~R.contact_ok).any()
    assert (R.loc[R.holdout, "text_send"] == "").all()
    assert (R.loc[R.holdout, "holdout_note"] != "").all() and (R.loc[~R.holdout, "holdout_note"] == "").all()
    sent = R.text_send != ""
    assert (sent == (R.contact_ok & ~R.holdout)).all()
    assert S["texts_sent"] == 184 - 30 == int(sent.sum())
    # the joined offers table carries the same columns, one row per account
    assert len(O) == 5042 and O.set_index("account_id").holdout.equals(R.set_index("account_id").holdout)
