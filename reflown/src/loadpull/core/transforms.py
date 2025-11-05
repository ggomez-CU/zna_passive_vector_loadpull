from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

import cmath
import math
import numpy as np
import skrf

TransformFunc = Callable[[dict, dict], dict]


class TransformRegistry:
    """Registry for measurement post-processing callbacks."""

    def __init__(self) -> None:
        self._transforms: Dict[str, TransformFunc] = {}

    def register(self, method: str, func: TransformFunc) -> None:
        self._transforms[method] = func

    def get(self, method: str) -> TransformFunc | None:
        return self._transforms.get(method)

    def apply(self, method: str, payload: dict, cal_cache: dict) -> dict:
        func = self.get(method)
        if not func:
            return payload
        return func(payload, cal_cache)


def default_registry() -> TransformRegistry:
    registry = TransformRegistry()

    def apply_power(payload: dict, cal: dict) -> dict:
        if "power" in payload:
            # payload = dict(payload)
            # payload["power_corr"] = payload["power"] - cal.get("power_offset", 0.0)
            return {"power_corr": payload["power"] - cal.get("power_offset", 0.0)}
        return {}

    registry.register("read_power", apply_power)

    def output_b2probe2_coupling(payload: dict, _cal: dict) -> dict:
        dut_terms = payload.get("DUT_calfile")
        pm_terms = payload.get("PM_calfile")
        pm_power = payload.get("PM_power")
        pm_s1p_ref = payload.get("PM_s1p")
        wave_values = payload.get("wave_values")

        pm_network: Optional[skrf.Network] = None
        pm_s1p_path: Optional[Path] = None
        if pm_s1p_ref:
            pm_s1p_path = Path(str(pm_s1p_ref)).expanduser().resolve()
            if not pm_s1p_path.exists():
                raise FileNotFoundError(f"PM S1P file not found: {pm_s1p_path}")
            pm_network = skrf.Network(str(pm_s1p_path))

        return _power_correction_cal(
            dut_terms=dut_terms,
            pm_terms=pm_terms,
            pm_power=pm_power,
            pm_network=pm_network,
            pm_s1p_path=pm_s1p_path,
            wave_values=wave_values,
        )

    registry.register("output_b2probe2_coupling", output_b2probe2_coupling)

    def z2gamma(payload: dict, _cal: dict) -> dict:
        import numpy as np
        z0 = float(payload.get("z0", 50.0))
        real = payload.get("real")
        imag = payload.get("imag")
        if real is None or imag is None:
            return {}

        r = np.asarray(real, dtype=float)
        i = np.asarray(imag, dtype=float)

        # Broadcast if one side is scalar
        if r.shape != i.shape:
            if r.size == 1:
                r = np.full_like(i, r.item(), dtype=float)
            elif i.size == 1:
                i = np.full_like(r, i.item(), dtype=float)
            else:
                return {}  # shape mismatch

        z = r + 1j * i
        gamma = (z - z0) / (z + z0)  # if you mean Z→Γ; else use z for polar of Z
        mag = np.abs(gamma)
        ang = np.angle(gamma)  # radians

        if mag.size == 1:
            return {"angle_rad": float(ang.ravel()[0]), "mag": float(mag.ravel()[0])}
        return {"angle_rad": ang.tolist(), "mag": mag.tolist()}

    registry.register("z2gamma", z2gamma)

    def set_plot_gamma(payload: dict, _cal: dict) -> dict:
        if "mag" in payload and "rad" in payload:
            return {"angle_rad": payload["rad"],
                "mag": payload["mag"]} 
        if "mag" in payload and "deg" in payload:
            return {"angle_rad": np.deg2rad(payload["deg"]).tolist(),
                "mag": payload["mag"]} 
        if "real" in payload and "imag" in payload:
            real = payload.get("real")
            imag = payload.get("imag")
            r = np.asarray(real, dtype=float)
            i = np.asarray(imag, dtype=float)
            return {"angle_rad": np.angle(complex(r,i)).tolist(),
                "mag": np.abs(complex(r,i)).tolist()} 
        return {}

    registry.register("set_plot_gamma", set_plot_gamma)

    # Running standard deviation (Welford) utilities
    def running_std_update(payload: dict, _cal: dict) -> dict:
        """Update running mean/M2 given a new scalar value.

        Expects payload like {"value": <number>, "state": {"count": n, "mean": m, "m2": M2}}
        Returns a state dict {"count", "mean", "m2"}.
        """
        x_raw = payload.get("value")
        try:
            x = float(x_raw)
        except (TypeError, ValueError):
            # Return previous state unchanged if value invalid
            return payload.get("state") or {"count": 0, "mean": 0.0, "m2": 0.0}

        state = payload.get("state") or {}
        try:
            n = int(state.get("count", 0))
        except Exception:
            n = 0
        mean = float(state.get("mean", 0.0) or 0.0)
        m2 = float(state.get("m2", 0.0) or 0.0)

        n += 1
        delta = x - mean
        mean += delta / n
        delta2 = x - mean
        m2 += delta * delta2
        return {"count": n, "mean": mean, "m2": m2}

    registry.register("running_std_update", running_std_update)

    def running_std_finalize(payload: dict, _cal: dict) -> dict:
        """Compute sample std (ddof=1) from running state.

        Expects payload like {"state": {"count": n, "m2": M2}}.
        Returns {"std": float, "count": n}.
        """
        state = payload.get("state") or {}
        try:
            n = int(state.get("count", 0))
        except Exception:
            n = 0
        m2 = float(state.get("m2", 0.0) or 0.0)
        std = float(np.sqrt(m2 / (n - 1))) if n > 1 else 0.0
        return {"std": std, "count": n}

    registry.register("running_std_finalize", running_std_finalize)

    # Load sweep helpers (CSV)
    import csv as _csv
    def _read_sweep_points(path: str) -> list[tuple[float, float]]:
        rows: list[tuple[float, float]] = []
        with open(path, 'r', encoding='utf-8') as fp:
            r = _csv.DictReader(fp)
            # Expect columns: mag, deg, real, imag (we only need mag/deg)
            for rec in r:
                try:
                    mag = float(rec.get('mag'))
                    deg = float(rec.get('deg'))
                except Exception:
                    continue
                rows.append((mag, deg))
        return rows

    def load_sweep_len(payload: dict, _cal: dict) -> dict:
        path = payload.get('file') or payload.get('path')
        pts = _read_sweep_points(str(path))
        # Expose count as to-index for simple 0..count-1 sweeps
        return {"count": max(0, len(pts) - 1)}

    def load_sweep_point(payload: dict, _cal: dict) -> dict:
        path = payload.get('file') or payload.get('path')
        idx_raw = payload.get('index')
        try:
            idx = int(idx_raw)
        except Exception:
            return {}
        pts = _read_sweep_points(str(path))
        if idx < 0 or idx >= len(pts):
            return {}
        mag, deg = pts[idx]
        return {"gamma_mag": mag, "gamma_deg": deg}

    registry.register("load_sweep_len", load_sweep_len)
    registry.register("load_sweep_point", load_sweep_point)

    def gamma_from_corrwave(payload: dict, cal: dict) -> dict:
        b1_keys, a1_keys, b2_keys, a2_keys = ['b1', 'B1'], ['a1', 'A1'], ['b2', 'B2'], ['a2', 'A2']
        wv = payload.get("wave_data") or payload
        
        b1_arr = _extract_array_field(wv, b1_keys, dtype=complex)
        a1_arr = _extract_array_field(wv, a1_keys, dtype=complex)
        b2_arr = _extract_array_field(wv, b2_keys, dtype=complex)
        a2_arr = _extract_array_field(wv, a2_keys, dtype=complex)
        if b1_arr is None or a1_arr is None or b2_arr is None or a2_arr is None:
            return {}

        b1 = np.asarray(b1_arr, dtype=complex).ravel()
        a1 = np.asarray(a1_arr, dtype=complex).ravel()
        b2 = np.asarray(b2_arr, dtype=complex).ravel()
        a2 = np.asarray(a2_arr, dtype=complex).ravel()

        with np.errstate(divide="ignore", invalid="ignore"):
            gamma_source = (b1 / a1) 
        
        with np.errstate(divide="ignore", invalid="ignore"):
            gamma_load = (a2 / b2)

        return {
            "gamma_L": {
                "real": float(gamma_load.real),
                "imag": float(gamma_load.imag),
                "mag": float(np.abs(gamma_load)),
                "angle_rad": float(np.angle(gamma_load)),
            },
            "gamma_S": {
                "real": float(gamma_source.real),
                "imag": float(gamma_source.imag),
                "mag": float(np.abs(gamma_source)),
                "angle_rad": float(np.angle(gamma_source)),
            },
        }

    registry.register("gamma_from_corrwave", gamma_from_corrwave)


    return registry

