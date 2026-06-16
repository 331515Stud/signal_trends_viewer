from PyQt6.QtWidgets import (
    QMdiSubWindow, QToolBar, QScrollArea, QToolButton, QLabel, QSlider,
    QCheckBox, QSizePolicy, QMessageBox, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QFileDialog
)
from PyQt6.QtGui import QIcon, QAction, QPalette, QColor
from PyQt6.QtCore import Qt, pyqtSignal, QThread
import PyQt6.QtCore as QtCore
from Lib import pipestreamdbread as pdb
from Lib import read_record_by_time_thread as rec_read_trr
from Lib import cifer_diapasons_parsing as cdp
import pyqtgraph as pg
import numpy as np
from scipy.fft import rfft
import base64
import struct
import logging
import os
import pandas as pd
from ui.widgets import ResizableLineEdit
from ui.date_time_dialog import DateTimeSelectionDialog
from ui.themes import ThemeManager
from core.module_base import BaseModule

pg.setConfigOptions(antialias=True, background='k', foreground='w')

# =============================================================================
# КОНСТАНТЫ v2 ФОРМАТА
# =============================================================================
ADC_FULL_SCALE_V = 0.93
ADC_RAW_MAX = (1 << 21)  # 2097152
DEFAULT_SAMPLE_RATE = 25600
DEFAULT_SIGNAL_LENGTH = 2048


# =============================================================================
# УТИЛИТЫ ДЕКОДИРОВАНИЯ СИГНАЛОВ v2
# =============================================================================
def decode_v2_signal(base64_str: str, signal_length: int = 2048, signal_bytes: int = 3) -> np.ndarray:
    """
    Декодирует осциллограмму из Base64 (v2 формат).
    Формат: 3 байта на точку, little endian (B1 B2 B3).
    Для преобразования в int32: переставляем в big endian (B3 B2 B1) + знаковое расширение.
    Затем >> 2 (сдвиг вправо на 2 бита).
    """
    if pd.isna(base64_str) or not base64_str or not isinstance(base64_str, str):
        return np.array([])

    try:
        raw_bytes = base64.b64decode(base64_str.strip())
    except Exception as e:
        logging.warning(f"Ошибка декодирования Base64: {e}")
        return np.array([])

    points = []
    for i in range(0, len(raw_bytes), signal_bytes):
        chunk = raw_bytes[i:i + signal_bytes]
        if len(chunk) < signal_bytes:
            break

        # little endian -> big endian: [B1, B2, B3] -> [B3, B2, B1]
        be_bytes = bytes(reversed(chunk))

        # Знаковое расширение до int32
        sign_byte = b'\xff' if (be_bytes[0] & 0x80) else b'\x00'
        int32_bytes = sign_byte + be_bytes

        val = struct.unpack('>i', int32_bytes)[0]
        points.append(val >> 2)

    return np.array(points, dtype=np.int32)


def adc_to_physical(adc_shifted: np.ndarray, mult: float, div: float) -> np.ndarray:
    """Преобразование сырых значений АЦП в физические единицы (В или А)."""
    if div == 0:
        return adc_shifted
    scale = (mult / div) / (ADC_RAW_MAX / ADC_FULL_SCALE_V)
    return adc_shifted * scale


# =============================================================================
# УТИЛИТА ПАРСИНГА TIMESTAMP
# =============================================================================
def parse_timestamp_to_ms(value) -> int:
    """
    Универсальный парсинг timestamp в миллисекунды.
    Поддерживает:
    - Числа (int, float) - Unix timestamp в мс
    - Строки ISO 8601 (например, '2026-06-09T17:10:01.075')
    - Строки с числами
    """
    if pd.isna(value):
        return 0

    # Если уже число
    if isinstance(value, (int, float)):
        return int(value)

    # Пробуем как число из строки
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        pass

    # Пробуем как ISO 8601 дату
    try:
        dt = pd.to_datetime(value)
        return int(dt.timestamp() * 1000)
    except Exception:
        pass

    return 0


