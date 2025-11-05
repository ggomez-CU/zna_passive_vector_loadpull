from __future__ import annotations

from PySide6 import QtCore


class Settings:
    ORG = "Loadpull"
    APP = "Viewer"

    def __init__(self) -> None:
        self._s = QtCore.QSettings(self.ORG, self.APP)

    def last_root(self) -> str | None:
        v = self._s.value("last_root", type=str)
        return v or None

    def set_last_root(self, path: str) -> None:
        self._s.setValue("last_root", path)

