from PyQt6.QtWidgets import (
    QMdiSubWindow, QTableView, QAbstractItemView, QVBoxLayout, QHBoxLayout, QPushButton,
    QMessageBox, QLineEdit, QWidget, QToolButton, QFileDialog, QTreeView,
    QDialog, QLabel, QFormLayout, QScrollArea, QFrame, QMenu
)
from PyQt6.QtGui import QIcon, QColor, QAction, QFont, QPalette
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QAbstractItemModel, QSettings
import PyQt6.QtCore as QtCore
import os
import json
from datetime import datetime

from Lib import read_tables_thread as rtt
from Lib import read_last_record_thread as last_rec_thr
from Lib import read_records_list_thread as rrlt
from Lib import pipestreamdbread as pdb
from ui.widgets import ResizableLineEdit
from ui.themes import ThemeManager

from core.module_base import BaseModule


# ============================================================
# Модель для таблицы БД
# ============================================================
class RecordsTableModel(QAbstractTableModel):
    hheaders = ["Устройство", "Ш, Д", "Число записей", "Первая запись", "Последняя запись"]

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self._full_data = data
        self._data = data.copy() if isinstance(data, list) else data
        self._is_dark_theme = True

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self._data[0]) if self._data else 0

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return str(self._data[index.row()][index.column()])
        elif role == Qt.ItemDataRole.BackgroundRole:
            if index.row() % 2 == 1:
                return QColor(45, 45, 45) if self._is_dark_theme else QColor(245, 245, 245)
        elif role == Qt.ItemDataRole.ForegroundRole:
            return QColor(255, 255, 255) if self._is_dark_theme else QColor(0, 0, 0)
        return None

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.hheaders[section]
        elif role == Qt.ItemDataRole.BackgroundRole:
            return QColor(64, 64, 64) if self._is_dark_theme else QColor(224, 224, 224)
        elif role == Qt.ItemDataRole.ForegroundRole:
            return QColor(255, 255, 255) if self._is_dark_theme else QColor(0, 0, 0)
        return None

    def set_dark_theme(self, is_dark):
        self._is_dark_theme = is_dark
        self.layoutChanged.emit()

    def insertRow(self, row, row_data, parent=QModelIndex()):
        self.beginInsertRows(parent, row, row)
        self._full_data.insert(row, row_data)
        self._data.insert(row, row_data)
        self.endInsertRows()
        return True

    def removeRows(self, row, count, parent=QModelIndex()):
        self.beginRemoveRows(parent, row, row + count - 1)
        for i in range(count):
            del self._data[row]
        self.endRemoveRows()
        return True

    def filter_by_device(self, search_text):
        self.beginResetModel()
        if not search_text:
            self._data = self._full_data.copy()
        else:
            s = search_text.lower()
            self._data = [row for row in self._full_data if s in row[0].lower()]
        self.endResetModel()


# ============================================================
# Узел дерева датасетов
# ============================================================
class DatasetNode:
    def __init__(self, name, node_type="root", data=None, parent=None, chunks=0):
        self.name = name
        self.node_type = node_type  # "dataset" | "session"
        self.data = data or {}
        self.parent = parent
        self.children = []
        self.chunks = chunks  # количество чанков (для сессии — свои, для датасета — сумма)

    def add_child(self, child):
        child.parent = self
        self.children.append(child)

    def child_count(self):
        return len(self.children)

    def child_at(self, row):
        return self.children[row] if 0 <= row < len(self.children) else None

    def row(self):
        if self.parent:
            return self.parent.children.index(self)
        return 0


