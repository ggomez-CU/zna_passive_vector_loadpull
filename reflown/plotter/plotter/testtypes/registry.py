from __future__ import annotations

"""Per-test plot presets and tab layouts.

Each test type returns a mapping of tab_name -> list of plot specs.
Spec keys: title, mode (line|scatter|polar-line|polar-scatter), x, y(list) or xy(tuple) or (r, theta_deg/theta_rad), columns(list), xlabel, ylabel.
"""

from typing import Dict, List, Union


class TestTypeRegistry:
    def __init__(self) -> None:
        # print("init: TestTypeRegistry.__init__", flush=True)
        # test_type -> tabs or single list
        self._layouts: Dict[str, Union[List[dict], Dict[str, List[dict]]]] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        # print("init: TestTypeRegistry._register_defaults", flush=True)
        self._layouts["test_VectorReceiver"] = {
            "Gamma": [
                {"title": "Gamma_L (complex plane)", "mode": "scatter", "xy": ("gamma.gamma_L.real", "gamma.gamma_L.imag"), "columns": ["gamma.gamma_L.real", "gamma.gamma_L.imag"], "xlabel": "Re", "ylabel": "Im"},
                {"title": "Gamma_L (complex plane)", "mode": "polar-scatter", "r": "gamma.gamma_L.mag", "theta_rad": "gamma.gamma_L.angle_rad", "columns": ["gamma.gamma_L.real", "gamma.gamma_L.imag"], "xlabel": "Re", "ylabel": "Im"},
                {"title": "|Gamma_L| vs sample", "x": "row_index", "y": ["gamma.gamma_L.mag"], "columns": ["row_index", "gamma.gamma_L.mag"], "xlabel": "sample", "ylabel": "|Gamma_L|"},
            ],
        }
        self._layouts["test_VNA_atten"] = {
            "Gamma": [
                {"title": "Load Sweep", "mode": "scatter", "xy": ("gamma.gamma_L.real", "gamma.gamma_L.imag"), "columns": ["gamma.gamma_L.real", "gamma.gamma_L.imag"]},
                {"title": "|Gamma_L| vs sample", "x": "row_index", "y": ["gamma.gamma_L.mag"], "columns": ["row_index", "gamma.gamma_L.mag"], "xlabel": "sample", "ylabel": "|Gamma_L|"},
            ],
        }
        self._layouts["calibrate_DMM"] = [
            {"title": "Mean convergence", "x": "tmp.noise_state.count", "y": ["tmp.noise_state.mean"], "columns": ["tmp.noise_state.m2"], "xlabel": "sample", "ylabel": "mean"},
        ]
        self._layouts["default"] = [
            {"title": "|Gamma_L| vs sample", "x": "row_index", "y": ["gamma.gamma_L.mag"], "columns": ["row_index", "gamma.gamma_L.mag"], "xlabel": "sample", "ylabel": "|Gamma_L|"},
        ]

    def tabs_for(self, test_type: str) -> Dict[str, List[dict]]:
        # print("init: TestTypeRegistry.tabs_for", flush=True)
        layout = self._layouts.get(test_type, self._layouts["default"])
        if isinstance(layout, list):
            return {"Main": layout}
        return layout
