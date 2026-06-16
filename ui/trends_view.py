from PyQt6.QtWidgets import (
    QMdiSubWindow, QWidget, QHBoxLayout, QVBoxLayout, QToolButton, QProgressBar, QLabel,
    QSizePolicy, QMessageBox, QFileDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QCursor, QPalette, QColor
import pyqtgraph as pg
import pandas as pd
import numpy as np
import logging
from datetime import datetime
import warnings
import time
import base64
import struct
from Lib import pipestreamdbread as pdb
from ui.themes import ThemeManager
from core.module_base import BaseModule

warnings.filterwarnings("ignore", category=UserWarning, module="pyqtgraph")
pg.setConfigOptions(antialias=True, background='k', foreground='w')

# Константы для преобразования АЦП (из документа v2)
ADC_FULL_SCALE_V = 0.93
ADC_RAW_MAX = (1 << 21)  # 2097152


class RenderProfiler:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.stages = {}
        self._active = {}

    def start(self, name):
        if not self.enabled:
            return
        self._active[name] = time.perf_counter()

    def end(self, name):
        if not self.enabled or name not in self._active:
            return
        elapsed = time.perf_counter() - self._active[name]
        self.stages[name] = elapsed
        del self._active[name]

    def summary(self):
        if not self.enabled:
            return "Profiling disabled"
        total = sum(self.stages.values())
        lines = ["=== PROFILING RESULT ==="]
        for k, v in self.stages.items():
            pct = v / total * 100 if total else 0
            lines.append(f"{k:25s} : {v:7.4f} s   ({pct:5.1f}%)")
        lines.append(f"{'-' * 40}TOTAL: {total:.4f} s")
        return "\n".join(lines)


# =============================================================================
# УТИЛИТЫ ДЛЯ РАСКОДИРОВАНИЯ СИГНАЛОВ (v2 формат)
# =============================================================================
def decode_v2_signal(base64_str: str, signal_length: int = 2048, signal_bytes: int = 3) -> np.ndarray:
    """
    Декодирует осциллограмму из Base64 (v2 формат).
    Формат: 3 байта на точку, little endian (B1 B2 B3 -> big endian: B3 B2 B1).
    Значение int32 со знаком, затем >> 2.
    """
    try:
        raw_bytes = base64.b64decode(base64_str)
    except Exception:
        return np.array([])

    points = []
    for i in range(0, len(raw_bytes), signal_bytes):
        chunk = raw_bytes[i:i + signal_bytes]
        if len(chunk) < signal_bytes:
            break

        # little endian -> big endian: переставляем байты
        # B1 B2 B3 -> B3 B2 B1
        be_bytes = bytes(reversed(chunk))  # [B3, B2, B1]

        # Дополняем до 4 байт знаковым расширением (MSB = B3)
        sign_byte = b'\xff' if (be_bytes[0] & 0x80) else b'\x00'
        int32_bytes = sign_byte + be_bytes

        val = struct.unpack('>i', int32_bytes)[0]
        points.append(val >> 2)

    return np.array(points, dtype=np.int32)


def adc_to_volts(adc_shifted: np.ndarray, mult: float, div: float) -> np.ndarray:
    """Преобразование сырых значений АЦП в вольты."""
    scale = (mult / div) / (ADC_RAW_MAX / ADC_FULL_SCALE_V)
    return adc_shifted * scale


def adc_to_amps(adc_shifted: np.ndarray, mult: float, div: float) -> np.ndarray:
    """Преобразование сырых значений АЦП в амперы."""
    scale = (mult / div) / (ADC_RAW_MAX / ADC_FULL_SCALE_V)
    return adc_shifted * scale


# =============================================================================
# ПОТОК ЗАГРУЗКИ ДАННЫХ ИЗ БД (legacy, оставлен для совместимости)
# =============================================================================
class DataLoaderThread(QThread):
    data_processed = pyqtSignal(object)
    error_occurred = pyqtSignal(str)
    progress_updated = pyqtSignal(int)

    def __init__(self, table_name, parent=None):
        super().__init__(parent)
        self.table_name = table_name

    def run(self):
        total_start = time.perf_counter()
        print(f"[DataLoaderThread] START загрузка таблицы: {self.table_name}")

        try:
            t0 = time.perf_counter()
            connection, cursor, status = pdb.connect_db(pdb.db_connection_params)
            print(f"[DataLoaderThread] Подключение к БД: {time.perf_counter() - t0:.3f} с")

            if connection == 0 or cursor == 0:
                self.error_occurred.emit(f"Ошибка подключения к БД: {status}")
                return

            colnames_list = pdb.get_column_names(cursor, self.table_name)
            rms_colnames = ["timestamp", "add_data_0", "add_data_1", "add_data_2", "add_data_3", "add_data_4",
                            "add_data_5"]
            multypliers_colnames = ["cfg_voltage_multiplier", "cfg_voltage_divider", "cfg_current_multiplier",
                                    "cfg_current_divider"]
            required_columns = rms_colnames + multypliers_colnames

            if not all(col in colnames_list for col in required_columns):
                self.error_occurred.emit(f"Ошибка: Таблица {self.table_name} не содержит всех необходимых столбцов")
                cursor.close()
                connection.close()
                return

            # --- Множители ---
            t0 = time.perf_counter()
            multypliers_names = ["VoltMult", "VoltDiv", "CurrMult", "CurrDiv"]
            query_last = f"SELECT {', '.join(multypliers_colnames)} FROM {self.table_name} ORDER BY timestamp DESC LIMIT 1"
            cursor.execute(query_last)
            last_ans = cursor.fetchone()
            if not last_ans:
                self.error_occurred.emit("Не удалось получить множители из таблицы")
                cursor.close()
                connection.close()
                return
            mult_dict = dict(zip(multypliers_names, last_ans))
            print(f"[DataLoaderThread] Получение множителей: {time.perf_counter() - t0:.3f} с")

            if any(v is None or v == 0 for v in [mult_dict["VoltDiv"], mult_dict["CurrDiv"]]):
                self.error_occurred.emit("Ошибка: Множители содержат None или нули")
                cursor.close()
                connection.close()
                return

            # --- Чтение всех RMS и векторная конвертация ---
            t0 = time.perf_counter()
            query = f"SELECT {', '.join(rms_colnames)} FROM {self.table_name} ORDER BY timestamp ASC"
            cursor.execute(query)
            records = cursor.fetchall()
            total_records = len(records)
            print(f"[DataLoaderThread] Прочитано {total_records} строк из БД: {time.perf_counter() - t0:.3f} с")

            if not records:
                self.error_occurred.emit(f"Нет данных в таблице {self.table_name}")
                cursor.close()
                connection.close()
                return

            arr = np.array(records, dtype=object)
            timestamps = arr[:, 0].astype('int64')
            adc_cols = arr[:, 1:].astype('float64')

            scale_volt = (mult_dict["VoltMult"] / mult_dict["VoltDiv"]) / (ADC_RAW_MAX / ADC_FULL_SCALE_V)
            scale_curr = (mult_dict["CurrMult"] / mult_dict["CurrDiv"]) / (ADC_RAW_MAX / ADC_FULL_SCALE_V)

            adc_cols = np.where(pd.isna(adc_cols), np.nan, adc_cols)
            adc_shift = np.floor_divide(adc_cols, 4.0)

            volts = np.round(adc_shift[:, :3] * scale_volt, 2)
            amps = np.round(adc_shift[:, 3:] * scale_curr, 2)

            df = pd.DataFrame({
                'timestamp': timestamps,
                'U_A_rms': volts[:, 0],
                'U_B_rms': volts[:, 1],
                'U_C_rms': volts[:, 2],
                'I_A_rms': amps[:, 0],
                'I_B_rms': amps[:, 1],
                'I_C_rms': amps[:, 2]
            })

            print(f"[DataLoaderThread] Конвертация {total_records} строк → DataFrame: {time.perf_counter() - t0:.3f} с")
            print(f"[DataLoaderThread] ОБЩЕЕ ВРЕМЯ ЗАГРУЗКИ: {time.perf_counter() - total_start:.3f} с")

            self.data_processed.emit(df)
            cursor.close()
            connection.close()

        except Exception as e:
            print(f"[DataLoaderThread] ОШИБКА: {e}")
            self.error_occurred.emit(f"Ошибка при загрузке: {str(e)}")


# =============================================================================
# ПОТОК ЗАГРУЗКИ CSV v2 (новый формат датасетов)
# =============================================================================
class CsvV2LoaderThread(QThread):
    """
    Загрузчик CSV файлов формата v2 датасетов.
    Поддерживает:
    - raw-файлы: {ORG}.{STAND}.{YYYYMMDD}.{HHMMSS}.raw.{NN}.csv
    - Разделитель: точка с запятой (;)
    - Декодирование Base64 сигналов (опционально)
    """
    data_processed = pyqtSignal(object)
    error_occurred = pyqtSignal(str)
    progress_updated = pyqtSignal(int)

    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.file_path = file_path

    def run(self):
        total_start = time.perf_counter()
        print(f"[CsvV2LoaderThread] START загрузка: {self.file_path}")

        try:
            # --- Чтение CSV ---
            t0 = time.perf_counter()
            df_raw = pd.read_csv(
                self.file_path,
                sep=';',
                encoding='utf-8',
                low_memory=False
            )
            total_rows = len(df_raw)
            print(f"[CsvV2LoaderThread] Прочитано {total_rows} строк: {time.perf_counter() - t0:.3f} с")
            self.progress_updated.emit(10)

            # --- Проверка обязательных колонок ---
            required_cols = ['timestamp', 'U_A_rms', 'U_B_rms', 'U_C_rms',
                             'I_A_rms', 'I_B_rms', 'I_C_rms']

            missing = [c for c in required_cols if c not in df_raw.columns]
            if missing:
                self.error_occurred.emit(
                    f"CSV не содержит обязательных колонок: {missing}\n"
                    f"Найдены: {list(df_raw.columns)}"
                )
                return

            self.progress_updated.emit(30)

            # --- Конвертация типов ---
            t0 = time.perf_counter()
            df = pd.DataFrame()

            # timestamp: УНИВЕРСАЛЬНАЯ КОНВЕРТАЦИЯ
            # Поддержка: Unix ms (число) и ISO 8601 строки
            ts_values = df_raw['timestamp'].astype(str).str.strip()

            # Сначала пробуем как числа
            ts_numeric = pd.to_numeric(ts_values, errors='coerce')
            mask_na = ts_numeric.isna()

            if mask_na.any():
                date_strings = ts_values[mask_na]
                parsed_dates = pd.to_datetime(date_strings, errors='coerce')
                ts_from_dates = (parsed_dates.astype('int64') // 10 ** 6)
                ts_numeric.loc[mask_na] = ts_from_dates.values

            df['timestamp'] = ts_numeric

            # RMS значения: заменяем запятую на точку, потом в число
            rms_cols = ['U_A_rms', 'U_B_rms', 'U_C_rms', 'I_A_rms', 'I_B_rms', 'I_C_rms']
            for col in rms_cols:
                # Замена запятой на точку для русской локали
                df[col] = pd.to_numeric(
                    df_raw[col].astype(str).str.replace(',', '.', regex=False),
                    errors='coerce'
                )

            # Теперь можно безопасно конвертировать timestamp в int64
            df['timestamp'] = df['timestamp'].astype('int64')

            # Округляем RMS до 2 знаков
            for col in rms_cols:
                df[col] = df[col].round(2)

            if len(df) == 0:
                self.error_occurred.emit("CSV не содержит валидных записей (все timestamp/RMS = NaN)")
                return

            print(f"[CsvV2LoaderThread] Валидных строк после очистки: {len(df)}")

            # --- Дополнительные поля v2 (сохраняем для использования) ---
            # Метаданные
            for meta_col in ['chunkID', 'standID', 'devicesID', 'scenario_code']:
                if meta_col in df_raw.columns:
                    df[meta_col] = df_raw.loc[df.index, meta_col].values

            # Множители
            for mult_col in ['U_mult', 'U_dev', 'I_mult', 'I_dev', 'ADC_scale', 'ADC_max']:
                if mult_col in df_raw.columns:
                    df[mult_col] = pd.to_numeric(df_raw.loc[df.index, mult_col], errors='coerce')

            # Параметры сигналов
            for sig_col in ['sample_rate', 'signal_length', 'signal_bytes', 'byte_order', 'coding']:
                if sig_col in df_raw.columns:
                    df[sig_col] = df_raw.loc[df.index, sig_col].values

            # Сигналы (Base64) - сохраняем как строки
            for sig_col in ['U_A_signal', 'U_B_signal', 'U_C_signal',
                            'I_A_signal', 'I_B_signal', 'I_C_signal']:
                if sig_col in df_raw.columns:
                    df[sig_col] = df_raw.loc[df.index, sig_col].astype(str).values

            df = df.reset_index(drop=True)

            print(f"[CsvV2LoaderThread] Конвертация типов: {time.perf_counter() - t0:.3f} с")
            self.progress_updated.emit(60)

            # --- Валидация диапазонов ---
            t0 = time.perf_counter()
            voltage_cols = ['U_A_rms', 'U_B_rms', 'U_C_rms']
            current_cols = ['I_A_rms', 'I_B_rms', 'I_C_rms']

            for col in voltage_cols:
                invalid = df[(df[col] < 0) | (df[col] > 300)]
                if len(invalid) > 0:
                    print(f"[CsvV2LoaderThread] Предупреждение: {len(invalid)} значений {col} вне диапазона 0..300")

            for col in current_cols:
                invalid = df[(df[col] < 0) | (df[col] > 100)]
                if len(invalid) > 0:
                    print(f"[CsvV2LoaderThread] Предупреждение: {len(invalid)} значений {col} вне диапазона 0..100")

            print(f"[CsvV2LoaderThread] Валидация: {time.perf_counter() - t0:.3f} с")
            self.progress_updated.emit(80)

            # --- Сортировка по timestamp ---
            df = df.sort_values('timestamp').reset_index(drop=True)

            # --- Финальная подготовка ---
            output_cols = ['timestamp', 'U_A_rms', 'U_B_rms', 'U_C_rms',
                           'I_A_rms', 'I_B_rms', 'I_C_rms']

            # Метаданные
            meta_cols = ['chunkID', 'standID', 'scenario_code', 'sample_rate', 'signal_length']
            for mc in meta_cols:
                if mc in df.columns:
                    output_cols.append(mc)

            # Сигналы
            signal_cols = ['U_A_signal', 'U_B_signal', 'U_C_signal',
                           'I_A_signal', 'I_B_signal', 'I_C_signal']
            for sc in signal_cols:
                if sc in df.columns:
                    output_cols.append(sc)

            df_out = df[output_cols].copy()

            self.progress_updated.emit(100)
            total_time = time.perf_counter() - total_start
            print(f"[CsvV2LoaderThread] ОБЩЕЕ ВРЕМЯ ЗАГРУЗКИ: {total_time:.3f} с")

            self.data_processed.emit(df_out)

        except Exception as e:
            print(f"[CsvV2LoaderThread] ОШИБКА: {e}")
            self.error_occurred.emit(f"Ошибка при загрузке CSV v2: {str(e)}")


# =============================================================================
# ВИДЖЕТЫ ГРАФИКОВ
# =============================================================================
class CustomInfiniteLine(pg.InfiniteLine):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseHover(True)
        self.is_dragged = False
        self.hovering = False

    def mouseDragEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            if ev.isStart():
                self.is_dragged = True
                self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            elif ev.isFinish():
                self.is_dragged = False
                if not self.hovering:
                    self.unsetCursor()
            super().mouseDragEvent(ev)

    def hoverEvent(self, ev):
        if not self.movable: return
        if ev.isEnter():
            if not self.hovering and not self.is_dragged:
                self.hovering = True
                self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
        elif ev.isExit():
            if self.hovering and not self.is_dragged:
                self.hovering = False
                self.unsetCursor()


class GapRegion(pg.GraphicsObject):
    def __init__(self, x1, x2, brush=None):
        super().__init__()
        self.x1 = float(x1)
        self.x2 = float(x2)
        self.brush = brush if brush is not None else pg.mkBrush(128, 128, 128, 80)

    def boundingRect(self):
        return pg.QtCore.QRectF(self.x1, -1e9, self.x2 - self.x1, 2e9)

    def paint(self, p, *args):
        p.setBrush(self.brush)
        p.setPen(pg.mkPen(None))
        p.drawRect(self.boundingRect())


class PlotContainer(QWidget):
    def __init__(self, columns, y_ranges):
        super().__init__()
        self.plot_widgets = {}
        self.view_boxes = {}
        self.cursors = {}
        self.columns = columns
        self.plot_items = {col: [] for col in columns}
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        for i, col in enumerate(columns):
            pw = pg.PlotWidget()
            pw.setBackground('k')

            pw.plotItem.setTitle(None)
            pw.getAxis('left').setTextPen('w')
            pw.getAxis('bottom').setTextPen('w')

            if i == len(columns) - 1:
                pw.setLabel('bottom', 'Time', color='white')
            else:
                pw.setLabel('bottom', '')

            pw.setLabel('left', col, color='white')
            pw.showGrid(x=True, y=True, alpha=0.3)
            pw.setMouseEnabled(x=True, y=False)

            try:
                pw.setYRange(y_ranges[i][0], y_ranges[i][1], padding=0)
            except:
                pass

            axis = pg.DateAxisItem(orientation='bottom')
            pw.setAxisItems({'bottom': axis})

            self.layout.addWidget(pw)
            self.plot_widgets[col] = pw
            self.view_boxes[col] = pw.getViewBox()

            if i > 0:
                self.view_boxes[col].setXLink(self.view_boxes[self.columns[0]])

            cursor = CustomInfiniteLine(
                pos=0,
                angle=90,
                pen=pg.mkPen('green', width=3),
                movable=True)
            cursor.setZValue(10)
            pw.addItem(cursor)
            self.cursors[col] = cursor

    def clear_plots(self):
        for col in self.columns:
            pw = self.plot_widgets[col]
            try:
                pw.clear()
            except Exception:
                for item in list(self.plot_items[col]):
                    try:
                        pw.removeItem(item)
                    except:
                        pass
            self.plot_items[col] = []
            try:
                pw.addItem(self.cursors[col])
            except Exception:
                pass


# =============================================================================
# ОСНОВНОЙ КЛАСС: TrendsSubwindow
# =============================================================================
class TrendsSubwindow(BaseModule):
    def __init__(self, bus, parent=None):
        super().__init__(bus, parent)
        self.setWindowTitle("Тренды")
        self.setMinimumWidth(300)

        self.all_data = pd.DataFrame()
        self.time_labels = []
        self.valid_data_indices = []
        self.all_time_labels = []
        self.all_valid_indices = []
        self.current_device = None
        self.data_loader = None
        self.pending_timestamps = []
        self.is_loading = False
        self.lock_cursor_mode = False

        self.main_widget = QWidget()
        if isinstance(self, QMdiSubWindow):
            self.setWidget(self.main_widget)

        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(5)
        self.main_widget.setLayout(self.main_layout)

        self.setup_top_bar()
        self.setup_values_display()
        self.setup_plot_area()

        self.current_theme = 'dark'
        self.apply_theme(self.current_theme)
        self.register_topics()

    def register_topics(self):
        if not self.bus: return
        self.bus.subscribe("signals.timestamp", self.on_signal_timestamp)
        self.bus.subscribe("record.selected", self.on_record_selected)
        self.bus.subscribe("csv.file.opened", self.on_csv_file_opened)

    def setup_top_bar(self):
        self.top_container = QWidget()
        self.top_layout = QHBoxLayout()
        self.top_container.setLayout(self.top_layout)
        self.top_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.addWidget(self.top_container)

        self.go_to_cursor_button = QToolButton()
        self.go_to_cursor_button.setIcon(QIcon("./icons/center_cursor.png"))
        self.go_to_cursor_button.setIconSize(QSize(20, 20))
        self.go_to_cursor_button.setToolTip("Центрировать вид на курсоре")
        self.go_to_cursor_button.clicked.connect(self.center_on_cursor)
        self.top_layout.addWidget(self.go_to_cursor_button)

        self.center_cursor_button = QToolButton()
        self.center_cursor_button.setIcon(QIcon("./icons/custom_center_view.png"))
        self.center_cursor_button.setIconSize(QSize(20, 20))
        self.center_cursor_button.setToolTip("Курсор в центр")
        self.center_cursor_button.clicked.connect(self.move_cursor_to_center)
        self.top_layout.addWidget(self.center_cursor_button)

        self.send_timestamp_button = QToolButton()
        self.send_timestamp_button.setIcon(QIcon("./icons/send_to_signals.png"))
        self.send_timestamp_button.setIconSize(QSize(20, 20))
        self.send_timestamp_button.setToolTip("Передать время в сигналы")
        self.send_timestamp_button.clicked.connect(self.send_timestamp_to_signals)
        self.top_layout.addWidget(self.send_timestamp_button)

        self.lock_cursor_button = QToolButton()
        self.lock_cursor_button.setIcon(QIcon("./icons/lock_cursor_active.png"))
        self.lock_cursor_button.setIconSize(QSize(20, 20))
        self.lock_cursor_button.setCheckable(True)
        self.lock_cursor_button.setToolTip("Фиксировать курсор в центре")
        self.lock_cursor_button.clicked.connect(self.toggle_lock_cursor_mode)
        self.top_layout.addWidget(self.lock_cursor_button)

        self.datetime_label = QLabel("Дата/время: -")
        self.datetime_label.setMinimumWidth(200)
        self.top_layout.addWidget(self.datetime_label)

        self.status_label = QLabel("Нет данных")
        self.top_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(150)
        self.progress_bar.setVisible(False)
        self.top_layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("0%")
        self.progress_label.setMinimumWidth(50)
        self.top_layout.addWidget(self.progress_label)

    def setup_values_display(self):
        self.values_container = QWidget()
        self.values_layout = QHBoxLayout()
        self.values_container.setLayout(self.values_layout)
        self.main_layout.addWidget(self.values_container)

        self.u_a_label = QLabel("U_A: -")
        self.u_a_label.setMinimumWidth(80)
        self.values_layout.addWidget(self.u_a_label)

        self.u_b_label = QLabel("U_B: -")
        self.u_b_label.setMinimumWidth(80)
        self.values_layout.addWidget(self.u_b_label)

        self.u_c_label = QLabel("U_C: -")
        self.u_c_label.setMinimumWidth(80)
        self.values_layout.addWidget(self.u_c_label)

        self.i_a_label = QLabel("I_A: -")
        self.i_a_label.setMinimumWidth(80)
        self.values_layout.addWidget(self.i_a_label)

        self.i_b_label = QLabel("I_B: -")
        self.i_b_label.setMinimumWidth(80)
        self.values_layout.addWidget(self.i_b_label)

        self.i_c_label = QLabel("I_C: -")
        self.i_c_label.setMinimumWidth(80)
        self.values_layout.addWidget(self.i_c_label)

    def setup_plot_area(self):
        self.plot_container = PlotContainer(
            columns=['U_A_rms', 'U_B_rms', 'U_C_rms', 'I_A_rms', 'I_B_rms', 'I_C_rms'],
            y_ranges=[[0, 300], [0, 300], [0, 300], [0, 100], [0, 100], [0, 100]]
        )
        self.main_layout.addWidget(self.plot_container)

        for col in self.plot_container.columns:
            self.plot_container.cursors[col].sigPositionChanged.connect(
                self.make_cursor_sync_function(col)
            )

        self.plot_container.view_boxes['U_A_rms'].sigRangeChanged.connect(
            self.update_cursor_on_range_change
        )

    # -------------------------------------------------------------------------
    # ЗАГРУЗКА ДАННЫХ
    # -------------------------------------------------------------------------

    def on_csv_file_opened(self, payload):
        """Получили уведомление от records_view об открытии CSV."""
        if isinstance(payload, dict):
            file_path = payload.get('file_path')
            if file_path:
                self._start_loader(CsvV2LoaderThread(file_path))

    def fetch_logger_data(self, table_name: str):
        """Загрузка данных из БД (legacy)."""
        self._start_loader(DataLoaderThread(table_name))

    def _start_loader(self, loader):
        """Универсальный запуск загрузчика."""
        if self.data_loader and self.data_loader.isRunning():
            self.data_loader.terminate()
            self.data_loader.wait()

        self.clear_previous_data()
        self.is_loading = True
        self.current_device = getattr(loader, 'table_name', None) or getattr(loader, 'file_path', 'unknown')
        self.status_label.setText("Загрузка данных...")
        self.progress_bar.setVisible(True)
        self.progress_label.setText("0%")

        self.data_loader = loader
        self.data_loader.data_processed.connect(self.on_data_processed)
        self.data_loader.error_occurred.connect(self.on_error_occurred)
        self.data_loader.progress_updated.connect(self.update_progress)
        self.data_loader.finished.connect(self.on_data_loader_finished)
        self.data_loader.start()

    def on_data_loader_finished(self):
        if self.data_loader:
            self.data_loader.deleteLater()
            self.data_loader = None

    def update_progress(self, val):
        self.progress_bar.setValue(val)
        self.progress_label.setText(f"{val}%")

    def on_error_occurred(self, text):
        self.is_loading = False
        self.progress_bar.setVisible(False)
        self.progress_label.setText("0%")
        self.status_label.setText("Ошибка")
        self.on_error_message(text)

    def on_data_processed(self, df):
        total_start = time.perf_counter()
        print(f"[TrendsSubwindow] on_data_processed: получено {len(df)} строк")

        try:
            if df is None or df.empty:
                self.on_error_message("Пустой DataFrame")
                return

            self.all_data = df

            t0 = time.perf_counter()
            self.plot_data(df)
            print(f"[TrendsSubwindow] plot_data() выполнен за {time.perf_counter() - t0:.3f} с")

            self.status_label.setText(f"Данные загружены: {len(df)} точек")
            self.is_loading = False
            self.progress_bar.setVisible(False)
            self.progress_label.setText("100%")

            total_time = time.perf_counter() - total_start
            print(f"[TrendsSubwindow] ПОЛНОЕ ОБНОВЛЕНИЕ ЗАВЕРШЕНО за {total_time:.3f} с")

            self.process_pending_timestamps()
        except Exception as e:
            logging.exception("Ошибка в on_data_processed")
            self.on_error_message(str(e))

    # -------------------------------------------------------------------------
    # ОТРИСОВКА ГРАФИКОВ
    # -------------------------------------------------------------------------

    def plot_data(self, df):
        profiler = RenderProfiler(enabled=True)
        profiler.start("TOTAL")

        profiler.start("clear_plots")
        self.plot_container.clear_plots()
        profiler.end("clear_plots")

        profiler.start("prepare_timestamps")
        timestamps = pd.to_datetime(df['timestamp'], unit='ms', errors='coerce')
        valid_mask = timestamps.notna().to_numpy()
        if not valid_mask.any():
            return

        ts_sec = timestamps.astype('int64') / 1e9
        ts_valid = ts_sec[valid_mask].astype(float)
        df_valid = df.iloc[np.nonzero(valid_mask)[0]].reset_index(drop=True)
        profiler.end("prepare_timestamps")

        profiler.start("find_gaps")
        if len(ts_valid) >= 2:
            diffs = np.diff(ts_valid)
            gap_idx = np.where(diffs > 900)[0]  # разрыв > 15 минут
        else:
            gap_idx = np.array([], dtype=int)
        profiler.end("find_gaps")

        profiler.start("build_plots")
        if gap_idx.size:
            insert_positions = (gap_idx + 1)
            ts2 = np.insert(ts_valid, insert_positions, np.nan)
        else:
            ts2 = ts_valid

        for col in self.plot_container.columns:
            y = df_valid[col].to_numpy(dtype=float)
            if gap_idx.size:
                y2 = np.insert(y, insert_positions, np.nan)
            else:
                y2 = y

            pw = self.plot_container.plot_widgets[col]
            item = pg.PlotDataItem(ts2, y2, pen=pg.mkPen('r', width=1), connect='finite')
            pw.addItem(item)
            self.plot_container.plot_items[col].append(item)

            for g in gap_idx:
                if g + 1 < len(ts_valid):
                    t1 = ts_valid[g]
                    t2 = ts_valid[g + 1]
                    pw.addItem(GapRegion(t1, t2))
        profiler.end("build_plots")

        profiler.start("set_ranges")
        self.all_time_labels = ts_valid.tolist()
        self.all_valid_indices = np.nonzero(valid_mask)[0].tolist()

        if self.all_time_labels:
            min_t, max_t = min(self.all_time_labels), max(self.all_time_labels)
            for c in self.plot_container.cursors.values():
                c.setBounds([min_t, max_t])
                if c.value() < min_t or c.value() > max_t:
                    c.setValue((min_t + max_t) / 2)
            for vb in self.plot_container.view_boxes.values():
                vb.setXRange(min_t, max_t, padding=0.05)
            if self.lock_cursor_mode:
                self.move_cursor_to_center()
        profiler.end("set_ranges")

        profiler.start("update_values")
        self.update_values()
        profiler.end("update_values")

        profiler.end("TOTAL")

    # -------------------------------------------------------------------------
    # КУРСОРЫ И СИНХРОНИЗАЦИЯ
    # -------------------------------------------------------------------------

    def make_cursor_sync_function(self, source_col):
        def sync(line):
            pos = line.value()
            for col, cursor in self.plot_container.cursors.items():
                if col != source_col:
                    cursor.blockSignals(True)
                    cursor.setValue(pos)
                    cursor.blockSignals(False)
            self.update_values()

        return sync

    def update_cursor_on_range_change(self, viewbox, range):
        if self.lock_cursor_mode:
            center = (range[0][0] + range[0][1]) / 2
            for c in self.plot_container.cursors.values():
                c.blockSignals(True)
                c.setValue(center)
                c.blockSignals(False)
            self.update_values()

    def center_on_cursor(self):
        if not self.plot_container.plot_widgets:
            return
        vb = self.plot_container.view_boxes[self.plot_container.columns[0]]
        pos = self.plot_container.cursors[self.plot_container.columns[0]].value()
        x_range = vb.viewRange()[0]
        w = x_range[1] - x_range[0]
        for vb in self.plot_container.view_boxes.values():
            vb.setXRange(pos - w / 2, pos + w / 2, padding=0)

    def move_cursor_to_center(self):
        if not self.plot_container.plot_widgets:
            return
        vb = self.plot_container.view_boxes[self.plot_container.columns[0]]
        r = vb.viewRange()[0]
        center = (r[0] + r[1]) / 2
        for c in self.plot_container.cursors.values():
            c.blockSignals(True)
            c.setValue(center)
            c.blockSignals(False)
        self.update_values()

    def send_timestamp_to_signals(self):
        try:
            pos = self.plot_container.cursors[self.plot_container.columns[0]].value()
            ts_ms = int(pos * 1000)
            if self.bus:
                self.bus.publish("trends.cursor.timestamp", ts_ms)
        except:
            pass

    def toggle_lock_cursor_mode(self):
        self.lock_cursor_mode = self.lock_cursor_button.isChecked()
        icon = "./icons/lock_cursor.png" if self.lock_cursor_mode else "./icons/lock_cursor_active.png"
        self.lock_cursor_button.setIcon(QIcon(icon))
        if self.lock_cursor_mode:
            self.move_cursor_to_center()

    def process_pending_timestamps(self):
        while self.pending_timestamps:
            self.set_cursor_to_timestamp(self.pending_timestamps.pop(0))

    def set_cursor_to_timestamp(self, timestamp_ms):
        if self.is_loading:
            self.pending_timestamps.append(timestamp_ms)
            return
        if self.all_data.empty or not self.all_time_labels:
            return
        try:
            target = timestamp_ms / 1000.0
            arr = np.array(self.all_time_labels, dtype=float)
            idx = np.searchsorted(arr, target)
            if idx == 0:
                pos = arr[0]
            elif idx >= len(arr):
                pos = arr[-1]
            else:
                pos = arr[idx] if abs(arr[idx] - target) < abs(arr[idx - 1] - target) else arr[idx - 1]

            for c in self.plot_container.cursors.values():
                c.blockSignals(True)
                c.setValue(pos)
                c.blockSignals(False)
            self.update_values()
            self.center_on_cursor()
        except Exception as e:
            logging.exception("set_cursor_to_timestamp error")

    def update_values(self):
        start = time.perf_counter()
        try:
            if self.all_data.empty or not self.all_time_labels:
                return
            pos = self.plot_container.cursors[self.plot_container.columns[0]].value()
            arr = np.array(self.all_time_labels, dtype=float)
            idx = np.searchsorted(arr, pos)
            if idx == 0:
                idx = 0
            elif idx >= len(arr):
                idx = len(arr) - 1
            else:
                if abs(arr[idx] - pos) >= abs(arr[idx - 1] - pos):
                    idx = idx - 1

            if idx >= len(self.all_valid_indices):
                return
            data_idx = self.all_valid_indices[idx]
            row = self.all_data.iloc[data_idx]

            ts_sec = row['timestamp'] / 1000.0
            self.datetime_label.setText(f"Дата/время: {datetime.fromtimestamp(ts_sec):%Y-%m-%d %H:%M:%S}")

            labels_map = [
                ('U_A_rms', self.u_a_label, "V"),
                ('U_B_rms', self.u_b_label, "V"),
                ('U_C_rms', self.u_c_label, "V"),
                ('I_A_rms', self.i_a_label, "A"),
                ('I_B_rms', self.i_b_label, "A"),
                ('I_C_rms', self.i_c_label, "A")
            ]
            for col, label, unit in labels_map:
                val = row[col]
                if pd.notna(val):
                    label.setText(f"{col[0]}: {val:.1f} {unit}")
                else:
                    label.setText(f"{col[0]}: -")
        except Exception:
            pass
        finally:
            elapsed = time.perf_counter() - start
            if elapsed > 0.03:
                print(f"[update_values] медленно: {elapsed:.4f} с")

    def clear_previous_data(self):
        self.all_data = pd.DataFrame()
        self.time_labels = []
        self.valid_data_indices = []
        self.all_time_labels = []
        self.all_valid_indices = []
        self.pending_timestamps = []
        self.is_loading = False
        self.plot_container.clear_plots()
        self.datetime_label.setText("Дата/время: -")
        for lbl in [self.u_a_label, self.u_b_label, self.u_c_label,
                    self.i_a_label, self.i_b_label, self.i_c_label]:
            lbl.setText(lbl.text().split(':')[0] + ": -")
        self.status_label.setText("Очистка...")
        self.progress_label.setText("0%")

    def on_error_message(self, text):
        msg = QMessageBox()
        msg.setWindowTitle("Ошибка")
        msg.setText(str(text))
        msg.exec()

    def on_signal_timestamp(self, timestamp_ms):
        self.set_cursor_to_timestamp(timestamp_ms)

    def on_record_selected(self, payload):
        table_name = payload.get("table_name") if isinstance(payload, dict) else payload
        if table_name:
            self.fetch_logger_data(table_name)

    # -------------------------------------------------------------------------
    # ТЕМЫ
    # -------------------------------------------------------------------------

    def apply_theme(self, theme_name: str):
        dark = theme_name == 'dark'

        palette = ThemeManager.get_palette(theme_name)
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        self.main_widget.setPalette(palette)
        self.main_widget.setAutoFillBackground(True)

        btn_style = ThemeManager.get_button_style(theme_name)
        lbl_style = ThemeManager.get_label_style(theme_name)

        for btn in [self.go_to_cursor_button, self.center_cursor_button,
                    self.send_timestamp_button, self.lock_cursor_button]:
            btn.setStyleSheet(btn_style)

        for lbl in [self.datetime_label, self.status_label, self.progress_label,
                    self.u_a_label, self.u_b_label, self.u_c_label,
                    self.i_a_label, self.i_b_label, self.i_c_label]:
            lbl.setStyleSheet(lbl_style)

        if dark:
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

        bg = 'k' if dark else 'w'
        fg = 'w' if dark else 'k'
        pg.setConfigOptions(background=bg, foreground=fg)
        bg_color = "#353535" if dark else "#ffffff"
        self.main_widget.setStyleSheet(f"background-color: {bg_color};")

        cursor_pos = None
        was_locked = self.lock_cursor_mode
        if self.plot_container.cursors:
            cursor_pos = self.plot_container.cursors[self.plot_container.columns[0]].value()

        self.plot_container.clear_plots()

        for idx, (col, pw) in enumerate(self.plot_container.plot_widgets.items()):
            pw.setBackground(bg)
            pw.plotItem.setTitle(None)

            left_axis = pw.getAxis('left')
            left_axis.setPen(fg)
            left_axis.setTextPen(fg)

            bottom_axis = pw.getAxis('bottom')
            bottom_axis.setPen(fg)
            bottom_axis.setTextPen(fg)

            if idx == len(self.plot_container.columns) - 1:
                pw.setLabel('bottom', 'Time', color=fg)
            else:
                pw.setLabel('bottom', '')

            pw.setLabel('left', col, color=fg)
            pw.showGrid(x=True, y=True, alpha=0.3)

            cursor = self.plot_container.cursors.get(col)
            if cursor:
                cursor.setPen(pg.mkPen('#00ff00', width=2))

        if not self.all_data.empty:
            self.plot_data(self.all_data)

        if cursor_pos is not None:
            for c in self.plot_container.cursors.values():
                c.blockSignals(True)
                c.setValue(cursor_pos)
                c.blockSignals(False)
            self.update_values()
            if was_locked:
                self.center_on_cursor()

        self.setPalette(palette)
        self.setAutoFillBackground(True)