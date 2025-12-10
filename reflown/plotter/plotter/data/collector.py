from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtCore

from ..database.sqlite_store import SQLiteStore
from .ingest import run_once as ingest_run_once


class DataCollectorService(QtCore.QObject):
    error = QtCore.Signal(str)

    def __init__(self, runs_root: Path, db_path: Path, interval_ms: int = 3000, use_hash: bool = False) -> None:
        super().__init__()
        self._root = Path(runs_root)
        self._db_path = Path(db_path)
        self._interval = int(interval_ms)
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(self._interval)
        self._timer.timeout.connect(self._scan_once)
        self._store: Optional[SQLiteStore] = None

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

    @QtCore.Slot()
    def _scan_once(self) -> None:
        if not self._store:
            return
        try:
            # Delegate to the unified ingest step; no UI prompts or conflicts
            ingest_run_once(self._root, self._store)
        except Exception as e:
            self.error.emit(f"ingest failed: {e}")
