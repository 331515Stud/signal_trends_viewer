from PyQt6.QtWidgets import QMainWindow, QMdiArea, QStatusBar, QToolBar, QToolButton
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt

from core.bus import EventBus
from ui.records_view import RecordsView_subwindow
from ui.signals_view import SignalsView_subwindow
from ui.trends_view import TrendsSubwindow
from ui.themes import ThemeManager
from ui.layout_manager import LayoutManager


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Визуализатор для PipeStreamDB v.1.0")
        self.setMinimumSize(1200, 800)
        self.app_icon = QIcon("./icons/oscilloscope.png")
        self.setWindowIcon(self.app_icon)

        self.mdi = QMdiArea()
        self.setCentralWidget(self.mdi)

        self.bus = EventBus()

        self.theme_manager = ThemeManager(self.bus)
        self.current_theme = 'dark'
        self.layout_manager = LayoutManager(self.mdi, self.bus)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.setup_toolbar()

        self.setup_subwindows()

        self.apply_theme()

        self.layout_manager.set_windows(
            self.records_view,
            self.trends_view,
            self.signals_view
        )

        self.showMaximized()

    def setup_toolbar(self):
        toolbar = QToolBar("Layout Control")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.theme_button = QToolButton()
        self.theme_button.setText("☀️ Светлая")
        self.theme_button.setToolTip("Переключить тему (тёмная/светлая)")
        self.theme_button.setIcon(QIcon("./icons/theme_light.png"))
        self.theme_button.setFixedSize(120, 40)
        self.theme_button.clicked.connect(self.toggle_theme)
        toolbar.addWidget(self.theme_button)

        self.layout_button = QToolButton()
        self.layout_button.setText("↔ Горизонтальная")
        self.layout_button.setToolTip("Переключить компоновку трендов и сигналов (↔ / ↕)")
        self.layout_button.setIcon(QIcon("./icons/layout_horizontal.png"))
        self.layout_button.setFixedSize(180, 40)
        self.layout_button.clicked.connect(self.toggle_layout)
        toolbar.addWidget(self.layout_button)

    def setup_subwindows(self):
        self.records_view = RecordsView_subwindow(self.bus, parent=self)
        self.trends_view = TrendsSubwindow(self.bus, parent=self)
        self.signals_view = SignalsView_subwindow(self.bus, parent=self)

        for win in [self.records_view, self.trends_view, self.signals_view]:
            win.setWindowIcon(self.app_icon)

    def apply_theme(self):
        palette = self.theme_manager.get_palette(self.current_theme)
        self.setPalette(palette)
        self.mdi.setPalette(palette)
        self.statusBar().setPalette(palette)

        bstyle = self.theme_manager.get_button_style(self.current_theme)
        self.theme_button.setStyleSheet(bstyle)
        self.layout_button.setStyleSheet(bstyle)

        for win in [self.records_view, self.signals_view, self.trends_view]:
            if hasattr(win, 'apply_theme'):
                win.apply_theme(self.current_theme)

    def toggle_theme(self):
        self.current_theme = 'light' if self.current_theme == 'dark' else 'dark'
        self.apply_theme()

        if self.current_theme == 'dark':
            self.theme_button.setText("☀️ Светлая")
            self.theme_button.setIcon(QIcon("./icons/theme_light.png"))
        else:
            self.theme_button.setText("🌙 Тёмная")
            self.theme_button.setIcon(QIcon("./icons/theme_dark.png"))

    def toggle_layout(self):
        new_mode = 'vertical' if self.layout_manager.mode == 'horizontal' else 'horizontal'
        self.layout_manager.set_mode(new_mode)

        self.layout_button.setText("↕ Вертикальная" if new_mode == 'vertical' else "↔ Горизонтальная")
        self.layout_button.setIcon(QIcon(f"./icons/layout_{new_mode}.png"))

    def resizeEvent(self, event):
        super().resizeEvent(event)