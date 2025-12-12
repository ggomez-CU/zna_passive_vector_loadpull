from __future__ import annotations

"""Plot deck with tabs; renders specs from registry using the SQLite store.

Supports multi-run overlays and log Y toggle.
"""

from typing import Dict, List, Set
import csv
import json
from pathlib import Path

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

    @staticmethod
    def needed_columns_for_spec(spec: dict) -> List[str]:
        cols: Set[str] = set()
        xk = spec.get("x")
        if xk:
            cols.add(xk)
        for yk in spec.get("y", []) or []:
            if yk:
                cols.add(yk)
        xy = spec.get("xy")
        if xy:
            cols.update([c for c in xy if c])
        for series in spec.get("series") or []:
            sx = series.get("x")
            if sx:
                cols.add(sx)
            sy = series.get("y")
            if sy:
                cols.add(sy)
            sxy = series.get("xy")
            if sxy:
                cols.update([c for c in sxy if c])
        # Allow explicit columns to add extra/non-axis fields
        cols.update(spec.get("columns", []) or [])
        return sorted(cols)

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
        needed: Set[str] = set()
        for s in specs_all:
            needed.update(self.needed_columns_for_spec(s))
        self._needed = sorted(needed)
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

    def get_columns_data(self, columns: List[str]) -> Dict[str, List[float]]:
        """Return data for requested columns for each loaded run."""
        out = []
        for run in self._runs:
            cols = self._run_cols.get(str(run.path), {})
            out.append((run.timestamp, {c: cols.get(c, []) for c in columns}))
        return out

    def export_current(self, kind: str) -> None:
        kind = kind.lower()
        # Minimal export: active tab, first plot
        tab = self._tabs.tabText(self._tabs.currentIndex()) if self._tabs.count() else None
        plots = self._tab_plots.get(tab or "", [])
        if not plots:
            # Fallback to first available tab
            for _, ps in self._tab_plots.items():
                if ps:
                    plots = ps
                    break
        if not plots:
            return
        if kind in ("png", "svg"):
            import pyqtgraph.exporters
            exp_cls = pyqtgraph.exporters.ImageExporter if kind.lower() == "png" else pyqtgraph.exporters.SVGExporter
            exp = exp_cls(plots[0].plotItem)
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, f"Export {kind.upper()}", filter=f"*.{kind}")
            if path:
                exp.export(path)
            return

        # CSV of plotted columns (first plot in current tab)
        if kind == "csv":
            if not self._runs:
                return
            tab_specs = self._tab_specs.get(tab or "", [])
            spec = tab_specs[0] if tab_specs else None
            if not spec:
                return
            cols: List[str] = []
            if spec.get("x"):
                cols.append(spec["x"])
            xy = spec.get("xy")
            if xy:
                cols.extend([c for c in xy if c])
            for yk in spec.get("y", []):
                if yk:
                    cols.append(yk)
            cols = [c for c in cols if c]
            if not cols:
                return
            # Ensure columns are available (load missing ones)
            for run in self._runs:
                data = self._run_cols.get(str(run.path), {})
                missing = [c for c in cols if c not in data]
                if missing:
                    extra = load_columns_db(run, missing, progress_cb=None)
                    data.update(extra)
                    self._run_cols[str(run.path)] = data
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export CSV", filter="*.csv")
            if not path:
                return
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", newline="", encoding="utf-8") as fp:
                writer = csv.writer(fp)
                writer.writerow(["run", "row_index"] + cols)
                for run in self._runs:
                    data = self._run_cols.get(str(run.path), {})
                    max_len = 0
                    for c in cols:
                        max_len = max(max_len, len(data.get(c, [])))
                    for i in range(max_len):
                        row = [run.timestamp, i]
                        for c in cols:
                            vals = data.get(c, [])
                            row.append(vals[i] if i < len(vals) else "")
                        writer.writerow(row)
            return

        if kind == "csv-all":
            # Dump entire JSONL for first run to CSV (if available)
            if not self._runs:
                return
            run = self._runs[0]
            in_path = run.data_file if hasattr(run, "data_file") else None
            if not in_path or not Path(in_path).exists():
                return
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export CSV (All Fields)", filter="*.csv")
            if not path:
                return
            src = Path(in_path)
            dst = Path(path)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.suffix.lower() == ".csv":
                dst.write_bytes(src.read_bytes())
                return
            # Convert JSONL -> CSV (union of keys)
            headers: Set[str] = set()
            with src.open("r", encoding="utf-8") as fp:
                for line in fp:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(rec, dict):
                        headers.update(str(k) for k in rec.keys() if not str(k).lower().endswith((".csv", "_csv")))
            if not headers:
                return
            fieldnames = sorted(headers)
            with dst.open("w", newline="", encoding="utf-8") as out_fp:
                writer = csv.DictWriter(out_fp, fieldnames=fieldnames)
                writer.writeheader()
                with src.open("r", encoding="utf-8") as in_fp:
                    for line in in_fp:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(rec, dict):
                            continue
                        row = {}
                        for k in fieldnames:
                            val = rec.get(k, "")
                            if isinstance(val, list) and len(val) == 1:
                                val = val[0]
                            if isinstance(val, (list, dict)):
                                try:
                                    val = json.dumps(val, separators=(",", ":"))
                                except Exception:
                                    val = str(val)
                            row[k] = "" if val is None else val
                        writer.writerow(row)
            return
