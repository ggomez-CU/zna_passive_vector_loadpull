from __future__ import annotations

"""Metadata panel with checkbox tree for series visibility."""

from typing import Iterable, List
from PySide6 import QtCore, QtWidgets


class MetadataPanel(QtWidgets.QWidget):
    sig_options_changed = QtCore.Signal(dict)

    def __init__(self, parent=None) -> None:
        print("init: MetadataPanel.__init__", flush=True)
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        print("init: MetadataPanel._build", flush=True)
        v = QtWidgets.QVBoxLayout(self)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Signals"])
        self.tree.itemChanged.connect(self._emit)
        v.addWidget(self.tree)

    def set_columns(self, columns: Iterable[str]) -> None:
        print("init: MetadataPanel.set_columns", flush=True)
        self.tree.blockSignals(True)
        self.tree.clear()
        parent = QtWidgets.QTreeWidgetItem(["Signals"])
        self.tree.addTopLevelItem(parent)
        for k in sorted(set(columns)):
            it = QtWidgets.QTreeWidgetItem([k])
            it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
            it.setCheckState(0, QtCore.Qt.Checked)
            parent.addChild(it)
        parent.setExpanded(True)
        self.tree.blockSignals(False)

    def _emit(self) -> None:
        print("init: MetadataPanel._emit", flush=True)
        cols: List[str] = []
        root = self.tree.topLevelItem(0)
        if root:
            for i in range(root.childCount()):
                it = root.child(i)
                if it.checkState(0) == QtCore.Qt.Checked:
                    cols.append(it.text(0))
        self.sig_options_changed.emit({"columns": cols})
