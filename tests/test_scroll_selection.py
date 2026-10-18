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
    D.apply_shared_selection(state, "ACC-02363")
    assert state["acc"] == "ACC-02363"
    assert state["customer_pick"] == "ACC-02363"
    assert state["seg"] == "ACC-02363"
    assert state["orbit_deal_quick"] == "ACC-02363"
    D.apply_shared_selection(state, "ACC-00001")
    assert state["acc"] == "ACC-00001"
    assert state["customer_pick"] == "ACC-00001"
    assert state["seg"] is None
    assert state["orbit_deal_quick"] is None


def test_quick_picks_span_risk_and_keep_a_do_nothing():
    labels = [D.quick_label(q) for q in D.QUICK]
    assert any(x == "low risk, do nothing" for x in labels)
    assert any(x.startswith("low risk") for x in labels)
    assert any(x.startswith("high risk") for x in labels)
    assert any(x.startswith("very high risk") and "fix-first" in x for x in labels)
    ids = {q["id"] for q in D.QUICK}
    assert "ACC-02363" in ids
    assert not ids & {"ACC-PERSONA-07", "ACC-PERSONA-31", "ACC-PERSONA-24"}
    assert D.quick_button(D.QUICK[0]).startswith("#")


def test_point_selection_reads_the_account_id():
    assert D.account_from_point_selection([{"customdata": ["ACC-02363", "#02363"]}]) == "ACC-02363"
    assert D.account_from_point_selection([{"customdata": "ACC-00001"}]) == "ACC-00001"
    assert D.account_from_point_selection([]) is None
    assert D.account_from_point_selection(None) is None


def test_scatter_is_fixed_and_plainly_labeled():
    import orbit_sections as O

    df = pd.DataFrame({
        "account_id": ["ACC-00001", "ACC-00002"],
        "p_churn_90d": [0.87, 0.01],
        "last_bill_cents": [14200, 8000],
        "flagged": [True, False],
        "channel": ["text", None],
        "is_demo": [False, False],
    })
    fig = O._hero_fig(df, "t", False)
    assert fig.layout.xaxis.title.text == "Churn risk"
    assert fig.layout.xaxis.fixedrange is True
    assert fig.layout.yaxis.title.text == "Monthly bill ($)"
    assert fig.layout.yaxis.fixedrange is True
    assert fig.layout.dragmode is False
    assert all(trace.type == "scatter" for trace in fig.data)
    ids = {row[0] for trace in fig.data for row in trace.customdata}
    assert ids == {"ACC-00001", "ACC-00002"}
    fig_log = O._hero_fig(df, "t2", True)
    assert fig_log.layout.xaxis.title.text == "Churn risk (log scale)"
    assert fig_log.layout.xaxis.type == "log"
    assert fig_log.layout.xaxis.fixedrange is True
    marked = O._mark_customers(
        fig, df, False,
        [{"id": "ACC-00001", "text": "#00001", "hover": "very high risk, fix-first message"}],
        "ACC-00002",
    )
    texts = [t for trace in marked.data if trace.text is not None
             for t in (trace.text if isinstance(trace.text, (list, tuple)) else [trace.text])]
    assert "#00001" in texts and "#00002" in texts
    assert len(marked.data) == len(fig.data) + 2
