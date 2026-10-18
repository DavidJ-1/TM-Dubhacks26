"""Engine checks against the shipped sandbox, not a toy fixture."""

import sqlite3

import pytest

from harness.config import RETENTION_SKUS, db_path
from harness.engine import build_console
from harness.messages import outbound_title
from harness.projections import project


@pytest.fixture(scope="module")
def console():
    return build_console(db_path())


def test_population_matches_sandbox_scoring(console):
    stats = console.stats
    assert stats["accounts"] == 5000
    assert 0.14 <= stats["expected_churn_rate"] <= 0.16
    assert 0.55 <= stats["concentration"]["top_20"]["share_of_expected_churners"] <= 0.67
    support = {row["bin"]: row for row in stats["support_bins"]}
    assert support["0"]["expected_churn"] < 0.08
    assert support["5+"]["expected_churn"] > 0.45
    assert support["5+"]["expected_churn"] > support["0"]["expected_churn"]
    assert stats["port_yes"]["expected_churn"] > stats["port_no"]["expected_churn"]
    assert stats["bill_up"]["expected_churn"] > stats["bill_flat"]["expected_churn"]


def test_support_counts_come_from_the_table(console):
    view = console.account("ACC-PERSONA-04")
    conn = sqlite3.connect(db_path())
    try:
        count = conn.execute(
            """
            SELECT COUNT(*) FROM support_interactions
            WHERE account_id = ? AND interaction_date >= date('2026-10-01', '-90 day')
            """,
            ("ACC-PERSONA-04",),
        ).fetchone()[0]
    finally:
        conn.close()
    assert view["support_90d"] == count
    assert count == 5


def test_model_a_is_explainable_and_separates_personas(console):
    assert console.metrics["holdout_auc"] > 0.75
    assert console.model.coefficients["support_90d"] > 0
    assert console.model.coefficients["tenure_capped"] < 0
    hot = console.account("ACC-PERSONA-04")
    calm = console.account("ACC-PERSONA-10")
    assert hot["model_p"] > 0.4
    assert calm["model_p"] < 0.08
    assert len(hot["leave"]) == 3
    assert len(hot["stay"]) == 3
    assert "support" in hot["leave"][0].lower()


def test_promotions_and_offer_choices(console):
    assert len(console.promos) == 21
    stub = {promo["sku"] for promo in console.promos if promo["source"] == "stub"}
    assert stub == set(RETENTION_SKUS)
    care = console.account("ACC-PERSONA-04")
    assert care["action"]["sku"] == "PROMO-STUB-CARE-CREDIT", care["action"]["why"]
    assert care["action"]["cost_cents"] == 2500
    for account_id in ("ACC-PERSONA-10", "ACC-PERSONA-23", "ACC-PERSONA-24", "ACC-PERSONA-22"):
        view = console.account(account_id)
        assert view["action"]["choice"] == "do_nothing", (account_id, view["action"]["why"])
    happy = console.account("ACC-PERSONA-24")
    assert happy["message"]["text"] is None


def test_upgrade_moment_uses_one_device_promo(console):
    old = console.account("ACC-PERSONA-30")
    moment = old["moment"]
    assert moment is not None
    assert moment["when"] == "now"
    assert moment["promo"]["sku"] == "PROMO-STUB-TRADEIN-ANY"
    assert moment["promo"]["savings_cents"] == 20_000
    assert moment["stacked_promos"] is False
    assert moment["balance_cents"] == 0
    assert moment["net_cents"] == moment["tradein_value_cents"] + 20_000
    assert "modeled" in moment["battery_note"].lower() or "sandbox has no battery" in moment["battery_note"].lower()
    waiting = console.account("ACC-PERSONA-25")
    assert waiting["moment"]["when"] == "wait"
    assert waiting["moment"]["upgrade_eligible"] is False
    assert "12" in waiting["moment"]["headline"]


def test_upgrade_now_is_not_titled_do_nothing(console):
    old = console.account("ACC-PERSONA-30")
    assert old["action"]["choice"] == "do_nothing"
    assert old["moment"]["when"] == "now"
    title = outbound_title(old["action"], old["moment"])
    assert title.startswith("Upgrade now")
    assert "Do nothing" not in title
    assert old["message"]["purpose"] == "upgrade"


def test_money_stays_in_cents_until_display(console):
    view = console.account("ACC-PERSONA-04")
    assert view["last_bill_cents"] > 1000
    owed = [line["financing_balance_cents"] for line in view["lines"]]
    assert any(cents > 100 for cents in owed)


def test_queue_open_button_selects_that_account():
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    script = Path(__file__).resolve().parents[1] / "app" / "console_app.py"
    app = AppTest.from_file(script, default_timeout=120)
    app.run()
    app.session_state["queue_open_click"] = {"row": 1, "label": "Open"}
    app.sidebar.radio[0].set_value("At-risk queue").run()
    assert not app.exception
    assert app.subheader[0].value == "ACC-00301"
    assert app.selectbox[0].value == "ACC-00301"


def test_projections_are_labeled_and_move_with_assumptions(console):
    population = console.frame.loc[console.frame["is_persona"] == 0]
    baseline = project(population, acceptance=0.0, save_given_accept=1.0, upgrade_acceptance=0.0)
    higher = project(population, acceptance=0.5, save_given_accept=1.0, upgrade_acceptance=0.4)
    assert baseline["label"] == "Projected, illustrative assumptions"
    assert baseline["projected_rate"] == pytest.approx(baseline["baseline_rate"])
    assert higher["projected_rate"] < baseline["baseline_rate"]
    assert higher["projected_upgrades"] > 0
    assert higher["targeted_offers"] == baseline["targeted_offers"]
