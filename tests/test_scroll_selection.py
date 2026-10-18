"""Shared customer selection for the scroll page. Pure helpers; no Streamlit run."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import orbit_data as D  # noqa: E402


def test_menu_label_matches_the_dropdown_copy():
    assert D.customer_menu_label("ACC-02363", 0.87, 14200) == "Customer #02363, 87% risk, $142/mo"
    assert D.customer_menu_label("ACC-PERSONA-38", 0.42, 9900) == "Customer 38, 42% risk, $99/mo"
    assert D.customer_menu_label("ACC-00001", 0.015, None) == "Customer #00001, 1.5% risk"
    assert D.format_monthly_bill(float("nan")) is None


def test_customers_sorted_by_risk_highest_first():
    df = pd.DataFrame({"account_id": ["ACC-00002", "ACC-00001", "ACC-00003"], "p_churn_90d": [0.2, 0.9, 0.2]})
    assert D.customers_by_risk(df) == ["ACC-00001", "ACC-00002", "ACC-00003"]
    assert D.customers_by_risk([("a", 0.1), ("b", 0.4)]) == ["b", "a"]


def test_resolve_typed_id():
    ids = {"ACC-PERSONA-38", "ACC-PERSONA-04", "ACC-01607", "ACC-00038"}
    assert D.resolve_typed_id("38", ids) == "ACC-PERSONA-38"
    assert D.resolve_typed_id("01607", ids) == "ACC-01607"
    assert D.resolve_typed_id("#01607", ids) == "ACC-01607"
    assert D.resolve_typed_id("ACC-00038", ids) == "ACC-00038"
    assert D.resolve_typed_id("nope", ids) is None
    assert D.resolve_typed_id("  ", ids) is None


def test_apply_shared_selection_is_one_customer():
    state = {}
    D.apply_shared_selection(state, "ACC-PERSONA-24")
    assert state["acc"] == "ACC-PERSONA-24"
    assert state["customer_pick"] == "ACC-PERSONA-24"
    assert state["seg"] == "24"
    assert state["orbit_deal_quick"] == "ACC-PERSONA-24"
    D.apply_shared_selection(state, "ACC-02363")
    assert state["acc"] == "ACC-02363"
    assert state["customer_pick"] == "ACC-02363"
    assert state["seg"] is None
    assert state["orbit_deal_quick"] is None


def test_point_selection_reads_the_account_id():
    assert D.account_from_point_selection([{"customdata": ["ACC-02363", "#02363"]}]) == "ACC-02363"
    assert D.account_from_point_selection([{"customdata": "ACC-00001"}]) == "ACC-00001"
    assert D.account_from_point_selection([]) is None
    assert D.account_from_point_selection(None) is None
