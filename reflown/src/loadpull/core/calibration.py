from __future__ import annotations

import json
import time
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

_HISTORY_KEY = "__history__"


@dataclass
class CalibrationStore:
    """Light-weight persistence helper for calibration constants."""

    path: Path
    bench_name: str | None = None
    autosave: bool = False
    _data: Dict[str, Any] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.path = Path(self.path) # the path is defined in the cli and is ../calibration/benchname.json
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = {}
        self.load()

    def load(self) -> None:
        """Load calibrations from disk into memory."""
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._data = {}
            return

        if not raw.strip():
            self._data = {}
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Calibration store at {self.path} is not valid JSON") from exc

        if not isinstance(data, dict):
            raise ValueError(f"Calibration store at {self.path} must contain a JSON object")

        self._data = data
        self._ensure_bucket()

    def _ensure_bucket(self) -> Dict[str, Any]:
        if self.bench_name is None:
            return self._data

        bucket = self._data.setdefault(self.bench_name, {})
        if not isinstance(bucket, dict):
            raise ValueError(
                f"Calibration bucket for bench '{self.bench_name}' must be a JSON object"
            )
        return bucket

    def _history_root(self) -> Dict[str, Any]:
        root = self._data.setdefault(_HISTORY_KEY, {})
        if not isinstance(root, dict):
            raise ValueError("Calibration history storage corrupted; expected an object")
        key = self.bench_name or "__global__"
        bucket = root.setdefault(key, {})
        if not isinstance(bucket, dict):
            raise ValueError("Calibration history bucket corrupted; expected an object")
        return bucket

    def _append_history(self, name: str, value: Any) -> None:
        history_bucket = self._history_root()
        history_list = history_bucket.setdefault(name, [])
        if not isinstance(history_list, list):
            raise ValueError(
                f"Calibration history for '{name}' is corrupted; expected a list"
            )
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "value": deepcopy(value),
        }
        history_list.append(entry)

    def save(self) -> None:
        """Persist the current calibration map to disk."""
        payload = json.dumps(self._data, indent=2, sort_keys=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(payload + "\n", encoding="utf-8")
        tmp_path.replace(self.path)

    def get(self, name: str, default: Any | None = None) -> Any:
        """Fetch a stored calibration constant, returning ``default`` if missing."""
        return self._ensure_bucket().get(name, default)

    def history(self, name: str) -> List[Dict[str, Any]]:
        """Return prior calibration entries for ``name`` (oldest first)."""
        history_bucket = self._history_root()
        entries = history_bucket.get(name, [])
        return list(entries) if isinstance(entries, list) else []

    def set(self, name: str, value: Any) -> None:
        """Save or update a calibration constant, archiving any previous value."""
        bucket = self._ensure_bucket()
        if name in bucket:
            self._append_history(name, bucket[name])
        bucket[name] = value
        if self.autosave:
            self.save()

    def delete(self, name: str) -> None:
        """Remove a calibration constant if it exists."""
        bucket = self._ensure_bucket()
        if name in bucket:
            self._append_history(name, bucket[name])
            del bucket[name]
            if self.autosave:
                self.save()

    def names(self) -> list[str]:
        """Return the list of calibration keys for the active bench."""
        return sorted(self._ensure_bucket().keys())

    def as_dict(self) -> Dict[str, Any]:
        """Return a shallow copy of the calibration constants for the active bench."""
        return dict(self._ensure_bucket())

    def __contains__(self, name: str) -> bool:  # pragma: no cover - convenience
        return name in self._ensure_bucket()

    def __iter__(self) -> Iterator[str]:  # pragma: no cover - convenience
        return iter(self.names())
