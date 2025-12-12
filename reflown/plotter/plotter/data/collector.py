from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
import json

from PySide6 import QtCore

from .discovery import discover_runs_grouped
from .model import RunInfo
from ..database.sqlite_store import SQLiteStore


@dataclass
class _PendingDecision:
    run: RunInfo
    size: int
    mtime: float


class DataCollectorService(QtCore.QObject):
    progress = QtCore.Signal(int, int)
    new_indexed = QtCore.Signal(str)
    conflict = QtCore.Signal(str, dict, dict)
    error = QtCore.Signal(str)

    def __init__(self, runs_root: Path, db_path: Path, interval_ms: int = 3000, use_hash: bool = False) -> None:
        super().__init__()
        self._root = Path(runs_root)
        self._db_path = Path(db_path)
        self._interval = int(interval_ms)
        self._use_hash = bool(use_hash)
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(self._interval)
        self._timer.timeout.connect(self._scan_once)
        self._store: Optional[SQLiteStore] = None
        self._pending: Dict[str, _PendingDecision] = {}

    @QtCore.Slot()
    def start(self) -> None:
        try:
            self._store = SQLiteStore(self._db_path)
            self._timer.start()
        except Exception as e:
            self.error.emit(f"collector start failed: {e}")

    @QtCore.Slot()
    def stop(self) -> None:
        self._timer.stop()
        if self._store:
            try:
                self._store.close()
            except Exception:
                pass
            self._store = None

    @QtCore.Slot(str, bool)
    def decide_overwrite(self, path: str, accept: bool) -> None:
        if not self._store:
            return
        pend = self._pending.pop(path, None)
        if not pend:
            return
        if not accept:
            return
        try:
            self._store.overwrite_meta(
                path=pend.run.data_file,
                size=pend.size,
                mtime=pend.mtime,
                test_type=pend.run.test_type,
                run_timestamp=pend.run.timestamp,
                file_hash=None,
            )
        except Exception as e:
            self.error.emit(f"overwrite failed: {e}")

    @QtCore.Slot()
    def _scan_once(self) -> None:
        if not self._store:
            return
        try:
            groups = discover_runs_grouped(self._root)
        except Exception as e:
            self.error.emit(f"discover failed: {e}")
            return
        total = sum(len(v) for v in groups.values())
        done = 0
        self.progress.emit(done, total)
        # Track per-type column union for results.jsonl and run counts
        type_columns: dict[str, set[str]] = {t: set() for t in groups.keys()}
        type_counts: dict[str, int] = {t: len(runs) for t, runs in groups.items()}
        for runs in groups.values():
            for run in runs:
                done += 1
                try:
                    st = run.data_file.stat()
                    size = int(st.st_size)
                    mtime = float(st.st_mtime)
                    old = self._store.get_meta(run.data_file, run.test_type)
                    if old is None:
                        self._store.insert_meta(
                            path=run.data_file,
                            size=size,
                            mtime=mtime,
                            test_type=run.test_type,
                            run_timestamp=run.timestamp,
                            file_hash=None,
                        )
                        self.new_indexed.emit(str(run.data_file))
                    else:
                        changed = (old.get("size") != size) or (abs(old.get("mtime", 0.0) - mtime) > 1e-6)
                        if changed:
                            new_meta = {
                                "path": str(run.data_file),
                                "size": size,
                                "mtime": mtime,
                                "hash": None,
                                "test_type": run.test_type,
                                "run_timestamp": run.timestamp,
                            }
                            self._pending[str(run.data_file)] = _PendingDecision(run, size, mtime)
                            self.conflict.emit(str(run.data_file), old, new_meta)

                    # Additionally index results.jsonl rows into per-type data table (typed columns)
                    results_path = run.path / "results.jsonl"
                    if results_path.exists():
                        rst = results_path.stat()
                        r_old = self._store.get_meta(results_path, run.test_type)
                        if (r_old is None) or (r_old.get("size") != rst.st_size) or (abs(r_old.get("mtime", 0.0) - rst.st_mtime) > 1e-6):
                            try:
                                # Re-import rows for this run
                                self._store.delete_results_for_run(run.test_type, run.path)
                                with results_path.open("r", encoding="utf-8") as f:
                                    lines = [line.rstrip("\n") for line in f]
                                parsed_rows = []
                                cols = set()
                                for line in lines:
                                    try:
                                        obj = json.loads(line)
                                    except Exception:
                                        obj = {}
                                    if not isinstance(obj, dict):
                                        obj = {}
                                    parsed_rows.append(obj)
                                    cols.update(obj.keys())
                                # Update per-type union (for summary table)
                                type_columns[run.test_type].update(cols)
                                # Persist typed rows
                                self._store.insert_typed_results_rows(
                                    run.test_type,
                                    run.path,
                                    run.timestamp,
                                    sorted(cols),
                                    parsed_rows,
                                )
                                # Track meta for results.jsonl as well in per-type files table
                                self._store.overwrite_meta(
                                    path=results_path,
                                    size=int(rst.st_size),
                                    mtime=float(rst.st_mtime),
                                    test_type=run.test_type,
                                    run_timestamp=run.timestamp,
                                    file_hash=None,
                                )
                            except Exception as e:
                                self.error.emit(f"results import failed for {results_path}: {e}")
                except Exception as e:
                    self.error.emit(f"scan error for {run.data_file}: {e}")
                self.progress.emit(done, total)

        # Update types summary table
        try:
            if self._store:
                for t, cols in type_columns.items():
                    self._store.upsert_type_info(t, sorted(cols), type_counts.get(t, 0))
        except Exception as e:
            self.error.emit(f"types summary update failed: {e}")
