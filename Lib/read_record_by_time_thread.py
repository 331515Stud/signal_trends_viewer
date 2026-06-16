from PyQt6 import QtCore
from Lib import pipestreamdbread as pdb
import logging


class ReadRecordThread(QtCore.QThread):
    result_signal = QtCore.pyqtSignal(dict)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, tablename, colnames_list, timestamp, parent = None):
        super().__init__(parent)
        QtCore.QThread.__init__(self, parent)
        self.tablename = tablename
        self.timestamp = timestamp
        self.colnames_list = colnames_list
        self.running = False

    def run(self):

        if len(self.tablename) <3:
            logging.error(f"Ошибка в потоке вычитывания последней записи; вместо имени таблицы получено: {self.tablename}")
            return

        self.running = True

        connection, cursor, status = pdb.connect_db(pdb.db_connection_params)

        if connection == 0 or cursor == 0:
            self.error_signal.emit(status)
            return

        rec_dict = pdb.get_record(cursor, self.tablename, self.timestamp, self.colnames_list)

        self.result_signal.emit(rec_dict)

        #---------------------------------------------
        #штатно закрываем соединение
        if connection:
            cursor.close()
            connection.close()
            logging.info(f"Соединение с PostgreSQL закрыто")   