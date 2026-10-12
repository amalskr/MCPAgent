import plotly.express as px
import streamlit as st

from app.dashboard_data import load_dashboard_data
from app.result_viz import PRIMARY_COLOR, SERIES_COLORS


REFRESH_OPTIONS = {
    "Off": None,
    "10s": 10,
    "30s": 30,
    "1m": 60,
}


@st.cache_data(ttl=5, show_spinner=False)
def get_dashboard_data():
    # Short TTL: shared across sessions so many viewers don't hammer MySQL.
    return load_dashboard_data()


# -----------------------------
# Header and refresh controls
# -----------------------------
st.title("Live dashboard")
st.caption("Business KPIs loaded directly from MySQL.")

with st.container(horizontal=True, vertical_alignment="bottom"):
    refresh_label = st.segmented_control(
        "Auto-refresh",
        list(REFRESH_OPTIONS),
        default="30s",
        required=True,
        key="dashboard_refresh",
    )

    if st.button("Refresh now", icon=":material/refresh:"):
        get_dashboard_data.clear()


# -----------------------------
# Charts
# -----------------------------
def order_status_figure(df, measure, form):
    if form == "Donut":
        fig = px.pie(
            df,
            names="order_status",
            values=measure,
            hole=0.55,
            color_discrete_sequence=SERIES_COLORS,
        )
        fig.update_traces(
            textinfo="percent+label",
            marker_line_width=2,
            hovertemplate="%{label}<br>%{value:,}<br>%{percent}<extra></extra>",
        )
        fig.update_layout(showlegend=False)
    else:
        plot_df = df.sort_values(measure)
        fig = px.bar(
            plot_df,
            x=measure,
            y="order_status",
            orientation="h",
            text_auto=",.0f",
            color_discrete_sequence=[PRIMARY_COLOR],
            labels={
                "orders": "Orders",
                "order_value": "Order value (LKR)",
                "order_status": "",
            },
        )
        fig.update_traces(marker_cornerradius=4)
        fig.update_xaxes(showgrid=False)

    fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10))
    return fig


def top_products_figure(df):
    plot_df = df.sort_values("price")
    fig = px.bar(
        plot_df,
        x="price",
        y="name",
        orientation="h",
        text_auto=",.2f",
        hover_data={"category": True, "quantity": True},
        color_discrete_sequence=[PRIMARY_COLOR],
        labels={"price": "Price (LKR)", "name": ""},
    )
    fig.update_traces(marker_cornerradius=4)
    fig.update_xaxes(showgrid=False)
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10))
    return fig


# -----------------------------
# Live section
# -----------------------------
@st.fragment(run_every=REFRESH_OPTIONS[refresh_label])
def live_dashboard():
    try:
        data = get_dashboard_data()
    except Exception as error:
        st.error(
            f"Unable to load dashboard data from MySQL: {error}",
            icon=":material/error:",
        )
        return

    kpis = data["kpis"]
    total_orders = kpis["total_orders"]

    def share(count):
        return f"{count / total_orders:.0%} of orders" if total_orders else None

    with st.container(horizontal=True):
        st.metric(
            "Total orders",
            f"{total_orders:,}",
            border=True,
            icon=":material/receipt_long:",
        )
        st.metric(
            "Total products",
            f"{kpis['total_products']:,}",
            border=True,
            icon=":material/inventory_2:",
        )
        st.metric(
            "Pending orders",
            f"{kpis['pending_orders']:,}",
            delta=share(kpis["pending_orders"]),
            delta_color="off",
            delta_arrow="off",
            border=True,
            icon=":material/pending_actions:",
        )
        st.metric(
            "Canceled orders",
            f"{kpis['canceled_orders']:,}",
            delta=share(kpis["canceled_orders"]),
            delta_color="off",
            delta_arrow="off",
            border=True,
            icon=":material/cancel:",
        )

    status_col, products_col = st.columns(2)

    with status_col:
        with st.container(border=True):
            st.markdown("**Order status**")

            with st.container(horizontal=True):
                measure = st.segmented_control(
                    "Measure",
                    ["orders", "order_value"],
                    format_func={
                        "orders": "Orders",
                        "order_value": "Order value",
                    }.get,
                    default="orders",
                    required=True,
                    key="status_measure",
                    label_visibility="collapsed",
                )
                form = st.segmented_control(
                    "Chart form",
                    ["Bar", "Donut"],
                    default="Bar",
                    required=True,
                    key="status_form",
                    label_visibility="collapsed",
                )

            if data["order_status"].empty:
                st.caption("No orders yet.")
            else:
                st.plotly_chart(
                    order_status_figure(data["order_status"], measure, form),
                    key="order_status_chart",
                    alt="Orders by order status",
                )

    with products_col:
        with st.container(border=True):
            st.markdown("**Top 5 products by price**")

            if data["top_products"].empty:
                st.caption("No priced products found.")
            else:
                chart_tab, table_tab = st.tabs(["Chart", "Table"])

                with chart_tab:
                    st.plotly_chart(
                        top_products_figure(data["top_products"]),
                        key="top_products_chart",
                        alt="Top 5 products by price",
                    )

                with table_tab:
                    st.dataframe(
                        data["top_products"],
                        hide_index=True,
                        column_config={
                            "name": "Product",
                            "category": "Category",
                            "price": st.column_config.NumberColumn(
                                "Price (LKR)", format="%.2f"
                            ),
                            "quantity": "Quantity",
                        },
                        alt="Top 5 products by price",
                    )

    refresh_note = (
        f" · refreshes every {refresh_label}"
        if REFRESH_OPTIONS[refresh_label] else " · auto-refresh off"
    )
    st.caption(
        f"Last updated {data['loaded_at']:%Y-%m-%d %H:%M:%S}{refresh_note}"
    )


live_dashboard()
