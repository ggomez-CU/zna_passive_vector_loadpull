from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from loadpull.core.scpi import Scpi
from loadpull.instruments.bias_controller import BiasController


class DummyTransport:
    def __init__(self, responses: List[str]):
        self.responses = list(responses)
        self.writes: List[str] = []

    def write(self, data: str) -> None:
        self.writes.append(data)

    def read(self, timeout_s: float) -> str:
        if not self.responses:
            raise AssertionError("No responses left in DummyTransport")
        return self.responses.pop(0)

    def close(self) -> None:  # pragma: no cover - compatibility stub
        pass


@dataclass
class DummySession:
    extra: Dict[str, List[str]]

    def new_scpi_for_resource(self, resource: str) -> Scpi:
        responses = self.extra.get(resource, ["0.0"])
        return Scpi(DummyTransport(responses))


def test_bias_controller_dual_channel_sums_channels() -> None:
    primary = Scpi(DummyTransport(["2.5", "1.2"]))
    bias = BiasController(primary)
    session = DummySession(extra={})
    bias.apply_bench_config(
        {
            "mode": "dual_channel",
            "channels": {"drain": "OUT1", "gate": "OUT2"},
        },
        session,
    )

    total = bias.read_supply()
    assert total == 3.7
    assert len(bias.read_segments()) == 2


def test_bias_controller_dual_supply_adds_secondary() -> None:
    primary = Scpi(DummyTransport(["4.0"]))
    session = DummySession(extra={"aux": ["1.5"]})
    bias = BiasController(primary)
    bias.apply_bench_config(
        {
            "mode": "dual_supply",
            "secondary": "aux",
        },
        session,
    )

    assert bias.read_supply() == 5.5
    segments = bias.read_segments()
    assert segments == [4.0, 1.5]


def test_bias_controller_mixed_mode_combines_channels_and_extra_supply() -> None:
    primary = Scpi(DummyTransport(["3.0", "1.0"]))
    session = DummySession(extra={"aux": ["0.5"]})
    bias = BiasController(primary)
    bias.apply_bench_config(
        {
            "mode": "mixed",
            "channels": {"drain": "OUT1", "gate": "OUT2"},
            "secondary": "aux",
        },
        session,
    )

    assert bias.read_supply() == 4.5
    assert bias.read_segments() == [3.0, 1.0, 0.5]
