from __future__ import annotations
from typing import Protocol, Optional


class Transport(Protocol):
    def open(self) -> None: ...
    def close(self) -> None: ...
    def write(self, data: str) -> None: ...
    def read(self, timeout_s: float) -> str: ...
    def query(self, data: str) -> str: ...

class VisaTransport(Transport):
    """
    Lightweight GPIB transport using PyVISA.

    Example resource strings:
      - "GPIB0::5::INSTR"
      - "GPIB0::7::INSTR"

    Notes:
      - Requires `pyvisa` and a VISA backend (NI, Keysight, pyvisa-py).
      - Termination is handled by the VISA resource properties.
    """
    def __init__(
        self,
        resource: str,
        read_termination: str = "\n",
        write_termination: str = "\n",
        timeout_ms: int = 3000,
    ):
        self.resource = resource
        self.read_termination = read_termination
        self.write_termination = write_termination
        self.timeout_ms = timeout_ms
        self._rm = None
        self._inst = None

    def open(self) -> None:
        import pyvisa
        self._rm = pyvisa.ResourceManager()
        self._inst = self._rm.open_resource(self.resource)
        # Configure terminations and timeout
        # self._inst.read_termination = self.read_termination
        # self._inst.write_termination = self.write_termination
        self._inst.timeout = self.timeout_ms  # milliseconds

    def close(self) -> None:
        if self._inst is not None:
            try:
                self._inst.close()
            finally:
                self._inst = None
        if self._rm is not None:
            try:
                self._rm.close()
            finally:
                self._rm = None

    def write(self, data: str) -> None:
        assert self._inst is not None, "Transport not open"
        # PyVISA appends write_termination automatically
        self._inst.write(data)

    def read(self, timeout_s: float) -> str:
        assert self._inst is not None, "Transport not open"
        # Temporarily adjust timeout for this read
        old = self._inst.timeout
        try:
            self._inst.timeout = int(timeout_s * 1000)
            return self._inst.read()
        finally:
            self._inst.timeout = old

    def query(self, data: str) -> str:
        assert self._inst is not None, "Transport not open"
        self._inst.write(data)
        return self._inst.read()

class SocketTransport:
    """Minimal TCP socket transport (SCPI over sockets)."""
    def __init__(self, host: str, port: int = 5025, terminator: str = "\n"):
        import socket
        self._addr = (host, port)
        self._sock: Optional[socket.socket] = None
        self._term = terminator.encode()


    def open(self) -> None:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect(self._addr)
        self._sock = s


    def close(self) -> None:
        if self._sock:
            try: self._sock.close()
            finally: self._sock = None


    def write(self, data: str) -> None:
        assert self._sock is not None, "Transport not open"
        self._sock.sendall(data.encode() + self._term)


    def read(self, timeout_s: float) -> str:
        assert self._sock is not None, "Transport not open"
        self._sock.settimeout(timeout_s)
        chunks = []
        while True:
            b = self._sock.recv(4096)
            if not b:
                break
            chunks.append(b)
            if b.endswith(self._term):
                break
        out = b"".join(chunks)
        return out.rstrip(self._term).decode()

    def query(self, data: str) -> None:
        self.write(data)
        return self.read()


class FakeTransport:
    """Record/Replay style transport for CI and local simulation.


    Provide a list of responses that will be returned sequentially on reads.
    Writes are collected for debugging.
    """
    def __init__(self, responses: list[str] | None = None):
        self.responses = responses or []
        self.writes: list[str] = []
        self._open = False


    def open(self) -> None:
        self._open = True


    def close(self) -> None:
        self._open = False


    def write(self, data: str) -> None:
        assert self._open, "Transport not open"
        self.writes.append(data)


    def read(self, timeout_s: float) -> str:
        assert self._open, "Transport not open"
        if not self.responses:
            return ""
        return self.responses.pop(0)