# ============================================================
# Модель дерева датасетов
# ============================================================
class DatasetTreeModel(QAbstractItemModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._root = DatasetNode("root", "root")
        self._is_dark_theme = True

    def set_dark_theme(self, is_dark):
        self._is_dark_theme = is_dark
        self.layoutChanged.emit()

    def clear(self):
        self.beginResetModel()
        self._root = DatasetNode("root", "root")
        self.endResetModel()

    def add_dataset(self, dataset_name, sessions):
        total_chunks = sum(sess.get("chunks", 0) for sess in sessions)
        dataset_node = DatasetNode(dataset_name, "dataset", {"name": dataset_name}, chunks=total_chunks)
        self._root.add_child(dataset_node)
        for sess in sessions:
            session_node = DatasetNode(
                sess["name"],
                "session",
                {
                    "raw_file": sess["raw_file"],
                    "folder_path": sess["folder_path"],
                    "full_path": os.path.join(sess["folder_path"], sess["raw_file"])
                },
                chunks=sess.get("chunks", 0)
            )
            dataset_node.add_child(session_node)

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        parent_node = parent.internalPointer() if parent.isValid() else self._root
        child_node = parent_node.child_at(row)
        if child_node:
            return self.createIndex(row, column, child_node)
        return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        child_node = index.internalPointer()
        parent_node = child_node.parent
        if parent_node == self._root or parent_node is None:
            return QModelIndex()
        return self.createIndex(parent_node.row(), 0, parent_node)

    def rowCount(self, parent=QModelIndex()):
        node = parent.internalPointer() if parent.isValid() else self._root
        return node.child_count()

    def columnCount(self, parent=QModelIndex()):
        return 1

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        node = index.internalPointer()

        if role == Qt.ItemDataRole.DisplayRole:
            if node.node_type == "dataset":
                return f"{node.name}  [{node.chunks}]"
            else:
                return f"{node.name}  [{node.chunks}]"
        elif role == Qt.ItemDataRole.ForegroundRole:
            return QColor(255, 255, 255) if self._is_dark_theme else QColor(0, 0, 0)
        elif role == Qt.ItemDataRole.BackgroundRole:
            if node.node_type == "dataset":
                return QColor(55, 55, 55) if self._is_dark_theme else QColor(220, 220, 220)
            # Для сессий — чётные/нечётные строки в пределах родителя
            row = index.row()
            if row % 2 == 1:
                return QColor(45, 45, 45) if self._is_dark_theme else QColor(245, 245, 245)
            return QColor(35, 35, 35) if self._is_dark_theme else QColor(255, 255, 255)
        elif role == Qt.ItemDataRole.UserRole:
            return node.data
        elif role == Qt.ItemDataRole.FontRole:
            font = QFont()
            if node.node_type == "dataset":
                font.setBold(True)
            return font
        return None

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return "Датасеты и сессии"
        return None


# ============================================================
# Окно просмотра метаданных датасета
# ============================================================
class DatasetMetadataDialog(QDialog):
    """Окно метаданных ДАТАСЕТА — общая информация, без каналов/нагрузок/путей."""

    def __init__(self, meta, loads, subclass_map, theme_name="dark", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Метаданные датасета")
        self.setMinimumWidth(450)
        self.setMinimumHeight(300)
        self._theme_name = theme_name
        self._meta = meta
        self._loads = loads
        self._subclass_map = subclass_map
        self._build_ui()
        self.apply_theme(theme_name)

    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # === Основная информация ===
        layout.addWidget(self._section_title("Основная информация"))
        form = QFormLayout()
        form.setSpacing(8)

        name = self._meta.get("name", "—")
        created = self._fmt_datetime(self._meta.get("created_at"))
        org = self._meta.get("org_code", "—")
        stand = self._meta.get("stand_id", "—")
        annotation = self._meta.get("annotation", "—")
        chunks = str(self._meta.get("chunks_count", "—"))
        folder = self._meta.get("folder_name", "—")

        form.addRow("Название:", self._value_label(name))
        form.addRow("Папка:", self._value_label(folder))
        form.addRow("Дата создания:", self._value_label(created))
        form.addRow("Организация:", self._value_label(org))
        form.addRow("Стенд:", self._value_label(stand))
        form.addRow("Аннотация:", self._value_label(annotation))
        form.addRow("Чанков всего:", self._value_label(chunks))
        layout.addLayout(form)

        # === Период записи ===
        layout.addWidget(self._section_title("Период записи"))
        rec_start = self._fmt_datetime(self._meta.get("rec_start_datetime"))
        rec_end = self._fmt_datetime(self._meta.get("rec_end_datetime"))
        period = f"{rec_start} — {rec_end}" if rec_end else f"с {rec_start} (не завершено)"
        layout.addWidget(self._value_label(period))

        # === Список сессий (кратко) ===
        layout.addWidget(self._section_title("Список сессий"))
        sessions = self._meta.get("sessions", [])
        if sessions:
            for sess in sessions:
                sess_name = sess.get("name", "—")
                start = self._fmt_datetime(sess.get("start_time"))
                end = self._fmt_datetime(sess.get("end_time"))
                text = f"• {sess_name}  ({start} — {end})"
                layout.addWidget(self._value_label(text))
        else:
            layout.addWidget(self._value_label("Сессии отсутствуют"))

        layout.addStretch()
        scroll.setWidget(container)

        dlg_layout = QVBoxLayout(self)
        dlg_layout.addWidget(scroll)

        btn = QPushButton("Закрыть")
        btn.clicked.connect(self.accept)
        dlg_layout.addWidget(btn)

    def _section_title(self, text):
        lbl = QLabel(text)
        font = QFont()
        font.setBold(True)
        font.setPointSize(11)
        lbl.setFont(font)
        return lbl

    def _value_label(self, text):
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        return lbl

    def _fmt_datetime(self, dt_str):
        if not dt_str:
            return "—"
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            return dt.strftime("%d.%m.%Y %H:%M:%S")
        except Exception:
            return str(dt_str)

    def apply_theme(self, theme_name):
        self._theme_name = theme_name
        dark = theme_name == "dark"
        bg = "#2d2d2d" if dark else "#f5f5f5"
        text = "#ffffff" if dark else "#000000"
        section_color = "#4a9eff" if dark else "#0066cc"

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {bg};
                color: {text};
            }}
            QLabel {{
                color: {text};
                font-size: 10pt;
            }}
            QPushButton {{
                background-color: {"#404040" if dark else "#e0e0e0"};
                color: {text};
                border: 1px solid {"#555555" if dark else "#cccccc"};
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 10pt;
            }}
            QPushButton:hover {{
                background-color: {"#505050" if dark else "#d0d0d0"};
            }}
            QScrollArea {{
                border: none;
                background-color: {bg};
            }}
        """)

        for child in self.findChildren(QLabel):
            if child.font().bold() and child.font().pointSize() == 11:
                child.setStyleSheet(f"color: {section_color};")


class SessionMetadataDialog(QDialog):
    """Окно метаданных ЗАПИСИ (сессии) — каналы, нагрузки, время, пути, длительность."""

    def __init__(self, meta, session, loads, subclass_map, theme_name="dark", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Метаданные записи: {session.get('name', '—')}")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self._theme_name = theme_name
        self._meta = meta
        self._session = session
        self._loads = loads
        self._subclass_map = subclass_map
        self._build_ui()
        self.apply_theme(theme_name)

    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # === К какому датасету относится ===
        layout.addWidget(self._section_title("Датасет"))
        ds_name = self._meta.get("name", "—")
        ds_org = self._meta.get("org_code", "—")
        ds_stand = self._meta.get("stand_id", "—")
        layout.addWidget(self._value_label(f"{ds_name}  (орг: {ds_org}, стенд: {ds_stand})"))

        # === Информация о записи ===
        layout.addWidget(self._section_title("Информация о записи"))
        form = QFormLayout()
        form.setSpacing(8)

        sess_name = self._session.get("name", "—")
        start = self._fmt_datetime(self._session.get("start_time"))
        end = self._fmt_datetime(self._session.get("end_time"))
        duration = self._calc_duration(self._session.get("start_time"), self._session.get("end_time"))
        chunks = str(self._session.get("chunks_count", "—"))
        annotation = self._session.get("annotation", "—")

        form.addRow("Название:", self._value_label(sess_name))
        form.addRow("Начало:", self._value_label(start))
        form.addRow("Конец:", self._value_label(end))
        form.addRow("Длительность:", self._value_label(duration))
        form.addRow("Чанков:", self._value_label(chunks))
        if annotation:
            form.addRow("Аннотация:", self._value_label(annotation))
        layout.addLayout(form)

        # === Файлы ===
        layout.addWidget(self._section_title("Файлы"))
        raw = self._session.get("raw_file", "—")
        markup = self._session.get("markup_file", "—")
        layout.addWidget(self._value_label(f"Raw:    {raw}"))
        layout.addWidget(self._value_label(f"Markup: {markup}"))

        # === Каналы и нагрузки ===
        layout.addWidget(self._section_title("Каналы и нагрузки"))
        channel_map = self._session.get("channel_map", {})
        if channel_map:
            ch_form = QFormLayout()
            ch_form.setSpacing(8)
            for ch, load_id in channel_map.items():
                if load_id and load_id in self._loads:
                    load = self._loads[load_id]
                    load_name = load.get("name", load_id)
                    subclass = load.get("subclass", "—")
                    subclass_desc = self._subclass_map.get(subclass, subclass)
                    pmax = load.get("pmax", "—")
                    phase = load.get("phase_num", "—")
                    is_target = "✓ целевая" if load.get("is_target") else ""
                    text = f"{load_name} ({subclass_desc}, {pmax} Вт, {phase}) {is_target}"
                else:
                    text = "не назначена"
                ch_form.addRow(f"{ch}:", self._value_label(text))
            layout.addLayout(ch_form)
        else:
            layout.addWidget(self._value_label("Каналы не назначены"))

        layout.addStretch()
        scroll.setWidget(container)

        dlg_layout = QVBoxLayout(self)
        dlg_layout.addWidget(scroll)

        btn = QPushButton("Закрыть")
        btn.clicked.connect(self.accept)
        dlg_layout.addWidget(btn)

    def _section_title(self, text):
        lbl = QLabel(text)
        font = QFont()
        font.setBold(True)
        font.setPointSize(11)
        lbl.setFont(font)
        return lbl

    def _value_label(self, text):
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        return lbl

    def _fmt_datetime(self, dt_str):
        if not dt_str:
            return "—"
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            return dt.strftime("%d.%m.%Y %H:%M:%S")
        except Exception:
            return str(dt_str)

    def _calc_duration(self, start_str, end_str):
        if not start_str or not end_str:
            return "—"
        try:
            start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            delta = end - start
            hours, remainder = divmod(delta.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{delta.days}д {hours:02d}:{minutes:02d}:{seconds:02d}" if delta.days else f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        except Exception:
            return "—"

    def apply_theme(self, theme_name):
        self._theme_name = theme_name
        dark = theme_name == "dark"
        bg = "#2d2d2d" if dark else "#f5f5f5"
        text = "#ffffff" if dark else "#000000"
        section_color = "#4a9eff" if dark else "#0066cc"
        frame_bg = "#3d3d3d" if dark else "#e8e8e8"

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {bg};
                color: {text};
            }}
            QLabel {{
                color: {text};
                font-size: 10pt;
            }}
            QPushButton {{
                background-color: {"#404040" if dark else "#e0e0e0"};
                color: {text};
                border: 1px solid {"#555555" if dark else "#cccccc"};
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 10pt;
            }}
            QPushButton:hover {{
                background-color: {"#505050" if dark else "#d0d0d0"};
            }}
            QScrollArea {{
                border: none;
                background-color: {bg};
            }}
            QFrame {{
                background-color: {frame_bg};
                border: 1px solid {"#555555" if dark else "#cccccc"};
                border-radius: 6px;
            }}
        """)

        for child in self.findChildren(QLabel):
            if child.font().bold() and child.font().pointSize() == 11:
                child.setStyleSheet(f"color: {section_color};")


