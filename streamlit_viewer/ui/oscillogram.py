from datetime import datetime

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from core.config import DEFAULT_SAMPLE_RATE
from core.signal_processing import parse_channel_range, decode_v2_signal
from adapters.file_loader import get_physical_signals

_MDASH = "\u2014"


def render_oscillograms(df, x, signal_cols, theme):
    if not signal_cols:
        return

    st.session_state.signal_idx = int(np.searchsorted(x, st.session_state.cursor_x, side="left"))
    st.session_state.signal_idx = min(st.session_state.signal_idx, len(df) - 1)

    st.markdown("---")
    st.subheader("Осциллограммы и спектр")

    if "step_size" not in st.session_state:
        st.session_state.step_size = 1

    show_grid = st.session_state.show_grid
    lock_x = st.session_state.lock_x
    lock_y = st.session_state.lock_y
    freq_min = st.session_state.freq_min
    freq_max = st.session_state.freq_max
    y_range_amp = st.session_state.get("y_range_amperes", 0)

    nav1, nav2, nav3, nav4, nav5 = st.columns([1, 1, 1, 1, 3])
    with nav1:
        if st.button("\u23ee", key="sig_first"):
            st.session_state.signal_idx = 0
            st.session_state.cursor_x = float(x[0])
            st.rerun()
    with nav2:
        if st.button("\u25c0", key="sig_prev"):
            st.session_state.signal_idx = max(0, st.session_state.signal_idx - st.session_state.step_size)
            st.session_state.cursor_x = float(x[st.session_state.signal_idx])
            st.rerun()
    with nav3:
        if st.button("\u25b6", key="sig_next"):
            st.session_state.signal_idx = min(len(df) - 1, st.session_state.signal_idx + st.session_state.step_size)
            st.session_state.cursor_x = float(x[st.session_state.signal_idx])
            st.rerun()
    with nav4:
        if st.button("\u23ed", key="sig_last"):
            st.session_state.signal_idx = len(df) - 1
            st.session_state.cursor_x = float(x[st.session_state.signal_idx])
            st.rerun()
    with nav5:
        step = st.number_input("Шаг", min_value=1, max_value=len(df), value=st.session_state.step_size, key="step_input")
        if step != st.session_state.step_size:
            st.session_state.step_size = step

    st.caption(f"Запись {st.session_state.signal_idx} / {len(df) - 1}")

    cursor_idx = st.session_state.signal_idx

    channels_with_data = []
    for i, sig_col in enumerate(signal_cols):
        sig_str = df.iloc[cursor_idx][sig_col]
        signal = decode_v2_signal(str(sig_str))
        if len(signal) > 0:
            channels_with_data.append(i + 1)

    if channels_with_data:
        default_channels = ",".join(str(c) for c in channels_with_data)
    else:
        default_channels = "1-6"

    if "channel_input" not in st.session_state:
        st.session_state.channel_input = default_channels

    channel_input = st.text_input("Каналы (напр: 1-6, 1-4, [1,3,6])", value=st.session_state.channel_input, key="channel_input")
    selected_indices = parse_channel_range(channel_input, len(signal_cols))
    selected_channels = [signal_cols[i] for i in selected_indices if i < len(signal_cols)]
    st.caption(f"Доступно каналов: {len(signal_cols)} | Выбрано: {len(selected_channels)}")

    physical_signals = get_physical_signals(cursor_idx, signal_cols, df)

    for sig_col in selected_channels:
        st.markdown("---")
        sig_data = physical_signals.get(sig_col)

        if sig_data is not None:
            _render_signal_with_spectrum(sig_col, sig_data, cursor_idx, x, theme, show_grid, lock_x, lock_y, freq_min, freq_max, y_range_amp)
        else:
            _render_empty_charts(sig_col, theme, show_grid, lock_x, lock_y)

    if selected_channels:
        _render_batch_export(selected_channels, physical_signals, cursor_idx, x)


