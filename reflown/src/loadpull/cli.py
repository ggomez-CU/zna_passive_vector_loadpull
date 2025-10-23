from __future__ import annotations

from pathlib import Path
from typing import Optional
import time

import typer
from rich import print

from .core.registry import INSTRUMENTS
from .core.sequencing import Context, Sequence
from .core.session import BenchConfig, Session
from .core.transforms import default_registry


app = typer.Typer(no_args_is_help=True)

_TRANSFORM_REGISTRY = default_registry()

def transform_measurement(method: str, payload: dict, cal_cache: dict) -> dict:
    return _TRANSFORM_REGISTRY.apply(method, payload, cal_cache)


@app.command()
def list_tests(path: str = typer.Option("testspecs", help="Directory of YAML testspecs")) -> None:
    specs = Path(path)
    if not specs.exists():
        print(f"[red]No testspecs at {path}")
        raise typer.Exit(1)
    for spec in sorted(specs.glob("*.yaml")):
        print(f"- {spec.name}")


@app.command()
def list_instruments() -> None:
    for name in INSTRUMENTS:
        print(f"- {name}")


@app.command()
def run(
    testspec: str = typer.Argument(..., help="YAML testspec path"),
    bench: str = typer.Option("benches/bench_default.toml", help="Bench TOML"),
) -> None:
    ts =  time.strftime("%Y-%m-%d_%H%M")
    bench_cfg = BenchConfig.from_toml(bench)
    # Load the testspec first so we can validate required instruments.
    sequence = Sequence.load(testspec)
    out = f"runs/{sequence.name}/{ts}"
    out_dir = Path(out)
    session = Session(bench_cfg, out_dir)

    instruments = {}
    # Iterate instruments defined in the bench TOML instead of the full registry
    for name, resource in session.bench.instruments.items():
        cls = INSTRUMENTS.get(name)
        if cls is None:
            print(f"[yellow]Skipping unknown instrument '{name}' (not in registry)")
            continue
        if isinstance(resource, dict):
            # Non-SCPI style instrument configured via inline table
            # Ignore optional 'driver' key if present
            kwargs = {k: v for k, v in resource.items() if k != "driver"}
            inst = cls(**kwargs)
        else:
            scpi = session.new_scpi(name)
            inst = cls(scpi)
        config = session.instrument_config(name)
        if config and hasattr(inst, "apply_bench_config"):
            inst.apply_bench_config(config, session)
        instruments[name] = inst

    # Validate required instruments from the testspec are present in the bench
    required = set(sequence.spec.get("requires", []))
    missing = sorted(r for r in required if r not in instruments)
    if missing:
        print(f"[red]Bench missing required instruments: {', '.join(missing)}")
        raise typer.Exit(1)
    # Set up dual writers: log (all steps) and results (explicit updates, drives plotting)
    from .core.results import DualWriter, JsonlWriter as _JsonlWriter
    plot_cfg: Optional[dict[str, object]] = sequence.spec.get("plot")
    log_writer = _JsonlWriter(out_dir / "log.jsonl")
    if plot_cfg:
        from .core.plotting import LivePlotWriter
        results_writer = LivePlotWriter(out_dir / "results.jsonl", plot_cfg)
    else:
        results_writer = _JsonlWriter(out_dir / "results.jsonl")
    writer = DualWriter(log_writer=log_writer, results_writer=results_writer)

    # Resolve optional shutdown order: prefer spec override; else bench TOML [shutdown].order
    shutdown_order: Optional[list[str]] = None
    spec_shutdown = sequence.spec.get("shutdown_order")
    if isinstance(spec_shutdown, list):
        shutdown_order = [str(x) for x in spec_shutdown]
    else:
        # Look for [shutdown] order in bench config extras
        extra = session.bench.extra_tables or {}
        sd = extra.get("shutdown") if isinstance(extra.get("shutdown"), dict) else None
        if isinstance(sd, dict):
            order = sd.get("order")
            if isinstance(order, list):
                shutdown_order = [str(x) for x in order]

    ctx = Context(
        instruments=instruments,
        writer=writer,
        cal_store=session.cal_store,
        cal_cache=session.cal_store.as_dict(),
        transform=transform_measurement,
        fail_policy=sequence.spec.get("fail_policy", "halt"),
        interrupt_policy=sequence.spec.get("interrupt_policy", "pause"),
        shutdown_order=shutdown_order,
    )

    try:
        sequence.run(ctx)
    finally:
        if hasattr(writer, "close"):
            writer.close()
        # Close the unused default session writer if it exists
        if hasattr(session, "writer") and hasattr(session.writer, "close"):
            try:
                session.writer.close()
            except Exception:
                pass

    session.record_manifest(
        {
            "test": sequence.name,
            "out": str(out_dir),
        }
    )
    print(f"[green]Run complete. Results at {out_dir}")
