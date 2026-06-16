from PyQt6.QtWidgets import (
    QMdiSubWindow, QTableView, QAbstractItemView, QVBoxLayout, QHBoxLayout, QPushButton,
    QMessageBox, QLineEdit, QWidget, QToolButton, QFileDialog
)
from PyQt6.QtGui import QIcon, QColor, QAction
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex
import PyQt6.QtCore as QtCore
import os

from Lib import read_tables_thread as rtt
from Lib import read_last_record_thread as last_rec_thr
from Lib import read_records_list_thread as rrlt
from Lib import pipestreamdbread as pdb
from ui.widgets import ResizableLineEdit
from ui.themes import ThemeManager

from core.module_base import BaseModule


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


class RecordsView_subwindow(BaseModule):
    data_to_plot_signal = QtCore.pyqtSignal(str, list, dict, int)
    record_list_signal = QtCore.pyqtSignal(list)

    def __init__(self, bus, parent=None):
        super().__init__(bus, parent)
        self.setWindowTitle("Выбор источника")
        self.setMinimumWidth(200)
        self._previous_width = 350

        self.model = RecordsTableModel([], parent=self)
        self.table_view = QTableView()
        self.table_view.setModel(self.model)
        self.table_view.resizeColumnsToContents()
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

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

        # === КНОПКА ОТКРЫТИЯ CSV v2 ===
        self.open_csv_button = QToolButton()
        self.open_csv_button.setText("CSV")
        self.open_csv_button.setToolTip("Открыть CSV v2 датасет")
        self.open_csv_button.setMinimumWidth(40)
        self.open_csv_button.clicked.connect(self.open_csv_v2_file)

        self.resize_button = QPushButton("↔")
        self.resize_button.setFixedWidth(30)
        self.resize_button.clicked.connect(self.toggle_resize)

        main_layout = QVBoxLayout()
        search_layout = QHBoxLayout()
        search_layout.addWidget(self.search_edit)
        search_layout.addWidget(self.open_csv_button)
        search_layout.addStretch()
        main_layout.addLayout(search_layout)

        table_layout = QHBoxLayout()
        table_layout.addWidget(self.table_view)
        table_layout.addWidget(self.resize_button, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        main_layout.addLayout(table_layout)

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

    def open_csv_v2_file(self):
        """Открытие CSV файла формата v2 и оповещение всех окон."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Открыть CSV v2 (датасет)",
            "",
            "CSV v2 файлы (*.raw.*.csv *.csv);;Все файлы (*)"
        )
        if not file_path:
            return

        device_name = os.path.basename(file_path)

        # Публикуем событие для trends_view и signals_view
        if self.bus:
            self.bus.publish("csv.file.opened", {
                'file_path': file_path,
                'device_name': device_name
            })

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
        msgBox.setText(f"Ошибка чтения БД: {text}")
        msgBox.exec()

    def apply_theme(self, theme_name: str):
        dark = theme_name == 'dark'
        palette = ThemeManager.get_palette(theme_name)
        self.setPalette(palette)
        self.MainWidget.setPalette(palette)
        self.MainWidget.setAutoFillBackground(True)
        self.table_view.setPalette(palette)
        self.search_edit.setPalette(palette)
        self.resize_button.setPalette(palette)
        self.open_csv_button.setPalette(palette)  # Стилизация кнопки CSV

        self.model.set_dark_theme(dark)

        line_edit_style = ThemeManager.get_line_edit_style(theme_name)
        self.search_edit.setStyleSheet(line_edit_style)

        btn_style = ThemeManager.get_button_style(theme_name)
        self.open_csv_button.setStyleSheet(btn_style)

        bg_color = "#404040" if dark else "#e0e0e0"
        text_color = "white" if dark else "black"
        border_color = "#555555" if dark else "#cccccc"
        hover_color = "#505050" if dark else "#d0d0d0"
        pressed_color = "#606060" if dark else "#c0c0c0"

        resize_button_style = f"""
            QPushButton {{
                background-color: {bg_color};
                color: {text_color};
                border: 2px solid {border_color};
                border-radius: 4px;
                padding: 5px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{ background-color: {hover_color}; }}
            QPushButton:pressed {{ background-color: {pressed_color}; }}
        """
        self.resize_button.setStyleSheet(resize_button_style)

        table_bg_color = "#353535" if dark else "white"
        grid_color = "#555555" if dark else "#d0d0d0"
        sel_bg_color = "#2a82da" if dark else "#4c9eff"
        sel_text_color = "black" if dark else "white"

        table_style = f"""
            QTableView {{
                background-color: {table_bg_color};
                gridline-color: {grid_color};
                selection-background-color: {sel_bg_color};
                selection-color: {sel_text_color};
                border: 1px solid {grid_color};
                border-radius: 3px;
                font-size: 9pt;
            }}
        """
        self.table_view.setStyleSheet(table_style)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.viewport().update()
        self.horizontal_header.update()
        self.vertical_header.update()
        self.model.layoutChanged.emit()