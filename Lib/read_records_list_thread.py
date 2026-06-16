from PyQt6 import QtCore
from Lib import pipestreamdbread as pdb
import logging


class ReadRecordListThread(QtCore.QThread):
    result_signal = QtCore.pyqtSignal(list)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, tablename, parent = None):
        super().__init__(parent)
        QtCore.QThread.__init__(self, parent)
        self.tablename = tablename
        self.running = False

    def run(self):

        if len(self.tablename) <3:
            logging.error(f"Ошибка в потоке вычитывания списка записей; вместо имени таблицы получено: {self.tablename}")
            return

        self.running = True

        logging.info(f"Вычитывание списка записей таблицы {self.tablename} в потоке (фоном)")

        connection, cursor, status = pdb.connect_db(pdb.db_connection_params)

        if connection == 0 or cursor == 0:
            self.error_signal.emit(status)
            return

        record_list = pdb.get_records_list(cursor, self.tablename)

        self.result_signal.emit(record_list)

        #---------------------------------------------
        #штатно закрываем соединение
        if connection:
            cursor.close()
            connection.close()
            logging.info(f"Соединение с PostgreSQL закрыто")   