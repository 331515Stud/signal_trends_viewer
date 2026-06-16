from PyQt6.QtWidgets import QMdiSubWindow

class BaseModule(QMdiSubWindow):

    def __init__(self, bus, parent=None):
        super().__init__(parent)
        self.bus = bus

    def publish(self, topic: str, payload=None):
        if self.bus:
            self.bus.publish(topic, payload)
