"""Tests for harness/pipeline.py (SYNTHETIC data only)."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness"))
import pipeline  # noqa: E402

IDS = ["stages", "trace"]
KEYS = {"synthetic", "caveat", "generated_at", "data_source", "label", "segment_key", "excluded_personas",
        "stages", "trace"}


def _fixture(tmp: Path):
    ids = [f"ACC-{i:03d}" for i in range(20)] + ["ACC-PERSONA-22"]
    pd.DataFrame({"account_id": ids, "is_persona": [0] * 20 + [1],
                  "language": ["es" if i % 4 == 0 else "en" for i in range(21)], "tenure_months": 12,
                  "plan_sku": "TMO-STUB-PLAN-MORE", "plan_family": "experience_more", "n_lines": 1,
                  "unresolved_90d": 2, "promo_expired_recent": 1, "bill_change_3m_pct": 0.2}
                 ).to_csv(tmp / "features.csv", index=False)
    pd.DataFrame({"account_id": ids, "is_family_plan": [i % 2 for i in range(21)]}).to_csv(tmp / "enrichment.csv",
                                                                                          index=False)
    pd.DataFrame({"account_id": ids, "p_churn_90d": [i / 21 for i in range(21)],
                  "risk_rank": list(range(21, 0, -1)), "risk_reason_1": "r", "stay_reason_1": "s"}
                 ).to_csv(tmp / "churn_scores.csv", index=False)
    acts = ["do nothing", "$25 care credit", "fix-first callback", "step-up plan"]
    pd.DataFrame({"account_id": ids, "action": [acts[i % 4] for i in range(21)],
                  "upgrade_moment": [i % 3 == 0 for i in range(21)]}).to_csv(tmp / "offers.csv", index=False)
    rows = [{"account_id": a, "action": x, "eligible": True, "expected_value": 1.0, "is_chosen": x == acts[i % 4]}
            for i, a in enumerate(ids) for x in acts]
    pd.DataFrame(rows).to_csv(tmp / "offer_candidates.csv", index=False)


def _check_schema(d):
    assert set(d) == KEYS and d["synthetic"] is True and d["generated_at"].endswith(("-07:00", "-08:00"))
    assert [s["id"] for s in d["stages"]] == ["accounts", "scored", "flagged", "offered", "wait", "messaged"]
    for s in d["stages"]:
        assert {"id", "label", "count", "by_segment"} <= set(s)
        if s["count"] is None:
            assert s.get("note")
    st = {s["id"]: s for s in d["stages"]}
    assert "by_action" in st["offered"] and "by_language" in st["messaged"]
    assert {"account_id", "signals", "all_signals", "score", "offer", "message"} <= set(d["trace"])
    t = d["trace"]
    assert len(t["signals"]) <= 8 and len(t["all_signals"]) >= len(t["signals"])
    for sig in t["all_signals"]:
        assert set(sig) == {"name", "value", "source"} and sig["source"] in {"commerce", "customer", "live"}
        txt = f"{sig['name']} {sig['value']}"
        assert "_" not in txt and "STUB" not in txt and "TMO-" not in txt, txt


def test_fixture_invariant_and_schema(tmp_path):
    _fixture(tmp_path)
    d = pipeline.summarize(tmp_path, features_path=tmp_path / "features.csv")
    _check_schema(d)
    st = {s["id"]: s for s in d["stages"]}
    assert st["offered"]["count"] + st["wait"]["count"] == st["flagged"]["count"]
    assert sum(st["offered"]["by_action"].values()) == st["offered"]["count"]
    assert sum(st["flagged"]["by_segment"].values()) == st["flagged"]["count"]
    assert "do nothing" not in st["offered"]["by_action"]
    bl = st["messaged"]["by_language"]
    assert bl["en"] + bl["es"] == st["messaged"]["count"] <= st["offered"]["count"]
    # persona (index 20) excluded; top 10% of 20 regular (ranked by p: 19, 18) or upgrade moment (i % 3 == 0)
    assert d["excluded_personas"] == 1 and st["accounts"]["count"] == 20 and st["scored"]["count"] == 20
    assert st["flagged"]["count"] == len({18, 19} | {i for i in range(20) if i % 3 == 0})
    t = d["trace"]
    assert t["account_id"] == "ACC-PERSONA-22" and t["offer"]["chosen"] == "do nothing"
    assert t["message"]["text"] is None            # do nothing -> no message; persona still traceable
    assert t["score"]["p_churn_90d"] == pytest.approx(20 / 21) and t["signals"]
    assert t["message"]["source"].startswith("app/messages.py")
    assert st["messaged"]["message_source"].startswith("app/messages.py")
    t = pipeline.summarize(tmp_path, features_path=tmp_path / "features.csv", trace_id="ACC-001")["trace"]
    assert t["offer"]["chosen"] == "$25 care credit" and t["message"]["language"] == "en" and t["message"]["text"]
    es = pipeline.summarize(tmp_path, features_path=tmp_path / "features.csv", trace_id="ACC-001", lang="es")
    assert es["trace"]["message"]["language"] == "es"


def test_family_plan_segment_and_fallback(tmp_path):
    _fixture(tmp_path)
    d = pipeline.summarize(tmp_path, features_path=tmp_path / "features.csv", segment_key="family_plan")
    st = {s["id"]: s for s in d["stages"]}
    assert st["accounts"]["by_segment"] == {"family_plan": 10, "not_family_plan": 10}
    (tmp_path / "enrichment.csv").write_text("account_id,other\nACC-000,1\n")
    old = pipeline.OUT
    pipeline.OUT = tmp_path            # no fallback to the canonical out/ file either
    try:
        d = pipeline.summarize(tmp_path, features_path=tmp_path / "features.csv", segment_key="family_plan")
    finally:
        pipeline.OUT = old
    assert d["stages"][0]["by_segment"] == {} and "family_plan" in d["stages"][0]["segment_note"]


def test_missing_offers_gives_null_with_note(tmp_path):
    _fixture(tmp_path)
    (tmp_path / "offers.csv").unlink()
    d = pipeline.summarize(tmp_path, features_path=tmp_path / "features.csv")
    _check_schema(d)
    st = {s["id"]: s for s in d["stages"]}
    assert st["scored"]["count"] == 20
    for k in ("flagged", "offered", "wait", "messaged"):
        assert st[k]["count"] is None and st[k]["note"]


def test_invariant_checker_catches_mismatch():
    d = {"stages": [{"id": i, "count": c} for i, c in
                    zip(["accounts", "scored", "flagged", "offered", "wait", "messaged"], [10, 10, 5, 2, 2, 1])]}
    with pytest.raises(AssertionError):
        pipeline.check_invariants(d)


@pytest.mark.skipif(not (pipeline.OUT / "offers.csv").exists(), reason="canonical lane outputs not present")
def test_real_outputs(tmp_path):
    d = pipeline.main(["--out", str(tmp_path / "p.json")])
    _check_schema(json.loads((tmp_path / "p.json").read_text()))
    st = {s["id"]: s for s in d["stages"]}
    assert st["offered"]["count"] + st["wait"]["count"] == st["flagged"]["count"]
    assert st["accounts"]["count"] == st["scored"]["count"] == 5000 and d["excluded_personas"] == 42
    srcs = {s["source"] for s in d["trace"]["signals"]}
    assert srcs <= {"commerce", "customer", "live"}
