import json
import re

import pandas as pd
import plotly.express as px
import streamlit as st


# Fixed categorical order (colorblind-validated). Assigned in order, never cycled.
SERIES_COLORS = [
    "#2a78d6",  # blue
    "#eb6834",  # orange
    "#1baf7a",  # aqua
    "#eda100",  # yellow
    "#e87ba4",  # magenta
    "#008300",  # green
    "#6250d6",  # violet
    "#e34948",  # red
]

PRIMARY_COLOR = SERIES_COLORS[0]
MAX_PIE_SLICES = 6
TOP_N_THRESHOLD = 15

ISO_DATE_PATTERN = re.compile(
    r"^\d{4}-\d{2}(-\d{2}([ T]\d{2}:\d{2}(:\d{2})?.*)?)?$"
)


# -----------------------------
# Extract rows from MCP output
# -----------------------------
def _rows_from_value(value):
    if isinstance(value, list) and value and all(
        isinstance(row, dict) for row in value
    ):
        return value

    if isinstance(value, dict):
        for key in ("result", "rows"):
            candidate = value.get(key)

            if isinstance(candidate, list) and all(
                isinstance(row, dict) for row in candidate
            ):
                return candidate

    return None


def extract_query_rows(tool_outputs):
    """
    Return the rows of the most recent successful query_database call.

    Prefers MCP structured content ({"result": [...]}) and falls back to
    the text content, where the server emits one JSON object per row.
    """
    for item in reversed(tool_outputs):
        if item.get("tool") != "query_database" or item.get("is_error"):
            continue

        rows = _rows_from_value(item.get("structured"))

        if rows is not None:
            return rows

        parsed_items = []

        for result_text in item.get("result", []):
            try:
                parsed_items.append(json.loads(result_text))
            except (json.JSONDecodeError, TypeError):
                continue

        # A single text block holding the whole list or a wrapper object.
        if len(parsed_items) == 1:
            rows = _rows_from_value(parsed_items[0])

            if rows is not None:
                return rows

        # One text block per row.
        if parsed_items and all(isinstance(row, dict) for row in parsed_items):
            return parsed_items

        # The query succeeded but returned no rows.
        if not parsed_items:
            return []

    return None


def extract_last_sql(tool_outputs):
    for item in reversed(tool_outputs):
        if item.get("tool") == "query_database":
            return item.get("arguments", {}).get("sql")

    return None


# -----------------------------
# Type coercion
# -----------------------------
def _is_identifier(column):
    name = str(column).lower()
    return name == "id" or name.endswith("_id")


def prepare_dataframe(rows):
    """
    MySQL DECIMAL and DATETIME values arrive as JSON strings.
    Convert them back to numbers and datetimes so they can be charted.
    """
    df = pd.DataFrame(rows)

    for column in df.columns:
        series = df[column]

        if (
            pd.api.types.is_numeric_dtype(series)
            or pd.api.types.is_datetime64_any_dtype(series)
        ):
            continue

        non_null = series.dropna()

        if non_null.empty:
            continue

        as_text = non_null.astype(str).str.strip()

        if as_text.str.match(ISO_DATE_PATTERN).all():
            converted = pd.to_datetime(
                series.astype("string"), errors="coerce", format="mixed"
            )

            if converted.notna().sum() == len(non_null):
                df[column] = converted
                continue

        converted = pd.to_numeric(series, errors="coerce")

        if converted.notna().sum() == len(non_null):
            df[column] = converted

    return df


def classify_columns(df):
    datetime_columns = df.select_dtypes(include="datetime").columns.tolist()

    numeric_columns = [
        column
        for column in df.select_dtypes(include="number").columns
        if not _is_identifier(column)
    ]

    label_columns = [
        column
        for column in df.columns
        if column not in numeric_columns and column not in datetime_columns
    ]

    return label_columns, numeric_columns, datetime_columns


# -----------------------------
# Chart selection
# -----------------------------
def available_charts(df, label_columns, numeric_columns, datetime_columns):
    """Return (chart options, suggested default) for the data's shape."""
    if not numeric_columns or len(df) < 2:
        return [], None

    charts = []

    if datetime_columns:
        charts += ["Line", "Area", "Bar"]

    if label_columns:
        if "Bar" not in charts:
            charts.append("Bar")

        category_count = df[label_columns[0]].nunique()
        values = df[numeric_columns[0]]

        if 2 < category_count <= MAX_PIE_SLICES and (values >= 0).all():
            charts.append("Pie")

        if len(numeric_columns) == 1 and category_count > 1:
            charts.append("Treemap")

    if len(numeric_columns) >= 2 and (not label_columns or len(df) > 10):
        charts.append("Scatter")

    if not label_columns and not datetime_columns:
        charts += ["Histogram", "Bar"]

    charts = list(dict.fromkeys(charts))

    if datetime_columns:
        default = "Line"
    elif "Pie" in charts and len(numeric_columns) == 1:
        default = "Pie"
    elif label_columns:
        default = "Bar"
    elif "Scatter" in charts:
        default = "Scatter"
    else:
        default = charts[0]

    return charts, default


