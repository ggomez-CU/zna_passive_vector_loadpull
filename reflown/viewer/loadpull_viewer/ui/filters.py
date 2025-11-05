from __future__ import annotations

from typing import Dict
from PySide6 import QtCore, QtWidgets


class FiltersPanel(QtWidgets.QWidget):
    sig_filters_changed = QtCore.Signal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        lay = QtWidgets.QFormLayout(self)

        self.freq_min = QtWidgets.QDoubleSpinBox(); self.freq_min.setRange(0, 1e12); self.freq_min.setDecimals(3)
        self.freq_max = QtWidgets.QDoubleSpinBox(); self.freq_max.setRange(0, 1e12); self.freq_max.setDecimals(3)
        self.power_min = QtWidgets.QDoubleSpinBox(); self.power_min.setRange(-300, 300)
        self.power_max = QtWidgets.QDoubleSpinBox(); self.power_max.setRange(-300, 300)
        self.bias_min = QtWidgets.QDoubleSpinBox(); self.bias_min.setRange(-1000, 1000)
        self.bias_max = QtWidgets.QDoubleSpinBox(); self.bias_max.setRange(-1000, 1000)

        lay.addRow("Freq min (Hz)", self.freq_min)
        lay.addRow("Freq max (Hz)", self.freq_max)
        lay.addRow("Power min (dBm)", self.power_min)
        lay.addRow("Power max (dBm)", self.power_max)
        lay.addRow("Bias min", self.bias_min)
        lay.addRow("Bias max", self.bias_max)

        apply_btn = QtWidgets.QPushButton("Apply")
        lay.addWidget(apply_btn)
        apply_btn.clicked.connect(self._emit)

    def _emit(self) -> None:
        payload = {
            "freq_min": self.freq_min.value(),
            "freq_max": self.freq_max.value(),
            "power_min": self.power_min.value(),
            "power_max": self.power_max.value(),
            "bias_min": self.bias_min.value(),
            "bias_max": self.bias_max.value(),
        }
        self.sig_filters_changed.emit(payload)

    def set_available_fields(self, fields: Dict[str, bool]) -> None:
        freq = fields.get("frequency", True)
        power = fields.get("power", True)
        bias = fields.get("bias", True)
        for w in (self.freq_min, self.freq_max):
            w.setEnabled(freq)
        for w in (self.power_min, self.power_max):
            w.setEnabled(power)
        for w in (self.bias_min, self.bias_max):
            w.setEnabled(bias)

