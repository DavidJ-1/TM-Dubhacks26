"""value_ledger (tm-offers): two-sided ledger math, hidden-value loader, ranking. ALL NUMBERS SYNTHETIC."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
import value_ledger as VL  # noqa: E402


def test_kept_margin_flat_matches_cited_1_8k():
    km = VL.kept_margin_mo(np.array([10.0, 500.0]), "flat")
    assert np.allclose(km * 24, 152.91 * 0.5 * 24)          # ~$1,835 (RESEARCH.md s12)
    assert np.allclose(VL.kept_margin_mo(np.array([100.0]), "bill"), 50.0)


def test_tm_value_price_cut_terms():
    # p90 10%, save|accept 30%, p_accept 3%, kept $76.455/mo, 12 months, saves customer $20/mo, $2 contact
    net, prev, kept, given = VL.tm_value(np.array([0.10]), np.array([0.30]), np.array([True]), np.array([0.03]),
                                         np.array([76.455]), 12, np.array([20.0]), 0.0, 0.0, np.array([2.0]), 0.0)
    assert prev[0] == pytest.approx(0.10 * 0.30 * 0.03)
    assert kept[0] == pytest.approx(prev[0] * 76.455 * 12)
    assert given[0] == pytest.approx(0.03 * 20 * 12)
    assert net[0] == pytest.approx(kept[0] - given[0] - 2.0)


def test_no_cac_in_net_and_replacement_is_separate():
    # tm_value has no CAC argument: replacement cost can't be summed with kept margin by construction
    import inspect
    assert "cac" not in inspect.signature(VL.tm_value).parameters
    assert "never summed" in VL.A["CAC"][2]


def test_backfire_is_a_loss():
    assert VL.backfire_loss(0.1, 0.03, 76.455, 12) > 0
    assert VL.backfire_loss(0.1, 0.03, 76.455, 12, rel=0.0) == 0


def test_rank_offers_profit_gate_and_customer_weight():
    led = pd.DataFrame({"account_id": ["a", "a", "b"], "offer": ["x", "y", "x"],
                        "tm_net_12m": [-5.0, 3.0, -1.0], "customer_expected_12m": [20.0, 0.0, 0.0]})
    b = VL.rank_offers(led, w=0.5)
    assert b.loc["a", "offer"] == "x" and b.loc["a", "score"] == pytest.approx(5.0)
    assert b.loc["b", "score"] < 0                           # caller treats score <= 0 as do_nothing
    assert VL.rank_offers(led, w=0.0).loc["a", "offer"] == "y"


def test_loader_maps_tm_models_columns(tmp_path):
    p = tmp_path / "hv.csv"
    pd.DataFrame({"account_id": ["A1", "A2"], "item_type": ["plan_essentials_4line", "tradein_value_paid_off"],
                  "customer_value_monthly": [20.0, 0.0], "customer_value_onetime": [0.0, 300.0],
                  "source_field": ["plans.line_prices", "tradein_curves"], "plain_text": ["save $20", "worth $300"],
                  "confidence": ["firm", "firm"]}).to_csv(p, index=False)
    hv = VL.load_hidden_value(p)
    assert list(hv.kind) == ["saving", "reminder"]
    assert hv.tmobile_value_monthly.tolist() == [-20.0, 0.0]
    assert hv.customer_value_one_time.tolist() == [0.0, 300.0]


def test_loader_fails_loudly(tmp_path):
    p = tmp_path / "bad.csv"
    pd.DataFrame({"account_id": ["A1"], "foo": [1]}).to_csv(p, index=False)
    with pytest.raises(ValueError, match="missing required columns"):
        VL.load_hidden_value(p)


def test_inferred_items_never_firm(tmp_path):
    p = tmp_path / "hv.csv"
    pd.DataFrame({"account_id": ["A1"], "item_type": ["student_credit_check"], "customer_value_monthly": [20.0],
                  "source_field": ["billing_history"], "plain_text": ["check"], "confidence": ["inferred"]}).to_csv(p, index=False)
    assert VL.load_hidden_value(p).kind.tolist() == ["check"]


def test_placeholder_runs_on_sandbox():
    try:
        conn = VL.connect_ro(VL.find_db())
    except Exception as e:  # no sandbox DB on this machine
        pytest.skip(f"sandbox unavailable: {e}")
    hv = VL.placeholder_hidden_value(conn)
    assert set(VL.HV_COLUMNS) <= set(hv.columns)
    assert (hv.loc[hv.kind == "reminder", "customer_value_monthly"] == 0).all()
    assert not hv.description.str.contains("haven't used|unused", case=False).any()
    g = hv.groupby("item_type").account_id.nunique()
    assert g.get("C_essentials_4line_offer") == 177 and g.get("D_tradein_paid_off") == 2212   # HIDDEN_VALUE.md
