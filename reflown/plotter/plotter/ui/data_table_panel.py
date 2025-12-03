from __future__ import annotations

"""Simple table panel to display selected columns."""

from typing import Dict, Iterable, List, Sequence, Tuple

from PySide6 import QtWidgets


class DataTablePanel(QtWidgets.QWidget):
    def __init__(self, parent=None) -> None:
        print("init: DataTablePanel.__init__", flush=True)
        super().__init__(parent)
        self._tabs = QtWidgets.QTabWidget(self)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tabs)

    def _build_table(self, cols: List[str], data: Dict[str, List]) -> QtWidgets.QTableWidget:
        table = QtWidgets.QTableWidget()
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.setColumnCount(len(cols))
        table.setHorizontalHeaderLabels(cols)
        if not cols:
            table.setRowCount(0)
            return table
        max_rows = max((len(data.get(c, [])) for c in cols), default=0)
        table.setRowCount(max_rows)
        for col_idx, col_name in enumerate(cols):
            values = data.get(col_name, [])
            for row_idx in range(max_rows):
                val = values[row_idx] if row_idx < len(values) else ""
                table.setItem(row_idx, col_idx, QtWidgets.QTableWidgetItem(str(val)))
        table.resizeColumnsToContents()
        return table

    def set_data(self, columns: Iterable[str], runs_data: Sequence[Tuple[str, Dict[str, List]]]) -> None:
        """Render one table per run with the same columns (one tab per run)."""
        print("init: DataTablePanel.set_data", flush=True)
        cols = list(columns)
        self._tabs.clear()
        if not cols or not runs_data:
            return
        for label, data in runs_data:
            table = self._build_table(cols, data)
            self._tabs.addTab(table, str(label))
