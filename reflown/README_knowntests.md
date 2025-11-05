### Quickstart


```bash
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\.venv\Scripts\Activate.ps1
pip install -e .
loadpull list-tests
```

## Easy copy paste tests

- loadpull run testspecs\test_instruments\test_registry.yaml --bench benches\bench_validation_codebase.toml 
- loadpull run testspecs\test_instruments\test_VNA.yaml --bench benches\bench_validation_codebase.toml 
- loadpull run testspecs\test_instruments\test_TUNER.yaml --bench benches\bench_validation_codebase.toml 
- loadpull run testspecs\test_instruments\test_VectorReceiver.yaml --bench benches\bench_validation_codebase.toml 
- Get-Content runs\calibrate_VNA\2025-10-24_1449\results.jsonl | ForEach-Object { $_ | ConvertFrom-Json | ConvertTo-Json -Depth 10 }
- loadpull run testspecs\calibrate_DMM1.yaml --bench benches\bench_validation_codebase.toml


PowerShell loop (same bench for all)

- Current folder only:
Get-ChildItem testspecs\test_instruments -Filter *.yaml | ForEach-Object { loadpull run $_.FullName --bench benches\bench_validation_codebase.toml }
Include subfolders:
Get-ChildItem testspecs -Recurse -Filter *.yaml | ForEach-Object { loadpull run $_.FullName --bench benches\bench_validation_codebase.toml }
Filter by name (e.g., only “test_*.yaml”):
Get-ChildItem testspecs -Filter test_*.yaml | ForEach-Object { loadpull run $_.FullName --bench benches\bench_validation_codebase.toml }


Generate Load Sweep
python -m src.loadpull.tools.make_load_sweep --center-mag 0.25 --center-deg -90 --radii 0.0,0.05,0.1,0.2,0.3 --angle-start -180 --angle-stop 180 --resolution fine --out loadsweeps/load_sweep.csv
Same number of points for each ring:
python -m src.loadpull.tools.make_load_sweep --center-mag 0 --center-deg 0 --radii 0.0,0.1,0.2,0.3,0.4,0.5 --points-per-ring 9 --angle-start -180 --angle-stop 180 --out loadsweeps/test_Tuner_sweep_long.csv
Fixed 10° angular step for all rings:
python -m src.loadpull.tools.make_load_sweep --center-mag 0.2 --center-deg -90 --radii 0.0,0.05,0.1,0.2,0.3 --deg-step 10 --angle-start -180 --angle-stop 180 --out loadsweeps/circle_10deg.csv
Default preset (unchanged):
python -m src.loadpull.tools.make_load_sweep --center-mag 0.2 --center-deg -90 --radii 0.0,0.05,0.1,0.2,0.3 --resolution ultra --out loadsweeps/circle_ultra.csv

Calibrate
loadpull run testspecs\calibrate\calibrate_TUNER.yaml --bench benches\bench_validation_codebase.toml
loadpull run testspecs\calibrate\calibrate_VNA.yaml --bench benches\bench_validation_codebase.toml