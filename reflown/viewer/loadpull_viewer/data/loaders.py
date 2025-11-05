from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Callable


def iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                yield rec


def iter_csv(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        for rec in reader:
            yield rec


def count_records(path: Path) -> int:
    n = 0
    it = iter_csv if path.suffix.lower() == ".csv" else iter_jsonl
    for _ in it(path):
        n += 1
    return n


def load_columns(
    path: Path,
    columns: List[str],
    *,
    max_points: int,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, List[float]]:
    total = count_records(path)
    stride = max(1, (total + max_points - 1) // max_points)
    out: Dict[str, List[float]] = {k: [] for k in columns}
    want_sample_index = "sample_index" in columns

    def push(i: int, rec: dict):
        if i % stride:
            return
        for k in columns:
            v = rec.get(k)
            try:
                out[k].append(float(v))
            except Exception:
                out[k].append(float("nan"))
        if want_sample_index:
            out["sample_index"].append(float(i))

    last_report = -1
    report_every = max(1, total // 200) if total > 0 else 1
    if path.suffix.lower() == ".csv":
        for i, rec in enumerate(iter_csv(path)):
            push(i, rec)
            if progress_cb and (i - last_report) >= report_every:
                progress_cb(i + 1, total)
                last_report = i
    else:
        for i, rec in enumerate(iter_jsonl(path)):
            push(i, rec)
            if progress_cb and (i - last_report) >= report_every:
                progress_cb(i + 1, total)
                last_report = i
    if progress_cb:
        progress_cb(total, total)
    return out
