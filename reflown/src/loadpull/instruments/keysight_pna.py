from __future__ import annotations
import time
from typing import Any, Dict
from .base import Instrument


class KeysightPNA(Instrument):
    def preset(self) -> str:
        self.scpi.write("SYST:PRES")
        time.sleep(0.2)
        return "OK"


    def set_freq(self, f_ghz: float) -> str:
        self.scpi.write(f"SENS1:FREQ {f_ghz}GHz")
        return "OK"


    def set_power(self, p_dbm: float) -> str:
        self.scpi.write(f"SOUR:POW {p_dbm}DBM")
        return "OK"


    def capture_point(self) -> Dict[str, Any]:
        # Example: read S11 magnitude and phase (device-specific SCPI may differ)
        s11 = self.scpi.query("CALC1:DATA? FDATA")
        # In real code, parse binary/ASCII block into arrays; here return raw
        return {"S11_raw": s11}