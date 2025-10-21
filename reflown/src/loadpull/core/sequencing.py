from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List

import yaml

from .calibration import CalibrationStore
from .results import JsonlWriter


@dataclass
class Context:
    instruments: Dict[str, Any]
    writer: JsonlWriter
    cal_store: CalibrationStore
    cal_cache: Dict[str, Any]
    transform: Callable[[str, dict, dict], dict] | None = None
    fail_policy: str = "halt"
    interrupt_policy: str = "pause"

class Sequence:
    def __init__(self, name: str, spec: Dict[str, Any]):
        self.name = name
        self.spec = spec

    @staticmethod
    def load(path: str | Path) -> "Sequence":
        data = yaml.safe_load(Path(path).read_text())
        return Sequence(data["name"], data)

    def run(self, ctx: Context) -> None:
        params = self.spec.get("parameters", {})
        steps: List[Dict[str, Any]] = self.spec.get("steps", []) or []
        env: Dict[str, Any] = {k: v.get("default") for k, v in params.items()}
        _run_actions(self.name, steps, env, ctx)


def _run_actions(
    test_name: str,
    actions: List[Dict[str, Any]] | None,
    env: Dict[str, Any],
    ctx: Context,
) -> None:
    """Execute a list of actions with support for nested sweeps."""
    if not actions:
        return

    for action in actions:
        try:
            if "sweep" in action:
                sweep = action["sweep"]
                var = sweep["var"]
                start = float(_resolve(ctx, env, sweep["from"]))
                stop = float(_resolve(ctx, env, sweep["to"]))
                step = float(_resolve(ctx, env, sweep["step"]))
                n = _num_points(start, stop, step)
                for i in range(n):
                    env[var] = start + i * step
                    _run_actions(test_name, sweep.get("do"), env, ctx)
            elif "call" in action:
                call_spec = action["call"]
                inst_name = call_spec["inst"]
                method_name = call_spec["method"]
                inst = ctx.instruments[inst_name]
                method = getattr(inst, method_name)
                args = [_resolve(ctx, env, arg) for arg in call_spec.get("args", [])]
                out = method(*args)
                save_as = call_spec.get("save_as")
                if save_as:
                    _set_mapping_value(env, save_as, out)
                payload = {"inst": inst_name, "method": method_name, "result": out}
                payload.update(_flat_env(env))
                ctx.writer.write_point(
                    test_name,
                    f"call:{method_name}",
                    payload,
                )
            elif "measure" in action:
                measure = action["measure"]
                inst_name = measure["inst"]
                method_name = measure["method"]
                inst = ctx.instruments[inst_name]
                method = getattr(inst, method_name)
                args = [_resolve(ctx, env, arg) for arg in measure.get("args", [])]
                val = method(*args)
                save_key = measure.get("save_as", method_name)
                _set_mapping_value(env, save_key, val)
                payload = {"inst": inst_name, "method": method_name, save_key: val}
                payload.update(_flat_env(env))
                ctx.writer.write_point(test_name, f"measure:{method_name}", payload)
            elif "results_update" in action or "update_results" in action:
                spec = action.get("results_update") or action.get("update_results") or {}
                step_name = spec.get("step", "results:update") if isinstance(spec, dict) else "results:update"
                payload = _flat_env(env)
                if isinstance(spec, dict) and isinstance(spec.get("extra"), dict):
                    payload = {**payload, **spec["extra"]}
                if hasattr(ctx.writer, "write_result"):
                    ctx.writer.write_result(test_name, step_name, payload)  # type: ignore[attr-defined]
                else:
                    ctx.writer.write_point(test_name, step_name, payload)
            elif "transform" in action:
                if ctx.transform is None:
                    raise RuntimeError("Transform action requested but no transform handler configured")
                spec = action["transform"]
                method = spec["method"]
                raw_args = spec.get("args", {})
                if not isinstance(raw_args, dict):
                    raise ValueError("Transform args must be a mapping")
                resolved_args = {k: _resolve(ctx, env, v) for k, v in raw_args.items()}
                payload = ctx.transform(method, resolved_args, ctx.cal_cache)
                if not isinstance(payload, dict):
                    raise ValueError(f"Transform '{method}' returned non-dict payload")
                save_as = spec.get("save_as")
                if save_as:
                    _set_mapping_value(env, save_as, payload)
                out_payload = {"method": method, **payload, **_flat_env(env)}
                ctx.writer.write_point(test_name, f"transform:{method}", out_payload)
            elif "plot_reset" in action:
                suffix = action["plot_reset"].get("suffix", "snap")
                if hasattr(ctx.writer, "snapshot"):
                    ctx.writer.snapshot(_resolve(ctx, env, suffix))
                if hasattr(ctx.writer, "reset"):
                    ctx.writer.reset()
            elif "calibrate" in action:
                spec = action["calibrate"]
                name = spec["name"]
                force = bool(spec.get("force", False))

                # cal constants from file in dict form 
                cached = ctx.cal_cache.get(name)
                if cached is None and not force:
                    cached = ctx.cal_store.get(name)

                if cached is not None and not force:
                    ctx.cal_cache[name] = cached
                    _set_mapping_value(env, name, cached)
                    ctx.writer.write_point(
                        test_name,
                        f"calibration:{name}",
                        {"method": "calibration", "status": "reuse", "value": cached},
                    )
                    continue

                _run_actions(test_name, spec.get("do"), env, ctx)

                if "save" not in spec:
                    raise ValueError(f"Calibration '{name}' must define a 'save' field")

                value = _resolve(ctx, env, spec["save"])
                ctx.cal_cache[name] = value
                ctx.cal_store.set(name, value)
                ctx.cal_store.save()
                _set_mapping_value(env, name, value)
                ctx.writer.write_point(
                    test_name,
                    f"calibration:{name}",
                    {"method": "calibration", "status": "update", "value": value},
                )
            else:
                raise ValueError(f"Unknown action: {action}")
        except KeyboardInterrupt as exc:
            if ctx.interrupt_policy == "shutdown":
                for inst in ctx.instruments.values():
                    if hasattr(inst, "safe_off"):
                        inst.safe_off()
            if ctx.interrupt_policy == "pause":
                ans = input(
                    f"Error: {exc}\nPress Enter to continue, or type 'q' to quit: "
                )
                if ans.strip().lower() == "q":
                    for inst in ctx.instruments.values():
                        if hasattr(inst, "safe_off"):
                            inst.safe_off()
                    raise SystemExit("User requested shutdown.")
                break
            if ctx.interrupt_policy == "continue":
                continue
        except Exception:
            if ctx.fail_policy == "shutdown":
                for inst in ctx.instruments.values():
                    if hasattr(inst, "safe_off"):
                        inst.safe_off()
            if ctx.fail_policy == "continue":
                continue
            raise


