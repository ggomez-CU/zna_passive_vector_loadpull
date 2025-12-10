from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Dict, Set

from .data.discovery import discover_runs_grouped_fs, compare_db_vs_fs, load_db_path
from .data.ingest import run_once as ingest_run_once
from .database.sqlite_store import SQLiteStore


def _install_enhanced_traceback() -> None:
    """Install a rich-style traceback that shows locals.

    Tries to use `rich.traceback.install(show_locals=True)` if available; otherwise
    installs a lightweight sys.excepthook that prints locals per frame with truncation.
    """
    try:
        from rich.traceback import install  # type: ignore

        install(show_locals=True, width=120, extra_lines=2, suppress=[])
        return
    except Exception:
        pass

    def _safe_repr(obj, maxlen: int = 200) -> str:
        try:
            s = repr(obj)
        except Exception:
            return "<unrepr>"
        if len(s) > maxlen:
            return s[:maxlen] + "…"
        return s

    def _hook(exc_type, exc, tb):
        print("".join(traceback.format_exception(exc_type, exc, tb)), file=sys.stderr, end="")
        print("Locals by frame (inner to outer):", file=sys.stderr)
        # Collect frames
        frames = []
        cur = tb
        while cur is not None:
            frames.append(cur)
            cur = cur.tb_next
        for tbf in frames:
            fr = tbf.tb_frame
            fname = fr.f_code.co_filename
            func = fr.f_code.co_name
            line = tbf.tb_lineno
            print(f"  Frame {func} at {fname}:{line}", file=sys.stderr)
            for k, v in fr.f_locals.items():
                print(f"    {k} = {_safe_repr(v)}", file=sys.stderr)
    sys.excepthook = _hook


def populate(root: Path, db_path: Path, verbose: bool = True, overwrite: bool = True) -> None:
    store = SQLiteStore(db_path)
    print(db_path)
    # Ingest once using the unified ingest pipeline
    ingest_run_once(root, store)

    # Compare DB vs FS for diagnostics only
    db_groups, fs_groups, missing_in_db, missing_on_disk = compare_db_vs_fs(root)
    groups = fs_groups
    # Determine the last run per test type by timestamp string
    last_run_by_type = {t: max(runs, key=lambda r: r.timestamp) for t, runs in groups.items() if runs}
    total = sum(len(v) for v in groups.values())
    if verbose:
        print(f"Discovered {total} runs across {len(groups)} test types (filesystem)")
        if missing_in_db:
            print(f"[WARN] {len(missing_in_db)} runs on disk missing from DB:")
            for t, p in sorted(missing_in_db):
                print(f"  + {t}: {p}\n")
        if missing_on_disk:
            print(f"[WARN] {len(missing_on_disk)} runs in DB missing on disk:")
            for t, p in sorted(missing_on_disk):
                print(f"  - {t}: {p}\n")

    # Refresh columns from the last run for each type so columns always reflect the latest file
    type_columns: Dict[str, Set[str]] = {t: set() for t in groups.keys()}
    type_counts: Dict[str, int] = {t: len(runs) for t, runs in groups.items()}
    for t, lr in last_run_by_type.items():
        try:
            rpath = lr.path / "results.jsonl"
            cols = set()
            if rpath.exists():
                with rpath.open("r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            obj = json.loads(line)
                            if isinstance(obj, dict):
                                cols.update(obj.keys())
                        except Exception:
                            pass
            # Replace with last-run columns only
            type_columns[t] = cols
        except Exception as e:
            print(f"[ERR] refresh type columns for {t}: {e}")

    # Update types summary
    for t, cols in type_columns.items():
        try:
            store.upsert_type_info(t, sorted(cols), type_counts.get(t, 0))
            if verbose:
                print(f"[TYPES] {t}: {len(cols)} columns, {type_counts.get(t, 0)} runs")
        except Exception as e:
            print(f"[ERR] types update {t}: {e}")


def main() -> None:
    # Install enhanced traceback unless disabled
    # (helps debug populate runs by showing locals on errors)
    # Use --plain-traceback to disable.
    here = Path(__file__).resolve()
    # Default root as the plotter folder so discovery uses ../runs
    default_root = here.parents[1]
    default_db = load_db_path()

    ap = argparse.ArgumentParser(description="Populate the plotter SQLite database from runs")
    ap.add_argument("--root", type=Path, default=default_root, help="Root directory (plotter root; runs expected under ../runs)")
    ap.add_argument("--db", type=Path, default=default_db, help="Path to SQLite database file")
    ap.add_argument("--no-verbose", action="store_true", help="Reduce output")
    ap.add_argument("--no-overwrite", action="store_true", help="Do not overwrite changed metadata")
    ap.add_argument("--plain-traceback", action="store_true", help="Disable enhanced traceback that shows locals")
    args = ap.parse_args()

    if not args.plain_traceback:
        _install_enhanced_traceback()

    populate(args.root, args.db, verbose=not args.no_verbose, overwrite=not args.no_overwrite)


if __name__ == "__main__":
    main()
