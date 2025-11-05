from __future__ import annotations

from PySide6 import QtWidgets


class IssuesPanel(QtWidgets.QTextEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)

    def log(self, msg: str) -> None:
        self.append(msg)

