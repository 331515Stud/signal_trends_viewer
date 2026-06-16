from PyQt6.QtWidgets import QLineEdit
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtCore import QSize

class ResizableLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.textChanged.connect(self.adjustSize)
        self.setFont(QFont("Arial", 10))
        self.setStyleSheet('''
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 5px;
                spacing: 5px;
            }
        ''')

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        text_width = fm.horizontalAdvance(self.text() or " ") + 40
        text_height = fm.height()
        padding = 10
        return QSize(text_width + padding, text_height + padding)

    def adjustSize(self):
        self.setMaximumSize(self.sizeHint())