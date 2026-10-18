"""household_optimizer (tm-offers, scratch): whole-household lowest-cost best-fit plan. ALL NUMBERS SYNTHETIC."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
PIDS = ["38", "05", "37", "39", "21", "04", "24"]


@pytest.fixture(scope="module")
def hp():
    try:
        import household_optimizer as H
        import offer_detectors as det
        conn = det.connect_ro()
    except Exception as e:  # no sandbox DB on this machine
        pytest.skip(f"sandbox unavailable: {e}")
    src = H._inputs_dir(None)
    cat = det.load_catalog(conn)
    facts = det.build_account_facts(conn)
    facts, _ = det.apply_features_csv(facts, src / "features.csv")
    sample = facts[facts.account_id.isin([f"ACC-PERSONA-{p}" for p in PIDS])
                   | facts.account_id.isin(facts.account_id.sample(200, random_state=7))]
    lt = pd.read_csv(src / "line_tradein.csv") if (src / "line_tradein.csv").exists() else None
    out = H.optimize(sample, cat["plans"], lt, H._addon_skus(conn))
    return out.set_index("account_id"), cat["plans"], sample.set_index("account_id")


def test_columns(hp):
    import household_optimizer as H
    assert list(hp[0].reset_index().columns) == H.COLUMNS


def test_persona_38_more_55_saves_40(hp):
    r = hp[0].loc["ACC-PERSONA-38"]
    assert r.best_plan == "Experience More w/ 55+ Savings 2.0" and r.monthly_saving == 40 and r.lines_affected == 2
    assert (r.current_monthly, r.best_monthly) == (150, 110)


def test_persona_05_essentials_saves_110(hp):
    r = hp[0].loc["ACC-PERSONA-05"]
    assert r.best_plan == "Essentials 2.0" and r.monthly_saving == 110 and (r.current_monthly, r.best_monthly) == (230, 120)


def test_persona_37_four_line_offer(hp):
    r = hp[0].loc["ACC-PERSONA-37"]
    assert r.best_plan == "Essentials 4 Line Offer 2.0" and r.monthly_saving == 100 and r.lines_affected == 4


def test_persona_39_five_lines_four_line_offer(hp):
    r = hp[0].loc["ACC-PERSONA-39"]
    assert r.best_plan == "Essentials 4 Line Offer 2.0" and r.monthly_saving == 10 and "5 lines meet 4+" in r.reason


def test_quiet_unlimited_users_stay(hp):
    for p in ("21", "24", "04"):
        r = hp[0].loc[f"ACC-PERSONA-{p}"]
        assert r.lines_affected == 0 and r.monthly_saving == 0, (p, r.best_plan)


def test_every_pick_is_eligible_and_priced_from_sandbox(hp):
    import offers as O
    out, plans, facts = hp
    P = plans.set_index("name")
    for acc, r in out.iterrows():
        f = facts.loc[acc]
        b = P.loc[r.best_plan]
        if r.lines_affected:
            assert O._plan_allowed(b, f["n_lines"], f["discount_group"]), acc
            assert O._fits_usage(b, f), acc
        assert abs(O._price(b, int(f["n_lines"])) / 100 - r.best_monthly) < 1e-9
        assert abs(r.current_monthly - r.best_monthly - r.monthly_saving) < 1e-9
        assert r.lines_affected in (0, int(f["n_lines"]))
        assert r.monthly_saving >= 0 or "doesn't fit" in r.reason, acc


def test_tradein_summary_present(hp):
    assert hp[0].loc["ACC-PERSONA-38", "tradein_verdict_summary"]
