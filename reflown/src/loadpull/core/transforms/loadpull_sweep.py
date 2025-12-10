from __future__ import annotations

from .registry import TransformRegistry
from .utils import _read_sweep_points


def register_loadpull_sweep_transforms(registry: TransformRegistry) -> None:
    
    def loadpull_sweep_len(payload: dict, _cal: dict) -> dict:
        path = payload.get("file") or payload.get("path")
        pts = _read_sweep_points(str(path))
        return {"count": max(0, len(pts) - 1)}

    registry.register("loadpull_sweep_len", loadpull_sweep_len)

    def loadpull_sweep_point(payload: dict, _cal: dict) -> dict:
        path = payload.get("file") or payload.get("path")
        idx_raw = payload.get("index")
        try:
            idx = int(idx_raw)
        except Exception:
            return {}
        pts = _read_sweep_points(str(path))
        if idx < 0 or idx >= len(pts):
            return {}
        mag, deg = pts[idx]
        return {"gamma_mag": mag, "gamma_deg": deg}

    registry.register("loadpull_sweep_point", loadpull_sweep_point)
