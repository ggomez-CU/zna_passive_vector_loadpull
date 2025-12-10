from __future__ import annotations

"""Plotter main window.

Modular, read‑only GUI for browsing and plotting measurement runs.
"""

import sys
from pathlib import Path
from typing import Optional, Iterable

from PySide6 import QtCore, QtWidgets, QtGui

from .settings import Settings
from .data.discovery import discover_runs_grouped
from .testtypes.registry import TestTypeRegistry
from .ui.toolbar import AppToolBar
from .ui.runs_panel import RunsPanel
from .ui.filters_panel import FiltersPanel
from .ui.metadata_panel import MetadataPanel
from .ui.issues_panel import IssuesPanel
from .plots.deck import PlotDeck
from .ui_form import Ui_MainWindow


class MainWindow(QtWidgets.QMainWindow):
    """Top‑level window with docks and central plot deck."""

    POLL_MS = 3000

    def __init__(self, root: Optional[str] = None) -> None:
        # print("init: MainWindow.__init__", flush=True)
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setWindowTitle("Loadpull Plotter")
        self.resize(1300, 850)

        self.settings = Settings()
        self.root_dir = Path(root or self.settings.last_root() or ".").resolve()
        self.registry = TestTypeRegistry()

        self._filters_state: dict = {}
        self._options_state: dict = {}

        self._build_ui()
        self._wire_signals()
        self._reload_runs()

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._maybe_refresh)
        self.timer.start(self.POLL_MS)

        # App now reads data from the database; no background collector

    def _build_ui(self) -> None:

        # Initializes widgets

        self.toolbar = AppToolBar(self)
        self.deck = PlotDeck(self.registry, self)
        self.runs = RunsPanel(self)
        self.filters = FiltersPanel(self)
        self.metadata = MetadataPanel(self)
        self.issues = IssuesPanel(self)

        #Set locations for widgets
        self.addToolBar(self.toolbar)
        self.setCentralWidget(self.deck)

        dock_runs = QtWidgets.QDockWidget("Runs", self)
        dock_runs.setWidget(self.runs)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock_runs)

        dock_filters = QtWidgets.QDockWidget("Filters", self)
        dock_filters.setWidget(self.filters)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock_filters)

        dock_meta = QtWidgets.QDockWidget("Metadata", self)
        dock_meta.setWidget(self.metadata)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock_meta)

        dock_issues = QtWidgets.QDockWidget("Issues", self)
        dock_issues.setWidget(self.issues)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, dock_issues)

        self.status = self.statusBar()
        self._update_title()

    def _wire_signals(self) -> None:
        # print("init: MainWindow._wire_signals", flush=True)
        self.toolbar.sig_select_root.connect(self._choose_root)
        self.toolbar.sig_toggle_log.connect(self.deck.set_log_mode)
        self.toolbar.sig_export.connect(self.deck.export_current)

        self.runs.sig_runs_selected.connect(self._load_runs)
        self.filters.sig_filters_changed.connect(self._on_filters)
        self.metadata.sig_options_changed.connect(self._on_options)

    def _update_title(self) -> None:
        # print("init: MainWindow._update_title", flush=True)
        self.setWindowTitle(f"Loadpull Plotter - {self.root_dir}")

    # No conflict handling needed; database is read-only for the app

    def _choose_root(self) -> None:
        # print("init: MainWindow._choose_root", flush=True)
        dlg = QtWidgets.QFileDialog(self, "Select runs root", str(self.root_dir))
        dlg.setFileMode(QtWidgets.QFileDialog.Directory)
        dlg.setOption(QtWidgets.QFileDialog.ShowDirsOnly, True)
        if dlg.exec():
            paths = dlg.selectedFiles()
            if paths:
                self.root_dir = Path(paths[0])
                self.settings.set_last_root(str(self.root_dir))
                self._update_title()
                self._reload_runs()

    def _reload_runs(self) -> None:
        # print("init: MainWindow._reload_runs", flush=True)
        grouped = discover_runs_grouped(self.root_dir)
        self.runs.load_groups(grouped)
        self.status.showMessage(f"Discovered {sum(len(v) for v in grouped.values())} runs")

    def _maybe_refresh(self) -> None:
        # print("init: MainWindow._maybe_refresh", flush=True)
        grouped = discover_runs_grouped(self.root_dir)
        if self.runs.refresh_if_changed(grouped):
            self.status.showMessage("Runs updated")

    def _load_runs(self, runs: list) -> None:
        # print("init: MainWindow._load_runs", flush=True)
        if not runs:
            return
        ttype = runs[0].test_type
        runs = [r for r in runs if r.test_type == ttype]
        self.deck.set_test_type(ttype)
        self.deck.load_runs(runs)
        # Build metadata options from registry specs
        cols: list[str] = []
        def _append_cols(value: Optional[Iterable[str] | str]) -> None:
            if not value:
                return
            if isinstance(value, str):
                cols.append(value)
                return
            for entry in value:
                if entry:
                    cols.append(entry)
        for specs in self.registry.tabs_for(ttype).values():
            for spec in specs:
                _append_cols(spec.get("y"))
                _append_cols(spec.get("x"))
                _append_cols(spec.get("xy"))
                for ser in spec.get("series", []) or []:
                    _append_cols(ser.get("x"))
                    _append_cols(ser.get("y"))
                    _append_cols(ser.get("xy"))
                _append_cols(spec.get("columns"))
        self.metadata.set_columns(sorted(set(cols)))

    def _on_filters(self, ranges: dict) -> None:
        # print("init: MainWindow._on_filters", flush=True)
        self._filters_state = dict(ranges)
        self.deck.apply_filters(self._filters_state)

    def _on_options(self, opts: dict) -> None:
        # print("init: MainWindow._on_options", flush=True)
        self._options_state = dict(opts)
        self.deck.set_options(self._options_state)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[name-defined]
        super().closeEvent(event)


def main() -> None:
    # print("init: main", flush=True)
    app = QtWidgets.QApplication(sys.argv)
    mw = MainWindow()
    mw.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
