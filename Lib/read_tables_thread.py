from PyQt6 import QtCore
from Lib import pipestreamdbread as pdb
import logging


class ReadTablesThread(QtCore.QThread):
    result_signal = QtCore.pyqtSignal(dict)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, parent = None):
        super().__init__(parent)
        QtCore.QThread.__init__(self, parent)
        self.running = False

    def run(self):
        self.running = True

        logging.info(f"Старт потока вычитыания списка таблиц и их параметров")


        connection, cursor, status = pdb.connect_db(pdb.db_connection_params)

        if connection == 0 or cursor == 0:
            self.error_signal.emit(status)
            return

        logger_data_table_list = pdb.get_logger_data_table_list(cursor)

        for device in logger_data_table_list:
            if not self.running:
                return

            table_description = pdb.get_table_description(cursor, device)
            self.result_signal.emit(table_description)

        #---------------------------------------------
        #штатно закрываем соединение
        if connection:
            cursor.close()
            connection.close()
            logging.info(f"Соединение с PostgreSQL закрыто")   