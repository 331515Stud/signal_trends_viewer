
from PyQt6.QtCore import pyqtSignal
import PyQt6.QtCore as QtCore
from Lib import pipestreamdbread as pdb

class SignalsPresenter(QtCore.QObject):
    timestamp_changed = pyqtSignal(int)

    def __init__(self, view, model, parent_window=None):
        super().__init__()
        self.view = view
        self.model = model
        self.parent_window = parent_window

        self.view.set_presenter(self)

    def set_current_data(self, in_data):
        self.model.current_data = in_data
        self.view.set_current_data(in_data)

    def plot_record(self, table_name, colname_list, in_data, rec_num):
        if not table_name or not colname_list or not in_data:
            return

        self.model.current_device = table_name
        self.model.colnameList = colname_list
        self.model.current_rec_num = rec_num

        self.set_current_data(in_data)

        signals = self.model.get_signals(in_data)
        processed_signals = self.model.process_signal(signals)

        self.view.plot_record(table_name, colname_list, in_data, rec_num)

    def send_timestamp_to_trends(self, timestamp):
        if self.parent_window and hasattr(self.parent_window, 'trends_view'):
            self.parent_window.trends_view.set_cursor_to_timestamp(timestamp)
            if hasattr(self.parent_window, 'status_bar'):
                self.parent_window.status_bar.showMessage(
                    f"Время {pdb.datetime_from_timestamp(timestamp).strftime('%d.%m.%Y %H:%M:%S')} передано в окно трендов", 5000
                )
        else:
            self.view.show_error("Окно трендов недоступно")

    def set_timestamp_from_trends(self, timestamp):
        # Вызывается из окна трендов
        self.view.set_timestamp_from_trends(timestamp)

    def show_error(self, text):
        self.view.on_error_message(text)