from loadpull.core.transport import FakeTransport
from loadpull.core.scpi import Scpi


def test_fake_transport_roundtrip():
ft = FakeTransport(responses=["KEYSIGHT,PNA,0,0", "0,No error"])
ft.open()
scpi = Scpi(ft)
out = scpi.query("*IDN?")
assert "KEYSIGHT" in out