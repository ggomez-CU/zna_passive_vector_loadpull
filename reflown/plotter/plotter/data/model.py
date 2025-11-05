from __future__ import annotations

"""Data models for discovered runs."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class RunInfo:
    """Lightweight description of a measurement run on disk."""

    test_type: str
    timestamp: str
    path: Path
    data_file: Path
    bench_file: Optional[Path]
    test_file: Optional[Path]

