"""v2 merge round: kept value, port-out switch, forced fix-first, limited-time receipt, one decision. SYNTHETIC."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
import offers as eng  # noqa: E402
import one_decision as od  # noqa: E402
import guardrail_join as gj  # noqa: E402

C = eng.CONFIG
OUT = Path(os.environ.get("TM_OUT_DIR", ROOT / "harness" / "out"))


def test_defaults():
    assert abs(C["KEPT_VALUE_MONTHS"] - 19.338) < 1e-9 and C["VALUE_HORIZON_MONTHS"] == 24
    assert C["PORT_OUT_CONTACT"] == "all" and C["PORT_OUT_SIGNAL_ORIGIN"] == "self_initiated"
    assert C["FIX_FIRST_FORCE"] == "ev_positive"


def test_port_out_modes(monkeypatch):
    for m, ok in (("off", False), ("self_initiated_only", True), ("all", True)):
        monkeypatch.setitem(C, "PORT_OUT_CONTACT", m)
        assert eng.port_out_allowed() is ok
    monkeypatch.setitem(C, "PORT_OUT_CONTACT", "self_initiated_only")
    monkeypatch.setitem(C, "PORT_OUT_SIGNAL_ORIGIN", "carrier_port_request")
    assert eng.port_out_allowed() is False          # FCC 2008: never on another carrier's port request
    monkeypatch.setitem(C, "PORT_OUT_CONTACT", "bogus")
    with pytest.raises(AssertionError):
        eng.port_out_allowed()


def _res(**ev):
    base = {a: {"eligible": False, "ev": 0.0} for a in eng.ACTIONS}
    for a, v in ev.items():
        base[a] = {"eligible": True, "ev": v}
    return base


def test_open_ticket_fix_first_only(monkeypatch):
    r = _res(perk_reminder=3.0, step_up=9.0, fix_first=-4.0, care_credit_fix_first=-6.0)
    assert eng.pick(r)[0] == "step_up"
    # ev_positive (default): fix-first is the only allowed type; EV <= 0 -> silent with its own reason
    a, ev, _, _ = eng.pick(r, open_ticket=True)
    assert a == "do_nothing" and eng.PICK_OVERRIDE[0] == "open_ticket_ev_le0"
    a, ev, _, _ = eng.pick(_res(step_up=9.0, fix_first=2.0, care_credit_fix_first=5.0), open_ticket=True)
    assert a == "care_credit_fix_first" and ev == 5.0 and eng.PICK_OVERRIDE[0] == "open_ticket_fix_only"
    # all_open: forced even at EV <= 0
    monkeypatch.setitem(C, "FIX_FIRST_FORCE", "all_open")
    a, ev, _, _ = eng.pick(r, open_ticket=True)
    assert a == "fix_first" and ev == -4.0 and eng.PICK_OVERRIDE[0] == "open_ticket"
    monkeypatch.setitem(C, "FIX_FIRST_FORCE", "nope")
    with pytest.raises(AssertionError):
        eng.pick(r, open_ticket=True)


def test_port_out_open_ticket_save_attempt_is_fix_first(monkeypatch):
    monkeypatch.setitem(C, "PORT_OUT_CONTACT", "all")
    r = _res(check_in=-1.0, fix_first=-4.0)
    a, _, _, _ = eng.pick(r, port_out=True, open_ticket=True)
    assert a == "fix_first" and eng.PICK_OVERRIDE[0] == "port_out"
    a, _, _, _ = eng.pick(r, port_out=True)
    assert a == "check_in" and eng.PICK_OVERRIDE[0] == "port_out"


def test_receipt_limited_time(monkeypatch):
    monkeypatch.setattr(eng, "PLAN_STATUS", {"TMO-STUB-PLAN-ESSENTIALS-4LINE": "limited_time", "X": "current"})
    r = _res()
    r["variant_switch"] = {"eligible": True, "ev": 1.0, "save": 20.0, "skus": "TMO-STUB-PLAN-ESSENTIALS-4LINE"}
    it = eng.receipt_item(r)
    assert it["receipt_limited_time"] and "Limited-time plan" in it["receipt_reason"] and it["receipt_plan_end_date"] == ""
    r["variant_switch"]["skus"] = "X"
    assert not eng.receipt_item(r)["receipt_limited_time"]


def _toy():
    o = pd.DataFrame({"account_id": ["A", "B", "C", "D", "E", "F"],
                      "action_code": ["perk_reminder", "fix_first", "do_nothing", "do_nothing", "check_in", "check_in"],
                      "expected_value": [2.0, 3.0, 0.0, 0.0, 1.0, -1.0], "p_churn_90d": [.1] * 6,
                      "customer_value_usd": [1000.0] * 6, "pick_override": [""] * 5 + ["port_out"],
                      "already_leaving_save_attempt": [""] * 5 + ["already leaving, one save attempt: check-in"]})
    cands = pd.DataFrame({"account_id": ["A", "A", "B", "E", "F"],
                          "action_code": ["perk_reminder", "care_credit", "fix_first", "check_in", "check_in"],
                          "eligible": ["True"] * 5, "expected_value": [2.0, 1.5, 3.0, 1.0, -1.0],
                          "save_rate": [.01, .02, .03, .01, .01], "offer_cost": [.5, 25, 15, 2, 2],
                          "annoyance": [0, 1, 1, 1, 1]})
    return o, cands


def test_one_decision_bill_rule_without_guardrail(monkeypatch):
    o, cands = _toy()
    g = pd.DataFrame({"account_id": list("ABCDEF"), "blocking_bill_change": [True, True] + [False] * 4})
    monkeypatch.setattr(od, "receipt_sets", lambda: {"strict": {"C"}, "lose_x": set(), "source": []})
    mom = pd.DataFrame({"account_id": ["E"], "decision": ["wait_until"], "wait_months": [1]})
    r = od.decide(o, cands, mom, g).set_index("account_id")
    assert r.loc["A", "final_action"] == "care_credit" and r.loc["A", "bill_rule_note"] == "swapped_to_offsetting_credit"
    assert r.loc["B", "final_action"] == "fix_first"          # fix-only callbacks pass the bill rule
    assert list(r.decision) == ["text_now", "text_now", "receipt_only", "silent", "wait_until 2026-11-01",
                                "already_leaving"]
    assert list(r.in_headline) == [True, True, False, False, True, False]


def test_one_decision_guardrail_gates_every_contact(monkeypatch):
    o, cands = _toy()
    g = pd.DataFrame({"account_id": list("ABCDEF"), "contact_ok": [True, False, False, False, True, True],
                      "block_reason": ["", "bill_change_no_fix", "receipt_only_plan_move", "not_worth_contacting",
                                       "", ""],
                      "timing": ["now", "now", "silent", "silent", "wait", "now"],
                      "wait_until": ["", "", "", "", "2026-11-05", ""],
                      "holdout": [True, False, False, False, False, False]})
    monkeypatch.setattr(od, "receipt_sets", lambda: {"strict": {"C"}, "lose_x": set(), "source": []})
    monkeypatch.delenv("TM_HOLDOUT", raising=False)
    r = od.decide(o, cands, None, g).set_index("account_id")
    assert list(r.decision) == ["text_now", "silent", "receipt_only", "silent", "wait_until 2026-11-05",
                                "already_leaving"]
    assert r.loc["B", "blocked_by_guardrail"] and r.loc["B", "final_action"] == "do_nothing"
    assert r.loc["A", "holdout_flag"] and r.loc["A", "decision"] == "text_now"   # holdout: flag only by default
    assert "tmm_contact_ok" in r.columns and "tmm_block_reason" in r.columns    # join point
    monkeypatch.setenv("TM_HOLDOUT", "0.2")
    r = od.decide(o, cands, None, g).set_index("account_id")
    assert r.loc["A", "decision"] == "silent (holdout)"


def test_engine_rules_hook_never_breaks_offers(monkeypatch, tmp_path, capsys):
    monkeypatch.setitem(sys.modules, "experiments.engine_rules.apply_rules", None)   # import fails
    assert eng.run_engine_rules(tmp_path) is False
    assert "WARNING: engine rules skipped" in capsys.readouterr().out


@pytest.fixture(scope="module")
def offers():
    if not (OUT / "offers.csv").exists():
        pytest.skip("run harness/offers.py first")
    o = pd.read_csv(OUT / "offers.csv")
    if "in_headline" not in o:
        pytest.skip("offers.csv predates this round")
    return o


def test_port_out_never_in_headline(offers):
    f = pd.read_csv(OUT / "features.csv", usecols=["account_id", "port_out_inquiry"])
    po = offers.merge(f, on="account_id").query("port_out_inquiry == 1")
    assert not po.in_headline.astype(bool).any()
    if not eng.port_out_allowed():
        assert (po.action_code == "do_nothing").all() and (po.already_leaving_save_attempt.fillna("") == "").all()
    else:   # every port-out inquiry gets exactly one save attempt on its own line
        sa = po[po.action_code != "do_nothing"]
        assert (sa.already_leaving_save_attempt.str.startswith("already leaving, one save attempt")).all()
        assert (sa.channel == "save_attempt").all()


def test_open_ticket_only_fix_first(offers):
    f = pd.read_csv(OUT / "features.csv", usecols=["account_id", "unresolved_90d"])
    t = offers.merge(f, on="account_id").query("unresolved_90d >= 1")
    assert t.action_code.isin(["do_nothing", "fix_first", "care_credit_fix_first"]).all()
    if C["FIX_FIRST_FORCE"] == "ev_positive":
        hl = t[t.in_headline.astype(bool)]
        assert (hl.expected_value > 0).all()
        s = t[t.do_nothing_reason == "open_ticket_ev_le0"]
        assert (s.why_this_offer == "Stay silent: open ticket, fix-first expected to cost more than it saves.").all()


def test_limited_time_receipts_are_4_line(offers):
    lim = offers[offers.receipt_limited_time.astype(bool)]
    assert lim.receipt_skus.str.contains("ESSENTIALS-4LINE").all()
    assert lim.receipt_reason.str.contains("Limited-time plan").all()


def test_decision_column_if_present(offers):
    if "decision" not in offers:
        pytest.skip("one_decision.py not run on this output")
    k = offers.decision.str.split(" ").str[0]
    assert set(k) <= {"text_now", "wait_until", "receipt_only", "silent", "already_leaving"}
    assert (offers.loc[k == "silent", "final_action"] == "do_nothing").all()
    if "tmm_contact_ok" in offers:   # guardrail gates every contact
        sent = k.isin(["text_now", "wait_until", "already_leaving"])
        assert offers.loc[sent, "tmm_contact_ok"].astype(bool).all()


OUR_COLS = ["account_id", "decision", "channel", "decided_by_rule", "decision_reason", "offer_label", "offer_cost_usd",
            "customer_saves_usd_mo", "receipt_line", "receipt_kind", "receipt_tradeoff_line", "message_en", "message_es"]


def _decisions():
    p = OUT / "decisions.csv"
    if not p.exists():
        pytest.skip("decisions.csv not generated for this output")
    return pd.read_csv(p, keep_default_na=False), pd.read_csv(OUT / "options.csv", keep_default_na=False)


def test_decisions_file():
    import decisions_out as dout
    d, _ = _decisions()
    assert list(d.columns[:len(OUR_COLS)]) == OUR_COLS
    assert len(d) == 5042 and d.account_id.is_unique
    assert set(d.decision) <= {"message", "receipt_only", "silent"}
    assert set(d.channel) <= {"text", "in_app", "email", "call", "bill", "none"}
    msg = d.decision == "message"
    assert msg.sum() == 184                       # contact set = the policy guardrail's contact_ok accounts
    assert (d.loc[d.decision == "receipt_only", "channel"] == "bill").all()
    assert (d.loc[d.decision == "silent", "channel"] == "none").all()
    assert (d.loc[~msg, "message_en"] == "").all() and (d.loc[msg, "message_en"] != "").all()
    assert (d.loc[d.receipt_kind == "clean", "receipt_line"] != "").all()
    assert (d.loc[d.receipt_kind == "tradeoff", "receipt_line"] == "").all()
    assert (d.loc[d.receipt_kind == "tradeoff", "receipt_tradeoff_line"].str.contains("but you'd lose")).all()
    assert set(d.loc[d.decision == "receipt_only", "receipt_kind"]) <= {"clean", "tradeoff"}
    assert set(d.decided_by_rule.astype(int)) <= {1, 2, 3, 4, 5, 6}
    strict = set(pd.read_csv(dout.STRICT_RECEIPT).account_id)     # strict bill-line rule: 394 like-for-like, nothing lost
    ro = set(d.account_id[d.decision == "receipt_only"])
    trade = set(pd.read_csv(dout.TRADEOFF_RECEIPT).account_id)  # "cheaper but you'd lose X": 110, still on the bill
    assert len(strict) == 394 and len(trade) == 110 and not (strict & trade)
    assert ro == (strict | trade) - set(d.account_id[msg])
    if "already_leaving_note" in d.columns:
        al = msg & (d.already_leaving.astype(str) == "True")
        assert (d.loc[al, "already_leaving_note"] == dout.AL_NOTE_OPEN).sum() >= al.sum() - 1
    assert not d.loc[d.decision == "silent", "decision_reason"].str.contains("cheaper plan is on your bill").any()
    for c in dout.TEXT_COLS:
        assert not d[c].astype(str).str.contains(dout.FORBIDDEN).any(), c
    # channel vs promise: only agent-call rows may promise a call
    for c in ("message_en", "message_es", "offer_label"):
        assert not ((d.channel != "call") & d[c].astype(str).str.contains(dout.CALL_PROMISE)).any(), c
    for c in [c for c in dout.MONEY_TEXT_COLS if c in d.columns]:   # 'Show money' off: no company money in text
        assert not d[c].map(dout.company_money).any(), c
    if "guardrail_result" in d.columns:           # tm-models' ledger joined: their pass set == our message set
        assert ((d.guardrail_result == "pass") == msg).all()


def test_options_file():
    d, o = _decisions()
    assert set(o.account_id) == set(d.account_id)
    assert (o.groupby("account_id").head(1).option_label == "Do nothing").all()
    assert set(o.verdict) <= {"picked", "not_sent", "ruled_out"}
    assert (o.loc[o.verdict == "ruled_out", "net_mid_usd"].astype(str) == "").all()
    assert (o[o.verdict == "picked"].groupby("account_id").size() == 1).all()
    import decisions_out as dout
    assert not o.reason.map(dout.company_money).any()


def test_fix_first_wording_templates():
    import decisions_out as dout
    for ch in ("text", "in_app", "email"):
        for t in (dout.FIX_EN[ch], dout.FIX_ES[ch]):
            assert not dout.CALL_PROMISE.search(t), (ch, t)
            assert not dout.PERK.search(t)
    assert "Reply STOP" in dout.FIX_EN["text"] and "STOP" in dout.FIX_ES["text"]
    assert dout.no_call("A specialist can call you to fix it at a time that works for you.") == \
        "Our team is working on your open request."
    assert not dout.FORBIDDEN.search("We value a saved account at its own monthly margin times 19.3 months.")
    assert dout.FORBIDDEN.search("a flat $1,478 per account")
    assert dout.company_money("Expected net $42") and dout.company_money("same $25 credit plus the explanation")
    assert not dout.company_money("Your bill went up $26.85 when a promo ended. Saves you $8/mo.")


def test_reasons_plain_short():
    import decisions_out as dout
    d, o = _decisions()
    for c in [c for c in ("decision_reason", "guardrail_note") if c in d.columns]:
        assert not [s for s, ch in zip(d[c], d.channel) if dout.reason_problem(s, ch == "call")], c
    assert not o.reason.map(dout.reason_problem).astype(bool).any()
    assert not o.reason.str.contains(r"(?i)callback|_|port-out|top driver").any()
    picked = o[o.verdict == "picked"].merge(d[["account_id", "channel"]], on="account_id")
    assert not picked[(picked.channel != "call") & picked.option_label.str.contains("callback")].any().any()
    assert dout.reason_problem("no child/teen line (lines.member_role)")
    assert dout.reason_problem("fix-first callback: worth it.", call_ok=False)