def _render_signal_with_spectrum(sig_col, sig_data, cursor_idx, x, theme, show_grid, lock_x, lock_y, freq_min, freq_max, y_range_amp):
    signal = sig_data["signal"]
    unit = sig_data["unit"]

    col_sig, col_spec = st.columns(2)

    with col_sig:
        t = np.linspace(0, len(signal) / DEFAULT_SAMPLE_RATE, len(signal)) * 1000

        is_current = "I_" in sig_col or "i_" in sig_col
        if y_range_amp > 0 and is_current:
            sig_y_min = -float(y_range_amp)
            sig_y_max = float(y_range_amp)
        else:
            sig_y_min = float(np.min(signal))
            sig_y_max = float(np.max(signal))

        fig_sig = go.Figure()
        fig_sig.add_trace(go.Scatter(x=t, y=signal, mode="lines",
                                     line=dict(color=theme["line_colors"][0], width=1)))
        fig_sig.update_layout(
            title=sig_col, height=200,
            xaxis_title="Время (мс)", yaxis_title=unit,
            paper_bgcolor=theme["paper"], plot_bgcolor=theme["bg"],
            font=dict(color=theme["text"]),
            hoverlabel=dict(bgcolor=theme["hover_bg"], font_color=theme["hover_text"]),
            xaxis=dict(gridcolor=theme["grid"], showgrid=show_grid,
                       fixedrange=lock_x,
                       tickfont=dict(color=theme["text"]),
                       title_font=dict(color=theme["text"])),
            yaxis=dict(gridcolor=theme["grid"], showgrid=show_grid,
                       fixedrange=lock_y, range=[sig_y_min, sig_y_max],
                       tickfont=dict(color=theme["text"]),
                       title_font=dict(color=theme["text"])),
            margin=dict(t=40, b=40),
        )
        st.plotly_chart(fig_sig, width="stretch",
                        config={"scrollZoom": not lock_x, "displayModeBar": not lock_x})

    with col_spec:
        sig = signal.astype(float) - np.mean(signal.astype(float))
        N = len(sig)
        yf = np.abs(np.fft.rfft(sig)) / N
        fr = np.fft.rfftfreq(N, 1 / DEFAULT_SAMPLE_RATE)

        mask = (fr >= freq_min) & (fr <= freq_max)
        fr_masked = fr[mask]
        yf_masked = yf[mask]

        spec_y_min = float(np.min(yf_masked)) if len(yf_masked) > 0 else 0
        spec_y_max = float(np.max(yf_masked)) if len(yf_masked) > 0 else 1

        fig_spec = go.Figure()
        fig_spec.add_trace(go.Scatter(x=fr_masked, y=yf_masked, mode="lines",
                                      line=dict(color=theme["line_colors"][1], width=1)))
        fig_spec.update_layout(
            title=f"{sig_col} {_MDASH} Спектр", height=200,
            xaxis_title="Частота (Гц)", yaxis_title="Амплитуда",
            paper_bgcolor=theme["paper"], plot_bgcolor=theme["bg"],
            font=dict(color=theme["text"]),
            hoverlabel=dict(bgcolor=theme["hover_bg"], font_color=theme["hover_text"]),
            xaxis=dict(gridcolor=theme["grid"], showgrid=show_grid,
                       fixedrange=lock_x,
                       tickfont=dict(color=theme["text"]),
                       title_font=dict(color=theme["text"])),
            yaxis=dict(gridcolor=theme["grid"], showgrid=show_grid,
                       fixedrange=lock_y,
                       tickfont=dict(color=theme["text"]),
                       title_font=dict(color=theme["text"])),
            margin=dict(t=40, b=40),
        )
        st.plotly_chart(fig_spec, width="stretch",
                        config={"scrollZoom": not lock_x, "displayModeBar": not lock_x})

    timestamp_ms = x[cursor_idx]
    dt_str = datetime.utcfromtimestamp(timestamp_ms / 1000).strftime('%Y%m%d_%H%M%S')

    signal_float32 = signal.astype(np.float32)
    st.download_button(
        label=f"\U0001f4be {sig_col}",
        data=signal_float32.tobytes(),
        file_name=f"{sig_col}_{dt_str}.bin",
        mime="application/octet-stream",
        key=f"save_{sig_col}",
    )


def _render_empty_charts(sig_col, theme, show_grid, lock_x, lock_y, zoom_factor, zoom_x_factor):
    col_sig, col_spec = st.columns(2)
    with col_sig:
        fig_empty = go.Figure()
        fig_empty.update_layout(
            title=sig_col, height=200,
            xaxis_title="Время (мс)", yaxis_title="В/А",
            paper_bgcolor=theme["paper"], plot_bgcolor=theme["bg"],
            font=dict(color=theme["text"]),
            xaxis=dict(gridcolor=theme["grid"], showgrid=show_grid,
                       fixedrange=lock_x,
                       tickfont=dict(color=theme["text"]),
                       title_font=dict(color=theme["text"])),
            yaxis=dict(gridcolor=theme["grid"], showgrid=show_grid,
                       fixedrange=lock_y,
                       tickfont=dict(color=theme["text"]),
                       title_font=dict(color=theme["text"])),
            margin=dict(t=40, b=40),
        )
        st.plotly_chart(fig_empty, width="stretch",
                        config={"scrollZoom": not lock_x, "displayModeBar": not lock_x})
    with col_spec:
        fig_empty_spec = go.Figure()
        fig_empty_spec.update_layout(
            title=f"{sig_col} {_MDASH} Спектр", height=200,
            xaxis_title="Частота (Гц)", yaxis_title="Амплитуда",
            paper_bgcolor=theme["paper"], plot_bgcolor=theme["bg"],
            font=dict(color=theme["text"]),
            xaxis=dict(gridcolor=theme["grid"], showgrid=show_grid,
                       fixedrange=lock_x,
                       tickfont=dict(color=theme["text"]),
                       title_font=dict(color=theme["text"])),
            yaxis=dict(gridcolor=theme["grid"], showgrid=show_grid,
                       fixedrange=lock_y,
                       tickfont=dict(color=theme["text"]),
                       title_font=dict(color=theme["text"])),
            margin=dict(t=40, b=40),
        )
        st.plotly_chart(fig_empty_spec, width="stretch",
                        config={"scrollZoom": not lock_x, "displayModeBar": not lock_x})


def _render_batch_export(selected_channels, physical_signals, cursor_idx, x):
    st.markdown("---")
    timestamp_ms = x[cursor_idx]
    dt_str = datetime.fromtimestamp(timestamp_ms / 1000).strftime('%Y%m%d_%H%M%S')

    all_signals = []
    for sig_col in selected_channels:
        sig_data = physical_signals.get(sig_col)
        if sig_data is not None:
            all_signals.append(sig_data["signal"].astype(np.float32))
        else:
            all_signals.append(np.array([], dtype=np.float32))

    if all_signals:
        max_len = max(len(s) for s in all_signals) if all_signals else 0
        if max_len > 0:
            matrix = np.zeros((max_len, len(all_signals)), dtype=np.float32)
            for i, sig in enumerate(all_signals):
                matrix[:len(sig), i] = sig
            st.download_button(
                label=f"\U0001f4be Все каналы ({len(selected_channels)} шт)",
                data=matrix.tobytes(),
                file_name=f"all_channels_{dt_str}.bin",
                mime="application/octet-stream",
                key="save_all",
            )
