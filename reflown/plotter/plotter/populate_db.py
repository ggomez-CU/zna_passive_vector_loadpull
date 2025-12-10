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
    def _collect_columns_from_results(path: Path) -> Set[str]:
        cols: Set[str] = set()
        if not path.exists():
            return cols
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except Exception:
                    obj = {}
                if not isinstance(obj, dict):
                    continue
                for k, v in obj.items():
                    if isinstance(v, list):
                        if len(v) == 1:
                            cols.add(k)
                        elif len(v) >= 2:
                            # Arrays stored separately
                            continue
                        else:
                            cols.add(k)
                    else:
                        cols.add(k)
        return cols

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
                print(f"  - {t}: {p}")

    # Track per-type column union and run counts
    type_columns: Dict[str, Set[str]] = {t: set() for t in groups.keys()}
    type_counts: Dict[str, int] = {t: len(runs) for t, runs in groups.items()}
    # Seed columns from the last run of each type so every run uses a non-empty column set
    for t, lr in last_run_by_type.items():
        try:
            type_columns[t].update(_collect_columns_from_results(lr.path / "results.jsonl"))
        except Exception:
            pass
    # Seed columns with any previously stored columns for each test type
    # for t in groups.keys():
    #     prev_cols = store.get_type_columns(t)
    #     if prev_cols:
    #         type_columns[t].update(prev_cols)

    for runs in groups.values():
        for run in runs:
            done += 1
            # try:
            st = run.data_file.stat()
            size = int(st.st_size)
            mtime = float(st.st_mtime)
            old = store.get_meta(run.data_file, run.test_type)
            if old is None:
                store.insert_meta(
                    path=run.data_file,
                    size=size,
                    mtime=mtime,
                    test_type=run.test_type,
                    run_timestamp=run.timestamp,
                    file_hash=None,
                )
                if verbose:
                    print(f"[NEW] meta {run.test_type}: {run.data_file}")
            else:
                changed = (old.get("size") != size) or (abs(old.get("mtime", 0.0) - mtime) > 1e-6)
                if changed and overwrite:
                    store.overwrite_meta(
                        path=run.data_file,
                        size=size,
                        mtime=mtime,
                        test_type=run.test_type,
                        run_timestamp=run.timestamp,
                        file_hash=None,
                    )
                    if verbose:
                        print(f"[UPD] meta {run.test_type}: {run.data_file}")

            # Ingest results.jsonl into per-type data table
            results_path = run.path / "results.jsonl"
            if results_path.exists():
                rst = results_path.stat()
                r_old = store.get_meta(results_path, run.test_type)
                # Ingest when we have no rows yet for this run, or file size changed, or no prior meta
                need_ingest = store.results_count_for_run(run.test_type, run.path, run.timestamp) == 0
                # print(breakhere)
                if (r_old is None) or need_ingest or (r_old.get("size") != rst.st_size):
                    store.delete_results_for_run(run.test_type, run.path)

                    with results_path.open("r", encoding="utf-8") as f:
                        lines = [line.rstrip("\n") for line in f]
                    # Update column union and prepare typed rows
                    # Only take columns from the last run for this test type
                        lr = last_run_by_type.get(run.test_type)
                    
                        parsed_rows = []
                        array_elems = []  # list of (row_index, field, elem_index, value)
                        for row_idx, line in enumerate(lines):
                            try:
                                obj = json.loads(line)
                            except Exception:
                                obj = {}
                            if not isinstance(obj, dict):
                                obj = {}
                            # Split arrays: len==1 -> keep scalar; len>=2 -> move to array_elems and drop from typed
                            normalized: dict = {}
                            for k, v in obj.items():
                                if isinstance(v, list):
                                    if len(v) == 1:
                                        normalized[k] = v[0]
                                    elif len(v) >= 2:
                                        for ei, ev in enumerate(v):
                                            try:
                                                val = float(ev)
                                            except Exception:
                                                val = None
                                            array_elems.append((row_idx, k, ei, val))
                                        # Do not keep in typed columns
                                    else:
                                        normalized[k] = None
                                else:
                                    normalized[k] = v
                            parsed_rows.append(normalized)
                            # Union columns across all runs (pre-seeded with last run)
                            type_columns[run.test_type].update(normalized.keys())
                        # Persist typed rows based on current columns for this type
                        cols_list = sorted(type_columns[run.test_type])
                        store.insert_typed_results_rows(run.test_type, run.path, run.timestamp, cols_list, parsed_rows)
                        # Persist array elements
                        if array_elems:
                            store.insert_array_elements(run.test_type, run.path, run.timestamp, array_elems)
                    store.overwrite_meta(
                        path=results_path,
                        size=int(rst.st_size),
                        mtime=float(rst.st_mtime),
                        test_type=run.test_type,
                        run_timestamp=run.timestamp,
                        file_hash=None,
                    )
                    if verbose:
                        print(f"[INGEST] results {run.test_type}: {results_path} ({len(lines)} rows)")

            # except Exception as e:
            #     print(f"[ERR] {run.data_file}: {e}")
            if verbose and (done % 50 == 0 or done == total):
                print(f"Progress: {done}/{total}")

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
