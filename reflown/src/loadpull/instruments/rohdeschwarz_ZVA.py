from __future__ import annotations
import time
from typing import Any, Dict, Tuple
from .base import Instrument


class RSZVA(Instrument):
    """Rohde & Schwarz ZVA Vector Network Analyzer (minimal SCPI driver).


    Notes:
    - Uses common R&S VNA SCPI (ZVA/ZNB/ZNA share many mnemonics).
    - Frequency is set via channel 1. Adapt for multi-channel setups as needed.
    - Data fetch returns formatted data (FDATA) or s-data (SDATA) as raw strings.
    """
    channel = '1' 
    input_port = '1'
    output_port = '2'

    # ---- Basic setup / utility ----
    def preset(self) -> str:
        self.scpi.write("SYST:PRES")
        time.sleep(0.5)
        return 1

    def idn(self) -> str:
        return self.scpi.query("*IDN?")

    # ---- Frequency / power ----
    def set_freq_center(self, f_hz: float) -> str:
        self.scpi.write(f"SENS1:FREQ:CENT {f_hz}")
        return 1

    def set_freq_span(self, span_hz: float) -> str:
        self.scpi.write(f"SENS1:FREQ:SPAN {span_hz}")
        return 1

    def set_freq_fixed(self, f_hz: float) -> str:
        # Fixed CW frequency: set start=stop=f
        self.scpi.write(f"SENS1:FREQ:STAR {f_hz}")
        self.scpi.write(f"SENS1:FREQ:STOP {f_hz}")
        return 1

    def set_points(self, n: int) -> str:
        self.scpi.write(f"SENS1:SWE:POIN {int(n)}")
        return 1

    def set_power(self, p_dbm: float) -> str:
        self.scpi.write(f"SOUR1:POW {p_dbm}")
        return 1

    # ---- Sweep control ----
    def sweep_single(self) -> str:
        self.scpi.write("INIT1:IMM; *WAI")
        return 1

    def set_continuous(self, on: bool) -> str:
        self.scpi.write(f"INIT1:CONT {'ON' if on else 'OFF'}")
        return 1

    # ---- Traces / parameters ----
    def select_parameter(self, name: str = "S11") -> str:
        # Ensure a trace exists and is selected
        self.scpi.write("CALC1:PAR:DEL:ALL")
        self.scpi.write(f"CALC1:PAR:DEF:EXT 'Trc1',{name}")
        self.scpi.write("CALC1:PAR:SEL 'Trc1'")
        return 1

    def select_trace(self, tracename):
        self.scpi.write(f"CALC1:PAR:SEL '{tracename}'")
        return 1

    def set_format_logmag(self) -> str:
        self.scpi.write("CALC1:FORM MLOG")
        return 1

    # ---- Data acquisition ----
    def fetch_fdata(self) -> str:
        """Formatted data (e.g., magnitude in current format). Returns CSV-like string."""
        data_str = self.scpi.query("CALC1:DATA? FDATA")
        nums = [float(x.strip()) for x in data_str.split(',') if x.strip()]

        return {"data": nums, "csv": data_str}

    def fetch_sdata(self) -> str:
        """Complex S-parameter data (real,imag pairs). Returns CSV-like string."""
        # Split by commas and strip whitespace
        data_str = self.scpi.query("CALC1:DATA? SDATA")
        nums = [float(x.strip()) for x in data_str.split(',') if x.strip()]
        
        # Separate real and imaginary parts
        real = nums[0::2]   # even indices
        imag = nums[1::2]   # odd indices

        return {"real": real, "imag": imag, "csv": data_str}

    def read_freq_axis(self) -> str:
        """Return stimulus axis for channel 1."""
        return [float(x.strip()) for x in self.scpi.query("SENS1:FREQ:DATA?").split(',') if x.strip()]

    # ---- Convenience measurement ----
    def measure_trace(self, tracename) -> Dict[str, Any]:
        self.select_trace(tracename)
        self.sweep_single()
        y = self.fetch_fdata()
        x = self.read_freq_axis()
        return {"freq_axis": x, "trace": y}

    def capture_point(self) -> Dict[str, Any]:
        return {'freq': self.read_freq_axis(),
                'a1': self.measure_trace('Trca1'), 
				'b1': self.measure_trace('Trcb1'), 
				'a2': self.measure_trace('Trca2'), 
				'b2': self.measure_trace('Trcb2')}
    
    def init_vector_receiver(self):
		
		# write to zva example: CALCulate1:PARameter:DEFine 'Trc3', 'A1D1'
		# manual has how to do external generator also. I am pretty sure these are returned as voltages but that needs to be confirmed

		self.write(f"CALCulate1{channel}:PARameter:SDEFine 'Trca1', 'A{input_port}D{input_port}'")
		self.write(f"CALCulate1{channel}:PARameter:SDEFine 'Trca2', 'A{output_port}D{input_port}'")
        self.write(f"CALCulate1{channel}:PARameter:SDEFine 'Trcb1', 'B{input_port}D{input_port}'")
		self.write(f"CALCulate1{channel}:PARameter:SDEFine 'Trcb2', 'B{output_port}D{input_port}'")

    def get_error_terms(self, filename) -> Dict[str, Any]:
        self.set_cal_file(cal1_filename)
        return {'directivity_input': self.write(f"CORR:CDAT 'DIRECTIVITY', {input_port}")
        'srcmatch_input': self.write(f"CORR:CDAT 'SRCMATCH', {input_port}")
        'refltrack_input': self.write(f"CORR:CDAT 'REFLTRACK', {input_port}")
        'loadmatch_input': self.write(f"CORR:CDAT 'LOADMATCH', {input_port}")
        'transtrack_input2output': self.write(f"CORR:CDAT 'TRANSTRACK', {input_port}, {output_port}")
        'directivity_output': self.write(f"CORR:CDAT 'DIRECTIVITY', {output_port}")
        'srcmatch_output': self.write(f"CORR:CDAT 'SRCMATCH', {output_port}")
        'refltrack_output': self.write(f"CORR:CDAT 'REFLTRACK', {output_port}")
        'loadmatch_output': self.write(f"CORR:CDAT 'LOADMATCH', {output_port}")
        'transtrack_output2input': self.write(f"CORR:CDAT 'TRANSTRACK', {output_port}, {input_port}")}


    def set_cal_file(self, cal_filename):
        self.write(f"CAL:LOAD {cal_filename}")