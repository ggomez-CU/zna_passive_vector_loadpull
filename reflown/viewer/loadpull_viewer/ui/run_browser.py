from __future__ import annotations

from typing import Dict, List
from PySide6 import QtCore, QtWidgets

from ..data.model import RunInfo


class RunBrowser(QtWidgets.QTreeWidget):
    sig_run_selected = QtCore.Signal(RunInfo)
    sig_runs_selected = QtCore.Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(["Runs"])
        self._cache: Dict[str, List[RunInfo]] = {}
        self._active_test: str | None = None
        self.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.itemChanged.connect(self._on_item_changed)

    def load_groups(self, grouped: Dict[str, List[RunInfo]]) -> None:
        self._cache = grouped
        self.clear()
        for test, runs in grouped.items():
            parent = QtWidgets.QTreeWidgetItem([test])
            self.addTopLevelItem(parent)
            for r in runs:
                child = QtWidgets.QTreeWidgetItem([r.timestamp])
                child.setData(0, QtCore.Qt.UserRole, r)
                child.setFlags(child.flags() | QtCore.Qt.ItemIsUserCheckable)
                child.setCheckState(0, QtCore.Qt.Unchecked)
                parent.addChild(child)
            parent.setExpanded(True)

    def refresh_if_changed(self, grouped: Dict[str, List[RunInfo]]) -> bool:
        if sum(len(v) for v in grouped.values()) != sum(len(v) for v in self._cache.values()):
            self.load_groups(grouped)
            return True
        return False

    def _on_item_changed(self, item: QtWidgets.QTreeWidgetItem, _col: int) -> None:
        data = item.data(0, QtCore.Qt.UserRole)
        if not isinstance(data, RunInfo):
            return
        # If this item was checked, enforce single test_type by unchecking all others of different type
        if item.checkState(0) == QtCore.Qt.Checked:
            if self._active_test is None or self._active_test != data.test_type:
                self._active_test = data.test_type
                # Uncheck everything not matching this type
                for i in range(self.topLevelItemCount()):
                    parent = self.topLevelItem(i)
                    for j in range(parent.childCount()):
                        ch = parent.child(j)
                        rd = ch.data(0, QtCore.Qt.UserRole)
                        if isinstance(rd, RunInfo) and rd.test_type != self._active_test:
                            if ch.checkState(0) != QtCore.Qt.Unchecked:
                                # block signal to avoid recursion
                                self.blockSignals(True)
                                ch.setCheckState(0, QtCore.Qt.Unchecked)
                                self.blockSignals(False)
        else:
            # If all are unchecked, clear active test
            any_checked = False
            for i in range(self.topLevelItemCount()):
                parent = self.topLevelItem(i)
                for j in range(parent.childCount()):
                    if parent.child(j).checkState(0) == QtCore.Qt.Checked:
                        any_checked = True
                        break
                if any_checked:
                    break
            if not any_checked:
                self._active_test = None

        # Gather checked runs and emit
        checked: List[RunInfo] = []
        for i in range(self.topLevelItemCount()):
            parent = self.topLevelItem(i)
            for j in range(parent.childCount()):
                ch = parent.child(j)
                if ch.checkState(0) == QtCore.Qt.Checked:
                    rd = ch.data(0, QtCore.Qt.UserRole)
                    if isinstance(rd, RunInfo):
                        checked.append(rd)
        if len(checked) == 1:
            self.sig_run_selected.emit(checked[0])
        if checked:
            self.sig_runs_selected.emit(checked)
