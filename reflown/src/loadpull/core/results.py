from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import gzip, json, time
import matplotlib.pyplot as plt

@dataclass
class JsonlWriter:
    path: Path

    def __post_init__(self):
        if str(self.path).endswith(".gz"):
            self._fp = gzip.open(self.path, mode="at")
        else:
            self._fp = open(self.path, mode="a", encoding="utf-8")

    def write_point(self, test: str, step: str, data: dict) -> None:
        rec = {
            "schema": "1.0.0",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "test": test,
            "step": step,
            **data,
            }
        self._fp.write(json.dumps(rec) + "\n")
        self._fp.flush()

    def close(self):
        try:
            self._fp.close()
        except Exception:
            pass


@dataclass
class DualWriter:
    """Facade that splits writes between a log and a results writer.

    - write_point(): logs every step to `log_writer` only
    - write_result(): writes to `results_writer` (used to drive plotting)
    - snapshot/reset/close: proxied to results_writer when available; close both
    """
    log_writer: JsonlWriter
    results_writer: object  # JsonlWriter or LivePlotWriter

    def write_point(self, test: str, step: str, data: dict) -> None:
        self.log_writer.write_point(test, step, data)

    def write_result(self, test: str, step: str, data: dict) -> None:
        # Results writer may be LivePlotWriter; just delegate
        self.results_writer.write_point(test, step, data)  # type: ignore[attr-defined]

    # Optional helpers used by sequencing when plotting is enabled
    def snapshot(self, suffix: str) -> None:
        if hasattr(self.results_writer, "snapshot"):
            getattr(self.results_writer, "snapshot")(suffix)

    def reset(self) -> None:
        if hasattr(self.results_writer, "reset"):
            getattr(self.results_writer, "reset")()

    def close(self) -> None:
        # Close results first to flush plots, then log
        try:
            if hasattr(self.results_writer, "close"):
                getattr(self.results_writer, "close")()
        finally:
            try:
                self.log_writer.close()
            except Exception:
                pass