def _power_correction_cal(*, dut_terms: Any, pm_terms: Any, pm_power: Any, pm_network: Optional[skrf.Network],pm_s1p_path: Optional[Path], wave_values: Any) -> dict:
    """Compute coupling factor using probe-term calibrations and measurements."""

    if pm_network is None:
        return {}

    wave_freq = _extract_frequency_vector(wave_values)
    network_freq = pm_network.f

    if wave_freq is not None and not _frequencies_overlap(wave_freq, network_freq):
        return {}

    gamma_pm = pm_network.s[:, 0, 0]
    freqs = []
    pm_power_linear = []
    for freq, data in sorted(pm_power.items()):
        if isinstance(data, dict) and "dBm" in data:
            freqs.append(freq)
            pm_power_linear.append(float(data["dBm"]))

    b2_values = _extract_array_field(wave_values, ["b2", "B2"], dtype=complex)
    es2_values = _extract_array_field(dut_terms, ["srcmatch_output", "Es2", "es2"], dtype=complex)

    result: Dict[str, Any] = {
        "dut_terms": dut_terms,
        "pm_terms": pm_terms,
        "pm_power": pm_power,
        "pm_s1p_path": str(pm_s1p_path) if pm_s1p_path else None,
        "pm_s1p_freq_hz": network_freq.tolist(),
        "pm_s1p_s": pm_network.s.tolist(),
        "wave_values": wave_values,
    }

    if pm_power_linear is None or b2_values is None or es2_values is None:
        result["C10_2"] = None
        return result

    gamma_pm = np.asarray(gamma_pm, dtype=complex)
    b2_values = _align_array_length(b2_values, gamma_pm.size)
    es2_values = _align_array_length(es2_values, gamma_pm.size)

    if b2_values is None or es2_values is None:
        result["C10_2"] = None
        return result

    numerator = pm_power_linear * np.abs(1.0 - es2_values * gamma_pm) ** 2
    denominator = (np.abs(b2_values) ** 2) * (1.0 - np.abs(gamma_pm) ** 2)

    with np.errstate(divide="ignore", invalid="ignore"):
        coupling = np.where(denominator != 0, numerator / denominator, np.nan)

    result["C10_2"] = coupling.tolist()
    result["pm_power_linear"] = pm_power_linear
    result["gamma_pm"] = gamma_pm.tolist()
    result["b2"] = b2_values.tolist()
    result["Es2"] = es2_values.tolist()

    return result