def _style(fig, height=420):
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        legend_title_text="",
        hoverlabel=dict(namelength=-1),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridwidth=1)
    return fig


def build_figure(df, chart_type, x, y_columns, color):
    y = y_columns[0]
    many_series = len(y_columns) > 1

    if chart_type in ("Line", "Area"):
        plot_df = df.sort_values(x)
        plot = px.line if chart_type == "Line" else px.area

        if many_series:
            fig = plot(
                plot_df, x=x, y=y_columns,
                color_discrete_sequence=SERIES_COLORS,
                markers=chart_type == "Line" and len(plot_df) <= 40,
            )
        else:
            fig = plot(
                plot_df, x=x, y=y, color=color,
                color_discrete_sequence=SERIES_COLORS,
                markers=chart_type == "Line" and len(plot_df) <= 40,
            )

        fig.update_traces(line_width=2)
        return _style(fig)

    if chart_type == "Bar":
        if many_series:
            fig = px.bar(
                df, x=x, y=y_columns, barmode="group",
                color_discrete_sequence=SERIES_COLORS,
            )
        elif color:
            fig = px.bar(
                df, x=x, y=y, color=color, barmode="group",
                color_discrete_sequence=SERIES_COLORS,
            )
        else:
            # Long or many category labels read better as horizontal bars.
            labels = df[x].astype(str)
            horizontal = (
                not pd.api.types.is_numeric_dtype(df[x])
                and (labels.str.len().max() > 12 or len(df) > 8)
            )

            if horizontal:
                plot_df = df.sort_values(y)
                fig = px.bar(
                    plot_df, x=y, y=x, orientation="h", text_auto=".3s",
                    color_discrete_sequence=[PRIMARY_COLOR],
                )
                fig.update_yaxes(type="category")
                return _style(fig, height=max(320, 28 * len(plot_df) + 80))

            fig = px.bar(
                df, x=x, y=y, text_auto=".3s",
                color_discrete_sequence=[PRIMARY_COLOR],
            )

            if not pd.api.types.is_numeric_dtype(df[x]):
                fig.update_xaxes(type="category")

        fig.update_traces(marker_cornerradius=4)
        return _style(fig)

    if chart_type == "Pie":
        fig = px.pie(
            df, names=x, values=y, hole=0.45,
            color_discrete_sequence=SERIES_COLORS,
        )
        fig.update_traces(
            textinfo="percent+label",
            marker_line_width=2,
            hovertemplate="%{label}<br>%{value:,}<br>%{percent}<extra></extra>",
        )
        return _style(fig)

    if chart_type == "Treemap":
        fig = px.treemap(
            df, path=[x], values=y,
            color_discrete_sequence=SERIES_COLORS,
        )
        fig.update_traces(textinfo="label+value+percent root")
        return _style(fig)

    if chart_type == "Scatter":
        fig = px.scatter(
            df, x=x, y=y, color=color,
            color_discrete_sequence=SERIES_COLORS,
        )
        fig.update_traces(marker_size=9)
        return _style(fig)

    if chart_type == "Histogram":
        fig = px.histogram(
            df, x=y, color_discrete_sequence=[PRIMARY_COLOR],
        )
        return _style(fig)

    return None


# -----------------------------
# Rendering
# -----------------------------
def _render_kpis(df, numeric_columns, label_columns):
    row = df.iloc[0]

    with st.container(horizontal=True):
        for column in numeric_columns:
            value = row[column]
            st.metric(
                str(column).replace("_", " ").capitalize(),
                f"{value:,.2f}".rstrip("0").rstrip(".")
                if isinstance(value, float) else f"{value:,}",
                border=True,
            )

        for column in label_columns[:3]:
            st.metric(
                str(column).replace("_", " ").capitalize(),
                str(row[column]),
                border=True,
            )


