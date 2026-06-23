from datetime import datetime

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from core.config import MAX_PLOT_POINTS
from core.signal_processing import downsample


def render_trend_charts(df, x, rms_cols, theme):
    x_min = float(x[0])
    x_max = float(x[-1])

    if st.session_state.cursor_x is None:
        st.session_state.cursor_x = float(x[0])

    cursor_x = st.session_state.cursor_x

    cursor_dt = datetime.utcfromtimestamp(cursor_x / 1000)
    st.markdown(f"### Курсор: `{cursor_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}`")

    selected_x = None

    need_downsample = len(x) > MAX_PLOT_POINTS
    show_grid = st.session_state.show_grid
    lock_x = st.session_state.lock_x
    lock_y = st.session_state.lock_y
    y_range_amp = st.session_state.get("y_range_amperes", 0)

    tick_interval = max(1, len(x) // 10)
    tickvals = x[::tick_interval]
    ticktext = [datetime.utcfromtimestamp(v / 1000).strftime('%d.%m %H:%M') for v in tickvals]

    y_cache = {}

    for idx, col in enumerate(rms_cols):
        y_full = df[col].values.astype(float)
        y_cache[col] = y_full

        cursor_y = float(np.interp(cursor_x, x, y_full))

        is_current = "I_" in col or "i_" in col
        if y_range_amp > 0 and is_current:
            y_min = -float(y_range_amp)
            y_max = float(y_range_amp)
        else:
            y_min_full = float(np.min(y_full))
            y_max_full = float(np.max(y_full))
            pad = (y_max_full - y_min_full) * 0.1
            if pad == 0:
                pad = 1
            y_min = y_min_full - pad
            y_max = y_max_full + pad

        fig = go.Figure()

        if need_downsample:
            x_ds, y_ds = downsample(x, y_full, MAX_PLOT_POINTS)
        else:
            x_ds, y_ds = x, y_full

        fig.add_trace(go.Scatter(
            x=x_ds, y=y_ds, mode="lines+markers",
            name=col,
            line=dict(color=theme["line_colors"][idx % len(theme["line_colors"])], width=1),
            marker=dict(size=2),
        ))

        fig.add_vline(x=cursor_x, line_color=theme["cursor"], line_width=3)

        fig.add_trace(go.Scatter(
            x=[cursor_x], y=[cursor_y],
            mode="markers", marker=dict(size=12),
            name="Cursor",
        ))

        fig.update_layout(
            title=col, height=250,
            hovermode="x", clickmode="event+select",
            dragmode=False,
            margin=dict(l=20, r=20, t=40, b=20),
            paper_bgcolor=theme["paper"],
            plot_bgcolor=theme["bg"],
            font=dict(color=theme["text"]),
            hoverlabel=dict(bgcolor=theme["hover_bg"], font_color=theme["hover_text"]),
            xaxis=dict(
                range=[x_min, x_max], fixedrange=lock_x,
                gridcolor=theme["grid"], showgrid=show_grid,
                tickvals=tickvals,
                ticktext=ticktext,
                tickfont=dict(color=theme["text"]),
            ),
            yaxis=dict(
                range=[y_min, y_max], fixedrange=lock_y,
                gridcolor=theme["grid"], showgrid=show_grid,
                tickfont=dict(color=theme["text"]),
            ),
        )

        result = st.plotly_chart(
            fig, key=f"plot_{idx}",
            on_select="rerun",
            width="stretch",
            config={"scrollZoom": not lock_x, "displayModeBar": not lock_x},
        )

        try:
            if result and result.selection and result.selection.points:
                point = result.selection.points[0]
                if "x" in point:
                    selected_x = float(point["x"])
        except Exception:
            pass

    st.markdown("---")
    st.subheader("Значения в точке курсора")
    cols = st.columns(len(rms_cols))
    for i, col in enumerate(rms_cols):
        y_full = y_cache[col]
        value = float(np.interp(st.session_state.cursor_x, x, y_full))
        cols[i].metric(col, f"{value:.2f}")

    return selected_x, y_cache
