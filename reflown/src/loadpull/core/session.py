from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from .calibration import CalibrationStore
from .results import JsonlWriter
from .scpi import Scpi
from .transport import SocketTransport, Transport
try:
    from .transport import VisaTransport  # Optional dependency
except ImportError:  # pragma: no cover - fallback when VISA support is absent
    VisaTransport = None  # type: ignore


@dataclass
class BenchConfig:
    instruments: dict[str, Any]
    timeouts: dict[str, float]
    bench_name: str = "bench_default"
    extra_tables: dict[str, Any] | None = None

    @staticmethod
    def from_toml(path: str | Path) -> "BenchConfig":
        import tomllib

        data = tomllib.loads(Path(path).read_text())
        extras = {k: v for k, v in data.items() if k not in ("bench", "visa", "timeouts")}
        return BenchConfig(
            instruments=data.get("visa", {}),
            timeouts=data.get("timeouts", {}),
            bench_name=data.get("bench", {}).get("name", "bench_default"),
            extra_tables=extras or {},
        )


class Session:
    def __init__(self, bench: BenchConfig, out_dir: Path):
        self.bench = bench
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = out_dir / "manifest.json"
        self.writer = JsonlWriter(out_dir / "results.jsonl")
        self.meta: Dict[str, Any] = {
            "schema": "1.0.0",
            "bench": bench.bench_name,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        cal_dir = Path("calibration")
        cal_file = cal_dir / f"{bench.bench_name}.json"
        self.cal_store = CalibrationStore(cal_file, bench_name=bench.bench_name)

    def new_scpi(self, inst_name: str) -> Scpi:
        """Create a SCPI session for a named instrument from bench config."""
        resource = self.bench.instruments.get(inst_name)
        if resource is None:
            raise ValueError(f"No resource for instrument {inst_name}")
        # Inline-table style configs are for non-SCPI instruments; they shouldn't
        # be opened as SCPI sessions here.
        if isinstance(resource, dict):
            raise ValueError(
                f"Instrument {inst_name} is configured with a mapping; use constructor kwargs instead of SCPI."
            )
        transport: Transport
        if (
            ":" in resource
            and not resource.startswith("GPIB")
            and not resource.startswith("TCPIP0::")
        ):
            host, port_str = resource.split(":", 1)
            transport = SocketTransport(host, int(port_str))
        elif resource.startswith("GPIB") or resource.startswith("TCPIP0::"):
            if VisaTransport is None:
                raise RuntimeError(
                    "VISA transport requested but VisaTransport is unavailable"
                )
            transport = VisaTransport(resource)
        else:
            # Default to SCPI over sockets on port 5025.
            transport = SocketTransport(resource, 5025)

        transport.open()
        return Scpi(transport)

    def instrument_config(self, name: str) -> Dict[str, Any] | None:
        """Return optional per-instrument config.

        Priority:
          1) Inline table in [visa] for this instrument name (dict value)
          2) Extra bench table matching snake_case of instrument name
        """
        # 1) Inline table under [visa]
        val = self.bench.instruments.get(name)
        if isinstance(val, dict):
            return val

        # 2) Extra table like [bias_ctrl]
        def _to_snake(s: str) -> str:
            out = []
            for i, ch in enumerate(s):
                if ch.isupper() and i > 0 and (not s[i-1].isupper()):
                    out.append("_")
                out.append(ch.lower())
            return "".join(out)

        key = _to_snake(name)
        if self.bench.extra_tables and key in self.bench.extra_tables:
            tbl = self.bench.extra_tables.get(key)
            if isinstance(tbl, dict):
                return tbl  # type: ignore[return-value]
        return None

    def record_manifest(self, extra: Dict[str, Any]) -> None:
        manifest = {**self.meta, **extra}
        manifest["hash"] = hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode()
        ).hexdigest()[:12]
        self.manifest_path.write_text(json.dumps(manifest, indent=2))
