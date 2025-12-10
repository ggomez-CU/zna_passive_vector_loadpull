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
    channel = 1
    input_port = 1
    output_port = 4

    # ---- Basic setup / utility ----
    def preset(self):
        try:
            self.scpi.write("*CLS")
        except Exception:
            pass
        self.scpi.write("SYST:PRES")
        time.sleep(0.5)
        
    def clear_syserror(self):
        try:
            self.scpi.write("*CLS")
        except Exception:
            pass

    def idn(self) -> str:
        return self.scpi.query("*IDN?")

    # ---- Frequency / power ----
    def set_freq_center(self, f_hz: float) -> str:
        self.scpi.write(f"SENS1:FREQ:CENT {f_hz}")
        return 1

    def set_freq_span(self, span_hz: float) -> str:
        self.scpi.write(f"SENS1:FREQ:SPAN {span_hz}")
        return 1

    def set_freq_fixed(self, f_hz: float, scale: str = "hz") -> str:
        # Fixed CW frequency: set start=stop=f
        if scale.lower() == "ghz":
            self.scpi.write(f"SENS1:FREQ:STAR {f_hz*1e9}")
            self.scpi.write(f"SENS1:FREQ:STOP {f_hz*1e9}")
        else:
            self.scpi.write(f"SENS1:FREQ:STAR {f_hz}")
            self.scpi.write(f"SENS1:FREQ:STOP {f_hz}")
        return 1

    def set_points(self, n: int) -> str:
        self.scpi.write(f"SENS1:SWE:POIN {int(n)}")
        return 1

    def set_power(self, p_dbm: float) -> str:
        self.scpi.write(f"SOUR1:POW {p_dbm}")
        return 1

    def set_atten(self, atten: float, port: int = output_port) -> str:
        atten_round = 5 * round(atten/5)
        if atten_round > 35: atten_round=35
        if atten_round < 0: atten_round=0
        self.scpi.write(f"POW:ATT {port}, {atten_round}")
        return 1

    # ---- Sweep control ----
    def sweep_single(self, channel=1) -> str:
        self.set_continuous(on=False)
        self.scpi.write(f"INIT{channel}:IMM; *WAI")
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

    def set_trace(self, name: str = "S11", tracename: str = "Trc1", channel: int = 1) -> str:
        # Ensure a trace exists and is selected
        self.scpi.write(f"CALC{channel}:PAR:SDEF '{tracename}', '{name}'")
        return 1

    def select_trace(self, tracename, channel = 1):
        self.scpi.write(f"CALC{channel}:PAR:SEL '{tracename}'")
        return 1

    def set_format_logmag(self) -> str:
        self.scpi.write("CALC1:FORM MLOG")
        return 1

    # ---- Data acquisition ----
    def fetch_fdata(self) -> dict:
        """Formatted data (e.g., magnitude in current format). Returns CSV-like string."""
        data_str = self.scpi.query("CALC1:DATA? FDATA")
        nums = [float(x.strip()) for x in data_str.split(',') if x.strip()]

        return {"data": nums, "csv": data_str}

    def fetch_cmd_complex(self, cmd) -> dict:
        """Formatted data (e.g., magnitude in current format). Returns CSV-like string."""
        data_str = self.scpi.query(cmd)
        nums = [float(x.strip()) for x in data_str.split(',') if x.strip()]
        
        # Separate real and imaginary parts
        real = nums[0::2]   # even indices
        imag = nums[1::2]   # odd indices

        return {"real": real, "imag": imag, "csv": data_str}


    def fetch_sdata(self, channel=1) -> str:
        """Complex S-parameter data (real,imag pairs). Returns CSV-like string."""
        # Split by commas and strip whitespace
        data_str = self.scpi.query(f"CALC{channel}:DATA? SDATA")
        nums = [float(x.strip()) for x in data_str.split(',') if x.strip()]
        
        # Separate real and imaginary parts
        real = nums[0::2]   # even indices
        imag = nums[1::2]   # odd indices

        return {"real": real, "imag": imag, "csv": data_str}

    def read_x_axis(self) -> str:
        """Return stimulus axis for channel 1."""
        if self.scpi.query("SWE:TYPE?") == "POW":
            return {'type': 'pow',
                'x_data': [float(x.strip()) for x in self.scpi.query(f"CALC{self.channel}:DATA:STIM?").split(',') if x.strip()]}
        else:
            return {'type': 'frequency',
                'x_data': [float(x.strip()) for x in self.scpi.query(f"CALC{self.channel}:DATA:STIM?").split(',') if x.strip()]}


    # ---- Convenience measurement ----
    def measure_trace(self, tracename, timeout_s=15) -> Dict[str, Any]:
        self.select_trace(tracename)
        self.sweep_single()
        self.scpi.query("*OPC?", timeout_s=timeout_s) 
        y = self.fetch_fdata()
        x = self.read_x_axis()
        self.set_continuous(on=True)
        return {"x_axis": x, "trace": y}

    def measure_trace_ydata(self, tracename, timeout_s=5) -> Dict[str, Any]:
        self.select_trace(tracename)
        self.sweep_single()
        self.scpi.query("*OPC?", timeout_s=timeout_s) 
        y = self.fetch_fdata()
        self.set_continuous(on=True)
        return y

    def measure_trace_ydata_complex(self, tracename, channel=1,timeout_s=5) -> Dict[str, Any]:
        self.select_trace(tracename, channel)
        self.sweep_single(channel = channel)
        self.scpi.query("*OPC?", timeout_s=timeout_s) 
        y = self.fetch_sdata(channel = channel)
        self.set_continuous(on=True)
        return y

    def capture_point(self) -> Dict[str, Any]:
        return {'x': self.read_x_axis(),
                'a1': self.measure_trace_ydata_complex('Trca1'), 
                'b1': self.measure_trace_ydata_complex('Trcb1'), 
                'a2': self.measure_trace_ydata_complex('Trca2'), 
                'b2': self.measure_trace_ydata_complex('Trcb2')}
    
    def init_channel(self, channel:int = 1):
        self.scpi.write(f":CONF:CHAN{channel}:STAT ON")
        self.clear_syserror()

    def init_vector_receiver(self, window:int = 2):
        
        # write to zva example: CALCulate1:PARameter:DEFine 'Trc3', 'A1D1'
        # manual has how to do external generator also. I am pretty sure these are returned as voltages but that needs to be confirmed

        self.scpi.write(f"C:SENSe1:CORRection:EWAVe:STATe ON")
        self.scpi.write(f"CALC{self.channel}:PAR:SDEF 'Trca1', 'A{self.input_port}D{self.input_port}'")
        self.scpi.write(f"CALC{self.channel}:PAR:SDEF 'Trca2', 'A{self.output_port}D{self.input_port}'")
        self.scpi.write(f"CALC{self.channel}:PAR:SDEF 'Trcb1', 'B{self.input_port}D{self.input_port}'")
        self.scpi.write(f"CALC{self.channel}:PAR:SDEF 'Trcb2', 'B{self.output_port}D{self.input_port}'")
        self.scpi.write(f"DISP:WIND{window}:STAT OFF")
        self.clear_syserror()
        self.scpi.write(f"DISP:WIND{window}:STAT ON")
        self.scpi.write(f"DISP:WIND{window}:TRAC1:FEED 'Trca1'")
        self.scpi.write(f"DISP:WIND{window}:TRAC2:FEED 'Trca2'")
        self.scpi.write(f"DISP:WIND{window}:TRAC3:FEED 'Trcb1'")
        self.scpi.write(f"DISP:WIND{window}:TRAC4:FEED 'Trcb2'")

    def get_error_terms(self, filename) -> Dict[str, Any]:
        self.set_cal_file(filename) 
        timeout_ms = self.scpi.t.timeout_ms
        self.scpi.t.timeout_ms = timeout_ms*10
        directivitytemp = self.fetch_cmd_complex(f"CORR:CDAT? 'DIRECTIVITY',{self.input_port},0")
        self.set_points(int(len(directivitytemp["imag"])))
        out =  {'freq_hz': self.read_x_axis(),
            'directivity_input': directivitytemp,
            'srcmatch_input': self.fetch_cmd_complex(f"CORR:CDAT? 'SRCMATCH',{self.input_port},0"),
            'refltrack_input': self.fetch_cmd_complex(f"CORR:CDAT? 'REFLTRACK',{self.input_port},0"),
            'loadmatch_input': self.fetch_cmd_complex(f"CORR:CDAT? 'LOADMATCH',{self.input_port},{self.output_port}"),
            'transtrack_input2output': self.fetch_cmd_complex(f"CORR:CDAT? 'TRANSTRACK',{self.input_port},{self.output_port}"),
            'directivity_output': self.fetch_cmd_complex(f"CORR:CDAT? 'DIRECTIVITY',{self.output_port},0"),
            'srcmatch_output': self.fetch_cmd_complex(f"CORR:CDAT? 'SRCMATCH',{self.output_port},0"),
            'refltrack_output': self.fetch_cmd_complex(f"CORR:CDAT? 'REFLTRACK',{self.output_port},0"),
            'loadmatch_output': self.fetch_cmd_complex(f"CORR:CDAT? 'LOADMATCH',{self.output_port},{self.input_port}"),
            'transtrack_output2input': self.fetch_cmd_complex(f"CORR:CDAT? 'TRANSTRACK',{self.output_port},{self.input_port}")}
        self.scpi.t.timeout_ms = timeout_ms
        return out

    def set_cal_file(self, cal_filename, channel=1):
        try:
            # Load the calibration by file path
            self.scpi.write(f"MMEM:LOAD:CORR {channel},'{cal_filename}'")
            return True
        except Exception as e:
            # Surface instrument/SCPI errors with context
            raise RuntimeError(f"Failed to load calibration '{cal_filename}': {e}") from e

    def load_setup(self, filename, channel=1):
        try:
            # Load the calibration by file path
            savepath = 'C:\\Rohde&Schwarz\\Nwa\\RecallSets\\'	
            self.scpi.write(f"MMEM:CDIR '{savepath}'")
            self.scpi.write(f"MMEM:STOR:STAT {channel},'{filename}'")
            return True
        except Exception as e:
            # Surface instrument/SCPI errors with context
            raise RuntimeError(f"Failed to load setup '{cal_filename}': {e}") from e