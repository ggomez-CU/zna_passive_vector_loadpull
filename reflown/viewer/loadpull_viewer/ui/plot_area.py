from __future__ import annotations

from typing import Dict, List, Optional
from PySide6 import QtCore, QtWidgets
import pyqtgraph as pg
import math
import time 

from ..data.model import RunInfo
from ..data.loaders import load_columns
from ..data.exporters import jsonl_to_csv, copy_csv
from ..testtypes.registry import TestTypeRegistry
from ..data.exporters import jsonl_to_csv, copy_csv
from pathlib import Path


class PlotArea(QtWidgets.QWidget):
    def __init__(self, registry: TestTypeRegistry, parent=None) -> None:
        super().__init__(parent)
        self.registry = registry
        self._log = False
        self._run: Optional[RunInfo] = None
        self._runs: List[RunInfo] = []
        self._run_cols: Dict[str, Dict[str, List[float]]] = {}
        self._plots: List[pg.PlotWidget] = []
        self._tab_specs: Dict[str, List[dict]] = {}
        self._tab_plots: Dict[str, List[pg.PlotWidget]] = {}
        self._tabs = QtWidgets.QTabWidget(self)
        self._progress = QtWidgets.QProgressBar(self)
        self._progress.setTextVisible(True)
        self._progress.setVisible(False)
        self._selected_columns: Optional[List[str]] = None
        self._detail: int = 3
        self._load_seq = 0
        self._thread: Optional[QtCore.QThread] = None
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self._progress)
        self._layout.addWidget(self._tabs)

    def clear(self) -> None:
        self._plots.clear()
        self._tab_specs.clear()
        for i in reversed(range(self._tabs.count())):
            w = self._tabs.widget(i)
            self._tabs.removeTab(i)
            w.deleteLater()

    def set_log_mode(self, enabled: bool) -> None:
        self._log = enabled
        for p in self._plots:
            try:
                p.plotItem.setLogMode(False, enabled)
            except Exception:
                pass

    def set_test_type(self, test_type: str) -> None:
        self.clear()
        self._tab_specs = self.registry.tabs_for(test_type)
        self._tab_plots = {}
        for tab_name, specs in self._tab_specs.items():
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
            self._tab_plots[tab_name] = plots
            self._tabs.addTab(container, tab_name)
        self.set_log_mode(self._log)

    def load_run(self, run: RunInfo) -> None:
        self._run = run
        self._runs = [run]
        self._start_loading()

    def load_runs(self, runs: List[RunInfo]) -> None:
        self._runs = list(runs)
        self._run = runs[0] if runs else None
        self._start_loading()

    def set_options(self, opts: dict) -> None:
        self._selected_columns = list(opts.get("columns", []) or [])
        self._detail = int(opts.get("detail", self._detail))
        # Re-render with current filters
        self.apply_filters({})

    def apply_filters(self, ranges: dict) -> None:
        # Re-render if columns already loaded
        if not self._runs:
            return
        # Gather specs across all tabs
        all_specs: List[dict] = []
        for specs in self._tab_specs.values():
            all_specs.extend(specs)
        if not all_specs:
            all_specs = self.registry.layout_for(self._run.test_type)
        detail = self._detail
        max_points = {1: 10000, 2: 30000, 3: 60000, 4: 120000, 5: 200000}.get(detail, 60000)

        needed: List[str] = []
        for s in all_specs:
            for k in s.get("columns", []):
                if (self._selected_columns is None) or (k in self._selected_columns) or (k in (s.get("x"),)):
                    if k not in needed:
                        needed.append(k)
            # Include per-series x/y keys when provided
            series = s.get("series")
            if isinstance(series, list):
                for ser in series:
                    xk = ser.get("x")
                    yk = ser.get("y")
                    if xk and xk not in needed:
                        needed.append(xk)
                    if yk and yk not in needed:
                        needed.append(yk)

        # Start async loading for current selection
        self._needed_cols = needed
        self._max_points = max_points
        self._begin_load_runs()

    def _start_loading(self) -> None:
        self._run_cols.clear()
        self.apply_filters({})

    def _begin_load_runs(self) -> None:
        self._load_seq += 1
        self._load_index = 0
        # Reset and show progress bar
        try:
            self._progress.setRange(0, 0)  # indeterminate until first update
            self._progress.setFormat("Loading…")
            self._progress.setVisible(True)
        except Exception:
            pass
        self._load_next(self._load_seq)

    def _load_next(self, seq: int) -> None:
        print(self._load_index)
        time.sleep(3)
        if self._load_index >= len(self._runs) - 1:
            # Done, render
            self._render_loaded(seq)
            return
        run = self._runs[self._load_index]
        loader = _ColumnsLoader(run.data_file, self._needed_cols, self._max_points)
        thread = QtCore.QThread(self)
        loader.moveToThread(thread)
        loader.finished.connect(lambda cols, r=run, s=seq: self._on_run_loaded(r, cols, s))
        loader.error.connect(lambda msg: None)
        loader.progress.connect(lambda done, total, r=run: self._on_progress(r, done, total))
        thread.started.connect(loader.run)
        loader.finished.connect(thread.quit)
        loader.finished.connect(loader.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        thread.start()

    def _on_run_loaded(self, run: RunInfo, cols: Dict[str, List[float]], seq: int) -> None:
        if seq != self._load_seq:
            return
        self._run_cols[str(run.path)] = cols
        self._load_index += 1
        self._load_next(seq)

    def _render_loaded(self, seq: int) -> None:
        if seq != self._load_seq:
            return
        # Hide progress
        try:
            self._progress.setVisible(False)
        except Exception:
            pass
        # Build a palette for multiple runs
        pens_cycle = ["y", "c", "m", "w", "g", "r"]
        # Draw per tab/spec
        for tab_name, specs in self._tab_specs.items():
            plots = self._tab_plots.get(tab_name, [])
            for i, spec in enumerate(specs):
                if i >= len(plots):
                    continue
                pw = plots[i]
                pw.clear()
                mode = spec.get("mode", "line")
                # For each run overlay
                for ridx, run in enumerate(self._runs):
                    cols = self._run_cols.get(str(run.path), {})
                    pen_color = spec.get("pen") or pens_cycle[ridx % len(pens_cycle)]
                    name_suffix = f" ({run.timestamp})" if len(self._runs) > 1 else ""
                    if mode == "scatter":
                        xk, yk = spec.get("xy", (None, None))
                        xs = cols.get(xk, [])
                        ys = cols.get(yk, [])
                        s = pg.ScatterPlotItem(pen=None, brush=pg.mkBrush(100, 150, 255, 200), size=5)
                        s.addPoints([{'pos': (xs[j], ys[j])} for j in range(min(len(xs), len(ys)))])
                        pw.addItem(s)
                    elif mode in ("polar", "polar_scatter"):
                        rk = spec.get("r"); tk = spec.get("theta")
                        if not rk or not tk:
                            continue
                        r = cols.get(rk, [])
                        t = cols.get(tk, [])
                        if spec.get("theta_units", "rad").lower().startswith("deg"):
                            t = [math.radians(v) for v in t]
                        x = [ri * math.cos(ti) for ri, ti in zip(r, t)]
                        y = [ri * math.sin(ti) for ri, ti in zip(r, t)]
                        if mode == "polar_scatter":
                            s = pg.ScatterPlotItem(pen=None, brush=pg.mkBrush(100, 150, 255, 200), size=5)
                            s.addPoints([{'pos': (x[j], y[j])} for j in range(min(len(x), len(y)))])
                            pw.addItem(s)
                        else:
                            pw.plot(x, y, pen=pen_color, name=(spec.get("title") or "") + name_suffix)
                        if spec.get("unit_circle", True):
                            self._draw_unit_circle(pw)
                        pw.setAspectLocked(True, 1)
                    elif mode == "smith_scatter":
                        rk = spec.get("r") or spec.get("mag"); tk = spec.get("theta")
                        if not rk or not tk:
                            continue
                        r = cols.get(rk, [])
                        t = cols.get(tk, [])
                        if spec.get("theta_units", "rad").lower().startswith("deg"):
                            t = [math.radians(v) for v in t]
                        x = [ri * math.cos(ti) for ri, ti in zip(r, t)]
                        y = [ri * math.sin(ti) for ri, ti in zip(r, t)]
                        s = pg.ScatterPlotItem(pen=None, brush=pg.mkBrush(100, 200, 120, 200), size=5)
                        s.addPoints([{'pos': (x[j], y[j])} for j in range(min(len(x), len(y)))])
                        pw.addItem(s)
                        self._draw_unit_circle(pw)
                        pw.setAspectLocked(True, 1)
                        pw.setXRange(-1.2, 1.2, padding=0)
                        pw.setYRange(-1.2, 1.2, padding=0)
                    else:
                        # line/series mode
                        x = cols.get(spec.get("x")) or list(range(len(next(iter(cols.values()), []))))
                        series = spec.get("series")
                        if isinstance(series, list) and series:
                            try:
                                if getattr(pw, "_legend_added", False) is not True:
                                    pw.addLegend()
                                    pw._legend_added = True  # type: ignore[attr-defined]
                            except Exception:
                                pass
                            for sidx, ser in enumerate(series):
                                xk = ser.get("x"); yk = ser.get("y")
                                label = (ser.get("label") or yk or f"series{sidx+1}") + name_suffix
                                pen = ser.get("pen", pen_color)
                                xs = cols.get(xk, []) if xk else x
                                ys = cols.get(yk, []) if yk else []
                                pw.plot(xs, ys, pen=pen, name=label)
                        else:
                            for ykey in spec.get("y", []):
                                if self._selected_columns and ykey not in self._selected_columns:
                                    continue
                                y = cols.get(ykey, [])
                                pw.plot(x, y, pen=pen_color, name=(ykey or "") + name_suffix)

    def _on_loaded(self, cols: Dict[str, List[float]], seq: int) -> None:
        if seq != self._load_seq:
            return  # stale
        # Apply basic range filters
        # (Filtering logic could be added here similar to earlier approach)
        # Draw per tab/spec
        plot_index = 0
        for tab_name, specs in self._tab_specs.items():
            plots = self._tab_plots.get(tab_name, [])
            for i, spec in enumerate(specs):
                if i >= len(plots):
                    continue
                pw = plots[i]
                pw.clear()
                mode = spec.get("mode", "line")
                if mode == "scatter":
                    xk, yk = spec.get("xy", (None, None))
                    xs = cols.get(xk, [])
                    ys = cols.get(yk, [])
                    pts = [{'pos': (xs[i], ys[i])} for i in range(min(len(xs), len(ys)))]
                    s = pg.ScatterPlotItem(pen=None, brush=pg.mkBrush(100, 150, 255, 200), size=5)
                    s.addPoints(pts)
                    pw.addItem(s)
                elif mode == "polar" or mode == "polar_scatter":
                    rk = spec.get("r")
                    tk = spec.get("theta")
                    if not rk or not tk:
                        continue
                    r = cols.get(rk, [])
                    t = cols.get(tk, [])
                    if spec.get("theta_units", "rad").lower().startswith("deg"):
                        t = [math.radians(v) for v in t]
                    x = [ri * math.cos(ti) for ri, ti in zip(r, t)]
                    y = [ri * math.sin(ti) for ri, ti in zip(r, t)]
                    if mode == "polar_scatter":
                        s = pg.ScatterPlotItem(pen=None, brush=pg.mkBrush(100, 150, 255, 200), size=5)
                        s.addPoints([{'pos': (x[i], y[i])} for i in range(min(len(x), len(y)))])
                        pw.addItem(s)
                    else:
                        pw.plot(x, y, pen=spec.get("pen", "y"))
                    if spec.get("unit_circle", True):
                        self._draw_unit_circle(pw)
                    pw.setAspectLocked(True, 1)
                elif mode == "smith_scatter":
                    # Plot Gamma on a Smith chart (unit circle baseline)
                    rk = spec.get("r") or spec.get("mag")
                    tk = spec.get("theta")
                    if not rk or not tk:
                        continue
                    r = cols.get(rk, [])
                    t = cols.get(tk, [])
                    if spec.get("theta_units", "rad").lower().startswith("deg"):
                        t = [math.radians(v) for v in t]
                    x = [ri * math.cos(ti) for ri, ti in zip(r, t)]
                    y = [ri * math.sin(ti) for ri, ti in zip(r, t)]
                    s = pg.ScatterPlotItem(pen=None, brush=pg.mkBrush(100, 200, 120, 200), size=5)
                    s.addPoints([{'pos': (x[i], y[i])} for i in range(min(len(x), len(y)))])
                    pw.addItem(s)
                    self._draw_unit_circle(pw)
                    pw.setAspectLocked(True, 1)
                    pw.setXRange(-1.2, 1.2, padding=0)
                    pw.setYRange(-1.2, 1.2, padding=0)
                else:
                    x = cols.get(spec.get("x")) or list(range(len(next(iter(cols.values()), []))))
                    # If explicit series list is provided, allow plotting multiple x/y pairs with labels
                    series = spec.get("series")
                    if isinstance(series, list) and series:
                        # Add legend once per plot
                        try:
                            if getattr(pw, "_legend_added", False) is not True:
                                pw.addLegend()
                                pw._legend_added = True  # type: ignore[attr-defined]
                        except Exception:
                            pass
                        default_pens = ["y", "c", "m", "w", "g", "r"]
                        for idx, ser in enumerate(series):
                            xk = ser.get("x")
                            yk = ser.get("y")
                            label = ser.get("label") or yk or f"series{idx+1}"
                            pen = ser.get("pen", default_pens[idx % len(default_pens)])
                            xs = cols.get(xk, []) if xk else x
                            ys = cols.get(yk, []) if yk else []
                            pw.plot(xs, ys, pen=pen, name=label)
                    else:
                        for ykey in spec.get("y", []):
                            if self._selected_columns and ykey not in self._selected_columns:
                                continue
                            y = cols.get(ykey, [])
                            pw.plot(x, y, pen=spec.get("pen", "y"))

    def _draw_unit_circle(self, pw: pg.PlotWidget) -> None:
        try:
            circle = pg.QtGui.QGraphicsEllipseItem(-1, -1, 2, 2)
            circle.setPen(pg.mkPen((180, 180, 180, 160), width=1, style=pg.QtCore.Qt.DashLine))
            pw.addItem(circle)
        except Exception:
            pass

    def _on_progress(self, run: RunInfo, done: int, total: int) -> None:
        try:
            if total and total > 0:
                if self._progress.maximum() != total:
                    self._progress.setRange(0, total)
                self._progress.setValue(done)
                self._progress.setFormat(f"Loading {run.test_type}/{run.timestamp} — %p%")
            else:
                self._progress.setRange(0, 0)  # busy
                self._progress.setFormat(f"Loading {run.test_type}/{run.timestamp}…")
            self._progress.setVisible(True)
        except Exception:
            pass

    def _default_save_path(self, ext: str) -> str:
        try:
            if not self._run:
                return ""
            root = self._run.path.parent.parent.parent 
            save_dir = Path(root) / "saves" / self._run.test_type 
            Path(save_dir).mkdir(parents=True, exist_ok=True)
            filename = f"{self._run.timestamp}.{ext}"
            return str(save_dir / filename)
        except Exception:
            return ""

    def export(self, kind: str) -> None:
        if not self._plots:
            return
        kind = (kind or "").lower()
        if kind in ("png", "svg"):
            import pyqtgraph.exporters
            exporter_cls = pyqtgraph.exporters.ImageExporter if kind == "png" else pyqtgraph.exporters.SVGExporter
            # Prefer active tab's first plot
            exp_plot = None
            if self._tabs.count() > 0:
                tab_name = self._tabs.tabText(self._tabs.currentIndex())
                plots = self._tab_plots.get(tab_name) or []
                if plots:
                    exp_plot = plots[0].plotItem
            if exp_plot is None and self._plots:
                exp_plot = self._plots[0].plotItem
            if exp_plot is None:
                return
            exp = exporter_cls(exp_plot)
            suggested = self._default_save_path(kind)
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, f"Export {kind.upper()}", suggested, filter=f"*.{kind}")
            if path:
                # Ensure directory exists
                try:
                    Path(path).parent.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
                exp.export(path)
            return
        if kind == "csv":
            if not self._run:
                return
            tab_specs = []
            if self._tabs.count() > 0:
                tab_name = self._tabs.tabText(self._tabs.currentIndex())
                tab_specs = self._tab_specs.get(tab_name, [])
            specs = tab_specs or self.registry.layout_for(self._run.test_type)
            if not specs:
                return
            first = specs[0]
            needed = list(set([first.get("x")] + first.get("y", [])))
            cols = load_columns(self._run.data_file, needed, max_points=200000)
            suggested = self._default_save_path("csv")
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export CSV", suggested, filter="*.csv")
            if path:
                import csv
                try:
                    Path(path).parent.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
                with open(path, "w", newline="", encoding="utf-8") as fp:
                    writer = csv.writer(fp)
                    writer.writerow(needed)
                    for i in range(len(cols[needed[0]])):
                        writer.writerow([cols[k][i] for k in needed])
            return
        if kind == "csv-all":
            if not self._run:
                return
            suggested = self._default_save_path("csv")
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export CSV (All Fields)", suggested, filter="*.csv")
            if not path:
                return
            in_path = self._run.data_file
            try:
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            if in_path.suffix.lower() == ".csv":
                copy_csv(in_path, path)
            else:
                jsonl_to_csv(in_path, path)
            return


class _ColumnsLoader(QtCore.QObject):
    finished = QtCore.Signal(dict)
    error = QtCore.Signal(str)
    progress = QtCore.Signal(int, int)  # done, total

    def __init__(self, path, columns, max_points):
        super().__init__()
        self.path = path
        self.columns = columns
        self.max_points = max_points

    @QtCore.Slot()
    def run(self):
        try:
            cols = load_columns(self.path, self.columns, max_points=self.max_points, progress_cb=self.progress.emit)
            self.finished.emit(cols)
        except Exception as e:
            self.error.emit(str(e))
