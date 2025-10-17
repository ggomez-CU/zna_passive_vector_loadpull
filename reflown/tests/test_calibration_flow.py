from __future__ import annotations

from pathlib import Path

import pytest

from loadpull.core.calibration import CalibrationStore
from loadpull.core.results import JsonlWriter
from loadpull.core.sequencing import Context, Sequence


class DummyInstrument:
    def __init__(self, readings: list[float]):
        self._readings = list(readings)
        self.read_calls = 0
        self.use_args: list[float] = []

    def read_value(self) -> float:
        self.read_calls += 1
        if not self._readings:
            raise RuntimeError("No readings left")
        return self._readings.pop(0)

    def use_offset(self, offset: float) -> float:
        self.use_args.append(offset)
        return offset


CAL_SPEC = {
    "name": "cal_cycle",
    "steps": [
        {
            "calibrate": {
                "name": "offset",
                "do": [
                    {
                        "measure": {
                            "inst": "DMM",
                            "method": "read_value",
                            "save_as": "offset",
                        }
                    }
                ],
                "save": "${offset}",
            }
        },
        {
            "call": {
                "inst": "DMM",
                "method": "use_offset",
                "args": ["${cal.offset}"],
            }
        },
    ],
}

CAL_FORCE_SPEC = {
    **CAL_SPEC,
    "steps": [
        {
            "calibrate": {
                **CAL_SPEC["steps"][0]["calibrate"],
                "force": True,
            }
        },
        *CAL_SPEC["steps"][1:],
    ],
}


def _run_sequence(tmp_path: Path, store: CalibrationStore, instrument: DummyInstrument, spec: dict) -> DummyInstrument:
    seq = Sequence(spec["name"], spec)
    writer = JsonlWriter(tmp_path / f"{spec['name']}.jsonl")
    ctx = Context(
        instruments={"DMM": instrument},
        writer=writer,
        cal_store=store,
        cal_cache=store.as_dict(),
    )
    try:
        seq.run(ctx)
    finally:
        writer.close()
    return instrument


def test_calibration_persistence_and_history(tmp_path: Path) -> None:
    cal_file = tmp_path / "calibration.json"
    store = CalibrationStore(cal_file, bench_name="bench_default")

    inst1 = DummyInstrument([10.0])
    _run_sequence(tmp_path, store, inst1, CAL_SPEC)

    assert inst1.read_calls == 1
    assert store.get("offset") == 10.0
    assert inst1.use_args == [10.0]

    inst2 = DummyInstrument([20.0])
    _run_sequence(tmp_path, store, inst2, CAL_SPEC)

    assert inst2.read_calls == 0  # reused cached calibration
    assert inst2.use_args == [10.0]

    inst3 = DummyInstrument([20.0])
    _run_sequence(tmp_path, store, inst3, CAL_FORCE_SPEC)

    assert inst3.read_calls == 1
    assert store.get("offset") == 20.0

    history = store.history("offset")
    assert len(history) == 1
    assert history[0]["value"] == 10.0
