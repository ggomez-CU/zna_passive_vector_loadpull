from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class AppToolBar(QtWidgets.QToolBar):
    sig_select_root = QtCore.Signal()
    sig_toggle_log = QtCore.Signal(bool)
    sig_export = QtCore.Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__("Toolbar", parent)
        self.setMovable(False)

        self.addAction("Open Root…", lambda: self.sig_select_root.emit())

        self._log = QtWidgets.QCheckBox("Log Y")
        self._log.stateChanged.connect(lambda _: self.sig_toggle_log.emit(self._log.isChecked()))
        self.addWidget(self._log)

        self.addSeparator()
        export_menu = QtWidgets.QMenu("Export", self)
        for kind, label in (("png", "PNG"), ("svg", "SVG"), ("csv", "CSV (Plotted Columns)"), ("csv-all", "CSV (All JSONL Fields)")):
            export_menu.addAction(label, lambda k=kind: self.sig_export.emit(k))
        btn = QtWidgets.QToolButton()
        btn.setText("Export")
        btn.setMenu(export_menu)
        btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.addWidget(btn)
