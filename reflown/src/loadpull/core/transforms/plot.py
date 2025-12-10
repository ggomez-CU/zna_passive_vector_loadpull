from __future__ import annotations

import numpy as np

from .registry import TransformRegistry
from .utils import _extract_array_field


def register_plot_transforms(registry: TransformRegistry) -> None:
    def z2gamma(payload: dict, _cal: dict) -> dict:
        z0 = float(payload.get("z0", 50.0))
        real = payload.get("real")
        imag = payload.get("imag")
        if real is None or imag is None:
            return {}

        r = np.asarray(real, dtype=float)
        i = np.asarray(imag, dtype=float)

        if r.shape != i.shape:
            if r.size == 1:
                r = np.full_like(i, r.item(), dtype=float)
            elif i.size == 1:
                i = np.full_like(r, i.item(), dtype=float)
            else:
                return {}

        z = r + 1j * i
        gamma = (z - z0) / (z + z0)
        mag = np.abs(gamma)
        ang = np.angle(gamma)

        if mag.size == 1:
            return {"angle_rad": float(ang.ravel()[0]), "mag": float(mag.ravel()[0])}
        return {"angle_rad": ang.tolist(), "mag": mag.tolist()}

    registry.register("z2gamma", z2gamma)

    def set_plot_gamma(payload: dict, _cal: dict) -> dict:
        if "mag" in payload and "rad" in payload:
            return {"angle_rad": payload["rad"], "mag": payload["mag"]}
        if "mag" in payload and "deg" in payload:
            return {"angle_rad": np.deg2rad(payload["deg"]).tolist(), "mag": payload["mag"]}
        if "real" in payload and "imag" in payload:
            real = payload.get("real")
            imag = payload.get("imag")
            r = np.asarray(real, dtype=float)
            i = np.asarray(imag, dtype=float)
            return {"angle_rad": np.angle(complex(r, i)).tolist(), "mag": np.abs(complex(r, i)).tolist()}
        return {}

    registry.register("set_plot_gamma", set_plot_gamma)
