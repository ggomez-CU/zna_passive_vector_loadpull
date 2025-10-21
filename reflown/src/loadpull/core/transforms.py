from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

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
            payload = dict(payload)
            payload["power_corr"] = payload["power"] - cal.get("power_offset", 0.0)
        return payload

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

    return registry

def _power_correction_cal(
    *,
    dut_terms: Any,
    pm_terms: Any,
    pm_power: Any, 
    pm_network: Optional[skrf.Network],
    pm_s1p_path: Optional[Path],
    wave_values: Any,
) -> dict:
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
    """Best-effort extraction of a frequency vector from arbitrary inputs."""
    if source is None:
        return None
    if isinstance(source, dict):
        freq = source.get("freq") or source.get("frequency")
        if freq is None:
            return None
        return np.asarray(freq, dtype=float)
    if isinstance(source, (list, tuple)):
        return np.asarray(source, dtype=float)
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


def _extract_array_field(
    source: Any,
    keys: Iterable[str],
    *,
    dtype: Any = complex,
) -> Optional[np.ndarray]:
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
