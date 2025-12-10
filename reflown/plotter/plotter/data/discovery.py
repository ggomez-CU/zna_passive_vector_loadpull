from __future__ import annotations

"""Run discovery utilities (DB and filesystem).

- DB: reads the `runs` table and returns runs grouped by test type.
- FS: scans the `runs` folder on disk and returns grouped runs.
- Helpers to compare DB vs FS for populate/validation.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
import sqlite3

from .model import RunInfo


def _db_path(_root: Path) -> Path:
    """Database lives under <reflown>/runs/plotter_database.sqlite.

    Keep path consistent with data.db_loaders._db_path.
    """
    return Path(__file__).resolve().parents[3] / "runs" / "plotter_database.sqlite"

def discover_runs_grouped_db(root: str | Path) -> Dict[str, List[RunInfo]]:
    # root_path = Path(root)
    # print(root_path)
    # dbp = _db_path(root_path)
    dbp = load_db_path()
    runs_root = dbp.parent
    groups: Dict[str, List[RunInfo]] = {}
    if not dbp.exists():
        return groups
    con = sqlite3.connect(str(dbp))
    cur = con.cursor()
    for ttype, rpath, ts in cur.execute(
        "SELECT test_type, run_path, run_timestamp FROM runs ORDER BY test_type, run_timestamp"
    ):
        p = Path(rpath)
        if not p.is_absolute():
            p = (runs_root / p).resolve(strict=False)
        ri = RunInfo(
            test_type=ttype,
            timestamp=str(ts or p.name),
            path=p,
            data_file=p / "results.jsonl",
            bench_file=None,
            test_file=None,
        )
        groups.setdefault(ttype, []).append(ri)
    con.close()
    return groups


def _detect_data_file(run_dir: Path) -> Optional[Path]:
    for name in ("results.jsonl", "data.jsonl", "data.csv"):
        p = run_dir / name
        if p.exists():
            return p
    return None


def discover_runs_grouped_fs(root: str | Path) -> Dict[str, List[RunInfo]]:
    root_path = Path(root)
    runs_dir = root_path.resolve().parents[0] / "runs"
    groups: Dict[str, List[RunInfo]] = {}
    if not runs_dir.exists():
        return groups
    for test_dir in sorted(d for d in runs_dir.iterdir() if d.is_dir()):
        tname = test_dir.name
        items: List[RunInfo] = []
        for stamp_dir in sorted(d for d in test_dir.iterdir() if d.is_dir()):
            data = _detect_data_file(stamp_dir)
            if not data:
                continue
            bench = stamp_dir / "bench.yaml"
            test = stamp_dir / "test.toml"
            items.append(
                RunInfo(
                    test_type=tname,
                    timestamp=stamp_dir.name,
                    path=stamp_dir,
                    data_file=data,
                    bench_file=bench if bench.exists() else None,
                    test_file=test if test.exists() else None,
                )
            )
        if items:
            groups[tname] = items
    return groups


def compare_db_vs_fs(
    root: str | Path,
) -> Tuple[Dict[str, List[RunInfo]], Dict[str, List[RunInfo]], Set[Tuple[str, str]], Set[Tuple[str, str]]]:
    """Return (db_groups, fs_groups, missing_in_db, missing_on_disk).

    missing_in_db: runs present on disk but not in DB (by (test_type, run_path))
    missing_on_disk: runs present in DB but not on disk
    """
    db = discover_runs_grouped_db(root)
    fs = discover_runs_grouped_fs(root)
    db_set: Set[Tuple[str, str]] = set()
    fs_set: Set[Tuple[str, str]] = set()
    for t, lst in db.items():
        for r in lst:
            db_set.add((t, str(r.path)))
    for t, lst in fs.items():
        for r in lst:
            fs_set.add((t, str(r.path)))
    missing_in_db = fs_set - db_set
    missing_on_disk = db_set - fs_set
    return db, fs, missing_in_db, missing_on_disk


# Default discovery for the plotter app: DB-backed
def discover_runs_grouped(root: str | Path) -> Dict[str, List[RunInfo]]:
    return discover_runs_grouped_db(root)
