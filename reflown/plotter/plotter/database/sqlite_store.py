from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path
from typing import Optional, Dict, Any, Iterable, List, Tuple
import json


class SQLiteStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        # Keep a legacy aggregate table for compatibility; new writes go to per-test tables
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                size INTEGER,
                mtime REAL,
                hash TEXT,
                test_type TEXT,
                run_timestamp TEXT,
                indexed_at REAL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS types (
                test_type TEXT PRIMARY KEY,
                columns TEXT,
                runs_count INTEGER,
                last_updated REAL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY,
                test_type TEXT NOT NULL,
                run_path TEXT NOT NULL,
                run_timestamp TEXT,
                UNIQUE(test_type, run_path)
            )
            """
        )
        self._conn.commit()

    @staticmethod
    def _table_name(test_type: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_]", "_", test_type or "unknown").strip("_")
        if not safe:
            safe = "unknown"
        return f"{safe}"

    def _ensure_table_for(self, test_type: str) -> str:
        table = f"files__{self._table_name(test_type)}"
        ddl = (
            f"CREATE TABLE IF NOT EXISTS {table} ("
            "path TEXT PRIMARY KEY,"
            "size INTEGER,"
            "mtime REAL,"
            "hash TEXT,"
            "run_timestamp TEXT,"
            "indexed_at REAL)"
        )
        cur = self._conn.cursor()
        cur.execute(ddl)
        self._conn.commit()
        return table

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def get_meta(self, path: Path, test_type: str) -> Optional[Dict[str, Any]]:
        table = self._ensure_table_for(test_type)
        cur = self._conn.cursor()
        row = cur.execute(
            f"SELECT path,size,mtime,hash,run_timestamp,indexed_at FROM {table} WHERE path=?",
            (str(path),),
        ).fetchone()
        if not row:
            return None
        return {
            "path": row[0],
            "size": row[1],
            "mtime": row[2],
            "hash": row[3],
            "test_type": test_type,
            "run_timestamp": row[4],
            "indexed_at": row[5],
        }

    def insert_meta(
        self,
        path: Path,
        size: int,
        mtime: float,
        test_type: str,
        run_timestamp: str,
        file_hash: Optional[str] = None,
    ) -> None:
        table = self._ensure_table_for(test_type)
        cur = self._conn.cursor()
        # Avoid accidental overwrite: insert only
        cur.execute(
            f"INSERT OR IGNORE INTO {table}(path,size,mtime,hash,run_timestamp,indexed_at) VALUES(?,?,?,?,?,?)",
            (str(path), int(size), float(mtime), file_hash, run_timestamp, time.time()),
        )
        self._conn.commit()

    def overwrite_meta(
        self,
        path: Path,
        size: int,
        mtime: float,
        test_type: str,
        run_timestamp: str,
        file_hash: Optional[str] = None,
    ) -> None:
        table = self._ensure_table_for(test_type)
        cur = self._conn.cursor()
        cur.execute(f"DELETE FROM {table} WHERE path=?", (str(path),))
        cur.execute(
            f"INSERT INTO {table}(path,size,mtime,hash,run_timestamp,indexed_at) VALUES(?,?,?,?,?,?)",
            (str(path), int(size), float(mtime), file_hash, run_timestamp, time.time()),
        )
        self._conn.commit()

    # Test-type summary table operations
    def upsert_type_info(self, test_type: str, columns: List[str], runs_count: int) -> None:
        cur = self._conn.cursor()
        cols_json = json.dumps(list(columns))
        cur.execute(
            """
            INSERT INTO types(test_type, columns, runs_count, last_updated)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(test_type) DO UPDATE SET
              columns=excluded.columns,
              runs_count=excluded.runs_count,
              last_updated=excluded.last_updated
            """,
            (test_type, cols_json, int(runs_count), time.time()),
        )
        self._conn.commit()

    # Per-test data tables for results.jsonl
    def _ensure_data_table_for(self, test_type: str) -> str:
        table = f"data__{self._table_name(test_type)}"
        ddl = (
            f"CREATE TABLE IF NOT EXISTS {table} ("
            "run_path TEXT,"
            "run_timestamp TEXT,"
            "row_index INTEGER,"
            "json TEXT,"
            "indexed_at REAL,"
            "PRIMARY KEY(run_path, row_index))"
        )
        cur = self._conn.cursor()
        cur.execute(ddl)
        self._conn.commit()
        return table

    def delete_results_for_run(self, test_type: str, run_path: Path) -> None:
        # Delete from both legacy and typed tables
        ltable = self._ensure_data_table_for(test_type)
        ttable, _ = self._ensure_typed_data_table(test_type, [])
        cur = self._conn.cursor()
        cur.execute(f"DELETE FROM {ltable} WHERE run_path=?", (str(run_path),))
        rid = self._get_or_create_run_id(test_type, run_path, None)
        cur.execute(f"DELETE FROM {ttable} WHERE run_id=?", (rid,))
        self._conn.commit()

    def insert_results_rows(
        self,
        test_type: str,
        run_path: Path,
        run_timestamp: str,
        rows: Iterable[str],
    ) -> None:
        table = self._ensure_data_table_for(test_type)
        cur = self._conn.cursor()
        now = time.time()
        batch = [(str(run_path), run_timestamp, i, line, now) for i, line in enumerate(rows)]
        if batch:
            cur.executemany(
                f"INSERT OR REPLACE INTO {table}(run_path,run_timestamp,row_index,json,indexed_at) VALUES(?,?,?,?,?)",
                batch,
            )
            self._conn.commit()

    def results_count_for_run(self, test_type: str, run_path: Path, run_timestamp: str) -> int:
        # Prefer typed table by run_id; fallback to legacy
        ttable, _ = self._ensure_typed_data_table(test_type, [])
        cur = self._conn.cursor()
        # Get or create run_id (create is harmless if new)
        rid = self._get_or_create_run_id(test_type, run_path, run_timestamp)
        row = cur.execute(
            f"SELECT COUNT(*) FROM {ttable} WHERE run_id=?",
            (rid,),
        ).fetchone()
        if row and row[0] is not None and int(row[0]) > 0:
            return int(row[0])
        # Legacy by path
        ltable = self._ensure_data_table_for(test_type)
        row = cur.execute(
            f"SELECT COUNT(*) FROM {ltable} WHERE run_path=?",
            (str(run_path),),
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    # Array elements table (per test type)
    def _ensure_array_table_for(self, test_type: str) -> str:
        table = f"data_array__{self._table_name(test_type)}"
        cur = self._conn.cursor()
        cur.execute(
            (
                f"CREATE TABLE IF NOT EXISTS {table} ("
                "run_id INTEGER,"
                "row_index INTEGER,"
                "field TEXT,"
                "elem_index INTEGER,"
                "value NUMERIC,"
                "indexed_at REAL,"
                "PRIMARY KEY(run_id, row_index, field, elem_index))"
            )
        )
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_field ON {table}(run_id, field, elem_index)")
        self._conn.commit()
        return table

    def insert_array_elements(
        self,
        test_type: str,
        run_path: Path,
        run_timestamp: str,
        elems: Iterable[Tuple[int, str, int, Optional[float]]],
    ) -> None:
        table = self._ensure_array_table_for(test_type)
        cur = self._conn.cursor()
        rid = self._get_or_create_run_id(test_type, run_path, run_timestamp)
        now = time.time()
        batch = [(rid, row_idx, field, elem_idx, val, now) for (row_idx, field, elem_idx, val) in elems]
        if batch:
            cur.executemany(
                f"INSERT OR REPLACE INTO {table}(run_id,row_index,field,elem_index,value,indexed_at) VALUES(?,?,?,?,?,?)",
                batch,
            )
            self._conn.commit()

    # Typed (columnar) per-test data table management
    @staticmethod
    def _sanitize_col(name: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_]", "_", name or "")
        if not safe or safe[0].isdigit():
            safe = f"c_{safe or 'col'}"
        return safe

    def _ensure_typed_data_table(self, test_type: str, columns: List[str]) -> Tuple[str, List[str]]:
        """Ensure a typed table exists with base columns + given columns.

        Returns (table_name, sanitized_columns_order).
        Adds any missing columns via ALTER TABLE; never drops columns.
        """
        table = f"data__{self._table_name(test_type)}"
        cur = self._conn.cursor()
        # Create base table if missing (include run_id for compact foreign key)
        cur.execute(
            (
                f"CREATE TABLE IF NOT EXISTS {table} ("
                "run_id INTEGER,"
                "run_path TEXT,"
                "run_timestamp TEXT,"
                "row_index INTEGER,"
                "indexed_at REAL)"
            )
        )
        # Existing columns
        existing = {r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()}
        if "run_id" not in existing:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN run_id INTEGER")
        ordered_sanitized: List[str] = []
        for col in columns:
            s = self._sanitize_col(col)
            ordered_sanitized.append(s)
            if s not in existing:
                # Use NUMERIC affinity to allow ints/floats, TEXT will also store
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {s} NUMERIC")
        # Ensure an index on (run_id, row_index) for fast per-run reads
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_run ON {table}(run_id, row_index)")
        self._conn.commit()
        return table, ordered_sanitized

    def _get_or_create_run_id(self, test_type: str, run_path: Path, run_timestamp: Optional[str]) -> int:
        cur = self._conn.cursor()
        row = cur.execute(
            "SELECT id FROM runs WHERE test_type=? AND run_path=?",
            (test_type, str(run_path)),
        ).fetchone()
        if row and row[0] is not None:
            return int(row[0])
        cur.execute(
            "INSERT INTO runs(test_type, run_path, run_timestamp) VALUES(?,?,?)",
            (test_type, str(run_path), run_timestamp),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def insert_typed_results_rows(
        self,
        test_type: str,
        run_path: Path,
        run_timestamp: str,
        columns: List[str],
        rows: Iterable[Dict[str, Any]],
    ) -> None:
        table, sani_cols = self._ensure_typed_data_table(test_type, columns)
        cur = self._conn.cursor()
        now = time.time()
        # Build insert statement with placeholders for base + dynamic columns
        col_list = ["run_id", "run_path", "run_timestamp", "row_index", "indexed_at", *sani_cols]
        qmarks = ",".join(["?"] * len(col_list))
        sql = f"INSERT OR REPLACE INTO {table} (" + ",".join(col_list) + ") VALUES(" + qmarks + ")"
        batch = []
        # Map from original names to sanitized
        name_map = {orig: sani for orig, sani in zip(columns, sani_cols)}
        rid = self._get_or_create_run_id(test_type, run_path, run_timestamp)
        for idx, obj in enumerate(rows):
            values = [rid, str(run_path), run_timestamp, idx, now]
            for orig in columns:
                v = obj.get(orig)
                # Keep scalars; coerce lists/dicts to string
                if isinstance(v, (int, float)):
                    values.append(v)
                elif isinstance(v, bool):
                    values.append(1 if v else 0)
                elif v is None:
                    values.append(None)
                else:
                    values.append(str(v))
            batch.append(tuple(values))
        if batch:
            cur.executemany(sql, batch)
            self._conn.commit()