def _extract_frequency_vector(source: Any) -> Optional[np.ndarray]:
    """Best-effort extraction of a frequency vector."""
    if source is None:
        return None
    if isinstance(source, dict):
        # Nested axis specs with x_data
        for key in ("x", "x_axis", "freq", "frequency"):
            val = source.get(key)
            if isinstance(val, dict) and "x_data" in val:
                try:
                    return np.asarray(val.get("x_data"), dtype=float)
                except Exception:
                    return None
            if isinstance(val, (list, tuple)):
                try:
                    return np.asarray(val, dtype=float)
                except Exception:
                    return None
        # Direct x_data
        if "x_data" in source:
            try:
                return np.asarray(source["x_data"], dtype=float)
            except Exception:
                return None
        # Explicit arrays under common keys
        for key in ("freq_hz", "frequency_hz", "freq", "frequency"):
            if key in source:
                try:
                    return np.asarray(source[key], dtype=float)
                except Exception:
                    return None
        return None
    if isinstance(source, (list, tuple)):
        try:
            return np.asarray(source, dtype=float)
        except Exception:
            return None
    if isinstance(source, np.ndarray):
        return source.astype(float, copy=False)
    return None


def _frequencies_overlap(a: np.ndarray, b: Iterable[float], tol: float = 1e-3) -> bool:
    """Return True if all frequencies in ``a`` are present in ``b`` within ``tol``."""
    if a.size == 0:
        return True
    b_array = np.asarray(list(b), dtype=float)
    if b_array.size == 0:
        return False
    return all(np.any(np.isclose(val, b_array, rtol=0, atol=tol)) for val in a)


