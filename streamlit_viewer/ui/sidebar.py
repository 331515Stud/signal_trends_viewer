import os

import streamlit as st

from adapters.file_loader import load_csv, load_meta_json, format_local_time

_MDASH = "\u2014"


def render_sidebar():
    with st.sidebar:
        st.radio("Тема", ["dark", "light"],
                  index=0 if st.session_state.theme == "dark" else 1,
                  horizontal=True, key="theme")

        st.divider()
        st.subheader("Настройки графиков")
        st.checkbox("Сетка", value=True, key="show_grid")
        st.checkbox("\U0001f512 Фикс X", value=True, key="lock_x")
        st.checkbox("\U0001f512 Фикс Y", value=True, key="lock_y")

        st.number_input(
            "Диапазон тока (А)", min_value=0, max_value=10000, value=0, step=1,
            key="y_range_amperes",
            help="0 = автоматический масштаб. Задайте значение для фиксированного диапазона (например 20 → от -20 до 20 А). Влияет только на каналы тока (I_*)",
        )

        st.divider()
        st.subheader("Фильтр частот")
        st.number_input("Мин. частота (Гц)", 0, 12800, 0, key="freq_min")
        st.number_input("Макс. частота (Гц)", 0, 12800, 12800, key="freq_max")

        st.divider()
        st.subheader("\U0001f4c2 CSV файл")
        uploaded_csv = st.file_uploader("Загрузить CSV", type=["csv"], key="csv_uploader")
        if uploaded_csv is not None:
            if st.button("\U0001f4c4 Загрузить CSV", key="load_single_csv"):
                st.session_state.selected_file = uploaded_csv.name
                st.session_state.cursor_x = None
                st.session_state.active_session_name = uploaded_csv.name
                st.session_state.active_dataset_name = None
                try:
                    st.session_state.df = load_csv(uploaded_csv)
                except Exception as e:
                    st.error(f"Ошибка: {e}")
                    st.session_state.df = None

        st.divider()
        st.subheader("\U0001f4c2 Датасеты")
        csv_path = st.text_input("Папка с датасетами", key="csv_path_input")

        if csv_path and os.path.isdir(csv_path):
            datasets_dir = os.path.join(csv_path, "datasets")
            if os.path.isdir(datasets_dir):
                _render_datasets_tree(datasets_dir)


def _render_datasets_tree(datasets_dir):
    for entry in sorted(os.listdir(datasets_dir)):
        folder = os.path.join(datasets_dir, entry)
        meta = load_meta_json(folder)
        if meta is None:
            continue
        ds_name = meta.get("name", entry)
        chunks_total = meta.get("chunks_count", 0)

        with st.expander(f"\U0001f4c1 {ds_name} [{chunks_total}]", expanded=False):
            st.caption(f"Организация: {meta.get('org_code', _MDASH)}")
            st.caption(f"Стенд: {meta.get('stand_id', _MDASH)}")
            st.caption(f"Аннотация: {meta.get('annotation', _MDASH)}")

            for sess in meta.get("sessions", []):
                sess_name = sess.get("name", "?")
                sess_chunks = sess.get("chunks_count", 0)
                raw_file = sess.get("raw_file", "")
                raw_path = os.path.join(folder, raw_file)

                if not os.path.exists(raw_path):
                    continue

                col1, col2 = st.columns([4, 1])
                with col1:
                    if st.button(
                        f"\U0001f4c4 {sess_name} [{sess_chunks}]",
                        key=f"sess_{entry}_{sess_name}_{sess_chunks}",
                    ):
                        st.session_state.selected_file = raw_path
                        st.session_state.cursor_x = None
                        st.session_state.active_session_name = sess_name
                        st.session_state.active_dataset_name = ds_name
                        try:
                            st.session_state.df = load_csv(raw_path)
                        except Exception as e:
                            st.error(f"Ошибка: {e}")
                            st.session_state.df = None
                with col2:
                    meta_key = f"meta_{entry}_{sess_name}_{sess_chunks}"
                    if st.button("\U0001f4cb", key=meta_key):
                        open_metas = st.session_state.get("open_meta_keys", set())
                        open_meta_data = st.session_state.get("open_meta_data", {})
                        if meta_key in open_metas:
                            open_metas.discard(meta_key)
                            open_meta_data.pop(meta_key, None)
                        else:
                            open_metas.add(meta_key)
                            open_meta_data[meta_key] = {
                                "entry": entry,
                                "dataset": ds_name,
                                "session": sess_name,
                                "raw_file": raw_file,
                                "chunks": sess_chunks,
                                "org": meta.get("org_code", _MDASH),
                                "stand": meta.get("stand_id", _MDASH),
                                "annotation": sess.get("annotation", _MDASH),
                                "start": sess.get("start_time", _MDASH),
                                "end": sess.get("end_time", _MDASH),
                                "channel_map": sess.get("channel_map", {}),
                            }
                        st.session_state.open_meta_keys = open_metas
                        st.session_state.open_meta_data = open_meta_data

                if meta_key in st.session_state.get("open_meta_keys", set()):
                    st.markdown(
                        '<div style="border-left:3px solid #4CAF50;padding:4px 8px;'
                        'margin:2px 0;border-radius:4px;">',
                        unsafe_allow_html=True,
                    )
                    _render_inline_meta(st.session_state.open_meta_data.get(meta_key, {}))
                    st.markdown("</div>", unsafe_allow_html=True)


def _render_inline_meta(m):
    with st.container():
        st.caption(f"\U0001f4cb **{m['session']}**")
        c1, c2 = st.columns(2)
        with c1:
            st.caption(f"Датасет: {m['dataset']}")
            st.caption(f"Файл: {m['raw_file']}")
            st.caption(f"Чанков: {m['chunks']}")
            st.caption(f"Организация: {m['org']}")
        with c2:
            st.caption(f"Стенд: {m['stand']}")
            st.caption(f"Аннотация: {m['annotation']}")
            st.caption(f"Начало: {format_local_time(m['start'])}")
            st.caption(f"Конец: {format_local_time(m['end'])}")
        if m["channel_map"]:
            st.caption("Каналы:")
            for ch, load in m["channel_map"].items():
                st.caption(f"  {ch}: {load}")
