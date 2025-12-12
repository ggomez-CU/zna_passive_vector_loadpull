from __future__ import annotations

"""Simple read-only log pane."""

from PySide6 import QtWidgets


class IssuesPanel(QtWidgets.QTextEdit):
    def __init__(self, parent=None) -> None:
        print("init: IssuesPanel.__init__", flush=True)
        super().__init__(parent)
        self.setReadOnly(True)

    def log(self, msg: str) -> None:
        print("init: IssuesPanel.log", flush=True)
        self.append(msg)
