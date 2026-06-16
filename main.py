import sys
import logging
from ui.main_window import MainWindow
from utils.config import setup_logging, create_export_directory
from PyQt6.QtWidgets import QApplication

def main():
    setup_logging()
    create_export_directory()
    logging.info("Старт программы")
    app = QApplication(sys.argv)
    ex = MainWindow()
    ex.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()