def parse_timestamps_column(series: pd.Series) -> pd.Series:
    """
    Универсальный парсинг колонки timestamp в миллисекунды.
    """
    # Сначала пробуем как числа
    numeric = pd.to_numeric(series, errors='coerce')

    # Для тех, что не распарсились как числа, пробуем как даты
    mask_na = numeric.isna()
    if mask_na.any():
        parsed_dates = pd.to_datetime(series[mask_na], errors='coerce')
        numeric[mask_na] = (parsed_dates.astype('int64') // 10**6)

    return numeric.fillna(0).astype('int64')


# =============================================================================
# ПОТОК ЗАГРУЗКИ ЗАПИСИ ИЗ CSV v2
# =============================================================================
class CsvV2RecordLoader(QThread):
    """Загружает одну запись (чанк) из CSV v2 по timestamp или индексу."""
    result_signal = pyqtSignal(object)  # dict с данными записи
    error_signal = pyqtSignal(str)

    def __init__(self, file_path, rec_num=1, timestamp=None, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.rec_num = rec_num
        self.timestamp = timestamp

    def run(self):
        try:
            df = pd.read_csv(self.file_path, sep=';', encoding='utf-8', low_memory=False)

            if self.timestamp is not None:
                # Ищем по timestamp - используем универсальный парсинг
                df['timestamp_ms'] = parse_timestamps_column(df['timestamp'])
                idx = (df['timestamp_ms'] - self.timestamp).abs().idxmin()
            else:
                # По номеру записи (1-based)
                idx = min(self.rec_num - 1, len(df) - 1)

            row = df.iloc[idx]

            # Формируем dict в формате совместимом с pdb.LogRecord
            record = {
                'timestamp': parse_timestamp_to_ms(row['timestamp']),
                'chunkID': str(row.get('chunkID', '')),
                'standID': str(row.get('standID', '')),
                'scenario_code': str(row.get('scenario_code', '')),
            }

            # RMS значения
            for col in ['U_A_rms', 'U_B_rms', 'U_C_rms', 'I_A_rms', 'I_B_rms', 'I_C_rms']:
                if col in row:
                    val = row[col]
                    if isinstance(val, str):
                        val = val.replace(',', '.')
                    record[col] = float(val) if pd.notna(val) else 0.0

            # Параметры сигналов
            sample_rate = int(row.get('sample_rate', DEFAULT_SAMPLE_RATE)) if pd.notna(row.get('sample_rate')) else DEFAULT_SAMPLE_RATE
            signal_length = int(row.get('signal_length', DEFAULT_SIGNAL_LENGTH)) if pd.notna(row.get('signal_length')) else DEFAULT_SIGNAL_LENGTH
            signal_bytes = int(row.get('signal_bytes', 3)) if pd.notna(row.get('signal_bytes')) else 3

            # Множители
            u_mult = float(row.get('U_mult', 23147)) if pd.notna(row.get('U_mult')) else 23147
            u_dev = float(row.get('U_dev', 47)) if pd.notna(row.get('U_dev')) else 47
            i_mult = float(row.get('I_mult', 25000)) if pd.notna(row.get('I_mult')) else 25000
            i_dev = float(row.get('I_dev', 66)) if pd.notna(row.get('I_dev')) else 66

            # Декодируем сигналы
            signals_dict = {}
            for sig_name, mult, div in [
                ('U_A_signal', u_mult, u_dev),
                ('U_B_signal', u_mult, u_dev),
                ('U_C_signal', u_mult, u_dev),
                ('I_A_signal', i_mult, i_dev),
                ('I_B_signal', i_mult, i_dev),
                ('I_C_signal', i_mult, i_dev),
            ]:
                if sig_name in row and pd.notna(row[sig_name]):
                    raw = decode_v2_signal(str(row[sig_name]), signal_length, signal_bytes)
                    if len(raw) > 0:
                        signals_dict[sig_name] = adc_to_physical(raw, mult, div)

            # Формируем points в формате совместимом с pdb.LogRecord.get_signals()
            # Объединяем 6 каналов в матрицу [signal_length x 6]
            if signals_dict:
                max_len = max(len(v) for v in signals_dict.values()) if signals_dict else 0
                if max_len > 0:
                    signals_matrix = np.zeros((max_len, 6))
                    channel_map = ['U_A_signal', 'U_B_signal', 'U_C_signal',
                                   'I_A_signal', 'I_B_signal', 'I_C_signal']
                    for i, sig_name in enumerate(channel_map):
                        if sig_name in signals_dict:
                            sig_data = signals_dict[sig_name]
                            signals_matrix[:len(sig_data), i] = sig_data
                    record['points'] = signals_matrix
                else:
                    record['points'] = None
            else:
                record['points'] = None

            self.result_signal.emit(record)

        except Exception as e:
            logging.error(f"Ошибка загрузки записи из CSV v2: {e}")
            self.error_signal.emit(str(e))


# =============================================================================
# ПОТОК ЗАГРУЗКИ СПИСКА ЗАПИСЕЙ ИЗ CSV v2
# =============================================================================
class CsvV2ListLoader(QThread):
    """Загружает список timestamp'ов из CSV v2."""
    result_signal = pyqtSignal(object)  # {'timestamps': [...], 'file_path': ...}
    error_signal = pyqtSignal(str)

    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.file_path = file_path

    def run(self):
        try:
            df = pd.read_csv(self.file_path, sep=';', encoding='utf-8', low_memory=False)

            # Универсальный парсинг timestamp
            df['timestamp_ms'] = parse_timestamps_column(df['timestamp'])
            df = df[df['timestamp_ms'] > 0]
            timestamps = df['timestamp_ms'].astype('int64').tolist()

            self.result_signal.emit({
                'timestamps': timestamps,
                'file_path': self.file_path,
                'total_records': len(timestamps)
            })

        except Exception as e:
            logging.error(f"Ошибка загрузки списка из CSV v2: {e}")
            self.error_signal.emit(str(e))


# =============================================================================
# КОНТЕЙНЕР ГРАФИКОВ
# =============================================================================
class PlotContainer(QWidget):
    def __init__(self, num_channels=6):
        super().__init__()
        self.plot_array = [[None, None] for _ in range(num_channels)]
        self.plot_row_layouts = [None] * num_channels

        self.plot_layout = QVBoxLayout()
        self.plot_layout.setContentsMargins(5, 5, 5, 5)
        self.plot_layout.setSpacing(10)
        self.setLayout(self.plot_layout)

        for plot_row in range(num_channels):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(10)
            self.plot_row_layouts[plot_row] = row_layout

            for col in range(2):
                plot_widget = pg.PlotWidget()
                plot_widget.showGrid(x=True, y=True, alpha=0.3)

                if col == 0:
                    plot_widget.setLabel('left', f'Канал {plot_row + 1}', color='w')
                    plot_widget.setLabel('bottom', 'Время, с', color='w')
                else:
                    plot_widget.setLabel('left', 'Амплитуда', color='w')
                    plot_widget.setLabel('bottom', 'Частота, Гц', color='w')

                self.plot_array[plot_row][col] = plot_widget
                row_layout.addWidget(plot_widget)

            self.plot_layout.addLayout(row_layout)

    def clear_plots(self):
        for i in range(len(self.plot_array)):
            if self.plot_array[i][0] is not None:
                self.plot_array[i][0].clear()
            if self.plot_array[i][1] is not None:
                self.plot_array[i][1].clear()


# =============================================================================
# ОСНОВНОЙ КЛАСС
# =============================================================================
class SignalsView_subwindow(BaseModule):
    timestamp_changed = pyqtSignal(int)

    def __init__(self, bus, parent=None):
        super().__init__(bus, parent)
        self.parent = parent
        self.presenter = None
        self.setWindowTitle("Просмотр сигналов")
        self.setMinimumWidth(100)

        self.current_current_table_timestamp_list = []
        self.current_rec_num = 0
        self.current_device = ""
        self.colnameList = []
        self.channel_boolmask = [True] * 6  # 6 каналов для v2 (было 7)
        self.current_data = {}
        self.current_freq_range = (-1, -1)
        self.show_grid = False

        # Флаг источника данных: 'db' или 'csv_v2'
        self.data_source = 'db'
        self.csv_file_path = None

        # === СОХРАНЕНИЕ МАСШТАБА ТОКА ===
        self.current_scale_limit = None  # Сохранённое значение масштаба тока (None = авто)

        self.size_policy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.navi_toolbar = QToolBar('Navigation')
        self.navi_toolbar.setSizePolicy(self.size_policy)

        self.plot_params = QToolBar('Plotting params')
        self.plot_params.setSizePolicy(self.size_policy)

        self.scrollArea = QScrollArea()
        self.scrollArea.setWidgetResizable(True)

        self.plot_container = PlotContainer(num_channels=6)  # 6 каналов для v2
        self.scrollArea.setWidget(self.plot_container)

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.navi_toolbar)
        main_layout.addWidget(self.plot_params)
        main_layout.addWidget(self.scrollArea)

        self.setup_navi_toolbar()
        self.setup_plot_params_toolbar()

        self.MainWidget = QWidget()
        self.MainWidget.setLayout(main_layout)
        self.setWidget(self.MainWidget)

        self.register_topics()

        self.apply_theme('dark')

    def register_topics(self):
        if not getattr(self, "bus", None):
            return
        self.bus.subscribe("record.selected", self.on_record_selected)
        self.bus.subscribe("record.list", self.on_record_list)
        self.bus.subscribe("trends.cursor.timestamp", self.on_trends_cursor_moved)
        # Подписка на событие открытия CSV из records_view
        self.bus.subscribe("csv.file.opened", self.on_csv_file_opened)

    def set_presenter(self, presenter):
        self.presenter = presenter

    def setup_navi_toolbar(self):
        self.firstButton = QToolButton()
        self.firstButton.setText("<<")
        self.firstButton.setToolTip("К первой записи")
        self.firstButton.setMinimumWidth(20)
        self.firstButton.setAutoRaise(True)
        self.firstButton.setEnabled(False)
        self.navi_toolbar.addWidget(self.firstButton)
        self.firstButton.clicked.connect(self.firstButton_clicked)

        self.leftButton = QToolButton()
        self.leftButton.setText("<")
        self.leftButton.setToolTip("К записи раньше")
        self.leftButton.setMinimumWidth(20)
        self.leftButton.setAutoRaise(True)
        self.leftButton.setEnabled(False)
        self.navi_toolbar.addWidget(self.leftButton)
        self.leftButton.clicked.connect(self.leftButton_clicked)

        self.timeEdit = ResizableLineEdit(parent=self)
        self.timeEdit.setText("0000-00-00 00:00:00")
        self.timeEdit.setToolTip("Дата и время записи (YYYY-MM-DD HH:MM:SS)")
        self.timeEdit.setPlaceholderText("YYYY-MM-DD HH:MM:SS")
        self.timeEdit.setReadOnly(True)
        timeEditIcon = QIcon("./icons/clock.png")
        timeEditIcon_action = QAction(timeEditIcon, "Время записи", self.timeEdit)
        self.timeEdit.addAction(timeEditIcon_action, QLineEdit.ActionPosition.LeadingPosition)
        self.timeEdit.setMinimumWidth(70)
        self.navi_toolbar.addWidget(self.timeEdit)
        self.timeEdit.mousePressEvent = self.show_datetime_dialog

        self.savePointsButton = QToolButton()
        self.savePointsButton.setText("Save")
        self.savePointsButton.setToolTip("Сохранить points в бинарный файл (.bin)")
        self.savePointsButton.setMinimumWidth(20)
        self.savePointsButton.setAutoRaise(True)
        self.savePointsButton.setEnabled(False)
        self.navi_toolbar.addWidget(self.savePointsButton)
        self.savePointsButton.clicked.connect(self.save_points_to_file)

        self.recNumEdit = ResizableLineEdit(parent=self)
        self.recNumEdit.setText("000000")
        self.recNumEdit.setToolTip("Номер записи")
        recNumEditIcon = QIcon("./icons/number.png")
        recNumEdit_action = QAction(recNumEditIcon, "Номер записи", self.recNumEdit)
        self.recNumEdit.addAction(recNumEdit_action, QLineEdit.ActionPosition.LeadingPosition)
        self.recNumEdit.setMinimumWidth(70)
        self.navi_toolbar.addWidget(self.recNumEdit)
        self.recNumEdit.textEdited.connect(self.rec_num_edited)

        self.rightButton = QToolButton()
        self.rightButton.setText(">")
        self.rightButton.setToolTip("К записи позже")
        self.rightButton.setMinimumWidth(20)
        self.rightButton.setAutoRaise(True)
        self.rightButton.setEnabled(False)
        self.navi_toolbar.addWidget(self.rightButton)
        self.rightButton.clicked.connect(self.rightButton_clicked)

        self.lastButton = QToolButton()
        self.lastButton.setText(">>")
        self.lastButton.setToolTip("К последней записи")
        self.lastButton.setMinimumWidth(20)
        self.lastButton.setAutoRaise(True)
        self.lastButton.setEnabled(False)
        self.navi_toolbar.addWidget(self.lastButton)
        self.lastButton.clicked.connect(self.lastButton_clicked)

        self.stepEdit = ResizableLineEdit(parent=self)
        self.stepEdit.setText("1")
        self.stepEdit.setToolTip("Шаг промотки")
        stepEditIcon = QIcon("./icons/walking-man.png")
        stepEditEdit_action = QAction(stepEditIcon, "Шаг промотки", self.stepEdit)
        self.stepEdit.addAction(stepEditEdit_action, QLineEdit.ActionPosition.LeadingPosition)
        self.stepEdit.setMinimumWidth(70)
        self.navi_toolbar.addWidget(self.stepEdit)

    def setup_plot_params_toolbar(self):
        filterIco = QIcon("./icons/three-horizontal-lines-icon.png")
        self.channelsFilterEdit = ResizableLineEdit(parent=self)
        self.channelsFilterEdit.setText("1-6")
        self.channelsFilterEdit.setToolTip("Фильтр отображения каналов (1-6)")
        self.channelsFilterEdit.setMinimumWidth(60)
        filter_action = QAction(filterIco, "Фильтр каналов", self.channelsFilterEdit)
        self.channelsFilterEdit.addAction(filter_action, QLineEdit.ActionPosition.LeadingPosition)
        self.plot_params.addWidget(self.channelsFilterEdit)
        self.channelsFilterEdit.textChanged.connect(self.on_channel_filter_changed)

        self.plot_params.addSeparator()

        self.plotColumnRationLabel = QLabel("1:1")
        self.plot_params.addWidget(self.plotColumnRationLabel)

        self.plotColumnRationSlider = QSlider(Qt.Orientation.Horizontal)
        self.plotColumnRationSlider.setToolTip("Соотношение ширины графиков сигнала и спектра")
        self.plotColumnRationSlider.setMinimum(1)
        self.plotColumnRationSlider.setMaximum(7)
        self.plotColumnRationSlider.setSliderPosition(4)
        self.plotColumnRationSlider.setMaximumWidth(150)
        self.plotColumnRationSlider.setMinimumWidth(50)
        self.plotColumnRationSlider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.plotColumnRationSlider.setTickInterval(1)
        self.plot_params.addWidget(self.plotColumnRationSlider)
        self.plotColumnRationSlider.valueChanged.connect(self.onPlotColumnSliderChanged)

        self.plot_params.addSeparator()

        self.freqRangeEdit = ResizableLineEdit(parent=self)
        self.freqRangeEdit.setText("  ")
        self.freqRangeEdit.setToolTip("Ограничение полосы отображения спектра")
        self.freqRangeEdit.setMinimumWidth(80)
        bandpassIco = QIcon("./icons/spectrum.png")
        bandpass_action = QAction(bandpassIco, "Полоса спектра", self.freqRangeEdit)
        self.freqRangeEdit.addAction(bandpass_action, QLineEdit.ActionPosition.LeadingPosition)
        self.plot_params.addWidget(self.freqRangeEdit)
        self.freqRangeEdit.textChanged.connect(self.on_freq_range_changed)

        self.plot_params.addSeparator()

        self.gridCheck = QCheckBox()
        self.gridCheck.setStyleSheet('''
            QCheckBox {
                spacing: 5px;
            }
        ''')
        gridIco = QIcon("./icons/grid.png")
        self.gridCheck.setIcon(gridIco)
        self.gridCheck.setSizePolicy(self.size_policy)
        self.gridCheck.setToolTip("Включить сетку на графиках")
        self.plot_params.addWidget(self.gridCheck)
        self.gridCheck.checkStateChanged.connect(self.on_grid_check_changed)

        self.currentScaleEdit = ResizableLineEdit(parent=self)
        self.currentScaleEdit.setText("  ")
        self.currentScaleEdit.setToolTip("Установка минимальной шкалы тока")
        self.currentScaleEdit.setMinimumWidth(60)
        current_scale_ico = QIcon("./icons/Y-scale.png")
        current_scale_action = QAction(current_scale_ico, "Шкала тока", self.currentScaleEdit)
        self.currentScaleEdit.addAction(current_scale_action, QLineEdit.ActionPosition.LeadingPosition)
        self.plot_params.addWidget(self.currentScaleEdit)
        self.currentScaleEdit.textChanged.connect(self.on_current_scale_changed)

        self.plot_params.addSeparator()

        self.fix_X_AxleCheck = QCheckBox()
        self.fix_X_AxleCheck.setStyleSheet('''
            QCheckBox {
                spacing: 5px;
            }
        ''')
        fixXIco = QIcon("./icons/axis-y.png")
        self.fix_X_AxleCheck.setIcon(fixXIco)
        self.fix_X_AxleCheck.setSizePolicy(self.size_policy)
        self.fix_X_AxleCheck.setToolTip("Зафиксировать ось X")
        self.plot_params.addWidget(self.fix_X_AxleCheck)
        self.fix_X_AxleCheck.checkStateChanged.connect(self.on_fixX_check_changed)

        self.fix_Y_AxleCheck = QCheckBox()
        self.fix_Y_AxleCheck.setStyleSheet('''
            QCheckBox {
                spacing: 5px;
            }
        ''')
        fixYIco = QIcon("./icons/axis-x.png")
        self.fix_Y_AxleCheck.setIcon(fixYIco)
        self.fix_Y_AxleCheck.setSizePolicy(self.size_policy)
        self.fix_Y_AxleCheck.setToolTip("Зафиксировать ось Y")
        self.plot_params.addWidget(self.fix_Y_AxleCheck)
        self.fix_Y_AxleCheck.checkStateChanged.connect(self.on_fixY_check_changed)

        self.autoScaleButtton = QToolButton()
        self.autoScaleButtton.setText("AUTO")
        self.autoScaleButtton.setToolTip("Сбросить ограничения масштаба")
        self.plot_params.addWidget(self.autoScaleButtton)
        self.autoScaleButtton.pressed.connect(self.autoScaleBottonPressed)

    # -------------------------------------------------------------------------
    # ЗАГРУЗКА CSV v2 (извне, через шину)
    # -------------------------------------------------------------------------

    def on_csv_file_opened(self, payload):
        """Получили уведомление от records_view об открытии CSV."""
        if isinstance(payload, dict):
            file_path = payload.get('file_path')
            if file_path and file_path != self.csv_file_path:
                self.data_source = 'csv_v2'
                self.csv_file_path = file_path
                self.current_device = payload.get('device_name', os.path.basename(file_path))

                # Загружаем список записей
                self.list_loader = CsvV2ListLoader(file_path)
                self.list_loader.result_signal.connect(self.on_csv_list_loaded)
                self.list_loader.error_signal.connect(self.on_error_message)
                self.list_loader.start()

    def on_csv_list_loaded(self, result):
        """Получен список timestamp'ов из CSV."""
        self.current_current_table_timestamp_list = result['timestamps']
        self.update_button_states()

        if self.current_current_table_timestamp_list:
            self.set_current_rec_num(1)
            # Загружаем первую запись
            self.load_csv_record(1)
        else:
            self.on_error_message("CSV файл не содержит записей")

    def load_csv_record(self, rec_num):
        """Загрузка записи из CSV v2."""
        if not self.csv_file_path:
            return

        self.csv_loader = CsvV2RecordLoader(self.csv_file_path, rec_num=rec_num)
        self.csv_loader.result_signal.connect(self.on_csv_record_loaded)
        self.csv_loader.error_signal.connect(self.on_error_message)
        self.csv_loader.start()

    def on_csv_record_loaded(self, record_dict):
        """Получена запись из CSV — отрисовываем."""
        self.current_data = record_dict
        self.plot_record(self.current_device, self.colnameList, record_dict, self.current_rec_num)

    # -------------------------------------------------------------------------
    # ВИДИМОСТЬ КАНАЛОВ
    # -------------------------------------------------------------------------

    def update_channel_visibility(self, channel_boolmask):
        if len(channel_boolmask) < 6:
            channel_boolmask += [False] * (6 - len(channel_boolmask))
        self.channel_boolmask = channel_boolmask[:6]

        pos = self.plotColumnRationSlider.value()
        stretch_left = [1, 1, 3, 1, 5, 3, 7][pos - 1]
        stretch_right = [7, 3, 5, 1, 3, 1, 1][pos - 1]

        for i in range(6):
            row_layout = self.plot_container.plot_row_layouts[i]
            time_plot = self.plot_container.plot_array[i][0]
            freq_plot = self.plot_container.plot_array[i][1]

            visible = self.channel_boolmask[i]

            if visible:
                time_plot.show()
                freq_plot.show()
                row_layout.setStretch(0, stretch_left)
                row_layout.setStretch(1, stretch_right)
                self.plot_container.plot_layout.setStretch(i, 1)
            else:
                time_plot.hide()
                freq_plot.hide()
                row_layout.setStretch(0, 0)
                row_layout.setStretch(1, 0)
                self.plot_container.plot_layout.setStretch(i, 0)

    def on_channel_filter_changed(self, text):
        text = text.strip()
        if not text:
            text = "1-6"
        mask = cdp.pars_cipher_diapasons_to_boolmask(text, 7)[1:7]  # 6 каналов
        self.channel_boolmask = mask
        self.update_channel_visibility(mask)

        if self.current_data:
            self.plot_record(self.current_device, self.colnameList, self.current_data, self.current_rec_num)

    def onPlotColumnSliderChanged(self, position):
        labels = ["1:7", "1:3", "3:5", "1:1", "5:3", "3:1", "7:1"]
        self.plotColumnRationLabel.setText(labels[position - 1])
        self.update_channel_visibility(self.channel_boolmask)

    # -------------------------------------------------------------------------
    # ТЕМЫ
    # -------------------------------------------------------------------------

    def apply_theme(self, theme_name: str):
        import pyqtgraph as pg

        dark_theme = theme_name == 'dark'

        palette = ThemeManager.get_palette(theme_name)
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self.MainWidget.setPalette(palette)
        self.MainWidget.setAutoFillBackground(True)

        self.scrollArea.setPalette(palette)
        self.scrollArea.setAutoFillBackground(True)

        self.plot_container.setPalette(palette)
        self.plot_container.setAutoFillBackground(True)

        toolbar_style = ThemeManager.get_toolbar_style(theme_name)
        self.navi_toolbar.setStyleSheet(toolbar_style)
        self.plot_params.setStyleSheet(toolbar_style)

        line_edit_style = ThemeManager.get_line_edit_style(theme_name)
        for edit in [
            self.timeEdit, self.recNumEdit, self.stepEdit,
            self.channelsFilterEdit, self.freqRangeEdit, self.currentScaleEdit
        ]:
            edit.setStyleSheet(line_edit_style)

        label_style = ThemeManager.get_label_style(theme_name)
        self.plotColumnRationLabel.setStyleSheet(label_style)

        checkbox_style = ThemeManager.get_checkbox_style(theme_name)
        for checkbox in [self.gridCheck, self.fix_X_AxleCheck, self.fix_Y_AxleCheck]:
            checkbox.setStyleSheet(checkbox_style)

        slider_style = ThemeManager.get_slider_style(theme_name)
        self.plotColumnRationSlider.setStyleSheet(slider_style)

        btn_style = ThemeManager.get_button_style(theme_name)
        self.autoScaleButtton.setStyleSheet(btn_style)

        if dark_theme:
            tooltip_style = """
                QToolTip {
                    background-color: #2b2b2b;
                    color: white;
                    border: 1px solid #aaaaaa;
                    padding: 4px;
                    font-size: 11px;
                    border-radius: 4px;
                }
            """
        else:
            tooltip_style = """
                QToolTip {
                    background-color: #ffffe0;
                    color: black;
                    border: 1px solid #aaaa00;
                    padding: 4px;
                    font-size: 11px;
                    border-radius: 4px;
                }
            """
        self.setStyleSheet(tooltip_style)

        bg = 'k' if dark_theme else 'w'
        fg = 'w' if dark_theme else 'k'
        pg.setConfigOptions(background=bg, foreground=fg)

        for row in self.plot_container.plot_array:
            for plot in row:
                if plot is None:
                    continue

                plot.setBackground(bg)

                left_axis = plot.getAxis('left')
                bottom_axis = plot.getAxis('bottom')
                left_axis.setPen(fg)
                left_axis.setTextPen(fg)
                bottom_axis.setPen(fg)
                bottom_axis.setTextPen(fg)

                plot.getAxis('left').setLabel(color=fg)
                plot.getAxis('bottom').setLabel(color=fg)

                plot_item = plot.getPlotItem()
                if plot_item and plot_item.titleLabel:
                    title_text = plot_item.titleLabel.text
                    plot_item.setTitle(title_text, color=fg)

                plot.getViewBox().update()
                plot.update()

        bg_color = "#353535" if dark_theme else "#ffffff"
        self.MainWidget.setStyleSheet(f"background-color: {bg_color};")
        self.scrollArea.viewport().setStyleSheet(f"background-color: {bg_color};")
        self.plot_container.setStyleSheet(f"background-color: {bg_color};")

        if self.current_data:
            self.plot_record(self.current_device, self.colnameList, self.current_data, self.current_rec_num)

    # -------------------------------------------------------------------------
    # ОБРАБОТЧИКИ СОБЫТИЙ
    # -------------------------------------------------------------------------

    def on_record_selected(self, payload):
        try:
            logging.info(f"Получено событие record.selected: {type(payload)}")

            if isinstance(payload, dict):
                table_name = payload.get("table_name")
                columns = payload.get("columns", [])
                data = payload.get("data", {})
                rec_num = payload.get("rec_num", 1)

                if table_name and data:
                    logging.info(f"Построение графиков для таблицы: {table_name}, запись: {rec_num}")
                    self.data_source = 'db'
                    self.plot_record(table_name, columns, data, rec_num)
                else:
                    logging.warning("Недостаточно данных в payload")
            else:
                self.current_device = payload
                logging.info(f"Выбрана таблица: {payload}")

        except Exception as e:
            logging.error(f"Ошибка в on_record_selected: {e}")
            self.on_error_message(f"Ошибка загрузки записи: {e}")

    def on_record_list(self, payload):
        try:
            logging.info(f"Получено событие record.list: {type(payload)}")

            if isinstance(payload, dict):
                timestamps = payload.get("timestamps", [])
                table_name = payload.get("table_name", "")
            else:
                timestamps = payload
                table_name = self.current_device

            if timestamps:
                self.set_current_table_timestamp_list(timestamps)
                self.set_current_device(table_name)
                logging.info(f"Получено {len(timestamps)} записей для {table_name}")

        except Exception as e:
            logging.error(f"Ошибка в on_record_list: {e}")

    def on_trends_cursor_moved(self, timestamp):
        try:
            logging.info(f"Получен timestamp от трендов: {timestamp}")
            if self.data_source == 'csv_v2' and self.csv_file_path:
                # Для CSV ищем ближайший timestamp и загружаем
                self.set_current_rec_num_by_timestamp(timestamp)
            else:
                self.set_current_rec_num_by_timestamp(timestamp)
        except Exception as e:
            logging.error(f"Ошибка в on_trends_cursor_moved: {e}")

    # -------------------------------------------------------------------------
    # СОХРАНЕНИЕ / ЭКСПОРТ
    # -------------------------------------------------------------------------

    def save_points_to_file(self):
        if not self.current_data:
            self.on_error_message("Нет выбранной записи для сохранения")
            return

        # Для CSV v2: points уже в виде numpy массива
        if self.data_source == 'csv_v2' and 'points' in self.current_data:
            points = self.current_data['points']
            if points is None or (isinstance(points, np.ndarray) and points.size == 0):
                self.on_error_message("Нет данных points в текущей записи")
                return

            try:
                timestamp = self.current_data.get('timestamp', 0)
                datetime_obj = pdb.datetime_from_timestamp(timestamp)
                filename = f"{self.current_device}_{datetime_obj.strftime('%Y%m%d_%H%M%S')}.bin"

                os.makedirs("export", exist_ok=True)
                full_path = os.path.join("export", filename)

                if isinstance(points, np.ndarray):
                    points.astype(np.float32).tofile(full_path)
                else:
                    with open(full_path, 'wb') as f:
                        f.write(points)

                if hasattr(self.parent, 'status_bar'):
                    self.parent.status_bar.showMessage(f"Данные сохранены в файл: {full_path}", 5000)
                logging.info(f"Сохранены данные points в файл: {full_path}")

            except Exception as e:
                self.on_error_message(f"Ошибка при сохранении файла: {str(e)}")
                logging.error(f"Ошибка при сохранении points в файл: {str(e)}")
            return

        # Legacy: БД формат
        try:
            rec = pdb.LogRecord(self.current_data)
            rec_dict = rec.get_record_dict()

            if "points" not in rec_dict or not rec_dict["points"]:
                self.on_error_message("Нет данных points в текущей записи")
                return

            byte_string = base64.b64decode(rec_dict["points"])
            timestamp = rec_dict["timestamp"]
            datetime_obj = pdb.datetime_from_timestamp(timestamp)

            filename = f"{self.current_device}_{datetime_obj.strftime('%Y%m%d_%H%M%S')}.bin"

            os.makedirs("export", exist_ok=True)
            full_path = os.path.join("export", filename)

            with open(full_path, 'wb') as f:
                f.write(byte_string)

            if hasattr(self.parent, 'status_bar'):
                self.parent.status_bar.showMessage(f"Данные points сохранены в файл: {full_path}", 5000)
            logging.info(f"Сохранены данные points в файл: {full_path}")

        except Exception as e:
            self.on_error_message(f"Ошибка при сохранении файла: {str(e)}")
            logging.error(f"Ошибка при сохранении points в файл: {str(e)}")

    # -------------------------------------------------------------------------
    # НАВИГАЦИЯ
    # -------------------------------------------------------------------------

    def set_current_table_timestamp_list(self, timestamp_list):
        self.current_current_table_timestamp_list = timestamp_list
        self.update_button_states()
        if timestamp_list:
            self.set_current_rec_num(1)
        else:
            self.set_current_rec_num(0)
            self.timeEdit.setText("0000-00-00 00:00:00")
            self.recNumEdit.setText("000000")

    def set_current_rec_num(self, rec_num: int):
        self.current_rec_num = rec_num
        self.recNumEdit.setText(str(rec_num))
        self.update_button_states()

    def set_current_rec_num_by_timestamp(self, timestamp):
        if not self.current_current_table_timestamp_list:
            return
        diffs = [abs(ts - timestamp) for ts in self.current_current_table_timestamp_list]
        idx = int(np.argmin(diffs))
        self.set_current_rec_num(idx + 1)
        self.select_and_plot_record(idx + 1)

    def set_current_device(self, table_name: str):
        self.current_device = table_name
        self.update_button_states()

    def set_colname_list(self, colnameList: list):
        self.colnameList = colnameList
        self.update_button_states()

    def set_current_data(self, in_data):
        self.current_data = in_data
        self.update_button_states()

    def set_current_freq_range(self, range: tuple):
        self.current_freq_range = range

    def update_button_states(self):
        has_data = (len(self.current_device) > 2 and
                    len(self.current_current_table_timestamp_list) > 0)
        self.firstButton.setEnabled(has_data and self.current_rec_num > 1)
        self.leftButton.setEnabled(has_data and self.current_rec_num > 1)
        self.rightButton.setEnabled(has_data and self.current_rec_num < len(self.current_current_table_timestamp_list))
        self.lastButton.setEnabled(has_data and self.current_rec_num < len(self.current_current_table_timestamp_list))
        self.savePointsButton.setEnabled(has_data and bool(self.current_data))

    def send_timestamp_to_trends(self):
        if not self.current_data or 'timestamp' not in self.current_data:
            self.on_error_message("Нет выбранной записи для передачи")
            return

        timestamp = self.current_data["timestamp"]
        if self.bus:
            self.bus.publish("signals.timestamp", timestamp)
        self.timestamp_changed.emit(timestamp)

    # -------------------------------------------------------------------------
    # ПРИМЕНЕНИЕ МАСШТАБА ТОКА
    # -------------------------------------------------------------------------

    def apply_current_scale(self):
        """Применяет сохранённый масштаб тока к графикам (каналы 3-5: I_A, I_B, I_C)."""
        if self.current_scale_limit is None:
            return

        for i in range(3, 6):
            if self.channel_boolmask[i] and self.plot_container.plot_array[i][0] is not None:
                self.plot_container.plot_array[i][0].setRange(yRange=[-self.current_scale_limit, self.current_scale_limit])

    # -------------------------------------------------------------------------
    # ОТРИСОВКА ГРАФИКОВ
    # -------------------------------------------------------------------------

    def plot_record(self, table_name: str, colname_list: list, in_data, rec_num: int):
        try:
            if not table_name or not in_data:
                logging.warning("Недостаточно данных для построения графиков")
                return

            logging.info(f"Начинаем построение графиков для {table_name}, запись {rec_num}")

            self.set_current_device(table_name)
            self.set_colname_list(colname_list)
            self.set_current_data(in_data)

            # Получаем timestamp
            timestamp = in_data.get("timestamp", 0)
            time_to_display = pdb.datetime_from_timestamp(timestamp)
            self.timeEdit.blockSignals(True)
            self.timeEdit.setText(str(time_to_display)[:-3])
            self.timeEdit.blockSignals(False)

            self.set_current_rec_num(rec_num)

            # Получаем сигналы
            signals = None
            if self.data_source == 'csv_v2':
                # Для CSV v2: points уже numpy массив [samples x 6]
                points = in_data.get('points')
                if points is not None and isinstance(points, np.ndarray) and points.size > 0:
                    signals = points
            else:
                # Legacy БД
                rec = pdb.LogRecord(in_data)
                signals = rec.get_signals()

            if signals is None or signals.size == 0:
                logging.warning("Нет данных сигналов для отрисовки")
                return

            channel_num = signals.shape[1] if len(signals.shape) > 1 else 1
            sampling = DEFAULT_SAMPLE_RATE

            logging.info(f"Сигналы: {signals.shape}, каналов: {channel_num}")

            self.plot_container.clear_plots()

            # Подписи каналов для v2
            channel_labels = ['U_A', 'U_B', 'U_C', 'I_A', 'I_B', 'I_C']

            for i in range(min(channel_num, 6)):
                if not self.channel_boolmask[i]:
                    continue

                plot_widget_time = self.plot_container.plot_array[i][0]
                plot_widget_freq = self.plot_container.plot_array[i][1]

                if plot_widget_time is None or plot_widget_freq is None:
                    continue

                sig = signals[:, i].copy()
                sig = sig - np.mean(sig)
                signal_length = len(sig)

                if signal_length == 0:
                    continue

                time_axis = np.linspace(0., signal_length / sampling, signal_length)

                plot_widget_time.clear()
                plot_widget_freq.clear()

                # Цвета для каналов
                colors = ['#FF0000', '#00FF00', '#0000FF', '#FF00FF', '#00FFFF', '#FFFF00']
                color = colors[i % len(colors)]

                label = channel_labels[i] if i < len(channel_labels) else f"Канал {i + 1}"
                plot_widget_time.plot(time_axis, sig, pen=pg.mkPen(color=color, width=1))
                plot_widget_time.setTitle(f"{label} (время)", color='white', size='12pt')

                try:
                    yf = rfft(sig)
                    spectrum = np.abs(yf) / signal_length
                    freq_axis = np.linspace(0, sampling / 2, len(yf))

                    low_ind = 0
                    hi_ind = len(spectrum)

                    if self.current_freq_range[0] > 0:
                        low_ind = int((len(spectrum) / (sampling / 2)) * self.current_freq_range[0])

                    if (self.current_freq_range[1] > 0 and
                            self.current_freq_range[1] > self.current_freq_range[0] and
                            self.current_freq_range[1] < (sampling / 2)):
                        hi_ind = int((len(spectrum) / (sampling / 2)) * self.current_freq_range[1])

                    plot_widget_freq.plot(freq_axis[low_ind:hi_ind], spectrum[low_ind:hi_ind],
                                          pen=pg.mkPen(color=color, width=1))
                    plot_widget_freq.setTitle(f"{label} (спектр)", color='white', size='12pt')

                except Exception as e:
                    logging.error(f"Ошибка построения спектра для канала {i}: {e}")

            self.update_channel_visibility(self.channel_boolmask)
            # === ИСПРАВЛЕНИЕ: не сбрасываем масштаб, а применяем сохранённый ===
            self.apply_current_scale()

            self.timestamp_changed.emit(timestamp)
            self.send_timestamp_to_trends()

            logging.info("Графики успешно построены")

        except Exception as e:
            logging.error(f"Ошибка в plot_record: {e}")
            self.on_error_message(f"Ошибка построения графиков: {e}")

    # -------------------------------------------------------------------------
    # НАВИГАЦИЯ ПО ЗАПИСЯМ
    # -------------------------------------------------------------------------

    def select_and_plot_record(self, num):
        try:
            if (not self.current_current_table_timestamp_list or
                    num < 1 or
                    num > len(self.current_current_table_timestamp_list)):
                return

            if self.data_source == 'csv_v2' and self.csv_file_path:
                # Загрузка из CSV
                self.load_csv_record(num)
                return

            # Legacy: загрузка из БД
            timestamp = self.current_current_table_timestamp_list[num - 1]
            logging.info(f"Загрузка записи {num}, timestamp: {timestamp}")

            self.read_rec_thread = rec_read_trr.ReadRecordThread(
                self.current_device,
                self.colnameList,
                timestamp
            )
            self.read_rec_thread.error_signal.connect(self.on_error_message)
            self.read_rec_thread.result_signal.connect(self.on_next_rec_result)
            self.read_rec_thread.start()

        except Exception as e:
            logging.error(f"Ошибка в select_and_plot_record: {e}")
            self.on_error_message(f"Ошибка загрузки записи: {e}")

    def on_next_rec_result(self, rec_dict):
        try:
            if rec_dict:
                self.plot_record(self.current_device, self.colnameList, rec_dict, self.current_rec_num)
            else:
                self.on_error_message("Пустой результат загрузки записи")
        except Exception as e:
            logging.error(f"Ошибка в on_next_rec_result: {e}")

    def on_error_message(self, text):
        msgBox = QMessageBox()
        msgBox.setText(f"Ошибка: {text}")
        msgBox.exec()

    # -------------------------------------------------------------------------
    # КНОПКИ НАВИГАЦИИ
    # -------------------------------------------------------------------------

    def firstButton_clicked(self):
        self.set_current_rec_num(1)
        self.select_and_plot_record(1)

    def leftButton_clicked(self):
        step_text = self.stepEdit.text()
        step = int(step_text) if step_text.isdigit() else 0

        if len(self.current_current_table_timestamp_list) < 1 or step < 1:
            return

        if step > self.current_rec_num:
            step = self.current_rec_num - 1

        if step == 0:
            return

        num = self.current_rec_num - step
        self.set_current_rec_num(num)
        self.select_and_plot_record(num)

    def rightButton_clicked(self):
        step_text = self.stepEdit.text()
        step = int(step_text) if step_text.isdigit() else 0

        if len(self.current_current_table_timestamp_list) < 1 or step < 1:
            return

        total_rec_num = len(self.current_current_table_timestamp_list)

        if step > total_rec_num - self.current_rec_num:
            step = total_rec_num - self.current_rec_num

        if step == 0:
            return

        num = self.current_rec_num + step
        self.set_current_rec_num(num)
        self.select_and_plot_record(num)

    def lastButton_clicked(self):
        last_num = len(self.current_current_table_timestamp_list)
        self.set_current_rec_num(last_num)
        self.select_and_plot_record(last_num)

    def rec_num_edited(self):
        rec_num_text = self.recNumEdit.text()
        num = int(rec_num_text) if rec_num_text.isdigit() else 0
        last = len(self.current_current_table_timestamp_list)

        if last < 1 or num < 1 or num > last:
            return

        self.set_current_rec_num(num)
        self.select_and_plot_record(num)

    def show_datetime_dialog(self, event=None):
        initial_datetime = None
        if self.current_data and "timestamp" in self.current_data:
            initial_datetime = pdb.datetime_from_timestamp(self.current_data["timestamp"])

        dialog = DateTimeSelectionDialog(initial_datetime, self)

        if dialog.exec():
            selected_dt = dialog.get_selected_datetime()
            timestamp = int(selected_dt.toSecsSinceEpoch() * 1000)

            if len(self.current_current_table_timestamp_list) < 1:
                self.on_error_message("Нет выбранного устройства или списка записей")
                return

            timestamp_list = self.current_current_table_timestamp_list
            if not timestamp_list:
                self.on_error_message("Список записей пуст")
                return

            closest_timestamp = min(timestamp_list, key=lambda x: abs(x - timestamp))
            closest_index = timestamp_list.index(closest_timestamp) + 1

            self.set_current_rec_num(closest_index)
            self.timeEdit.blockSignals(True)
            self.timeEdit.setText(selected_dt.toString("yyyy-MM-dd HH:mm:ss"))
            self.timeEdit.blockSignals(False)
            self.select_and_plot_record(closest_index)
            if hasattr(self.parent, 'status_bar'):
                self.parent.status_bar.showMessage(
                    f"Загрузка осциллограммы с {selected_dt.toString('dd.MM.yyyy HH:mm:ss')}", 5000
                )

    # -------------------------------------------------------------------------
    # ПАРАМЕТРЫ ОТОБРАЖЕНИЯ
    # -------------------------------------------------------------------------

    def on_freq_range_changed(self, text):
        range = cdp.rangeTextParse(text)
        self.set_current_freq_range(range)
        if self.current_data:
            self.plot_record(self.current_device, self.colnameList, self.current_data, self.current_rec_num)

    def on_grid_check_changed(self, state):
        is_checked = self.gridCheck.isChecked()
        self.show_grid = is_checked

        for i in range(len(self.plot_container.plot_array)):
            if self.plot_container.plot_array[i][0] is not None:
                self.plot_container.plot_array[i][0].showGrid(x=is_checked, y=is_checked, alpha=0.3)
                self.plot_container.plot_array[i][1].showGrid(x=is_checked, y=is_checked, alpha=0.3)

    def on_current_scale_changed(self, text):
        blankless = ''.join(text.split())
        if len(blankless) == 0 or not blankless.isdigit():
            self.current_scale_limit = None
            # Сбрасываем масштаб тока в авто
            for i in range(3, 6):
                if self.channel_boolmask[i] and self.plot_container.plot_array[i][0] is not None:
                    self.plot_container.plot_array[i][0].enableAutoRange(axis='y')
        else:
            self.current_scale_limit = int(blankless)
            # Сразу применяем к текущим графикам
            self.apply_current_scale()

    def on_fixX_check_changed(self):
        checked = self.fix_X_AxleCheck.isChecked()
        for i in range(len(self.plot_container.plot_array)):
            if self.plot_container.plot_array[i][0] is not None:
                self.plot_container.plot_array[i][0].setMouseEnabled(x=not checked)
                self.plot_container.plot_array[i][1].setMouseEnabled(x=not checked)

    def on_fixY_check_changed(self):
        checked = self.fix_Y_AxleCheck.isChecked()
        for i in range(len(self.plot_container.plot_array)):
            if self.plot_container.plot_array[i][0] is not None:
                self.plot_container.plot_array[i][0].setMouseEnabled(y=not checked)
                self.plot_container.plot_array[i][1].setMouseEnabled(y=not checked)

    def autoScaleBottonPressed(self):
        self.current_scale_limit = None          # Сбрасываем сохранённый масштаб
        self.currentScaleEdit.clear()            # Очищаем поле ввода
        self.set_current_freq_range((-1, -1))
        self.freqRangeEdit.setText("  ")         # Очищаем поле частоты
        for i in range(len(self.plot_container.plot_array)):
            if self.plot_container.plot_array[i][0] is not None:
                self.plot_container.plot_array[i][0].enableAutoRange()
                self.plot_container.plot_array[i][1].enableAutoRange()

    def moveEvent(self, event):
        super().moveEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def set_timestamp_from_trends(self, timestamp):
        if self.current_device and self.current_current_table_timestamp_list:
            closest_timestamp = min(self.current_current_table_timestamp_list, key=lambda x: abs(x - timestamp))
            closest_index = self.current_current_table_timestamp_list.index(closest_timestamp) + 1
            self.set_current_rec_num(closest_index)
            self.select_and_plot_record(closest_index)
            self.timeEdit.setText(pdb.datetime_from_timestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S'))
            if hasattr(self.parent, 'status_bar'):
                self.parent.status_bar.showMessage(
                    f"Загрузка сигнала на {pdb.datetime_from_timestamp(timestamp).strftime('%d.%m.%Y %H:%M:%S')}", 5000)