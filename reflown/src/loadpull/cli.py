from __future__ import annotations

from pathlib import Path
from typing import Optional

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
    out: str = typer.Option("runs/out", help="Output directory"),
) -> None:
    bench_cfg = BenchConfig.from_toml(bench)
    out_dir = Path(out)
    session = Session(bench_cfg, out_dir)

    instruments = {}
    for name, cls in INSTRUMENTS.items():
        scpi = session.new_scpi(name)
        inst = cls(scpi)
        config = session.instrument_config(name)
        if config and hasattr(inst, "apply_bench_config"):
            inst.apply_bench_config(config, session)
        instruments[name] = inst

    sequence = Sequence.load(testspec)
    writer = session.writer
    plot_cfg: Optional[dict[str, object]] = sequence.spec.get("plot")
    if plot_cfg:
        from .core.plotting import LivePlotWriter

        writer = LivePlotWriter(out_dir / "results.jsonl", plot_cfg)

    ctx = Context(
        instruments=instruments,
        writer=writer,
        cal_store=session.cal_store,
        cal_cache=session.cal_store.as_dict(),
        transform=transform_measurement,
        fail_policy=sequence.spec.get("fail_policy", "halt"),
        interrupt_policy=sequence.spec.get("interrupt_policy", "pause"),
    )

    try:
        sequence.run(ctx)
    finally:
        if writer is not session.writer and hasattr(writer, "close"):
            writer.close()
        if hasattr(session.writer, "close"):
            session.writer.close()

    session.record_manifest(
        {
            "test": sequence.name,
            "out": str(out_dir),
        }
    )
    print(f"[green]Run complete. Results at {out_dir}")