# ============================================================
# Основное окно
# ============================================================
class RecordsView_subwindow(BaseModule):
    data_to_plot_signal = QtCore.pyqtSignal(str, list, dict, int)
    record_list_signal = QtCore.pyqtSignal(list)

    MODE_DB = "db"
    MODE_CSV = "csv"

    def __init__(self, bus, parent=None):
        super().__init__(bus, parent)
        self.setWindowTitle("Выбор источника")
        self.setMinimumWidth(200)
        self._previous_width = 350
        self._current_theme = "dark"

        self._current_mode = self.MODE_DB
        self._settings = QSettings("Lartech", "RecordsView")
        self._csv_base_path = self._settings.value("csv_base_path", "")
        self._datasets_meta = {}
        self._loads = {}
        self._subclass_map = {}

        self.model = RecordsTableModel([], parent=self)
        self.tree_model = DatasetTreeModel(parent=self)

        self.table_view = QTableView()
        self.table_view.setModel(self.model)
        self.table_view.resizeColumnsToContents()
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self.tree_view = QTreeView()
        self.tree_view.setModel(self.tree_model)
        self.tree_view.setHeaderHidden(False)
        self.tree_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # AlternatingRowColors отключено — управляем через модель
        self.tree_view.clicked.connect(self.on_tree_item_clicked)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.on_tree_context_menu)
        self.tree_view.setVisible(False)

        self.horizontal_header = self.table_view.horizontalHeader()
        self.vertical_header = self.table_view.verticalHeader()

        selection_model = self.table_view.selectionModel()
        selection_model.selectionChanged.connect(self.row_selection_event_handler)

        self.search_edit = ResizableLineEdit(parent=self)
        self.search_edit.setPlaceholderText("Поиск по устройству")
        self.search_edit.setMinimumWidth(150)
        search_icon = QIcon("./icons/search.png")
        search_action = QAction(search_icon, "Поиск устройства", self.search_edit)
        self.search_edit.addAction(search_action, QLineEdit.ActionPosition.LeadingPosition)
        self.search_edit.textChanged.connect(self.filter_table)

        self.btn_mode_db = QPushButton("БД")
        self.btn_mode_db.setCheckable(True)
        self.btn_mode_db.setChecked(True)
        self.btn_mode_db.clicked.connect(lambda: self.set_mode(self.MODE_DB))

        self.btn_mode_csv = QPushButton("CSV")
        self.btn_mode_csv.setCheckable(True)
        self.btn_mode_csv.setChecked(False)
        self.btn_mode_csv.clicked.connect(lambda: self.set_mode(self.MODE_CSV))

        self.btn_select_csv_folder = QToolButton()
        self.btn_select_csv_folder.setText("📁")
        self.btn_select_csv_folder.setToolTip("Выбрать папку с датасетами")
        self.btn_select_csv_folder.setMinimumWidth(30)
        self.btn_select_csv_folder.clicked.connect(self.select_csv_folder)
        self.btn_select_csv_folder.setVisible(False)

        self.resize_button = QPushButton("↔")
        self.resize_button.setFixedWidth(30)
        self.resize_button.clicked.connect(self.toggle_resize)

        mode_layout = QHBoxLayout()
        mode_layout.addWidget(self.btn_mode_db)
        mode_layout.addWidget(self.btn_mode_csv)
        mode_layout.addWidget(self.btn_select_csv_folder)
        mode_layout.addStretch()

        search_layout = QHBoxLayout()
        search_layout.addWidget(self.search_edit)
        search_layout.addStretch()

        top_layout = QVBoxLayout()
        top_layout.addLayout(mode_layout)
        top_layout.addLayout(search_layout)

        content_layout = QHBoxLayout()
        content_layout.addWidget(self.table_view)
        content_layout.addWidget(self.tree_view)
        content_layout.addWidget(self.resize_button, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

        main_layout = QVBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addLayout(content_layout)

        self.MainWidget = QWidget()
        self.MainWidget.setLayout(main_layout)
        self.setWidget(self.MainWidget)

        self.ReadTablesThread = rtt.ReadTablesThread()
        self.ReadTablesThread.error_signal.connect(self.on_error_message)
        self.ReadTablesThread.result_signal.connect(self.on_rtt_result_message)
        self.ReadTablesThread.start()

        self.register_topics()

    def register_topics(self):
        return

    def set_mode(self, mode):
        if mode == self._current_mode:
            return
        self._current_mode = mode

        if mode == self.MODE_DB:
            self.btn_mode_db.setChecked(True)
            self.btn_mode_csv.setChecked(False)
            self.table_view.setVisible(True)
            self.tree_view.setVisible(False)
            self.search_edit.setVisible(True)
            self.btn_select_csv_folder.setVisible(False)
            self.setWindowTitle("Выбор источника — БД")
        else:
            self.btn_mode_db.setChecked(False)
            self.btn_mode_csv.setChecked(True)
            self.table_view.setVisible(False)
            self.tree_view.setVisible(True)
            self.search_edit.setVisible(False)
            self.btn_select_csv_folder.setVisible(True)
            self.setWindowTitle("Выбор источника — CSV")

            if not self._csv_base_path or not os.path.isdir(self._csv_base_path):
                self.select_csv_folder()
            else:
                self.load_datasets()

    def select_csv_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку с датасетами",
            self._csv_base_path or ""
        )
        if not folder:
            if not self._csv_base_path:
                self.set_mode(self.MODE_DB)
            return

        self._csv_base_path = folder
        self._settings.setValue("csv_base_path", folder)
        self.load_datasets()

    def load_datasets(self):
        if not self._csv_base_path:
            return

        data_dir = self._csv_base_path
        if not os.path.isdir(data_dir):
            self.on_error_message(f"Папка не найдена: {data_dir}")
            return

        datasets_dir = os.path.join(data_dir, "datasets")
        if not os.path.isdir(datasets_dir):
            self.on_error_message(f"Подпапка datasets/ не найдена в {data_dir}")
            return

        self._loads = {}
        self._subclass_map = {}
        self._datasets_meta = {}

        for filename, target_dict, key_in_json in [
            ("loads.json", self._loads, "loads"),
            ("subclass_map.json", self._subclass_map, "subclasses"),
        ]:
            found = False
            for base in [data_dir, datasets_dir]:
                filepath = os.path.join(base, filename)
                if os.path.exists(filepath):
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            target_dict.update(data.get(key_in_json, {}))
                        found = True
                        break
                    except Exception:
                        pass

        datasets_index = {"datasets": []}
        for base in [data_dir, datasets_dir]:
            idx_path = os.path.join(base, "datasets.json")
            if os.path.exists(idx_path):
                try:
                    with open(idx_path, "r", encoding="utf-8") as f:
                        datasets_index = json.load(f)
                    break
                except Exception:
                    pass

        self.tree_model.clear()
        found_any = False

        for entry in sorted(os.listdir(datasets_dir)):
            folder_path = os.path.join(datasets_dir, entry)
            if not os.path.isdir(folder_path):
                continue

            meta_path = os.path.join(folder_path, "meta.json")
            if not os.path.exists(meta_path):
                continue

            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception as e:
                self.on_error_message(f"Ошибка чтения {meta_path}: {e}")
                continue

            self._datasets_meta[meta.get("dataset_id", entry)] = meta

            dataset_name = meta.get("name", entry)
            for ds_info in datasets_index.get("datasets", []):
                if ds_info.get("folder_name") == entry:
                    dataset_name = ds_info.get("name", dataset_name)
                    break

            sessions = []
            for sess in meta.get("sessions", []):
                raw_file = sess.get("raw_file", "")
                raw_full_path = os.path.join(folder_path, raw_file)
                if raw_file and os.path.exists(raw_full_path):
                    sessions.append({
                        "name": sess.get("name", raw_file),
                        "raw_file": raw_file,
                        "folder_path": folder_path,
                        "chunks": sess.get("chunks_count", 0)
                    })

            if sessions:
                self.tree_model.add_dataset(dataset_name, sessions)
                found_any = True

        if not found_any:
            self.on_error_message(f"В папке {datasets_dir} не найдено датасетов с meta.json")

        self.tree_view.expandAll()
        self.apply_theme(self._current_theme)

    def on_tree_item_clicked(self, index):
        if not index.isValid():
            return
        node = index.internalPointer()
        if node.node_type != "session":
            return

        data = node.data
        full_path = data.get("full_path", "")
        device_name = node.name

        if not full_path or not os.path.exists(full_path):
            self.on_error_message(f"Файл не найден: {full_path}")
            return

        if self.bus:
            self.bus.publish("csv.file.opened", {
                "file_path": full_path,
                "device_name": device_name
            })

    def on_tree_context_menu(self, position):
        index = self.tree_view.indexAt(position)
        if not index.isValid():
            return
        node = index.internalPointer()

        # Находим meta по имени датасета (родитель сессии = датасет)
        meta = None
        if node.node_type == "session":
            # Ищем датасет-родителя
            parent_node = node.parent
            if parent_node:
                for m in self._datasets_meta.values():
                    if m.get("name") == parent_node.name:
                        meta = m
                        break
        elif node.node_type == "dataset":
            for m in self._datasets_meta.values():
                if m.get("name") == node.name:
                    meta = m
                    break

        if not meta:
            return

        menu = QMenu(self)
        menu.setToolTipsVisible(True)

        dark = self._current_theme == "dark"
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {"#2d2d2d" if dark else "#f5f5f5"};
                color: {"#ffffff" if dark else "#000000"};
                border: 1px solid {"#555555" if dark else "#cccccc"};
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 24px;
                font-size: 10pt;
            }}
            QMenu::item:selected {{
                background-color: {"#4a9eff" if dark else "#0066cc"};
                color: #ffffff;
            }}
            QMenu::item:hover {{
                background-color: {"#4a9eff" if dark else "#0066cc"};
                color: #ffffff;
            }}
            QToolTip {{
                background-color: {"#404040" if dark else "#ffffe0"};
                color: {"#ffffff" if dark else "#000000"};
                border: 1px solid {"#666666" if dark else "#cccccc"};
                padding: 4px;
                font-size: 9pt;
            }}
        """)

        if node.node_type == "dataset":
            action = menu.addAction("📋  Просмотреть метаданные датасета")
            action.setToolTip("Общая информация о датасете: название, дата, организация, стенд, период записи")
            action.triggered.connect(lambda: self.show_dataset_metadata_dialog(meta))
        elif node.node_type == "session":
            # Находим сессию в meta
            sess = None
            for s in meta.get("sessions", []):
                if s.get("name") == node.name:
                    sess = s
                    break
            if sess:
                action = menu.addAction("📄  Просмотреть метаданные записи")
                action.setToolTip("Подробная информация о записи: каналы, нагрузки, время, файлы, длительность")
                action.triggered.connect(lambda: self.show_session_metadata_dialog(meta, sess))

        menu.exec(self.tree_view.viewport().mapToGlobal(position))

    def show_dataset_metadata_dialog(self, meta):
        dlg = DatasetMetadataDialog(
            meta, self._loads, self._subclass_map,
            theme_name=self._current_theme, parent=self
        )
        dlg.exec()

    def show_session_metadata_dialog(self, meta, session):
        dlg = SessionMetadataDialog(
            meta, session, self._loads, self._subclass_map,
            theme_name=self._current_theme, parent=self
        )
        dlg.exec()

    def on_rtt_result_message(self, result):
        device = result.get("device", "-")
        first_records = result.get("first_records", "-")
        last_records = result.get("last_records", "-")
        gps_latitude = result.get("gps_latitude", "-")
        gps_longitude = result.get("gps_longitude", "-")
        record_num = result.get("record_num", "-")

        first_records = str(pdb.datetime_from_timestamp(first_records))[:-4] if first_records != "-" else "-"
        last_records = str(pdb.datetime_from_timestamp(last_records))[:-4] if last_records != "-" else "-"

        row = [device, f"{gps_latitude}, {gps_longitude}", record_num, first_records, last_records]
        self.model.insertRow(self.model.rowCount(), row)
        self.table_view.resizeColumnsToContents()
        self.filter_table(self.search_edit.text())

    def row_selection_event_handler(self, selected, deselected):
        if selected:
            ind = selected.indexes()[0]
            device_name = self.model.data(self.model.index(ind.row(), 0))

            self.ReadLastRecordThread = last_rec_thr.ReadLastRecordThread(device_name)
            self.ReadLastRecordThread.error_signal.connect(self.on_error_message)
            self.ReadLastRecordThread.result_signal.connect(self.on_last_rec_message)
            self.ReadLastRecordThread.start()

            self.ReadRecordListThread = rrlt.ReadRecordListThread(device_name)
            self.ReadRecordListThread.error_signal.connect(self.on_error_message)
            self.ReadRecordListThread.result_signal.connect(self.on_rrlt_result_message)
            self.ReadRecordListThread.start()

    def on_rrlt_result_message(self, result_list):
        self.publish("record.list", result_list)
        self.record_list_signal.emit(result_list)

    def on_last_rec_message(self, table_name, column_list, result_dict, rec_num):
        payload = {
            "table_name": table_name,
            "columns": column_list,
            "data": result_dict,
            "rec_num": rec_num
        }
        self.publish("record.selected", payload)
        self.data_to_plot_signal.emit(table_name, column_list, result_dict, rec_num)

    def filter_table(self, text):
        self.model.filter_by_device(text)
        self.table_view.resizeColumnsToContents()

    def toggle_resize(self):
        if self.width() < 300:
            new_width = self._previous_width
        else:
            self._previous_width = self.width()
            new_width = 250
        self.resize(new_width, self.height())
        self.publish("RESIZE_RECORDS_PANEL", {"width": new_width})

    def on_error_message(self, text):
        msgBox = QMessageBox()
        msgBox.setText(f"Ошибка: {text}")
        msgBox.exec()

    # ========================================================
    # Темы — адаптивные, без хардкода
    # ========================================================
    def apply_theme(self, theme_name: str):
        self._current_theme = theme_name
        dark = theme_name == "dark"
        palette = ThemeManager.get_palette(theme_name)
        self.setPalette(palette)
        self.MainWidget.setPalette(palette)
        self.MainWidget.setAutoFillBackground(True)
        self.table_view.setPalette(palette)
        self.tree_view.setPalette(palette)
        self.search_edit.setPalette(palette)
        self.resize_button.setPalette(palette)
        self.btn_mode_db.setPalette(palette)
        self.btn_mode_csv.setPalette(palette)
        self.btn_select_csv_folder.setPalette(palette)

        self.model.set_dark_theme(dark)
        self.tree_model.set_dark_theme(dark)

        # Получаем цвета из палитры для адаптивных стилей
        window_col = palette.color(QPalette.ColorRole.Window).name()
        window_text = palette.color(QPalette.ColorRole.WindowText).name()
        base_col = palette.color(QPalette.ColorRole.Base).name()
        alt_base = palette.color(QPalette.ColorRole.AlternateBase).name()
        button_col = palette.color(QPalette.ColorRole.Button).name()
        button_text = palette.color(QPalette.ColorRole.ButtonText).name()
        highlight = palette.color(QPalette.ColorRole.Highlight).name()
        highlighted_text = palette.color(QPalette.ColorRole.HighlightedText).name()
        text_col = palette.color(QPalette.ColorRole.Text).name()

        # Стиль для QLineEdit — берём цвета из палитры
        line_edit_style = f"""
            QLineEdit {{
                background-color: {base_col};
                color: {text_col};
                border: 1px solid {"#555555" if dark else "#cccccc"};
                border-radius: 4px;
                padding: 4px;
                font-size: 9pt;
            }}
        """
        self.search_edit.setStyleSheet(line_edit_style)

        # Стиль для кнопок — берём цвета из палитры
        btn_style = f"""
            QPushButton, QToolButton {{
                background-color: {button_col};
                color: {button_text};
                border: 1px solid {"#555555" if dark else "#cccccc"};
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 9pt;
            }}
            QPushButton:hover, QToolButton:hover {{
                background-color: {"#505050" if dark else "#d0d0d0"};
            }}
            QPushButton:checked {{
                background-color: {highlight};
                color: {highlighted_text};
            }}
        """
        self.btn_mode_db.setStyleSheet(btn_style)
        self.btn_mode_csv.setStyleSheet(btn_style)
        self.btn_select_csv_folder.setStyleSheet(btn_style)

        # Resize button
        resize_style = f"""
            QPushButton {{
                background-color: {button_col};
                color: {button_text};
                border: 2px solid {"#555555" if dark else "#cccccc"};
                border-radius: 4px;
                padding: 5px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {"#505050" if dark else "#d0d0d0"};
            }}
        """
        self.resize_button.setStyleSheet(resize_style)

        # Таблица — цвета из палитры
        table_style = f"""
            QTableView {{
                background-color: {base_col};
                gridline-color: {"#555555" if dark else "#d0d0d0"};
                selection-background-color: {highlight};
                selection-color: {highlighted_text};
                border: 1px solid {"#555555" if dark else "#d0d0d0"};
                border-radius: 3px;
                font-size: 9pt;
            }}
            QHeaderView::section {{
                background-color: {alt_base};
                color: {text_col};
                padding: 5px;
                border: 1px solid {"#555555" if dark else "#cccccc"};
                font-weight: bold;
            }}
        """
        self.table_view.setStyleSheet(table_style)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.viewport().update()
        self.horizontal_header.update()
        self.vertical_header.update()
        self.model.layoutChanged.emit()

        self.apply_tree_theme()

    def apply_tree_theme(self):
        dark = self._current_theme == "dark"
        palette = self.palette()
        bg = palette.color(QPalette.ColorRole.Base).name()
        text = palette.color(QPalette.ColorRole.Text).name()
        highlight = palette.color(QPalette.ColorRole.Highlight).name()
        highlighted_text = palette.color(QPalette.ColorRole.HighlightedText).name()
        alt_base = palette.color(QPalette.ColorRole.AlternateBase).name()

        tree_style = f"""
            QTreeView {{
                background-color: {bg};
                color: {text};
                border: 1px solid {"#555555" if dark else "#d0d0d0"};
                border-radius: 3px;
                font-size: 9pt;
                outline: none;
            }}
            QTreeView::item {{
                padding: 4px;
                border: none;
            }}
            QTreeView::item:selected {{
                background-color: {highlight};
                color: {highlighted_text};
            }}
            QTreeView::item:hover {{
                background-color: {"#404040" if dark else "#e8f0fe"};
            }}
            QHeaderView::section {{
                background-color: {alt_base};
                color: {text};
                padding: 5px;
                border: 1px solid {"#555555" if dark else "#cccccc"};
                font-weight: bold;
            }}
        """
        self.tree_view.setStyleSheet(tree_style)
        self.tree_view.viewport().update()