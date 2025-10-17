from pathlib import Path

from loadpull.core.results import JsonlWriter
from loadpull.core.sequencing import Context, Sequence


class DummyInstrument:
    def measure_with_args(self, value: float, unit: str) -> dict:
        assert unit == "dBm"
        return {"power": value, "unit": unit}


SPEC = {
    "name": "measure_args",
    "parameters": {"p": {"default": -5.0}},
    "steps": [
        {
            "measure": {
                "inst": "PM",
                "method": "measure_with_args",
                "args": ["${p}", "dBm"],
                "save_as": "measurements.power",
            }
        }
    ],
}


def test_measure_supports_args(tmp_path: Path) -> None:
    seq = Sequence(SPEC["name"], SPEC)
    writer = JsonlWriter(tmp_path / "out.jsonl")
    ctx = Context(
        instruments={"PM": DummyInstrument()},
        writer=writer,
        cal_store=None,  # type: ignore[arg-type]
        cal_cache={},
    )
    seq.run(ctx)
    writer.close()
    data = (tmp_path / "out.jsonl").read_text().strip()
    assert "measure:measure_with_args" in data
    assert "\"power\": -5.0" in data
