from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtWidgets

from .settings import Settings
from .ui.run_browser import RunBrowser
from .ui.filters import FiltersPanel
from .ui.metadata import MetadataPanel
from .ui.issues import IssuesPanel
from .ui.plot_area import PlotArea
from .ui.toolbar import AppToolBar
from .data.discovery import discover_runs_grouped
from .testtypes.registry import TestTypeRegistry


class MainWindow(QtWidgets.QMainWindow):
    POLL_MS = 3000

    def __init__(self, root: Optional[str] = None) -> None:
        super().__init__()
        self.setWindowTitle("Loadpull Viewer")
        self.resize(1300, 850)

        self.settings = Settings()
        self.root_dir = Path(root or self.settings.last_root() or ".").resolve()
        self.registry = TestTypeRegistry()

        self._filters_state = {}
        self._options_state = {}

        self._build_ui()
        self._wire_signals()
        self._reload_runs()

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._maybe_refresh)
        self.timer.start(self.POLL_MS)

    def _build_ui(self) -> None:
        self.toolbar = AppToolBar(parent=self)
        self.addToolBar(self.toolbar)

        # Central plots
        self.plots = PlotArea(self.registry, self)
        self.setCentralWidget(self.plots)

        # Docks
        self.browser = RunBrowser(self)
        dock_runs = QtWidgets.QDockWidget("Runs", self)
        dock_runs.setWidget(self.browser)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock_runs)

        self.filters = FiltersPanel(self)
        dock_filters = QtWidgets.QDockWidget("Filters", self)
        dock_filters.setWidget(self.filters)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock_filters)

        self.metadata = MetadataPanel(self)
        dock_meta = QtWidgets.QDockWidget("Metadata", self)
        dock_meta.setWidget(self.metadata)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock_meta)

        self.issues = IssuesPanel(self)
        dock_issues = QtWidgets.QDockWidget("Issues", self)
        dock_issues.setWidget(self.issues)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, dock_issues)

        self.status = self.statusBar()
        self._update_title()

    def _wire_signals(self) -> None:
        self.toolbar.sig_select_root.connect(self._choose_root)
        self.toolbar.sig_toggle_log.connect(self.plots.set_log_mode)
        self.toolbar.sig_export.connect(self._export_current)

        self.browser.sig_run_selected.connect(self._load_run)
        self.browser.sig_runs_selected.connect(self._load_runs)
        self.filters.sig_filters_changed.connect(self._on_filters)
        self.metadata.sig_options_changed.connect(self._on_options)

    def _update_title(self) -> None:
        self.setWindowTitle(f"Loadpull Viewer — {self.root_dir}")

    def _choose_root(self) -> None:
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
        grouped = discover_runs_grouped(self.root_dir)
        self.browser.load_groups(grouped)
        self.status.showMessage(f"Discovered {sum(len(v) for v in grouped.values())} runs")

    def _maybe_refresh(self) -> None:
        grouped = discover_runs_grouped(self.root_dir)
        if self.browser.refresh_if_changed(grouped):
            self.status.showMessage("Runs updated")

    def _load_run(self, run) -> None:
        self.plots.set_test_type(run.test_type)
        self.plots.load_run(run)
        # Build metadata columns from all tabs/specs: y, xy, series, and declared columns
        cols = []
        tabs = self.registry.tabs_for(run.test_type)
        for specs in tabs.values():
            for spec in specs:
                cols.extend(spec.get("y", []) or [])
                xy = spec.get("xy")
                if xy:
                    cols.extend([c for c in xy if c])
                for ser in spec.get("series", []) or []:
                    xk = ser.get("x")
                    yk = ser.get("y")
                    if xk:
                        cols.append(xk)
                    if yk:
                        cols.append(yk)
                cols.extend(spec.get("columns", []) or [])

        self.metadata.set_columns(sorted(set(cols)))

    def _load_runs(self, runs: list) -> None:
        if not runs:
            return
        test_type = runs[0].test_type
        runs = [r for r in runs if r.test_type == test_type]
        self.plots.set_test_type(test_type)
        self.plots.load_runs(runs)
        # Reuse metadata construction from single-run (first run defines tabs/specs by type)
        self._load_run(runs[0])

    def _on_filters(self, ranges: dict) -> None:
        self._filters_state = dict(ranges)
        self._apply_all()

    def _on_options(self, opts: dict) -> None:
        self._options_state = dict(opts)
        self.plots.set_options(self._options_state)

    def _apply_all(self) -> None:
        self.plots.apply_filters(self._filters_state)

    def _export_current(self, kind: str) -> None:
        self.plots.export(kind)


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    # Load optional application stylesheet
    try:
        style_path = Path(__file__).resolve().parents[1] / "style.qss"
        if style_path.exists():
            app.setStyleSheet(style_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    mw = MainWindow()
    mw.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
