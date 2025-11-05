from __future__ import annotations

"""Plot deck with tabs; renders specs from registry using the SQLite store.

Supports multi-run overlays and log Y toggle.
"""

from typing import Dict, List

from PySide6 import QtWidgets
import pyqtgraph as pg

from ..data.db_loaders import load_columns_db
from ..testtypes.registry import TestTypeRegistry


class PlotDeck(QtWidgets.QWidget):
    def __init__(self, registry: TestTypeRegistry, parent=None) -> None:
        super().__init__(parent)
        self.registry = registry
        self._tabs = QtWidgets.QTabWidget(self)
        self._plots: List[pg.PlotWidget] = []
        self._tab_specs: Dict[str, List[dict]] = {}
        self._tab_plots: Dict[str, List[pg.PlotWidget]] = {}
        self._log = False
        self._runs: List[object] = []
        self._run_cols: Dict[str, Dict[str, List[float]]] = {}

        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self._tabs)

    def set_log_mode(self, enabled: bool) -> None:
        self._log = enabled
        for p in self._plots:
            try:
                p.plotItem.setLogMode(False, enabled)
            except Exception:
                pass

    def set_test_type(self, test_type: str) -> None:
        # clear
        self._plots.clear()
        for i in reversed(range(self._tabs.count())):
            w = self._tabs.widget(i)
            self._tabs.removeTab(i)
            w.deleteLater()
        # build from registry
        self._tab_specs = self.registry.tabs_for(test_type)
        self._tab_plots = {}
        for tab, specs in self._tab_specs.items():
            container = QtWidgets.QWidget()
            vlay = QtWidgets.QVBoxLayout(container)
            vlay.setContentsMargins(0, 0, 0, 0)
            plots: List[pg.PlotWidget] = []
            for spec in specs:
                pw = pg.PlotWidget()
                pw.showGrid(x=True, y=True, alpha=0.2)
                pw.setLabel("bottom", spec.get("xlabel", "index"))
                pw.setLabel("left", spec.get("ylabel", ""))
                pw.setTitle(spec.get("title", ""))
                plots.append(pw)
                vlay.addWidget(pw)
                self._plots.append(pw)
            self._tab_plots[tab] = plots
            self._tabs.addTab(container, tab)
        self.set_log_mode(self._log)

    def load_runs(self, runs: List[object]) -> None:
        self._runs = list(runs)
        self._run_cols.clear()
        self.apply_filters({})

    def set_options(self, opts: dict) -> None:
        # Re-apply filters to reload with new options
        self.apply_filters({})

    def apply_filters(self, ranges: dict) -> None:
        if not self._runs:
            return
        # compute needed columns from specs
        specs_all: List[dict] = []
        for specs in self._tab_specs.values():
            specs_all.extend(specs)
        needed: List[str] = []
        for s in specs_all:
            needed.extend(s.get("columns", []) or [])
            ser = s.get("series") or []
            for e in ser:
                if e.get("x"):
                    needed.append(e["x"])
                if e.get("y"):
                    needed.append(e["y"])
            xk = s.get("x")
            if xk:
                needed.append(xk)
        self._needed = sorted(set(needed))
        self._begin_load()

    def _begin_load(self) -> None:
        if not self._runs:
            return
        self._run_cols.clear()
        for run in self._runs:
            try:
                cols = load_columns_db(run, self._needed, progress_cb=None)
            except Exception:
                cols = {}
            self._run_cols[str(run.path)] = cols
        self._render()

    def _render(self) -> None:
        pens_cycle = ["y", "c", "m", "w", "g", "r"]
        for tab, specs in self._tab_specs.items():
            plots = self._tab_plots.get(tab, [])
            for i, spec in enumerate(specs):
                if i >= len(plots):
                    continue
                pw = plots[i]
                pw.clear()
                mode = spec.get("mode", "line")
                for ridx, run in enumerate(self._runs):
                    cols = self._run_cols.get(str(run.path), {})
                    pen = spec.get("pen") or pens_cycle[ridx % len(pens_cycle)]
                    if mode == "scatter":
                        xk, yk = spec.get("xy", (None, None))
                        xs = cols.get(xk, [])
                        ys = cols.get(yk, [])
                        s = pg.ScatterPlotItem(pen=None, brush=pg.mkBrush(100, 150, 255, 200), size=5)
                        s.addPoints([{"pos": (xs[j], ys[j])} for j in range(min(len(xs), len(ys)))])
                        pw.addItem(s)
                    else:
                        x = cols.get(spec.get("x")) or list(range(len(next(iter(cols.values()), []))))
                        for yk in spec.get("y", []):
                            y = cols.get(yk, [])
                            if y:
                                pw.plot(x, y, pen=pen)
                            else:
                                # expand array series if available as yk[0], yk[1], ...
                                idx = 0
                                while True:
                                    key = f"{yk}[{idx}]"
                                    if key not in cols:
                                        break
                                    pw.plot(x, cols.get(key, []), pen=pen)
                                    idx += 1
        # keep log mode
        self.set_log_mode(self._log)

    def export_current(self, kind: str) -> None:
        # Minimal export: active tab, first plot
        tab = self._tabs.tabText(self._tabs.currentIndex()) if self._tabs.count() else None
        plots = self._tab_plots.get(tab or "", [])
        if not plots:
            return
        if kind.lower() in ("png", "svg"):
            import pyqtgraph.exporters
            exp_cls = pyqtgraph.exporters.ImageExporter if kind.lower() == "png" else pyqtgraph.exporters.SVGExporter
            exp = exp_cls(plots[0].plotItem)
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, f"Export {kind.upper()}", filter=f"*.{kind}")
            if path:
                exp.export(path)
        # CSV export could be added similarly by reusing loaded cols
