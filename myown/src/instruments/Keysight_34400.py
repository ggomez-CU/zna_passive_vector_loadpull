from __future__ import annotations
from typing import Any, Dict
from .base import Instrument

class Keysight34400(Instrument):
    """
    Keysight 34400 Series Digital Multimeter (DMM).
    Minimal SCPI driver adapted for the loadpull scaffold.
    """

    def preset(self) -> str:
        """Clear status and reset."""
        self.scpi.write("*CLS")
        self.scpi.write("*RST")
        return "OK"

    def set_low_power_mode(self, enable: bool, four_wire: bool = False) -> str:
        """Enable/disable low power resistance measurement."""
        if four_wire:
            self.scpi.write(f"SENS:FRES:POW:LIM:STATE {'ON' if enable else 'OFF'}")
        else:
            self.scpi.write(f"SENS:RES:POW:LIM:STATE {'ON' if enable else 'OFF'}")
        return "OK"

    def configure_resistance(self, four_wire: bool = False) -> str:
        """Configure 2-wire or 4-wire resistance mode."""
        if four_wire:
            self.scpi.write("CONF:FRES")
        else:
            self.scpi.write("CONF:RES")
        return "OK"

    def configure_voltage_dc(self) -> str:
        """Configure DC voltage measurement."""
        self.scpi.write("CONF:VOLT:DC")
        return "OK"

    def measure_voltage(self) -> Dict[str, Any]:
        """Trigger and read a DC voltage measurement."""
        val = float(self.scpi.query("READ?"))
        return {"Vdc": val}

    def measure_resistance(self, four_wire: bool = False) -> Dict[str, Any]:
        """Trigger and read a resistance measurement."""
        if four_wire:
            self.scpi.write("CONF:FRES")
        else:
            self.scpi.write("CONF:RES")
        val = float(self.scpi.query("READ?"))
        return {"R": val}

    def fetch_last(self) -> Dict[str, Any]:
        """Fetch the last value (numeric only)."""
        val = float(self.scpi.query("FETCh?"))
        return {"last": val}