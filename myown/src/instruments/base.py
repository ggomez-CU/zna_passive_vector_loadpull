from __future__ import annotations
from ..core.scpi import Scpi


class Instrument:
    def __init__(self, scpi: Scpi):
        self.scpi = scpi


    def idn(self) -> str:
        return self.scpi.query("*IDN?")