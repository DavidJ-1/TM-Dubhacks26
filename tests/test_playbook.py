"""Targeting playbook: rule order, traps, one action, no stacking, frequency cap."""

from datetime import date

import pytest

from harness.config import db_path
from harness.engine import build_console
from harness.playbook.build import build_playbook
from harness.playbook.decide import decide
from harness.playbook.rules import RULES
from harness.playbook.segments import value_score
from harness.playbook.send import clear_ledger, frequency_open, record_send


@pytest.fixture(scope="module")
def console():
    return build_console(db_path())


@pytest.fixture(scope="module")
def playbook(console):
    return build_playbook(console)


def _ctx(console, playbook, account_id: str) -> dict:
    detail = console.account(account_id)
    row = playbook.frame.set_index("account_id").loc[account_id]
    return {
        "account": dict(detail),
        "lines": detail["lines"],
        "promos": console.promos,
        "catalog_plans": [],
        "device_names": {},
        "curves": None,
        "candidates": [],
        "moment": detail.get("moment"),
        "unresolved_90d": 0,
        "risk_band": row["risk_band"],
        "value_band": row["value_band"],
        "assumption_credit_cents": 2500,
    }


def test_value_formula_uses_bill_lines_and_tenure():
    assert value_score(10_000, 1, 60) == 10_000
    assert value_score(10_000, 3, 60) == 12_000
    assert value_score(10_000, 1, 0) == 0


def test_rule_order_is_the_config_order():
    assert [rule["id"] for rule in RULES] == [
        "fix_first",
        "retention",
        "explain_bill",
        "plan_fit",
        "upgrade_timing",
        "promo_expired",
        "do_nothing",
    ]


def test_unresolved_support_wins_over_port_out(console, playbook):
    ctx = _ctx(console, playbook, "ACC-PERSONA-21")
    ctx["unresolved_90d"] = 2
    ctx["account"]["port_out_inquiry"] = 1
    decision = decide(ctx)
    assert decision["action"] == "FIX-FIRST"
    assert decision["promo_skus"] == []
    assert decision["rule_id"] == "fix_first"


def test_grid_covers_every_account_and_names_the_priority_cell(playbook):
    assert int(playbook.grid["accounts"].sum()) == len(playbook.frame)
    priority = playbook.grid.loc[playbook.grid["priority"]]
    assert len(priority) == 1
    assert priority.iloc[0]["risk_band"] == "top_10"
    assert priority.iloc[0]["value_band"] == "high"
    assert priority.iloc[0]["accounts"] > 0


def test_every_account_has_one_action_and_no_stacked_promos(console, playbook):
    assert len(playbook.decisions) == len(console.details)
    for decision in playbook.decisions.values():
        assert decision["action"]
        assert len(decision["promo_skus"]) <= 1
        assert decision["stacked_promos"] is False


def test_traps_hold(playbook):
    assert playbook.decision("ACC-PERSONA-24")["action"] == "DO NOTHING"
    assert "nothing would help" in playbook.decision("ACC-PERSONA-24")["message_en"]
    for account_id in ("ACC-PERSONA-07", "ACC-PERSONA-31"):
        decision = playbook.decision(account_id)
        assert decision.get("upgrade_outcome") != "now"
        assert decision["promo_skus"] == [] or decision["action"] != "UPGRADE TIMING"


def test_low_value_does_not_get_an_assumption_credit(console, playbook):
    ctx = _ctx(console, playbook, "ACC-PERSONA-21")
    ctx["promos"] = []
    ctx["value_band"] = "low"
    ctx["risk_band"] = "top_10"
    ctx["account"]["port_out_inquiry"] = 1
    ctx["account"]["account_id"] = "ACC-NOT-A-TRAP"
    decision = decide(ctx)
    assert decision["offer_is_assumption"] is False
    assert decision["offer_name"] == "None"


def test_low_risk_reoffer_is_not_a_discount(console, playbook):
    ctx = _ctx(console, playbook, "ACC-PERSONA-10")
    ctx["risk_band"] = "rest"
    ctx["unresolved_90d"] = 0
    ctx["account"]["port_out_inquiry"] = 0
    ctx["account"]["bill_increase_pct"] = 0
    ctx["account"]["promo_expired_recent"] = 1
    ctx["account"]["account_id"] = "ACC-NOT-A-TRAP"
    ctx["lines"] = []
    ctx["moment"] = None
    decision = decide(ctx)
    assert decision["promo_skus"] == []
    assert decision["offer_is_assumption"] is False


def test_frequency_cap_blocks_a_second_nudge():
    clear_ledger()
    assert frequency_open("ACC-1", date(2026, 10, 1))
    record_send("ACC-1", date(2026, 10, 1))
    assert frequency_open("ACC-1", date(2026, 10, 20)) is False
    assert frequency_open("ACC-1", date(2026, 10, 31)) is True
    clear_ledger()
