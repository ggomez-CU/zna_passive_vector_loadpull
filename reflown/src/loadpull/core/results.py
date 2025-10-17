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
