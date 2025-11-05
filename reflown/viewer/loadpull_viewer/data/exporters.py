from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Iterable, List


def _normalize_value(val):
    if val is None:
        return ""
    # Flatten single-element lists
    if isinstance(val, list) and len(val) == 1:
        val = val[0]
    # JSON-encode complex structures
    if isinstance(val, (list, dict)):
        try:
            return json.dumps(val, separators=(",", ":"))
        except Exception:
            return str(val)
    return val


def _include_field(name: str) -> bool:
    ln = str(name).lower()
    # Skip helper fields like "*.csv" or "*_csv"
    return not (ln.endswith(".csv") or ln.endswith("_csv"))


def jsonl_to_csv(in_path: str | Path, out_path: str | Path) -> int:
    """Convert a JSONL file to CSV with columns = union of keys.

    Missing values are written as blanks. Returns number of rows written.
    """
    src = Path(in_path)
    dst = Path(out_path)

    # First pass: collect headers
    headers: set[str] = set()
    with src.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                for k in rec.keys():
                    if _include_field(str(k)):
                        headers.add(str(k))

    fieldnames = sorted(headers)

    # Second pass: write rows
    dst.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with dst.open("w", encoding="utf-8", newline="") as out_fp:
        writer = csv.DictWriter(out_fp, fieldnames=fieldnames)
        writer.writeheader()
        with src.open("r", encoding="utf-8") as in_fp:
            for line in in_fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                row = {k: _normalize_value(rec.get(k, "")) for k in fieldnames}
                writer.writerow(row)
                rows += 1
    return rows


def copy_csv(in_path: str | Path, out_path: str | Path) -> int:
    src = Path(in_path)
    dst = Path(out_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    # Count rows for confirmation (optional)
    count = 0
    with dst.open("r", encoding="utf-8", newline="") as fp:
        reader = csv.reader(fp)
        for _ in reader:
            count += 1
    # minus header if present; keep as-is
    return max(0, count - 1)
