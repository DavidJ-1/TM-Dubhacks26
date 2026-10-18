"""The deal example shows the selected customer on the same run as a quick-pick click."""
from __future__ import annotations

import html
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))


def test_deal_quick_pick_updates_the_example_immediately():
    from streamlit.testing.v1 import AppTest

    def page():
        import pandas as pd
        import streamlit as st
        import orbit_sections as sections

        st.session_state.setdefault("acc", "ACC-00001")

        def on_quick(account_id):
            st.session_state["acc"] = account_id

        df = pd.DataFrame({
            "account_id": ["ACC-00001", "ACC-00002"],
            "p_churn_90d": [0.1, 0.8],
            "messaged": [False, True],
            "channel": [None, "text"],
            "message_en": ["", "Hello"],
            "reason_line": ["Quiet.", "Reach out."],
            "language": ["en", "en"],
        })
        sections.render_deal_engine(
            df, st.session_state["acc"], demo_ids=["ACC-00001", "ACC-00002"], on_quick=on_quick, key="orbit",
        )

    at = AppTest.from_function(page).run()
    text = html.unescape(" ".join(m.value for m in at.markdown))
    assert "Customer #00001" in text
    at = next(b for b in at.button if b.label == "Customer #00002").click().run()
    text = html.unescape(" ".join(m.value for m in at.markdown))
    assert "Customer #00002" in text
    assert at.session_state["acc"] == "ACC-00002"
