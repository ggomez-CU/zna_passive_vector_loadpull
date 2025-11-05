from __future__ import annotations

from typing import Iterable, List
from PySide6 import QtCore, QtWidgets


class MetadataPanel(QtWidgets.QWidget):
    sig_options_changed = QtCore.Signal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        lay = QtWidgets.QVBoxLayout(self)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Columns"])
        self.tree.itemChanged.connect(self._emit)

        self.detail = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.detail.setRange(1, 5)
        self.detail.setValue(3)
        self.detail.valueChanged.connect(lambda _: self._emit())

        lay.addWidget(self.tree)
        form = QtWidgets.QFormLayout()
        form.addRow("Detail", self.detail)
        lay.addLayout(form)

    def set_columns(self, columns: Iterable[str]) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        parent = QtWidgets.QTreeWidgetItem(["Signals"])
        self.tree.addTopLevelItem(parent)
        for k in sorted(columns):
            item = QtWidgets.QTreeWidgetItem([k])
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(0, QtCore.Qt.Checked)
            parent.addChild(item)
        parent.setExpanded(True)
        self.tree.blockSignals(False)

    def _emit(self) -> None:
        selected: List[str] = []
        root = self.tree.topLevelItem(0)
        if root:
            for i in range(root.childCount()):
                it = root.child(i)
                if it.checkState(0) == QtCore.Qt.Checked:
                    selected.append(it.text(0))
        self.sig_options_changed.emit({"columns": selected, "detail": int(self.detail.value())})

