from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class TaskSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()


class BackgroundTask(QRunnable):
    def __init__(self, operation: Callable[[], Any]):
        super().__init__()
        self.operation = operation
        self.signals = TaskSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.completed.emit(self.operation())
        except Exception as error:
            self.signals.failed.emit(str(error))
        finally:
            self.signals.finished.emit()
