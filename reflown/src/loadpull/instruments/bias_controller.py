from __future__ import annotations

from typing import Any, Dict, List

from ..core.session import Session
from ..core.scpi import Scpi
from .base import Instrument


class BiasController(Instrument):
    """Bias controller supporting single, dual-channel, dual-supply, or mixed setups."""

    def __init__(self, scpi: Scpi):
        super().__init__(scpi)
        self.mode = "single"
        self._channels: Dict[str, str] = {}
        self._secondary_scpi: List[Scpi] = []

    def apply_bench_config(self, config: Dict[str, Any], session: Session) -> None:
        mode = str(config.get("mode", "single")).lower()
        self.mode = mode
        self._channels = {}
        self._close_secondaries()

        if mode in {"dual_channel", "mixed"}:
            channels = config.get("channels", {})
            if isinstance(channels, dict):
                self._channels = {str(k): str(v) for k, v in channels.items()}
        resources: List[str] = []
        if mode in {"dual_supply", "mixed"}:
            secondary = config.get("secondary") or config.get("secondary_resource")
            extras = config.get("extra_supplies", [])
            if isinstance(secondary, str):
                resources.append(secondary)
            if isinstance(extras, list):
                resources.extend(str(r) for r in extras if isinstance(r, str))
        for resource in resources:
            self._secondary_scpi.append(session.new_scpi_for_resource(resource))
        # Any other keys can be handled similarly if needed.

    def read_segments(self) -> List[float]:
        return list(self._collect_segments())

    def idn(self) -> List[float]:
        if self.mode in {"dual_channel", "mixed"} and self._channels:
            values = [self._get_idn(self.scpi)]
            if self.mode == "mixed" and self._secondary_scpi:
                values.extend(self._get_idn(scpi) for scpi in self._secondary_scpi)
        elif self.mode == "dual_supply":
            values = [self._get_idn(self.scpi)]
            values.extend(self._get_idn(scpi) for scpi in self._secondary_scpi)
        else:
            values = [self._get_idn(self.scpi)]
        return values

    def _collect_segments(self) -> List[float]:
        if self.mode in {"dual_channel", "mixed"} and self._channels:
            values = [self._measure_channel(ch) for ch in self._channels.values()]
            if self.mode == "mixed" and self._secondary_scpi:
                values.extend(self._measure_default(scpi) for scpi in self._secondary_scpi)
        elif self.mode == "dual_supply":
            values = [self._measure_default(self.scpi)]
            values.extend(self._measure_default(scpi) for scpi in self._secondary_scpi)
        else:
            values = [self._measure_default(self.scpi)]
        return values

    def _get_idn(self, scpi:Scpi) -> str:
        return scpi.query("*IDN?")

    def _measure_channel(self, channel: str) -> float:
        return float(self.scpi.query_no_poll(f"MEAS:VOLT? (@{channel})"))

    def _measure_default(self, scpi: Scpi) -> float:
        return float(scpi.query_no_poll("MEAS:VOLT?"))

    def _close_secondaries(self) -> None:
        for scpi in self._secondary_scpi:
            try:
                scpi.t.close()
            except Exception:
                pass
        self._secondary_scpi.clear()

    def close(self) -> None:  # pragma: no cover - cleanup helper
        self._close_secondaries()