def _extract_scalar(source: Any, keys: Iterable[str]) -> Optional[float]:
    """Attempt to extract a scalar numeric value from assorted representations."""
    if source is None:
        return None
    if isinstance(source, (int, float, complex, np.number)):
        return float(source)
    if isinstance(source, str):
        try:
            return float(source)
        except ValueError:
            return None
    if isinstance(source, dict):
        for key in keys:
            if key in source:
                value = source[key]
                if value is source:
                    continue
                return _extract_scalar(value, keys)
        return None
    for key in keys:
        if hasattr(source, key):
            attr = getattr(source, key)
            if callable(attr):
                try:
                    attr = attr()
                except Exception:
                    return None
            if attr is source:
                continue
            return _extract_scalar(attr, keys)
    if isinstance(source, np.ndarray):
        if source.size == 0:
            return None
        return float(source.ravel()[0])
    return None


def _convert_dbm_to_linear(value_dbm: Optional[float]) -> Optional[float]:
    """Convert dBm to linear power in watts."""
    if value_dbm is None:
        return None
    return 10 ** ((value_dbm - 30.0) / 10.0)


def _extract_array_field(source: Any,keys: Iterable[str],*,dtype: Any = complex) -> Optional[np.ndarray]:
    """Extract an array-like field from dicts or objects."""
    
    if source is None:
        return None
    
    if isinstance(source, dict):
        for key in keys:
            if key in source:
                return _to_array(source[key], dtype=dtype)
        return None
    for key in keys:
        if hasattr(source, key):
            attr = getattr(source, key)
            if callable(attr):
                try:
                    attr = attr()
                except Exception:
                    return None
            return _to_array(attr, dtype=dtype)
    return _to_array(source, dtype=dtype)


def _to_array(value: Any, *, dtype: Any = complex) -> Optional[np.ndarray]:
    if value is None:
        return None
    # Support dicts with real/imag parts: {"real": [...], "imag": [...]} always
    
    if isinstance(value, dict):
        real = value.get("real")
        imag = value.get("imag")
        if real is not None and imag is not None:
            try:
                r = np.asarray(real, dtype=float)
                i = np.asarray(imag, dtype=float)
                # Attempt simple broadcasting of scalars; else require same shape
                if r.shape != i.shape:
                    if r.size == 1:
                        r = np.full_like(i, r.item(), dtype=float)
                    elif i.size == 1:
                        i = np.full_like(r, i.item(), dtype=float)
                    else:
                        return None
                arr = r + 1j * i
                return arr.astype(dtype, copy=False)
            except Exception:
                return None
    if isinstance(value, (int, float, complex, np.number)):
        return np.asarray([value], dtype=dtype)
    if isinstance(value, np.ndarray):
        if value.size == 0:
            return None
        return value.astype(dtype, copy=False)
    try:
        arr = np.asarray(value, dtype=dtype)
    except Exception:
        return None
    return arr


def _align_array_length(values: np.ndarray, target: int) -> Optional[np.ndarray]:
    """Broadcast or trim arrays to match desired length."""
    if values.size == target:
        return values
    if values.size == 1:
        return np.full(target, values.item(), dtype=values.dtype)
    return None
