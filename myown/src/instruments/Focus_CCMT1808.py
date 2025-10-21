from __future__ import annotations
import re, time, functools
from typing import Any, Dict, Optional
from .base import Instrument

def retry(n=3, delay=0.2, exc=(Exception,)):
    def deco(fn):
        @functools.wraps(fn)
        def wrap(*a, **k):
            last = None
            for _ in range(n):
                try: return fn(*a, **k)
                except exc as e: last = e; time.sleep(delay)
            raise last
        return wrap
    return deco

class FocusCCMT1808(Instrument):
    """
    Focus (CCMT) Ethernet tuner driver (non-SCPI).
    - Uses PyVISA SOCKET resource (e.g. TCPIP0::10.0.0.1::23::SOCKET).
    - Reads/writes strings with custom terminations.
    - Exposes high-level methods used by YAML sequences.
    Bench example:
      [visa]
      TUNER = {driver="FocusTuner",
               resource="TCPIP0::10.0.0.1::23::SOCKET",
               read_term="CCMT->", write_term="\\r\\n", timeout_ms=2000}
    """
    def __init__(self, *_: Any, **cfg: Any):
        # Ignore SCPI; open PyVISA resource directly from cfg
        import pyvisa
        resource = cfg.get("resource")
        if not resource:
            raise ValueError("FocusTuner requires 'resource' in bench config")
        read_term  = cfg.get("read_term", "CCMT->")
        write_term = cfg.get("write_term", "\r\n")
        timeout_ms = int(cfg.get("timeout_ms", 1000))

        rm = pyvisa.ResourceManager()
        self._inst = rm.open_resource(resource, open_timeout=3000)
        self._inst.read_termination = read_term
        self._inst.write_termination = write_term
        self._inst.timeout = timeout_ms
        self._inst.query_delay = float(cfg.get("query_delay_s", 0.2))

        self._axis_limits = (0, 0, 0)     # x, y_high, y_low
        self._step_size = 1.0
        self._cal = None
        self._connected = False

        # Best-effort init
        try:
            self._clearbuffer()
            self.preset()
            self.configure()  # populate limits/metadata
            self._connected = True
        except Exception:
            # Leave partially initialized; caller can inspect/close
            raise

    # -------- low-level helpers --------
    def _clearbuffer(self) -> None:
        try:
            _ = self._inst.read()
        except Exception:
            pass

    @retry(n=3, delay=0.1)
    def _write(self, cmd: str) -> None:
        self._inst.write(cmd)

    @retry(n=3, delay=0.2)
    def _query(self, cmd: str) -> str:
        return self._inst.query(cmd)

    def safe_off(self) -> None:
        try: self._inst.close()
        except Exception: pass

    # -------- public API (sequencer-facing) --------
    def preset(self) -> bool:
        """Clear/init session."""
        # CCMT uses INIT to handshake; *CLS/*RST not applicable
        self._clearbuffer()
        self._write("INIT")
        return True

    def idn(self) -> str:
        # No *IDN?; return CONFIG snippet as identity
        try:
            return self._query("CONFIG?")
        except Exception:
            return "Unkown Config."

    def configure(self) -> bool:
        """Query CONFIG? and cache tuner parameters (limits, step size, etc.)."""
        cfg = self._query("CONFIG?")
        # Parse with regexes following user’s legacy driver
        step = re.search(r"Step Size:\s*([\d.]+)", cfg)
        cross = re.search(r"CrossOver:([\d.]+)", cfg)
        # A1/A2/A3 lines → axis limits; order in legacy: x, y_low, y_high
        a1 = re.search(r"A1=(\d+)", cfg) or re.search(r"#1\t1\t(\d+)", cfg)
        a2 = re.search(r"A2=(\d+)", cfg) or re.search(r"#2\t2\t(\d+)", cfg)
        a3 = re.search(r"A3=(\d+)", cfg) or re.search(r"#3\t3\t(\d+)", cfg)
        x = int(a1.group(1)) if a1 else 0
        y_low = int(a2.group(1)) if a2 else 0
        y_high = int(a3.group(1)) if a3 else 0
        self._axis_limits = (x, y_high, y_low)
        self._step_size = float(step.group(1)) if step else 1.0
        self._crossover_mhz = float(cross.group(1)) if cross else None
        return True

    def load_cal_freq(self, freq_ghz: float) -> bool:
        """Load nearest cal by frequency (GHz)."""
        try:
            self._write(f"LOADFREQ {freq_ghz*1000:.6f}")
            self._cal = self._query("CALPOINT?")
            return True
        except Exception:
            # Optional: print calibration directory for debugging
            try: _ = self._query("DIR")
            except Exception: pass
            self._cal = None
            return False

    def load_cal_id(self, cal_id: int) -> bool:
        """Load a specific calibration ID."""
        try:
            self._write(f"LOADCAL {int(cal_id)}")
            self._cal = self._query("CALPOINT?")
            return True
        except Exception:
            try: _ = self._query("DIR")
            except Exception: pass
            self._cal = None
            return False

    def move_axis(self, axis: str, position: int) -> Dict[str, int]:
        """
        Move a given axis to an absolute position with limit/step checks.
        axis: 'x' | 'y_low' | 'y_high'
        """
        axis_lc = axis.lower()
        limits = {
            "x": self._axis_limits[0],
            "y_low": self._axis_limits[2],
            "y_high": self._axis_limits[1],
        }
        if axis_lc not in limits:
            raise ValueError(f"Unknown axis '{axis}'")
        if position < 0 or position > limits[axis_lc]:
            raise ValueError(f"{axis} exceeds limit {limits[axis_lc]}")

        # Skip tiny moves
        cur = self.pos()
        cur_map = {"x": cur["x"], "y_low": cur["y_low"], "y_high": cur["y_high"]}
        if abs(cur_map[axis_lc] - int(position)) < self._step_size:
            return cur

        self._query(f"POS {axis_lc} {int(position)}")  # POS echoes result
        return self.pos()

    def status(self) -> int:
        """Return numeric status code (0 = ready)."""
        ret = self._query("STATUS?")
        # Example substring per legacy: 'STATUS:... Result=0x0000 ...'
        m = re.search(r"Result=0x000(\d+)", ret)
        return int(m.group(1)) if m else 1

    def pos(self) -> Dict[str, int]:
        """Return current positions: {'x':..., 'y_low':..., 'y_high':...}."""
        ret = self._query("POS?")
        # Accept both legacy formats: "A1=123 A2=456 A3=789" or tabbed lines
        a1 = re.search(r"A1=(\d+)", ret) or re.search(r"#1\t1\t(\d+)", ret)
        a2 = re.search(r"A2=(\d+)", ret) or re.search(r"#2\t2\t(\d+)", ret)
        a3 = re.search(r"A3=(\d+)", ret) or re.search(r"#3\t3\t(\d+)", ret)
        x = int(a1.group(1)) if a1 else 0
        y_low = int(a2.group(1)) if a2 else 0
        y_high = int(a3.group(1)) if a3 else 0
        return {"x": x, "y_low": y_low, "y_high": y_high}

    def wait_ready(self, timeout_s: float = 10.0, poll_s: float = 0.25) -> int:
        """Poll STATUS? until 0 or timeout; returns final status."""
        t0 = time.time()
        code = self.status()
        while (time.time() - t0) < timeout_s and code != 0:
            time.sleep(poll_s)
            # best-effort clearbuffer to keep stream clean
            try: self._clearbuffer()
            except Exception: pass
            code = self.status()
        return code

    # Optional convenience: impedance move via reflection coeff Γ
    def move_impedance(self, z_real: float, z_imag: float, z0: float = 50.0) -> bool:
        if self._cal is None:
            return False
        # Γ = (Z - Z0)/(Z + Z0)
        Z = complex(z_real, z_imag)
        G = (Z - z0) / (Z + z0)
        mag = abs(G)
        ang = (180.0 / 3.141592653589793) * (complex(G).phase if hasattr(G, "phase") else (re or 0.0))
        # numpy.angle would be nicer; avoid hard dep here—send string
        # If numpy available, use: ang = float(__import__("numpy").angle(G, deg=True))
        try:
            import numpy as _np
            ang = float(_np.angle(G, deg=True))
        except Exception:
            # crude fallback using cmath
            import cmath as _cm
            ang = float(_cm.phase(G) * 180.0 / 3.141592653589793)
        self._write(f"TUNETO {mag} {ang}")
        return True

    def close(self) -> None:
        try: self._inst.close()
        finally: self._connected = False
