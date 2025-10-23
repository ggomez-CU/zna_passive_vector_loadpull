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
- Get-Content runs\test_VNA\2025-10-21_1126\results.jsonl | ForEach-Object { $_ | ConvertFrom-Json | ConvertTo-Json -Depth 10 }
- loadpull run testspecs\calibrate_DMM1.yaml --bench benches\bench_validation_codebase.toml