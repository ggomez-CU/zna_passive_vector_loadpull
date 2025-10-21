from __future__ import annotations

from typing import Dict, Type

from ..instruments.base import Instrument
from ..instruments.bias_controller import BiasController
from ..instruments.Focus_CCMT1808 import FocusCCMT1808
from ..instruments.Keysight_34400 import Keysight34400
from ..instruments.keysight_pna import KeysightPNA
from ..instruments.rohdeschwarz_ZVA import RSZVA

INSTRUMENTS: Dict[str, Type[Instrument]] = {
    "VNA": RSZVA,
    "DMM1": Keysight34400,
    "DMM2": Keysight34400,
    "PM": Keysight34400,
    "LOADTUNER": FocusCCMT1808,
    "SOURCETUNER": FocusCCMT1808,
    "BiasCtrl": BiasController,
}
