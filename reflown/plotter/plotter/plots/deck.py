from __future__ import annotations

"""Plot deck with tabs; renders specs from registry using the SQLite store.

Supports multi-run overlays and log Y toggle.
"""

from typing import Dict, List
from pathlib import Path

from PySide6 import QtWidgets
import pyqtgraph as pg
import numpy as np

from ..database.sqlite_store import SQLiteStore
from ..testtypes.registry import TestTypeRegistry
from ..data.discovery import load_db_path

class PlotDeck(QtWidgets.QWidget):
    def __init__(self, registry: TestTypeRegistry, parent=None) -> None:
        super().__init__(parent)
        self.registry = registry
        # Open the SQLite store (default DB path under ../runs)
        self._store = SQLiteStore(Path(load_db_path()))
        print(load_db_path())
        self._tabs = QtWidgets.QTabWidget(self)
        self._plots: List[pg.PlotWidget] = []
        self._tab_specs: Dict[str, List[dict]] = {}
        self._tab_plots: Dict[str, List[pg.PlotWidget]] = {}
        self._log = False
        self._runs: List[object] = []
        self._run_cols: Dict[str, Dict[str, List[float]]] = {}
        self._col_map: Dict[str, str] = {}

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
        self._col_map = {}

        def _collect(value) -> None:
            if value is None:
                return
            if isinstance(value, str):
                sanitized = SQLiteStore._sanitize_col(value)
                self._col_map.setdefault(value, sanitized)
                needed.append(sanitized)
            elif isinstance(value, (list, tuple, set)):
                for entry in value:
                    _collect(entry)

        for s in specs_all:
            _collect(s.get("columns"))
            _collect(s.get("x"))
            _collect(s.get("y"))
            ser = s.get("series") or []
            for e in ser:
                _collect(e.get("x"))
                _collect(e.get("y"))
            _collect(s.get("xy"))
        self._needed = sorted(set(needed))
        self._begin_load()

    def _begin_load(self) -> None:
        if not self._runs:
            return
        self._run_cols.clear()
        for run in self._runs:
            try:
                cols = self._store.load_columns(run.test_type, run.path, self._needed, progress_cb=None)
            except Exception:
                cols = {}
            self._run_cols[str(run.path)] = cols
        self._render()

    def _render(self) -> None:
        pens_cycle = ["y", "c", "m", "w", "g", "r"]

        def _col_name(name: str | None) -> str | None:
            if not name:
                return None
            return self._col_map.get(name, name)

        for tab, specs in self._tab_specs.items():
            plots = self._tab_plots.get(tab, [])
            for i, spec in enumerate(specs):
                if i >= len(plots):
                    continue
                pw = plots[i]
                pw.clear()
                mode = spec.get("mode", "line")
                single_series = mode not in ("scatter", "polar-scatter") and not spec.get("series") and len(spec.get("y", []) or []) == 1
                is_scatter = mode == "scatter"
                is_polar_scatter = mode == "polar-scatter"
                is_polar_line = mode == "polar-line"
                if single_series:
                    try:
                        if getattr(pw, "_legend_added", False) is not True:
                            pw.addLegend()
                            pw._legend_added = True  # type: ignore[attr-defined]
                    except Exception:
                        pass
                for ridx, run in enumerate(self._runs):
                    cols = self._run_cols.get(str(run.path), {})
                    pen = spec.get("pen") or pens_cycle[ridx % len(pens_cycle)]
                    if is_polar_scatter or is_polar_line:
                        r_key = _col_name(spec.get("r"))
                        theta_deg_key = _col_name(spec.get("theta_deg"))
                        theta_rad_key = _col_name(spec.get("theta_rad"))
                        r_vals = cols.get(r_key or spec.get("r"), [])
                        theta_deg_vals = cols.get(theta_deg_key or spec.get("theta_deg"))
                        theta_rad_vals = cols.get(theta_rad_key or spec.get("theta_rad"))
                        if theta_deg_vals is None and theta_rad_vals is None:
                            continue
                        try:
                            r_arr = np.asarray(r_vals, dtype=float)
                            if theta_rad_vals is not None:
                                theta_arr = np.asarray(theta_rad_vals, dtype=float)
                            else:
                                theta_arr = np.deg2rad(np.asarray(theta_deg_vals, dtype=float))
                            if r_arr.size == 0 or theta_arr.size == 0:
                                continue
                            # Align lengths
                            n = min(r_arr.size, theta_arr.size)
                            r_arr = r_arr[:n]
                            theta_arr = theta_arr[:n]
                            x = r_arr * np.cos(theta_arr)
                            y = r_arr * np.sin(theta_arr)
                        except Exception:
                            continue
                        color = pg.mkColor(pen)
                        run_name = str(getattr(run, "timestamp", None) or getattr(run, "path", None) or f"run{ridx+1}")
                        item = None
                        if is_polar_scatter:
                            item = pg.ScatterPlotItem(
                                x,
                                y,
                                pen=pg.mkPen(color),
                                brush=pg.mkBrush(color),
                                size=6,
                            )
                            pw.addItem(item)
                        else:
                            item = pw.plot(x, y, pen=pen, name=run_name if single_series else None)
                        legend = getattr(pw, "legend", None)
                        if legend is None:
                            try:
                                legend = pw.addLegend()
                            except Exception:
                                legend = None
                        if legend is not None:
                            legend.addItem(item, run_name)
                    elif mode == "scatter":
                        xk, yk = spec.get("xy", (None, None))
                        sx = _col_name(xk)
                        sy = _col_name(yk)
                        xs = cols.get(sx or xk, [])
                        ys = cols.get(sy or yk, [])
                        color = pg.mkColor(pen)
                        pts = list(zip(xs, ys))
                        s = pg.ScatterPlotItem(
                            [p[0] for p in pts],
                            [p[1] for p in pts],
                            pen=pg.mkPen(color),
                            brush=pg.mkBrush(color),
                            size=6,
                        )
                        run_name = str(getattr(run, "timestamp", None) or getattr(run, "path", None) or f"run{ridx+1}")
                        pw.addItem(s)
                        legend = getattr(pw, "legend", None)
                        if legend is None:
                            try:
                                legend = pw.addLegend()
                            except Exception:
                                legend = None
                        if legend is not None:
                            legend.addItem(s, run_name)
                    else:
                        x_key = _col_name(spec.get("x"))
                        x = cols.get(x_key or spec.get("x")) or list(range(len(next(iter(cols.values()), []))))
                        for yk in spec.get("y", []):
                            y_key = _col_name(yk)
                            y = cols.get(y_key or yk, [])
                            if y:
                                name = None
                                if single_series:
                                    run_name = getattr(run, "timestamp", None) or getattr(run, "path", None) or f"run{ridx+1}"
                                    name = str(run_name)
                                pw.plot(x, y, pen=pen, name=name)
                            else:
                                # expand array series if available as yk[0], yk[1], ...
                                idx = 0
                                while True:
                                    key = f"{yk}[{idx}]"
                                    mapped = self._col_map.get(key, key)
                                    if mapped not in cols:
                                        break
                                    pw.plot(x, cols.get(mapped, []), pen=pen)
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
