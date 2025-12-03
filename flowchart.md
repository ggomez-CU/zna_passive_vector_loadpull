# Sequencer Flow (detailed)

## Boot / Session
```text
BenchConfig.from_toml -> Session(bench, out_dir)
    |
    |-- mkdir out_dir; create JsonlWriter(results.jsonl)
    |-- cal_store = CalibrationStore("calibration/<bench>.json")
    |-- meta (schema, bench, ts) -> manifest.json (later)
```

## Load + run a test
```text
Sequence.load(spec.yaml) -> Sequence.run(ctx)
    |
    |-- params defaults -> env
    |-- steps list -> _run_actions(test_name, steps, env, ctx)
```

## Action dispatcher (per step)
```text
_run_actions:
  for action in steps:
    - sweep:
        compute points (from,to,step)
        loop var=point -> recurse into sweep.do actions

    - call:
        resolve args (env + ${cal.*} substitution)
        inst = ctx.instruments[inst]; result = inst.method(*args)
        optional save_as -> env
        writer.write_point("call:<method>", payload)

    - measure:
        resolve args; val = inst.method(*args)
        save_as (default method name) -> env
        writer.write_point("measure:<method>", payload)

    - results_update / update_results:
        payload = flattened env
        optional limits: evaluate -> may shutdown or annotate violations
        writer.write_result(...) if available else write_point("results:update")

    - transform:
        ctx.transform(method, resolved args, cal_cache) -> dict
        optional save_as -> env
        writer.write_point("transform:<method>", payload)

    - plot_reset:
        writer.snapshot(suffix) if present; writer.reset() if present

    - calibrate:
        name, force flag
        try cal_cache[name] (or cal_store.get) unless force
        if found: reuse -> writer.write_point("calibration:<name>", status=reuse)
        else:
            run calibrate.do actions (same dispatcher)
            value = resolve(calibrate.save)
            cal_cache[name] = value
            cal_store.set(name, value); cal_store.save()
            writer.write_point("calibration:<name>", status=update, value)

    - else: error unknown action
```

## Data sinks
```text
results.jsonl     <- JsonlWriter streams points/results per step
manifest.json     <- Session.record_manifest(meta + hash)
calibration/<bench>.json <- CalibrationStore persists cal constants (+__history__)
```

Notes:
- `${cal.foo}` tokens resolve via cal_cache then cal_store; other `${...}` resolve from env.
- Sweeps recurse, so nested actions run for each point.
- fail_policy/interrupt_policy control shutdown/continue on errors or Ctrl+C.
