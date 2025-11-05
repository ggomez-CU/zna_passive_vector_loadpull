from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from .model import RunInfo


def _detect_data_file(run_dir: Path) -> Optional[Path]:
    for name in ("data.jsonl", "data.csv", "results.jsonl"):
        p = run_dir / name
        if p.exists():
            return p
    return None


def discover_runs_grouped(root: str | Path) -> Dict[str, List[RunInfo]]:
    root_path = Path(root)
    runs_dir = root_path
    groups: Dict[str, List[RunInfo]] = {}
    if not runs_dir.exists():
        return groups
    for test_dir in sorted(d for d in runs_dir.iterdir() if d.is_dir()):
        test_name = test_dir.name
        items: List[RunInfo] = []
        for stamp_dir in sorted(d for d in test_dir.iterdir() if d.is_dir()):
            data_file = _detect_data_file(stamp_dir)
            if not data_file:
                continue
            bench = stamp_dir / "bench.yaml"
            test = stamp_dir / "test.toml"
            bench_file = bench if bench.exists() else None
            test_file = test if test.exists() else None
            available = {"frequency": False, "power": False, "bias": False,
                         "gamma.gamma_L.real": False, "gamma.gamma_L.imag": False, "gamma.gamma_L.mag": False}
            items.append(RunInfo(test_name, stamp_dir.name, stamp_dir, data_file, bench_file, test_file, available))
        if items:
            groups[test_name] = items
    return groups

