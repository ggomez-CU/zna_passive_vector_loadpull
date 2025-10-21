from __future__ import annotations
from .transport import Transport

class Scpi:
    def __init__(self, transport: Transport, terminator: str = "\n", err_poll: bool = True):
        self.t = transport
        # self.term = terminator
        self.err_poll = err_poll

    def write(self, cmd: str) -> None:
        self.t.write(cmd)

    def query(self, cmd: str, timeout_s: float = 3.0) -> str:
        self.write(cmd)
        out = self.t.read(timeout_s)
        if self.err_poll:
            err = self.query_no_poll("SYST:ERR?", timeout_s)
            if not err.startswith("0") and not err.startswith("+0"):
                raise RuntimeError(f"SCPI error after '{cmd}': {err}")
        return out

    def query_no_poll(self, cmd: str, timeout_s: float = 3.0) -> str:
        self.t.write(cmd)
        return self.t.read(timeout_s)