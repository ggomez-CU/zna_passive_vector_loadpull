from __future__ import annotations

from typing import Dict, List, Union


class TestTypeRegistry:
    def __init__(self) -> None:
        # Each entry can be either:
        # - List[spec] for a single-tab view
        # - Dict[tab_name, List[spec]] for multi-tab views
        self._layouts: Dict[str, Union[List[dict], Dict[str, List[dict]]]] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        # Minimal working test type preset
        self._layouts["test_VectorReceiver"] = {
            " ": [
                # {"title": "Gamma_L (complex plane)", "mode": "scatter", "xy": ("gamma.gamma_L.real", "gamma.gamma_L.imag"), "columns": ["gamma.gamma_L.real", "gamma.gamma_L.imag"], "xlabel": "Re{Gamma_L}", "ylabel": "Im{Gamma_L}"},
                {"title": "|Gamma_L| vs idx", "x": "sample_index", "y": ["gamma.gamma_L.mag"], "columns": ["idx", "gamma.gamma_L.mag"], "xlabel": "idx", "ylabel": "|Gamma_L|"},
                {"title": "Compare A/B vs idx",
                    "columns": ["sample_index", "gamma.gamma_L.mag", "gamma.gamma_L.angle_rad"],
                    "xlabel": "Sample Index",
                    "ylabel": "|Gamma|",
                    "series": [
                        {"x": "sample_index", "y": "gamma.gamma_L.mag", "label": "Load Mag"},
                        {"x": "sample_index", "y": "loads11.mag", "label": "S11 Mag"}
                    ]
                }
            ],
            "Source": [
                {"title": "|Gamma_S| vs idx", "x": "idx", "y": ["gamma.gamma_S.mag"], "columns": ["idx", "gamma.gamma_S.mag"], "xlabel": "idx", "ylabel": "|Gamma_S|"},
            ],
        }
        self._layouts["default"] = [
            {"title": "|Gamma_L| vs idx", "x": "idx", "y": ["gamma.gamma_L.mag"], "columns": ["idx", "gamma.gamma_L.mag"], "xlabel": "idx", "ylabel": "|Gamma_L|"},
        ]

    def layout_for(self, test_type: str) -> List[dict]:
        """Backward-compatible: returns a flat list of specs (first tab if multi-tab)."""
        layout = self._layouts.get(test_type, self._layouts["default"])
        if isinstance(layout, list):
            return layout
        # Dict: return the first tab's specs
        for _, specs in layout.items():
            return specs
        return []

    def tabs_for(self, test_type: str) -> Dict[str, List[dict]]:
        """Return a mapping of tab_name -> list of specs for a test type."""
        layout = self._layouts.get(test_type, self._layouts["default"])
        if isinstance(layout, list):
            return {"Main": layout}
        return layout
