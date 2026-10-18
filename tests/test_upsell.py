"""Life-moment upsells: seed, rule order, guardrails, and what the screen is allowed to show."""

import ast
from pathlib import Path

import pandas as pd
import pytest

from harness.config import db_path
from harness.engine import build_console
from harness.upsell.build import build_upsell, display_frame
from harness.upsell.config import (
    DISPLAY_COLUMNS,
    DO_NOTHING_ACCOUNTS,
    INCLUDE_SYNTHETIC_DEFAULT,
    SYNTHETIC_BADGE,
    UPGRADE_PUSH_BLOCKED,
)
from harness.upsell.decide import decide
from harness.upsell.signals import generate

ROOT = Path(__file__).resolve().parents[1]


def _ctx(**overrides) -> dict:
    account = {
        "account_id": "ACC-1",
        "segment": "single",
        "discount_group": None,
        "credit_tier": "prime",
        "tenure_months": 40,
        "bill_increase_pct": 0.0,
        "has_home_internet": 0,
        "language": "en",
    }
    account.update(overrides.pop("account", {}))
    ctx = {
        "account": account,
        "lines": [],
        "unresolved_90d": 0,
        "risk_band": "rest",
        "late_payments": 0,
        "near_cap_months": 0,
        "usage_growth": False,
        "growth_detail": "",
        "paid_off_eligible": False,
        "moment": None,
        "student_graduating": False,
        "synthetic_event": None,
        "candidates": {
            "next_plan": {"name": "Experience More", "sku": "MORE", "diff_cents": 2500, "monthly_cents": 9000},
            "better_value": None,
            "standard_plan": None,
            "cheaper_plan": {"name": "Essentials", "sku": "ESS", "diff_cents": -1000, "monthly_cents": 5000},
            "merge_plan": {
                "name": "Essentials",
                "sku": "ESS",
                "diff_cents": 2000,
                "monthly_cents": 8000,
                "current_monthly_cents": 6000,
                "added_lines": 3,
            },
            "kid": {"device_name": "Galaxy A17", "device_sku": "A17", "promo": None, "plan": {"name": "Essentials", "sku": "ESS", "diff_cents": 3500, "monthly_cents": 3500}},
            "device": None,
            "premium_plan": {"name": "Experience More", "sku": "MORE", "diff_cents": 2500, "monthly_cents": 9000},
            "home_internet": {"name": "Home Internet Basic", "sku": "HINT", "monthly_cents": 5000, "promo": None},
            "has_home_internet": False,
            "parental_controls": False,
        },
        "upgrade_blocked_ids": UPGRADE_PUSH_BLOCKED,
    }
    ctx.update(overrides)
    return ctx


def _function_source(path: Path, name: str) -> str:
    source = path.read_text()
    tree = ast.parse(source)
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == name)
    return ast.get_source_segment(source, node) or ""


@pytest.fixture(scope="module")
def upsell():
    return build_upsell(build_console(db_path()))


def test_generator_is_deterministic():
    ids = pd.Series([f"ACC-{i:04d}" for i in range(300)])
    children = {ids.iloc[0], ids.iloc[10]}
    first = generate(ids, children)
    second = generate(ids, children)
    pd.testing.assert_frame_equal(first, second)
    assert set(first["label"]) == {SYNTHETIC_BADGE}
    assert first["synthetic_event"].nunique() >= 1
    assert len(first) < len(ids)


def test_rule_order_cap_beats_a_paid_off_phone():
    decision = decide(_ctx(near_cap_months=2, paid_off_eligible=True), include_synthetic=False)
    assert decision["rule_id"] == "near_cap"
    assert decision["action"] == "PLAN STEP-UP"
    assert decision["diff_cents"] == 2500


def test_usage_growth_does_nothing_before_a_device():
    decision = decide(_ctx(usage_growth=True, growth_detail="data", paid_off_eligible=True), include_synthetic=False)
    assert decision["rule_id"] == "usage_growth"
    assert decision["action"] == "DO NOTHING"
    assert decision["promo_skus"] == []


