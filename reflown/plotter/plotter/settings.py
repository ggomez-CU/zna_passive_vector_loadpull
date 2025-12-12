from __future__ import annotations

"""Application settings wrapper using QSettings.

Keeps UI/user preferences such as last root directory.
"""

from PySide6 import QtCore


class Settings:
    """Thin wrapper over QSettings with typed helpers."""

    ORG = "Loadpull"
    APP = "Plotter"

    def __init__(self) -> None:
        print("init: Settings.__init__", flush=True)
        self._s = QtCore.QSettings(self.ORG, self.APP)

    def last_root(self) -> str | None:
        print("init: Settings.last_root", flush=True)
        v = self._s.value("last_root", type=str)
        return v or None

    def set_last_root(self, path: str) -> None:
        print("init: Settings.set_last_root", flush=True)
        self._s.setValue("last_root", path)
