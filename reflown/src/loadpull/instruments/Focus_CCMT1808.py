from __future__ import annotations
import re, time, functools
from typing import Any, Dict, Optional
import numpy as np
from .base import Instrument

import numpy as np
from cmath import polar
import math

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
        self._crossover_mhz: Optional[float] = None
        self._sn: Optional[str] = None
        self._last_config: Optional[Dict[str, Any]] = None
        self._cal = None
        self._connected = False
        self._tuner_cal: Optional["TunerCal"] = None  # optional preloaded tuner calibration

        # Optionally preload a tuner calibration from bench config
        try:
            cal_path = cfg.get("tuner_cal_path") or cfg.get("tuner_calfile")
            if cal_path:
                from ..core.tunercal import TunerCal as _TunerCal
                self._tuner_cal = _TunerCal.from_txt(str(cal_path))
        except Exception:
            # Ignore preload errors; user can set later
            self._tuner_cal = None

        # Best-effort init
        try:
            self._clearbuffer()
            self.preset()
            self.config_info()  # populate limits/metadata
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
        self.wait_ready(timeout_s = 60)
        self._clearbuffer()
        return True

    def idn(self) -> str:
        # No *IDN?; return CONFIG snippet as identity
        try:
            return self._query("CONFIG?")
        except Exception:
            return "Unkown Config."

    def move_axis(self, axis: str, position: int) -> Dict[str, int]:
        """
        Move a given axis to an absolute position with limit/step checks.
        axis: 'x' | 'y_low' | 'y_high'

        Limits are derived from config_info axis mapping: 1->x, 2->y_low, 3->y_high.
        Falls back to cached tuple self._axis_limits if config not available.
        """
        axis_lc = axis.lower()
        # Try to use latest parsed config limits
        try:
            axmap = self._axis_limits or {}
            derived_limits = {
                "x": int(axmap.get(1, 0)),
                "y_low": int(axmap.get(2, 0)),
                "y_high": int(axmap.get(3, 0)),
            }
        except Exception:
            raise
        if axis_lc not in derived_limits:
            raise ValueError(f"Unknown axis '{axis}'")
        limit_val = int(derived_limits[axis_lc])
        if position < 0 or position > limit_val:
            raise ValueError(f"{axis} exceeds limit {limit_val}")

                # Skip tiny moves
        cur = self.pos()
        if abs(cur[axis_lc] - int(position)) < self._step_size:
            print("step too small. no movement")
            return cur

        # Use numeric axis IDs: 1=x, 2=y_low, 3=y_high
        axis_num = {"x": 1, "y_low": 2, "y_high": 3}[axis_lc]
        # print(f"POS {axis_num} {int(position)}")
        self._query(f"POS {axis_num} {int(position)}")  # POS echoes result
        return self.pos()


    def move_all(self, position: dict) -> Dict[str, int]:
        """Move multiple axes at once with limit and step-size checks.

        position: dict with any of keys {'x','y_low','y_high'} and integer targets.
        - Validates each provided axis against limits (if known)
        - Skips tiny moves smaller than self._step_size
        - Sends a single command: POS 1 <x> 2 <y_low> 3 <y_high>
        Returns updated positions.
        """
        # Current positions and limits
        cur = self.pos()
        try:
            axmap = self._axis_limits or {}
            limits = {"x": int(axmap.get(1, 0)), "y_low": int(axmap.get(2, 0)), "y_high": int(axmap.get(3, 0))}
        except Exception:
            limits = {"x": 0, "y_low": 0, "y_high": 0}

        # Initialize with current values
        to_send = {"x": int(cur.get("x", 0)), "y_low": int(cur.get("y_low", 0)), "y_high": int(cur.get("y_high", 0))}

        for name in ("x", "y_low", "y_high"):
            if name in position and position[name] is not None:
                target = int(position[name])
                limit = int(limits.get(name, 0))
                if limit and (target < 0 or target > limit):
                    raise ValueError(f"{name} exceeds limit {limit}")
                if abs(target - int(cur.get(name, 0))) >= self._step_size:
                    to_send[name] = target

        cmd = f"POS 1 {to_send['x']} 2 {to_send['y_low']} 3 {to_send['y_high']}"
        # print(breakhere)
        self._query(cmd)
        # print(breakhere)
        return self.pos()

    def status(self) -> int:
        """Return numeric status code (0 = ready)."""
        ret = self._query("STATUS?")
        # Example substring per legacy: 'STATUS:... Result=0x0000 ...'
        m = re.search(r"STATUS: 0x(\d+)", ret)
        return int(m.group(1)) if m else 1

    def _parse_axis_limits_from_table(self, text: str) -> Dict[int, int]:
        """Parse any table that contains Axis and Limit columns, independent of order.

        Returns {axis_number: limit}.
        """
        import re as _re
        lines = [ln.strip() for ln in text.splitlines() if ln is not None]
        # Identify a header that has both Axis and Limit
        header_idx = None
        header_keys = []
        def _norm(s: str) -> str:
            return _re.sub(r"[^a-z0-9]+", "", s.lower())
        for i, ln in enumerate(lines):
            if not ln:
                continue
            cols = _re.split(r"\s+", ln)
            keys = [_norm(c) for c in cols]
            if any(k.startswith("axis") for k in keys) and "limit" in keys:
                header_idx = i
                header_keys = keys
                break
        if header_idx is None:
            return {}
        # Resolve indices
        def _find_idx(cands):
            for cand in cands:
                for j, k in enumerate(header_keys):
                    if k == cand:
                        return j
            return None
        axis_idx = _find_idx(["axis", "axisno", "axisnumber"])
        limit_idx = _find_idx(["limit"])
        if axis_idx is None or limit_idx is None:
            return {}
        # Parse rows beneath header
        out: Dict[int, int] = {}
        for ln in lines[header_idx + 1:]:
            if not ln:
                continue
            cols = _re.split(r"\s+", ln)
            if len(cols) <= max(axis_idx, limit_idx):
                continue
            m = _re.search(r"#?(\d+)", cols[axis_idx])
            if not m:
                continue
            ax = int(m.group(1))
            m2 = _re.match(r"(\d+)", cols[limit_idx])
            if not m2:
                continue
            out[ax] = int(m2.group(1))
        return out

    def config_info(self) -> Dict[str, Any]:
        """Return parsed config info: serial, step size (um), crossover (MHz), axis limits.

        Handles multiple firmware formats:
        - Case 1: "Step Size = 25.40 um/step", mixed-case 'CrossOver' embedded in Fmin/Fmax line,
                  and multi-column Axis table with 'Limit' column.
        - Case 2: "Step Size: 12.70 um/step", and compact Axis/Limit table.
        """
        cfg = self._query("CONFIG?")
        # Serial number
        m_sn = re.search(r"SN#\s*:?\s*([\w-]+)", cfg, re.IGNORECASE)
        sn = m_sn.group(1) if m_sn else None
        # Step size (micrometers per step)
        m_step = re.search(r"Step\s*Size\s*[:=]\s*([\d.]+)", cfg, re.IGNORECASE)
        step_um = float(m_step.group(1)) if m_step else 1.0
        # Crossover frequency in MHz (appears on Fmin/Fmax line)
        m_cross = re.search(r"CrossOver\s*:?\s*([\d.]+)\s*MHz", cfg, re.IGNORECASE)
        crossover_mhz = float(m_cross.group(1)) if m_cross else None
        # Axis limits via header-driven table parsing
        axis_limits = self._parse_axis_limits_from_table(cfg)
        info = {
            "sn": sn,
            "step_um": step_um,
            "crossover_mhz": crossover_mhz,
            "axis_limits": axis_limits,
        }
        # Cache for later and update core fields for convenience
        self._last_config = info
        self._sn = sn
        self._crossover_mhz = crossover_mhz
        self._step_size = step_um
        self._axis_limits = axis_limits
        return info

    def pos(self) -> Dict[str, int]:
        """Return current positions: {'x':..., 'y_low':..., 'y_high':...}."""
        self.wait_ready()

        ret = self._query("POS?")
        # Accept both legacy formats: "A1=123 A2=456 A3=789" or tabbed lines
        a1 = re.search(r"A1=(\d+)", ret) or re.search(r"#1\t1\t(\d+)", ret)
        a2 = re.search(r"A2=(\d+)", ret) or re.search(r"#2\t2\t(\d+)", ret)
        a3 = re.search(r"A3=(\d+)", ret) or re.search(r"#3\t3\t(\d+)", ret)
        x = int(a1.group(1)) if a1 else 0
        y_low = int(a2.group(1)) if a2 else 0
        y_high = int(a3.group(1)) if a3 else 0
        return {"x": x, "y_low": y_low, "y_high": y_high}

    def wait_ready(self, timeout_s: float = 30.0, poll_s: float = 0.25) -> int:
        """Poll STATUS? until 0 or timeout; returns final status."""
        t0 = time.time()
        code = self.status()
        while (time.time() - t0) < timeout_s and code != 0:
            time.sleep(poll_s)
            # best-effort clearbuffer to keep stream clean
            try: self._clearbuffer()
            except Exception: pass
            code = self.status()
        if (time.time() - t0) > timeout_s:
            print(f"Status: {code} took too long and failed to wait")
        return code

    # ---- Cal-assisted lookup helpers ----
    def set_tuner_cal_from_file(self, path: str) -> bool:
        """Load and cache a tuner calibration TXT file for later lookups."""
        try:
            from ..core.tunercal import TunerCal as _TunerCal
            self._tuner_cal = _TunerCal.from_txt(path)
            return True
        except Exception:
            self._tuner_cal = None
            return False

    def set_tuner_cal(self, cal: "TunerCal") -> None:
        """Inject an already-parsed TunerCal instance."""
        self._tuner_cal = cal

    def _y_axis_for_freq(self, freq_ghz: float) -> str:
        """Choose Y axis by crossover: below -> y_low, above/equal -> y_high.

        Falls back to y_low if crossover is unknown.
        """
        try:
            cross_mhz = float(self._crossover_mhz) if self._crossover_mhz is not None else None
        except Exception:
            cross_mhz = None
        if cross_mhz is None:
            return 'y_low'
        return 'y_low' if (freq_ghz * 1000.0) < cross_mhz else 'y_high'
        
    def positions_for_s11(self, freq_ghz: float, gamma_mag: float, gamma_deg: float, z0: float = 50.0) -> Dict[str, int]:
        """Look up nearest axis positions for a target S11 from a tuner cal text file.

        Returns a dict like {"x": int, "y_low": int, "y_high": int or 0}.
        For 2-axis cals, maps file "Y pos" to the active Y axis per crossover and sets the other to 0.
        """

        if self._tuner_cal is None:
            raise ValueError("No tuner calibration available. Provide cal_path or preload with set_tuner_cal().")
        g = complex(gamma_mag * math.cos(math.radians(gamma_deg)), gamma_mag * math.sin(math.radians(gamma_deg)))
        best, _, _ =  self._tuner_cal.nearest(freq_ghz, g)
        y_axis = self._y_axis_for_freq(freq_ghz)
        y_low = int(best.y or 0) if y_axis == 'y_low' else 0
        y_high = int(best.y or 0) if y_axis == 'y_high' else 0
        # print(breakhere)
        return {"x": int(best.x), "y_low": y_low, "y_high": y_high}

    def set_impedance(self, freq_ghz: float, z_real: float, z_imag: float, z0:float = 50) -> Dict[str, int]:
        """Move axes to the nearest cal positions for the requested S11.

        Uses positions_for_s11() and issues POS moves for available axes.
        """
        gamma_mag, gamma_rad = polar((complex(z_real,z_imag) - z0) / (complex(z_real,z_imag) + z0))
        pos = self.set_gamma(freq_ghz, gamma_mag, gamma_rad*57.2957795130) #180/pi

    def set_gamma(self, freq_ghz: float, gamma_mag: float, gamma_deg: float) -> Dict[str, int]:
        """Move axes to the nearest cal positions for the requested S11.

        Uses positions_for_s11() and issues POS moves for available axes.
        """
        pos = self.positions_for_s11(freq_ghz, gamma_mag, gamma_deg) #180/pi

        self.move_all(pos)
        # try:
        #     self.move_all(pos)
        # except Exception:
        #     pass
        return self.pos()

    def close(self) -> None:
        try: self._inst.close()
        finally: self._connected = False
