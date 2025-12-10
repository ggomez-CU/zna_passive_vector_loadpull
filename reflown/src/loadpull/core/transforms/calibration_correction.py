from __future__ import annotations

import numpy as np

from .registry import TransformRegistry
from .utils import _extract_array_field


def register_calibration_corrections_transforms(registry: TransformRegistry) -> None:

    def corr_gamma(payload: dict, _cal: dict) -> dict:
        b1_keys, a1_keys, b2_keys, a2_keys = ["b1", "B1"], ["a1", "A1"], ["b2", "B2"], ["a2", "A2"]
        wave_data = payload.get("wave_data") or payload

        b1_arr = _extract_array_field(wave_data, b1_keys, dtype=complex)
        a1_arr = _extract_array_field(wave_data, a1_keys, dtype=complex)
        b2_arr = _extract_array_field(wave_data, b2_keys, dtype=complex)
        a2_arr = _extract_array_field(wave_data, a2_keys, dtype=complex)
        if b1_arr is None or a1_arr is None or b2_arr is None or a2_arr is None:
            return {}

        b1 = np.asarray(b1_arr, dtype=complex).ravel()
        a1 = np.asarray(a1_arr, dtype=complex).ravel()
        b2 = np.asarray(b2_arr, dtype=complex).ravel()
        a2 = np.asarray(a2_arr, dtype=complex).ravel()

        with np.errstate(divide="ignore", invalid="ignore"):
            gamma_source = b1 / a1

        with np.errstate(divide="ignore", invalid="ignore"):
            gamma_load = a2 / b2

        return {
            "gamma_L": {
                "real": gamma_load.real.tolist(),
                "imag": gamma_load.imag.tolist(),
                "mag": np.abs(gamma_load).tolist(),
                "angle_rad": np.angle(gamma_load).tolist(),
            },
            "gamma_S": {
                "real": gamma_source.real.tolist(),
                "imag": gamma_source.imag.tolist(),
                "mag": np.abs(gamma_source).tolist(),
                "angle_rad": np.angle(gamma_source).tolist(),
            },
        }

    registry.register("corr_gamma", corr_gamma)
    
    def corr_power(payload: dict, cal: dict) -> dict:
        if "power" in payload:
            return {"power_corr": payload["power"] - cal.get("power_offset", 0.0)}
        return {}

    registry.register("corr_power", corr_power)