from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List, Tuple, Iterable

from .discovery import discover_runs_grouped_fs, discover_runs_grouped_db
from ..database.sqlite_store import SQLiteStore


def _row_count(path: Path) -> int:
    if not path.exists():
        return 0
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as fp:
            return sum(1 for _ in csv.DictReader(fp))
    # jsonl
    with path.open("r", encoding="utf-8") as fp:
        return sum(1 for _ in fp if _.strip())


def diff_fs_db(root: Path, store: SQLiteStore) -> Tuple[Dict[str, List], Dict[str, List], List[Tuple[str, Path]]]:
    """Return (fs_groups, db_groups, to_ingest) where to_ingest are (test_type, run_path)."""
    fs = discover_runs_grouped_fs(root)
    db = discover_runs_grouped_db(root)
    db_index = {(t, r.path): True for t, runs in db.items() for r in runs}
    to_ingest: List[Tuple[str, Path]] = []
    for testtypes, runs in fs.items():
        for r in runs:
            needs_ingest = (testtypes, r.path) not in db_index
            # prefer results.jsonl; fallback to data.jsonl/csv
            data_file = r.path / "results.jsonl"
            if not data_file.exists():
                if (r.path / "data.jsonl").exists():
                    data_file = r.path / "data.jsonl"
                elif (r.path / "data.csv").exists():
                    data_file = r.path / "data.csv"
            size = data_file.stat().st_size if data_file.exists() else 0
            rows = _row_count(data_file) if data_file.exists() else 0
            st = store.get_file_stats(data_file) if data_file.exists() else None
            if needs_ingest or (st is None) or (st.get("size") != size) or (st.get("row_count") != rows):
                to_ingest.append((testtypes, r.path))
    return fs, db, to_ingest


def _parse_rows(path: Path) -> Iterable[dict]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as fp:
            for rec in csv.DictReader(fp):
                yield rec
    else:
        with path.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    obj = {}
                yield obj if isinstance(obj, dict) else {}


def ingest_run(store: SQLiteStore, test_type: str, run_path: Path, run_timestamp: str) -> Tuple[int, int]:
    """Ingest or append data for a single run. Returns (rows_ingested, total_rows)."""
    # Data file
    data_file = run_path / "results.jsonl"
    if not data_file.exists():
        if (run_path / "data.jsonl").exists():
            data_file = run_path / "data.jsonl"
        elif (run_path / "data.csv").exists():
            data_file = run_path / "data.csv"
        else:
            return 0, 0
    size = data_file.stat().st_size
    total_rows = _row_count(data_file)
    prev = store.get_file_stats(data_file)
    start_idx = 0
    if prev is not None:
        prev_rows = int(prev.get("row_count") or 0)
        if total_rows < prev_rows:
            # truncated/rewritten: delete all existing
            start_idx = 0
        else:
            start_idx = prev_rows
    # Ensure run row exists and drop any stale rows at or beyond start_idx.
    # store.delete_typed_from_index(test_type, run_path, start_idx, run_timestamp)
    # Iterate rows, split arrays
    parsed = []
    for idx, rec in enumerate(_parse_rows(data_file)):
        if idx < start_idx:
            continue
        norm: dict = {}
        for k, v in rec.items():
            # Keep lists as-is; they will be stored as JSON in the typed table
            if isinstance(v, list) and len(v) == 1:
                norm[k] = v[0]
            else:
                norm[k] = v
        parsed.append(norm)
    # Columns for typed
    cols = sorted({k for rec in parsed for k in rec.keys()})
    # if parsed:
    store.insert_typed_results_rows(test_type, run_path, run_timestamp, cols, parsed)
    # print(run_path)
    # Update file stats and per-type file meta
    store.upsert_file_stats(data_file, size, total_rows)
    store.overwrite_meta(data_file, size, data_file.stat().st_mtime, test_type, run_timestamp, None)
    return len(parsed), total_rows


def refresh_type_columns_if_needed(store: SQLiteStore, test_type: str, last_run_path: Path, last_run_timestamp: str) -> None:
    # Determine last run file
    df = last_run_path / "results.jsonl"
    if not df.exists():
        if (last_run_path / "data.jsonl").exists():
            df = last_run_path / "data.jsonl"
        elif (last_run_path / "data.csv").exists():
            df = last_run_path / "data.csv"
        else:
            return
    size = df.stat().st_size
    rows = _row_count(df)
    # Compare with schema record
    rid = store._get_or_create_run_id(test_type, last_run_path, last_run_timestamp)  # internal helper
    schema = store.get_type_schema(test_type)
    if schema and schema.get("last_run_id") == rid and schema.get("last_size") == size and schema.get("last_row_count") == rows:
        return
    # Recompute columns from last run file
    cols = set()
    for rec in _parse_rows(df):
        if isinstance(rec, dict):
            for k, v in rec.items():
                if isinstance(v, list):
                    # include base key; arrays are stored as JSON per row
                    cols.add(k)
                else:
                    cols.add(k)
    cols_list = sorted(cols)
    store.upsert_type_schema(test_type, rid, size, rows, cols_list)
    # Mirror into types table for compatibility
    # Count runs per type: we can approximate with DB runs table
    # (The populate script can pass the accurate count if needed)
    # Here we leave runs_count unchanged; populate_db updates it precisely.


def run_once(root: Path, store: SQLiteStore) -> None:
    fs, db, to_ingest = diff_fs_db(root, store)
    # Ingest changed runs
    for t, runs in fs.items():
        for r in runs:
            if (t, r.path) in to_ingest:
                ingest_run(store, t, r.path, r.timestamp)
        # Refresh type columns using the last run for this type
        if runs:
            last = max(runs, key=lambda x: x.timestamp)
            refresh_type_columns_if_needed(store, t, last.path, last.timestamp)
