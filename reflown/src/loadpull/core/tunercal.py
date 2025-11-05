from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
import math


@dataclass
class CalPoint:
    freq_ghz: float
    x: int
    y: Optional[int]
    gamma_mag: float
    gamma_deg: float

    @property
    def gamma_complex(self) -> complex:
        rad = math.radians(self.gamma_deg)
        return complex(self.gamma_mag * math.cos(rad), self.gamma_mag * math.sin(rad))


class TunerCal:
    """Lightweight parser/lookup for Focus tuner text exports.

    Supports files with header like:
      ! Probe    Frequency  Pt Number  X pos  Y pos  Gamma s11  Phi s11 ...

    and variants where only Axis/Limit tables exist are out of scope here.
    """

    def __init__(self, points: List[CalPoint]):
        self._points = points
        # index by frequency (GHz)
        self._by_freq: Dict[float, List[CalPoint]] = {}
        for p in points:
            self._by_freq.setdefault(p.freq_ghz, []).append(p)
        self._freqs = sorted(self._by_freq.keys())

    @staticmethod
    def from_txt(path: str | Path) -> "TunerCal":
        p = Path(path)
        rows: List[CalPoint] = []
        if not p.exists():
            raise FileNotFoundError(f"Tuner cal file not found: {p}")
        for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("!"):
                continue
            parts = [tok for tok in line.split("\t") if tok != ""]
            # Expect at least: Probe, Frequency, Pt, X pos, Y pos, Gamma s11, Phi s11
            if len(parts) < 8:
                continue
            try:
                freq_ghz = float(parts[1])
                x = int(float(parts[3]))
                y = int(float(parts[4]))
                gm = float(parts[5])
                gd = float(parts[6])
            except Exception:
                continue
            rows.append(CalPoint(freq_ghz=freq_ghz, x=x, y=y, gamma_mag=gm, gamma_deg=gd))
        if not rows:
            raise ValueError(f"No calibration rows parsed from {p}")
        return TunerCal(rows)

    def nearest(self, freq_ghz: float, gamma: complex, freq_tolerance_ghz: float | None = None) -> Tuple[CalPoint, float, float]:
        """Return the nearest cal point to target gamma at the closest frequency.

        - Picks the exact frequency bin if present; else the closest available frequency.
        - freq_tolerance_ghz: if provided, raises if the nearest frequency exceeds this delta.
        Returns (CalPoint, freq_delta, gamma_distance).
        """
        if not self._freqs:
            raise ValueError("Calibration has no frequency bins")
        # find nearest frequency
        nearest_f = min(self._freqs, key=lambda f: abs(f - freq_ghz))
        df = abs(nearest_f - freq_ghz)
        if freq_tolerance_ghz is not None and df > freq_tolerance_ghz:
            raise ValueError(f"No cal near {freq_ghz} GHz (nearest {nearest_f} GHz, Δ={df} GHz)")
        candidates = self._by_freq[nearest_f]
        def dist(pt: CalPoint) -> float:
            g = pt.gamma_complex
            return abs(g - gamma)
        best = min(candidates, key=dist)
        return best, df, dist(best)