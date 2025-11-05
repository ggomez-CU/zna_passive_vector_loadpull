from __future__ import annotations

"""Per-test plot presets and tab layouts.

Each test type returns a mapping of tab_name -> list of plot specs.
Spec keys: title, mode (line|scatter), x, y(list) or xy(tuple), columns(list), xlabel, ylabel.
"""

from typing import Dict, List, Union


class TestTypeRegistry:
    def __init__(self) -> None:
        print("init: TestTypeRegistry.__init__", flush=True)
        # test_type -> tabs or single list
        self._layouts: Dict[str, Union[List[dict], Dict[str, List[dict]]]] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        print("init: TestTypeRegistry._register_defaults", flush=True)
        self._layouts["test_VectorReceiver"] = {
            "Gamma": [
                {"title": "Gamma_L (complex plane)", "mode": "scatter", "xy": ("gamma.gamma_L.real", "gamma.gamma_L.imag"), "columns": ["gamma.gamma_L.real", "gamma.gamma_L.imag"], "xlabel": "Re", "ylabel": "Im"},
                {"title": "|Gamma_L| vs sample", "x": "sample_index", "y": ["gamma.gamma_L.mag"], "columns": ["sample_index", "gamma.gamma_L.mag"], "xlabel": "sample", "ylabel": "|Gamma_L|"},
            ],
        }
        self._layouts["default"] = [
            {"title": "|Gamma_L| vs sample", "x": "sample_index", "y": ["gamma.gamma_L.mag"], "columns": ["sample_index", "gamma.gamma_L.mag"], "xlabel": "sample", "ylabel": "|Gamma_L|"},
        ]

    def tabs_for(self, test_type: str) -> Dict[str, List[dict]]:
        print("init: TestTypeRegistry.tabs_for", flush=True)
        layout = self._layouts.get(test_type, self._layouts["default"])
        if isinstance(layout, list):
            return {"Main": layout}
        return layout
