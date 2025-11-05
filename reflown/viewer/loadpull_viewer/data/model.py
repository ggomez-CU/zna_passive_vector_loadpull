from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass(frozen=True)
class RunInfo:
    test_type: str
    timestamp: str
    path: Path
    data_file: Path
    bench_file: Optional[Path]
    test_file: Optional[Path]
    available_fields: Dict[str, bool]

