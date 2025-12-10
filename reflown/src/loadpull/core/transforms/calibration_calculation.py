from __future__ import annotations

from pathlib import Path
from typing import Optional

import skrf
import numpy as np

from .registry import TransformRegistry
from .utils import _power_correction_cal, _to_array, _extract_frequency_vector, _convert_dbm_to_linear


def register_calibration_calculation_transforms(registry: TransformRegistry) -> None:

    def cal_std_update(payload: dict, _cal: dict) -> dict:
        """Update running mean/M2 given a new scalar value."""
        x_raw = payload.get("value")
        try:
            x = float(x_raw)
        except (TypeError, ValueError):
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

    registry.register("cal_std_update", cal_std_update)

    def cal_std_finalize(payload: dict, _cal: dict) -> dict:
        """Compute sample std (ddof=1) from running state."""
        state = payload.get("state") or {}
        try:
            n = int(state.get("count", 0))
        except Exception:
            n = 0
        m2 = float(state.get("m2", 0.0) or 0.0)
        std = float(np.sqrt(m2 / (n - 1))) if n > 1 else 0.0
        return {"std": std, "count": n}

    registry.register("cal_std_finalize", cal_std_finalize)

    def cal_import_pms1p(payload: dict) -> dict:
        pm_s1p_ref = payload.get("PM_s1p")

        pm_network: Optional[skrf.Network] = None
        pm_s1p_path: Optional[Path] = None
        if pm_s1p_ref:
            pm_s1p_path = Path(str(pm_s1p_ref)).expanduser().resolve()
            if not pm_s1p_path.exists():
                raise FileNotFoundError(f"PM S1P file not found: {pm_s1p_path}")
            pm_network = skrf.Network(str(pm_s1p_path))

        return {"s11":{
                    "real": np.real(pm_network.s[:, 0, 0]), 
                    "imag": np.imag(pm_network.s[:, 0, 0])},
                "freq_hz": pm_network.f}

    registry.register("cal_import_pms1p", cal_import_pms1p)

    def cal_power_coupling(payload: dict, _cal: dict) -> dict:
        """
        Compute probe-tip power using Eq. (8):

          P_L = |b2^M|^2 |C10/E10|^2 |(1 - E11*Gamma_t)/(1 - Es2*Gamma_t)|^2 (1 - |Gamma_L|^2)

        Inputs are expected in payload:
          - probe_calfile: mapping with per-frequency complex arrays for C10, E10, E11, Es2, Er2, Ed2 and frequency vector (freq_hz)
          - PM_s1p: path to a .s1p file (Gamma_L)
          - wave_values: VNA capture with b2 (complex)
        """
        probe_terms_raw = payload.get("probe_calfile") or {}
        pm_s1p = payload.get("pm_s1p") or {}
        freq_pm = np.asarray(pm_s1p.get("freq_hz") or [], dtype=float)
        pm_s11 = _to_array(pm_s1p.get("s11"), dtype=complex)
        wave_values = payload.get("wave_values") or {}

        # Convert probe error terms to complex arrays
        probe_terms = _load_error_terms(probe_terms_raw)
        freq_probe = np.asarray(probe_terms_raw.get("freq_hz") or probe_terms_raw.get("frequency") or [], dtype=float)

        # Measurement frequency (Hz)
        freq_wave = _extract_frequency_vector(wave_values)
        f_target = float(freq_wave.ravel()[0]) if freq_wave is not None and freq_wave.size else None
        if f_target is None and freq_pm is not None and freq_pm.size:
            f_target = float(freq_pm[0])
        if f_target is None and freq_probe.size:
            f_target = float(freq_probe[0])
        if f_target is None:
            return {}

        # Require matching frequency grids; filter to intersection, no interpolation
        common_freqs = freq_probe
        if freq_pm.size:
            common_freqs = np.intersect1d(freq_probe, freq_pm)
            if common_freqs.size != freq_pm.size or common_freqs.size != freq_probe.size:
                print("Warning: probe and PM frequency grids differ; filtering to common frequencies")
        if common_freqs.size == 0:
            print("Warning: no common frequencies between probe and PM data")
            return {}
        if f_target is not None and not np.isclose(common_freqs, f_target).any():
            print(f"Warning: measurement frequency {f_target} not present in both probe/PM grids; skipping")
            return {}
        # Choose target frequency
        if f_target is None:
            f_target = float(common_freqs[0])

        # Masks for the selected frequency
        probe_mask = np.isclose(freq_probe, f_target) if freq_probe.size else None
        pm_mask = np.isclose(freq_pm, f_target) if freq_pm.size else None

        # Extract probe terms at target frequency
        def _get_term(name: str) -> complex:
            arr = probe_terms.get(name)
            if arr is None:
                return complex(np.nan, np.nan)
            # Normalize to ndarray for masking
            if isinstance(arr, list):
                arr = np.asarray(arr, dtype=complex)
            if isinstance(arr, np.ndarray):
                if arr.size == 0:
                    return complex(np.nan, np.nan)
                # Only use values at the common frequency index
                if freq_probe.size and arr.size == freq_probe.size:
                    if probe_mask is not None:
                        arr = arr[probe_mask]
                    if arr.size:
                        return complex(arr.ravel()[0])
                    return complex(np.nan, np.nan)
                return complex(arr.ravel()[0])
            return complex(arr)

        C10 = _get_term("C10")
        E10 = _get_term("E10")
        E11 = _get_term("E11")
        Es2 = _get_term("Es2")
        Ed2 = _get_term("Ed2")
        Er2 = _get_term("Er2")

        # PM reflection Gamma_pm at target frequency
        gamma_pm = None
        if isinstance(pm_s11, np.ndarray) and pm_s11.size and pm_mask is not None:
            subset = pm_s11[pm_mask]
            if subset.size:
                gamma_pm = complex(subset.ravel()[0])
        if gamma_pm is None:
            gamma_pm = complex(np.nan, np.nan)

        # Gamma_L same as PM reflection here (no interpolation)
        gamma_L = gamma_pm

        # Gamma_t: (Gamma_L^M - Ed2) / (Er2 + Es2*(Gamma_L^M - Ed2))
        with np.errstate(divide="ignore", invalid="ignore"):
            gamma_t = (gamma_L - Ed2) / (Er2 + Es2 * (gamma_L - Ed2))

        # Measured b2 from wave_values
        b2_arr = _to_array(wave_values.get("b2") or wave_values.get("wave_data", {}).get("b2"), dtype=complex)
        if b2_arr is None or b2_arr.size == 0:
            return {}
        b2 = complex(b2_arr.ravel()[0])

        # Optional |C10| from Eq. (9) if not provided (exact frequency match only)
        if np.isnan(C10) or C10 == 0:
            pm_power = payload.get("PM_power") or {}

            def _exact_pm_power(pwr: dict) -> Optional[float]:
                if not isinstance(pwr, dict) or not pwr:
                    return None
                for k, v in pwr.items():
                    try:
                        fk = float(k)
                    except Exception:
                        continue
                    if not np.isclose(fk, f_target):
                        continue
                    if isinstance(v, dict) and "dBm" in v:
                        return _convert_dbm_to_linear(float(v["dBm"]))
                    if isinstance(v, (int, float)):
                        return float(v)
                return None

            pm_pwr_linear = _exact_pm_power(pm_power)
            if pm_pwr_linear is not None and not np.isnan(pm_pwr_linear):
                with np.errstate(divide="ignore", invalid="ignore"):
                    num = pm_pwr_linear * abs(1 - Es2 * gamma_pm) ** 2
                    den = (abs(b2) ** 2) * (1 - abs(gamma_pm) ** 2)
                    if den != 0:
                        C10_mag = np.sqrt(num / den)
                        C10 = complex(C10_mag)

        # Compute P_L per Eq. (8)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio_ce = pm_pwr_linear * abs(1 - Es2 * gamma_pm) ** 2 / ( abs(E10) ** 2 *abs(b2) ** 2 * (1 - abs(gamma_pm) ** 2) ) if E10 else np.nan
            corr = (1 - E11 * gamma_t) / (1 - Es2 * gamma_t) if (Es2 is not None) else np.nan
            pl = (abs(b2) ** 2) * (abs(ratio_ce) ** 2) * (abs(corr) ** 2) * (1 - abs(gamma_L) ** 2)

        return {
            "P_L": pl,
            "freq_hz": f_target,
            "gamma_t": gamma_t,
            "gamma_L": gamma_L,
            "gamma_pm": gamma_pm,
            "E10": E10,
            "E11": E11,
            "Es2": Es2,
            "Ed2": Ed2,
            "Er2": Er2,
            "b2": b2,
        }

    registry.register("cal_power_coupling", cal_power_coupling)

def _onwafer_power_278582(payload: dict) -> dict:
    gamma_t_num = Gamma_L - Ed2
    gamma_t_den = Er2+Es2*(Gamma_L-Ed2)
    Gamma_t = gamma_t_num / gammat_den

    output_probe_power = abs(b2)^2*abs(C10/E10)*abs(1-E11*Gamma_t)^2*(1-abs(Gamma_L)^2)
    return {"output_probe_power": output_probe_power}

def _load_error_terms(payload: dict) -> dict:
    """Convert error-term real/imag pairs in the payload into complex values."""
    terms: dict[str, object] = {}
    for name, data in (payload or {}).items():
        if str(name).lower() == "csv":
            continue  # ignore any CSV path metadata
        if not isinstance(data, dict):
            continue
        arr = _to_array({"real": data.get("real"), "imag": data.get("imag")}, dtype=complex)
        if arr is None:
            continue
        terms[name] = complex(arr.ravel()[0]) if arr.size == 1 else [complex(x) for x in arr.ravel()]
    return terms
    
