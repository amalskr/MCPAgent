
import streamlit as st

from app.agent_service import ask_agent
from app.result_viz import (
    display_results,
    extract_last_sql,
    extract_query_rows,
)


st.set_page_config(
    page_title="SME Analytics Agent",
    page_icon="📊",
    layout="wide",
)

st.title("📊 SME Analytics Agent")
st.caption(
    "Ask questions about your business data using Gemini + MCP + MySQL."
)


# -----------------------------
# Session state
# -----------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "gemini_history" not in st.session_state:
    st.session_state.gemini_history = []

if "tool_outputs" not in st.session_state:
    st.session_state.tool_outputs = []

if "pending_question" not in st.session_state:
    st.session_state.pending_question = None


# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.header("Dashboard")
    st.write("Connected through your existing MCP server.")

    if st.button("Clear conversation", width="stretch"):
        st.session_state.messages = []
        st.session_state.gemini_history = []
        st.session_state.tool_outputs = []
        st.session_state.pending_question = None
        st.rerun()

    st.divider()
    st.caption("Suggested questions")

    suggestions = [
        "How many products are in the products table?",
        "Show the top 5 most expensive products.",
        "Count orders grouped by order_status.",
        "Calculate order value grouped by order_status.",
        "Show monthly order totals over time.",
        "Which stores have the most orders?",
    ]

    for index, suggestion in enumerate(suggestions):
        if st.button(
            suggestion,
            key=f"suggestion_{index}",
            width="stretch",
        ):
            st.session_state.pending_question = suggestion
            st.rerun()


# -----------------------------
# Display conversation history
# -----------------------------
for index, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        if message.get("table") is not None:
            display_results(
                message["table"],
                key_prefix=f"history_{index}",
                sql=message.get("sql"),
            )


# -----------------------------
# Question input
# -----------------------------
question = st.chat_input(
    "Ask a question about your business data..."
)

if not question and st.session_state.pending_question:
    question = st.session_state.pending_question
    st.session_state.pending_question = None


# -----------------------------
# Process question
# -----------------------------
if question:
    st.session_state.messages.append({
        "role": "user",
        "content": question,
    })

    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing your business data..."):
            try:
                answer, history, tool_outputs = ask_agent(
                    question,
                    st.session_state.gemini_history,
                )

                st.session_state.gemini_history = history
                st.session_state.tool_outputs = tool_outputs

                st.markdown(answer)

                # Show MCP activity for debugging and transparency.
                if tool_outputs:
                    with st.expander("View database tool activity"):
                        for item in tool_outputs:
                            st.write("Tool:", item["tool"])
                            st.json(item.get("arguments", {}))

                            for result_text in item.get("result", []):
                                st.code(
                                    result_text,
                                    language="text",
                                )

                            if item.get("is_error"):
                                st.warning("This tool call returned an error.")

                # Extract structured query rows.
                rows = extract_query_rows(tool_outputs)
                sql = extract_last_sql(tool_outputs)

                message_data = {
                    "role": "assistant",
                    "content": answer,
                    "table": rows,
                    "sql": sql,
                }

                if rows is not None:
                    display_results(
                        rows,
                        key_prefix=f"history_{len(st.session_state.messages)}",
                        sql=sql,
                    )

                st.session_state.messages.append(message_data)

            except Exception as error:
                error_message = (
                    f"Unable to complete the request: {error}"
                )

                st.error(error_message)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": error_message,
                })
