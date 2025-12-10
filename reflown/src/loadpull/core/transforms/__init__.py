from __future__ import annotations

from .registry import TransformRegistry
from .calibration_calculation import register_calibration_calculation_transforms
from .calibration_correction import register_calibration_corrections_transforms
from .loadpull_sweep import register_loadpull_sweep_transforms
from .plot import register_plot_transforms


__all__ = ["TransformRegistry", "default_registry"]


def default_registry() -> TransformRegistry:
    registry = TransformRegistry()
    register_calibration_calculation_transforms(registry)
    register_calibration_corrections_transforms(registry)
    register_loadpull_sweep_transforms(registry)
    register_plot_transforms(registry)
    return registry