def _render_chart(df, label_columns, numeric_columns, datetime_columns, key_prefix):
    charts, default = available_charts(
        df, label_columns, numeric_columns, datetime_columns
    )

    if not charts:
        st.caption(
            "No chart for this result: it needs a numeric column "
            "and at least two rows."
        )
        return

    chart_type = st.segmented_control(
        "Chart type",
        charts,
        default=default,
        required=True,
        key=f"{key_prefix}_type",
    )

    if chart_type in ("Line", "Area") and datetime_columns:
        x_options = datetime_columns + label_columns
    elif chart_type == "Scatter":
        x_options = numeric_columns
    elif chart_type == "Histogram":
        x_options = []
    else:
        x_options = label_columns + datetime_columns or numeric_columns

    with st.container(horizontal=True):
        x = None

        if x_options:
            x = st.selectbox(
                "Category / X-axis", x_options, key=f"{key_prefix}_{chart_type}_x"
            )

        single_value_chart = chart_type in ("Pie", "Treemap", "Histogram", "Scatter")
        y_choices = [column for column in numeric_columns if column != x]

        if single_value_chart:
            y_columns = [
                st.selectbox("Value", y_choices, key=f"{key_prefix}_{chart_type}_y")
            ]
        else:
            y_columns = st.multiselect(
                "Values",
                y_choices,
                default=y_choices[:1],
                key=f"{key_prefix}_{chart_type}_ys",
            ) or y_choices[:1]

        color = None
        color_options = [c for c in label_columns if c != x]

        if (
            color_options
            and len(y_columns) == 1
            and chart_type in ("Line", "Area", "Bar", "Scatter")
        ):
            color_choice = st.selectbox(
                "Split by",
                ["(none)"] + color_options,
                key=f"{key_prefix}_{chart_type}_color",
            )
            color = None if color_choice == "(none)" else color_choice

    plot_df = df

    # Keep large categorical results readable.
    if (
        x in label_columns
        and chart_type in ("Bar", "Treemap")
        and df[x].nunique() > TOP_N_THRESHOLD
        and not color
    ):
        top_n = st.slider(
            "Show top N",
            min_value=5,
            max_value=int(df[x].nunique()),
            value=TOP_N_THRESHOLD,
            key=f"{key_prefix}_topn",
        )
        plot_df = df.nlargest(top_n, y_columns[0])

    if color and plot_df[color].nunique() > len(SERIES_COLORS):
        st.caption(
            f"'{color}' has more than {len(SERIES_COLORS)} values; "
            "showing the largest groups only."
        )
        keep = (
            plot_df.groupby(color)[y_columns[0]].sum()
            .nlargest(len(SERIES_COLORS)).index
        )
        plot_df = plot_df[plot_df[color].isin(keep)]

    fig = build_figure(plot_df, chart_type, x, y_columns, color)

    if fig is not None:
        st.plotly_chart(
            fig,
            key=f"{key_prefix}_plot",
            alt=f"{chart_type} chart of {', '.join(map(str, y_columns))}"
            + (f" by {x}" if x else ""),
        )


def _render_table(df, key_prefix):
    column_config = {}

    for column in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[column]):
            column_config[column] = st.column_config.DatetimeColumn(
                format="YYYY-MM-DD HH:mm"
            )
        elif pd.api.types.is_float_dtype(df[column]):
            column_config[column] = st.column_config.NumberColumn(
                format="localized"
            )

    st.dataframe(
        df,
        hide_index=True,
        column_config=column_config,
        key=f"{key_prefix}_table",
        alt="Query results table",
    )

    st.download_button(
        "Download CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name="query_results.csv",
        mime="text/csv",
        icon=":material/download:",
        on_click="ignore",
        key=f"{key_prefix}_download",
    )


def display_results(rows, key_prefix, sql=None):
    if rows is None:
        return

    if not rows:
        st.info("The query returned no rows.", icon=":material/info:")
        return

    df = prepare_dataframe(rows)
    label_columns, numeric_columns, datetime_columns = classify_columns(df)

    with st.container(border=True):
        st.caption(f"{len(df):,} rows · {len(df.columns)} columns")

        # A single row is a headline number, not a chart.
        if len(df) == 1 and numeric_columns:
            _render_kpis(df, numeric_columns, label_columns)
            _render_table(df, key_prefix)
        else:
            chart_tab, table_tab, stats_tab = st.tabs([
                ":material/bar_chart: Chart",
                ":material/table: Table",
                ":material/functions: Summary",
            ])

            with chart_tab:
                _render_chart(
                    df, label_columns, numeric_columns,
                    datetime_columns, key_prefix,
                )

            with table_tab:
                _render_table(df, key_prefix)

            with stats_tab:
                if numeric_columns:
                    st.dataframe(
                        df[numeric_columns].describe().T,
                        alt="Summary statistics for numeric columns",
                    )
                else:
                    st.caption("No numeric columns to summarize.")

        if sql:
            with st.expander("SQL used", icon=":material/code:"):
                st.code(sql, language="sql")