def test_guardrails_come_before_offers():
    blocked = decide(_ctx(unresolved_90d=2, near_cap_months=3), include_synthetic=False)
    assert blocked["action"] == "RETENTION PLAYBOOK"
    assert blocked["promo_skus"] == []
    poor = decide(_ctx(near_cap_months=3, account={"credit_tier": "subprime"}), include_synthetic=False)
    assert poor["action"] == "NO UPSELL"
    trap = decide(
        _ctx(near_cap_months=3, account={"account_id": next(iter(DO_NOTHING_ACCOUNTS))}),
        include_synthetic=False,
    )
    assert trap["action"] == "DO NOTHING"


def test_toggle_default_hides_tier2_and_the_screen_uses_it():
    assert INCLUDE_SYNTHETIC_DEFAULT is False
    hidden = decide(_ctx(synthetic_event="moving"), include_synthetic=False)
    shown = decide(_ctx(synthetic_event="moving"), include_synthetic=True)
    assert hidden["tier"] != "tier2"
    assert shown["rule_id"] == "moving"
    assert shown["badge"] == SYNTHETIC_BADGE
    page = _function_source(ROOT / "app" / "console_app.py", "upgrades_page")
    assert "INCLUDE_SYNTHETIC_DEFAULT" in page
    assert "With synthetic life-event signals" in page


def test_tier2_stays_out_of_overview_and_projections():
    for name in ("overview", "projections"):
        source = _function_source(ROOT / "app" / "console_app.py", name).lower()
        assert "upsell" not in source
        assert "synthetic" not in source
        assert "life_signals" not in source
        assert "life moment" not in source


def test_screen_and_export_do_not_show_rates():
    page = _function_source(ROOT / "app" / "console_app.py", "upgrades_page").lower()
    for phrase in ("conversion", "uplift", "base rate", "synthetic_share", "% of"):
        assert phrase not in page
    for column in DISPLAY_COLUMNS:
        assert "rate" not in column
        assert "uplift" not in column
    assert "readiness" not in DISPLAY_COLUMNS


def test_satisfied_customer_is_not_sold_to():
    decision = decide(_ctx(), include_synthetic=False)
    assert decision["action"] == "DO NOTHING"
    assert "not a reason to sell" in decision["why"]


def test_message_drafts_do_not_say_cents(upsell):
    import re

    word = re.compile(r"\bcents\b", re.IGNORECASE)
    hits = []
    for decision in list(upsell.real.values()) + list(upsell.with_synthetic.values()):
        for language in ("message_en", "message_es"):
            text = decision[language]
            if word.search(text):
                hits.append((decision["account_id"] if "account_id" in decision else decision["rule_id"], language, text))
    assert hits == []


def test_plan_step_up_draft_is_dollars_in_both_languages():
    decision = decide(_ctx(near_cap_months=2), include_synthetic=False)
    assert "$25.00" in decision["message_en"]
    assert "$25.00" in decision["message_es"]
    assert "cents" not in decision["message_en"].lower()
    assert "cents" not in decision["message_es"].lower()
    assert "Next catalog plan" not in decision["message_es"]
    assert "Siguiente plan del catálogo Experience More" in decision["message_es"]


def test_personas_and_one_offer(upsell):
    assert upsell.decision("ACC-PERSONA-24")["action"] == "DO NOTHING"
    for account_id in ("ACC-PERSONA-07", "ACC-PERSONA-31"):
        decision = upsell.decision(account_id, True)
        assert decision.get("upgrade_outcome") != "now"
        assert decision["promo_skus"] == [] or decision["action"] != "UPGRADE TIMING"
    real = upsell.ranked(False)
    both = upsell.ranked(True)
    assert (real["tier"] == "tier2").sum() == 0
    assert (both["tier"] == "tier2").sum() > 0
    assert set(both.loc[both["tier"] == "tier2", "badge"]) == {SYNTHETIC_BADGE}
    assert upsell.seeded_accounts > int((both["tier"] == "tier2").sum())
    shown = display_frame(both)
    assert "readiness" not in shown.columns
    for decision in list(upsell.real.values()) + list(upsell.with_synthetic.values()):
        assert len(decision["promo_skus"]) <= 1
        assert decision["stacked_promos"] is False
