# Generating Load Pull Sweeps

### Make a sweep CSV

Here are the different parameters of the sweep:

- `--center-mag` Center |Gamma| for the rings (0..1).
- `--center-deg` Center angle in degrees for the rings.
- `--radii` Comma-separated ring radii relative to center (e.g., `0.0,0.1,0.2`); `0.0` is added if omitted.
- `--angle-start` / `--angle-stop` Start/stop angles (deg) for each ring (default -180/180).
- `--resolution` Angular preset per ring: `coarse` (~18 pts at outer ring), `fine` (~36), `ultra` (~54). Ignored if points-per-ring or deg-step is provided.
- `--points-per-ring` Fixed number of points for each nonzero ring (overrides resolution).
- `--deg-step` Fixed angular step in degrees for all rings (overrides resolution if given).
- `--out` Output CSV path.

From repo root, activate the venv and run the generator. Examples:
```bash
python -m src.loadpull.tools.make_load_sweep --center-mag 0.25 --center-deg -90 --radii 0.25,0.5 --angle-start -180 --angle-stop 180 --resolution coarse --out loadsweeps/load_sweep_attenvalidation.csv
```
  - Same points per ring: 
```bash
python -m src.loadpull.tools.make_load_sweep --center-mag 0 --center-deg 0 --radii 0.0,0.1,0.2,0.3,0.4,0.5 --points-per-ring 9 --angle-start -180 --angle-stop 180 --out loadsweeps/test_Tuner_sweep_long.csv
```
  - Fixed angle step: 
```bash
python -m src.loadpull.tools.make_load_sweep --center-mag 0.2 --center-deg -90 --radii 0.0,0.05,0.1,0.2,0.3 --deg-step 10 --angle-start -180 --angle-stop 180 --out loadsweeps/circle_10deg.csv
```
- The CSV columns expected by the transforms are `mag` and `deg` (optionally real/imag); no header changes needed.

### Use the sweep in a testspec
- Point your YAML to the CSV via a parameter, e.g. in `testspecs/Loadsweep.yaml`:
  - `sweep_file: loadsweeps/load_sweep.csv`
- The provided load-sweep block uses:
  - `transform: {method: load_sweep_len, args: {file: "${sweep_file}"}, save_as: sweep_info}`
  - Sweep `idx` from 0 to `${sweep_info.count}` with `load_sweep_point` to fetch each (mag, deg).
  - `set_gamma` on the tuner with `${point.gamma_mag}`, `${point.gamma_deg}`, then measure (`capture_point`).

### Run it
- `python -m loadpull.cli run testspecs/Loadsweep.yaml --bench benches/bench_default.toml`
- Replace bench path as needed; the bench must define the instruments used (`LOADTUNER`, `VNA`, etc.).

Notes
- No interpolation: the sweep executes exactly the points in the CSV.
- Keep the CSV in `loadsweeps/` (already gitignored in most setups) to avoid cluttering the repo root.
