import sys
from pathlib import Path

import streamlit as st

# `streamlit run app/web_ui.py` only puts app/ on the path; pages import `app.*`.
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

st.set_page_config(
    page_title="SME Analytics Agent",
    page_icon="📊",
    layout="wide",
)

page = st.navigation([
    st.Page(
        "app_pages/dashboard.py",
        title="Live dashboard",
        icon=":material/monitoring:",
        default=True,
    ),
    st.Page(
        "app_pages/chat.py",
        title="Ask the agent",
        icon=":material/chat:",
    ),
])

page.run()
