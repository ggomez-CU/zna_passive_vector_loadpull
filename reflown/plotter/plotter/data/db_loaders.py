from __future__ import annotations

import math
import re
import sqlite3
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, DefaultDict
from collections import defaultdict

from .model import RunInfo


def _db_path() -> Path:
    # <repo>/reflown/plotter/plotter/data/db_loaders.py -> parents[2] == <repo>/reflown
    return Path(__file__).resolve().parents[2] / "runs" / "plotter_database.sqlite"


def _sanitize(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "_", name or "")
    if not s or s[0].isdigit():
        s = f"c_{s or 'col'}"
    return s


def _type_table(test_type: str) -> str:
    t = re.sub(r"[^A-Za-z0-9_]", "_", test_type or "unknown").strip("_") or "unknown"
    return f"data__{t}"


def _array_table(test_type: str) -> str:
    t = re.sub(r"[^A-Za-z0-9_]", "_", test_type or "unknown").strip("_") or "unknown"
    return f"data_array__{t}"


def load_columns_db(
    run: RunInfo,
    columns: List[str],
    *,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, List[float]]:
    con = sqlite3.connect(str(_db_path()))
    cur = con.cursor()
    # Resolve run_id
    row = cur.execute(
        "SELECT id FROM runs WHERE test_type=? AND run_path=?",
        (run.test_type, str(run.path)),
    ).fetchone()
    if not row:
        return {k: [] for k in columns}
    run_id = int(row[0])

    table = _type_table(run.test_type)
    # Determine available columns in typed table
    existing = {r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()}
    want_sample_index = "sample_index" in columns
    wanted = [c for c in columns if c != "sample_index"]
    sani_map = {c: _sanitize(c) for c in wanted}
    present = [c for c in wanted if sani_map[c] in existing]
    # Build query
    select_cols = ",".join(["row_index"] + [sani_map[c] for c in present])
    # Count rows for progress
    # Compute total rows using typed table first, else array table
    total = cur.execute(f"SELECT COUNT(*) FROM {table} WHERE run_id=?", (run_id,)).fetchone()
    total_rows = int(total[0] or 0)
    if total_rows == 0:
        atab = _array_table(run.test_type)
        try:
            mr = cur.execute(f"SELECT MAX(row_index) + 1 FROM {atab} WHERE run_id=?", (run_id,)).fetchone()
            if mr and mr[0]:
                total_rows = int(mr[0])
        except sqlite3.OperationalError:
            total_rows = 0
    out: Dict[str, List[float]] = {k: [] for k in columns}
    if total_rows == 0:
        if progress_cb:
            progress_cb(0, 0)
        con.close()
        return out
    # Stream typed scalar rows
    last_report = -1
    report_every = max(1, total_rows // 200)
    for i, row in enumerate(cur.execute(f"SELECT {select_cols} FROM {table} WHERE run_id=? ORDER BY row_index", (run_id,))):
        # row[0] is row_index; values follow in order of `present`
        for idx, cname in enumerate(present, start=1):
            v = row[idx]
            try:
                out[cname].append(float(v))
            except Exception:
                try:
                    out[cname].append(float("nan"))
                except Exception:
                    out[cname].append(float("nan"))
        if want_sample_index:
            out["sample_index"].append(float(i))
        if progress_cb and (i - last_report) >= report_every:
            progress_cb(i + 1, total_rows)
            last_report = i
    if progress_cb:
        progress_cb(total_rows, total_rows)
    # Fill missing requested columns with NaN lists of correct length
    for cname in wanted:
        if cname not in present:
            out[cname] = [float("nan")] * total_rows

    # Expand array fields: if a requested column isn't in typed table, check array table and expand into name[idx]
    atab = _array_table(run.test_type)
    try:
        # For each requested field absent in typed, fetch array elements
        array_fields = [c for c in wanted if sani_map[c] not in existing]
        for base in array_fields:
            # Does this field exist as array?
            row = cur.execute(
                f"SELECT 1 FROM {atab} WHERE run_id=? AND field=? LIMIT 1",
                (run_id, base),
            ).fetchone()
            if not row:
                continue
            # Fetch all elements
            rows = cur.execute(
                f"SELECT row_index, elem_index, value FROM {atab} WHERE run_id=? AND field=? ORDER BY row_index, elem_index",
                (run_id, base),
            )
            series: DefaultDict[int, List[float]] = defaultdict(lambda: [float('nan')] * total_rows)
            for rix, eix, val in rows:
                try:
                    series[int(eix)][int(rix)] = float(val) if val is not None else float('nan')
                except Exception:
                    # keep NaN
                    pass
            for eix, vals in series.items():
                out[f"{base}[{eix}]"] = vals
    except sqlite3.OperationalError:
        # Array table may not exist
        pass

    con.close()
    return out
