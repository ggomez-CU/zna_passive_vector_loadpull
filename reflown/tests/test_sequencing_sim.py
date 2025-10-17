from pathlib import Path

from loadpull.core.calibration import CalibrationStore
from loadpull.core.results import JsonlWriter
from loadpull.core.scpi import Scpi
from loadpull.core.sequencing import Context, Sequence
from loadpull.core.transport import FakeTransport
from loadpull.instruments.base import Instrument


class FakePNA(Instrument):
    def preset(self) -> str:
        return "OK"

    def set_freq(self, f_ghz: float) -> str:  # pragma: no cover - unused in test
        return "OK"

    def set_power(self, p_dbm: float) -> str:
        return f"POWER {p_dbm}"

    def capture_point(self) -> dict:
        return {"S11_raw": "1,2,3"}


SPEC = {
    "name": "sim_sweep",
    "steps": [
        {"call": {"inst": "PNA", "method": "preset"}},
        {
            "sweep": {
                "var": "p",
                "from": -30,
                "to": -20,
                "step": 5,
                "do": [
                    {"call": {"inst": "PNA", "method": "set_power", "args": ["${p}"]}},
                    {"measure": {"inst": "PNA", "method": "capture_point", "save_as": "sparams"}},
                    {
                        "transform": {
                            "method": "power_log",
                            "args": {"power": "${p}", "sparams": "${sparams}"},
                            "save_as": "derived.log_point",
                        }
                    },
                ],
            }
        },
    ],
}


def _fake_transform(method: str, payload: dict, _cal_cache: dict) -> dict:
    assert method == "power_log"
    return {"power": payload["power"], "tag": "xform"}


def test_sequence_runs(tmp_path: Path) -> None:
    seq = Sequence("sim_sweep", SPEC)
    writer = JsonlWriter(tmp_path / "out.jsonl")
    cal_store = CalibrationStore(tmp_path / "cal.json")
    transport = FakeTransport([])
    transport.open()
    ctx = Context(
        instruments={"PNA": FakePNA(Scpi(transport))},
        writer=writer,
        cal_store=cal_store,
        cal_cache=cal_store.as_dict(),
        transform=_fake_transform,
    )
    seq.run(ctx)
    writer.close()
    data = (tmp_path / "out.jsonl").read_text().strip().splitlines()
    assert any("transform:power_log" in line for line in data)
