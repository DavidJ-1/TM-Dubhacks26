"""Unit tests for the timekeeper trade-in math (harness/tradein_wait.py). ALL NUMBERS SYNTHETIC.

Reads the judge sandbox strictly read-only (mode=ro); never writes data/sandbox.db.
Expected values are hand-checked from sandbox tradein_curves + promotions (as_of 2026-10-01).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
import offer_detectors as det  # noqa: E402
import tradein_wait as tw  # noqa: E402


@pytest.fixture(scope="module")
def lt():
    try:
        conn = det.connect_ro()
    except FileNotFoundError:
        pytest.skip("sandbox.db not found (set DUBHACKS_DB)")
    cat = det.load_catalog(conn)
    fam = pd.read_sql("SELECT l.account_id, p.family FROM lines l JOIN plans p ON p.sku = l.plan_sku", conn) \
        .drop_duplicates("account_id").set_index("account_id")["family"]
    return tw.build_line_tradein(conn, cat["promotions"], fam).set_index("line_id")


def test_29_1_waits_until_payoff_feb_2027(lt):
    r = lt.loc["LN-PERSONA-29-1"]          # iPhone 16, 20 months old, 4 x $34.58 left ($138.32)
    assert r.decision == "wait_until_payoff"
    assert r.wait_until == "2027-02-01"
    # $200 TRADEIN-ANY unlocks at payoff; trade-in falls $369.80 -> $330.61 (-$39.19): net +$160.81
    assert r.tradein_drop_cents == 36980 - 33061
    assert r.promo_gain_cents == 20000
    assert r.delta_cents == 16081
    # the remaining balance must NOT count as savings: it is paid either way
    assert r.installments_paid_by_wait_cents + r.balance_at_wait_cents == r.financing_balance_cents == 13832
    assert r.delta_cents < r.financing_balance_cents + 16081   # old bug: delta was 29913 (= balance + gain)


def test_34_both_lines_wait_together_until_old_phone_credit(lt):
    a, b = lt.loc["LN-PERSONA-34-1"], lt.loc["LN-PERSONA-34-2"]   # Galaxy S23 32 mo, iPhone 14 33 mo, paid off
    for r in (a, b):
        assert r.decision == "wait_until_promo"
        assert r.wait_until == "2027-02-01"      # both are 36+ months by then (rubric: Jan/Feb 2027, together)
        assert bool(r.joint_upgrade)
        assert "PROMO-STUB-OLD-PHONE-UPGRADE" in r.promo_wait_skus
        assert r.promo_gain_cents == 15000
    assert a.delta_cents == 15000 - (25471 - 22772)   # +$123.01
    assert b.delta_cents == 15000 - (24768 - 22144)   # +$123.76 (at the shared date, 37 months)


def test_delta_never_counts_balance(lt):
    assert (lt["delta_cents"] == lt["value_wait_cents"] - lt["value_now_cents"]).all()
    assert (lt["delta_cents"] == lt["promo_gain_cents"] - lt["tradein_drop_cents"]).all()
    assert (lt["installments_paid_by_wait_cents"] + lt["balance_at_wait_cents"]
            == lt["financing_balance_cents"]).all()


def test_keep_when_keeping_beats_both(lt):
    assert lt.loc["LN-PERSONA-07-1"].decision == "keep"   # 3-month-old phone: no wait gain, no reason to buy now
    assert lt.loc["LN-PERSONA-35-1"].decision == "keep"   # year-old budget phone, paid off


def test_single_verdict_and_real_promos_only(lt):
    assert set(lt["decision"]) <= {"keep", "wait_until_payoff", "wait_until_promo", "upgrade_now"}
    alias = lt["decision"].map(lambda d: "wait" if d.startswith("wait") else d)
    assert (lt["wait_verdict"] == alias).all()
    assert ((lt["wait_until"] != "") == lt["decision"].str.startswith("wait")).all()
    used = set(",".join(lt["promo_wait_skus"].fillna("").tolist() + lt["promo_now_skus"].fillna("").tolist())
               .split(",")) - {""}
    assert used <= {"PROMO-STUB-TRADEIN-ANY", "PROMO-STUB-OLD-PHONE-UPGRADE"}
