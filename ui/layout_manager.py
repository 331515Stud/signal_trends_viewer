from PyQt6.QtWidgets import QWidget, QSplitter, QVBoxLayout
from PyQt6.QtCore import Qt
from event_bus import EventBus

class LayoutManager:
    def __init__(self, mdi_area, bus: EventBus = None):
        self.mdi = mdi_area
        self.bus = bus
        self.mode = "horizontal"

        self.records_view = None
        self.trends_view = None
        self.signals_view = None

        self.container_widget = None
        self.outer_splitter = None
        self.inner_splitter = None

        if self.bus:
            @self.bus.on("LAYOUT_CHANGED")
            def handle_layout_changed(payload):
                mode = payload.get("mode", self.mode)
                self.set_mode(mode)

            @self.bus.on("AUTO_RESIZE_SIGNALS")
            def handle_auto_resize_signals(payload):
                ratio = payload.get("ratio", 0.4)
                self.resize_signals_panel(ratio)

            @self.bus.on("RESIZE_RECORDS_PANEL")
            def handle_resize_records_panel(payload):
                width = payload.get("width", 250)
                self.resize_records_panel(width)

    def set_mode(self, mode):
        self.mode = mode
        if self.inner_splitter:
            orient = Qt.Orientation.Horizontal if mode == "horizontal" else Qt.Orientation.Vertical
            self.inner_splitter.setOrientation(orient)

    def set_windows(self, records_view, trends_view, signals_view):
        self.records_view = records_view
        self.trends_view = trends_view
        self.signals_view = signals_view

        for sub in self.mdi.subWindowList():
            sub.close()

        self.inner_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.inner_splitter.addWidget(trends_view)
        self.inner_splitter.addWidget(signals_view)
        self.inner_splitter.setHandleWidth(4)
        self.inner_splitter.setChildrenCollapsible(False)
        self.inner_splitter.setStretchFactor(0, 1)
        self.inner_splitter.setStretchFactor(1, 1)

        self.outer_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.outer_splitter.addWidget(records_view)
        self.outer_splitter.addWidget(self.inner_splitter)
        self.outer_splitter.setHandleWidth(5)
        self.outer_splitter.setChildrenCollapsible(False)
        self.outer_splitter.setStretchFactor(0, 1)
        self.outer_splitter.setStretchFactor(1, 3)

        self._apply_splitter_style()

        self.container_widget = QWidget()
        layout = QVBoxLayout(self.container_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.outer_splitter)

        self.mdi.setViewMode(self.mdi.ViewMode.SubWindowView)
        sub = self.mdi.addSubWindow(self.container_widget)
        sub.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        sub.showMaximized()
        sub.setStyleSheet("background: transparent; border: none;")

    def resize_signals_panel(self, ratio: float = 0.4):
        if not self.inner_splitter:
            return
        total_size = sum(self.inner_splitter.sizes())
        new_signals_size = int(total_size * ratio)
        new_trends_size = total_size - new_signals_size
        self.inner_splitter.setSizes([new_trends_size, new_signals_size])

    def resize_records_panel(self, width: int):
        if not self.outer_splitter:
            return
        total_size = sum(self.outer_splitter.sizes())
        new_records_size = width
        new_inner_size = total_size - new_records_size
        if new_inner_size < 100:
            new_inner_size = 100
            new_records_size = total_size - new_inner_size
        self.outer_splitter.setSizes([new_records_size, new_inner_size])

    def _apply_splitter_style(self):
        splitter_style = """
        QSplitter::handle {
            background-color: #444;
        }
        QSplitter::handle:hover {
            background-color: #666;
        }
        QSplitter > QWidget {
            border: 1px solid #333;
            background-color: #202020;
        }
        """
        if self.outer_splitter:
            self.outer_splitter.setStyleSheet(splitter_style)
        if self.inner_splitter:
            self.inner_splitter.setStyleSheet(splitter_style)