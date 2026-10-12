import streamlit as st


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
