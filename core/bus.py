
from typing import Callable, Dict, List, Any
from PyQt6.QtCore import QObject, pyqtSignal

class EventBus(QObject):
    event_published = pyqtSignal(str, object)

    def __init__(self):
        super().__init__()
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}

    def subscribe(self, topic: str, callback: Callable[[Any], None]):
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(callback)

    def on(self, topic: str):
        def decorator(func: Callable[[Any], None]):
            self.subscribe(topic, func)
            return func
        return decorator

    def publish(self, topic: str, payload: Any = None):
        if topic in self._subscribers:
            for callback in list(self._subscribers[topic]):
                try:
                    callback(payload)
                except Exception as e:
                    print(f"[EventBus] Error in handler {callback}: {e}")
        try:
            self.event_published.emit(topic, payload)
        except Exception:
            pass