def _num_points(start: float, stop: float, step: float) -> int:
    if step == 0:
        raise ValueError("Sweep step cannot be zero")
    return int(math.floor((stop - start) / step)) + 1


def _resolve(ctx: Context, env: Dict[str, Any], value: Any) -> Any:
    if isinstance(value, str):
        return _subst(ctx, env, value)
    if isinstance(value, list):
        return [_resolve(ctx, env, item) for item in value]
    if isinstance(value, dict):
        return {k: _resolve(ctx, env, v) for k, v in value.items()}
    return value


def _subst(ctx: Context, env: Dict[str, Any], token: str) -> Any:
    if token.startswith("${") and token.endswith("}"):
        key = token[2:-1]
        if key.startswith("cal."):
            path = key[4:]
            root, *rest = path.split(".")
            value = ctx.cal_cache.get(root)
            if value is None:
                value = ctx.cal_store.get(root)
                if value is not None:
                    ctx.cal_cache[root] = value
            return _walk(value, rest)
        return _walk(env, key.split("."))
    return token


def _walk(value: Any, path: List[str]) -> Any:
    current = value
    for segment in path:
        if current is None:
            return None
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            return None
    return current


def _set_mapping_value(target: Dict[str, Any], dotted_key: str, value: Any) -> None:
    parts = dotted_key.split(".")
    cursor: Dict[str, Any] = target
    for part in parts[:-1]:
        next_val = cursor.get(part)
        if not isinstance(next_val, dict):
            next_val = {}
            cursor[part] = next_val
        cursor = next_val
    cursor[parts[-1]] = value


def _flat_env(env: Dict[str, Any]) -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    def walk(prefix, data):
        for k, v in data.items():
            name = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                walk(name, v)
            else:
                flat[name] = v
    walk("", env)
    return flat
