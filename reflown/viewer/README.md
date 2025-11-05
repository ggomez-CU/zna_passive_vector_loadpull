Loadpull Viewer (PySide6 + pyqtgraph)
=====================================

Standalone, read-only GUI (PySide6 + pyqtgraph) to browse and plot measurement runs under
`runs/<test_type>/<YYYYMMDD_HHMMSS>/`, reading `data.jsonl` or `data.csv` (fallback: `results.jsonl`),
along with `bench.yaml` and `test.toml`.

Highlights
- Panels (dockable): Runs, Filters, Metadata, Issues
- Center: multi-plot layout per test type (multiple plots visible)
- Filters: freq/power/bias; Metadata: checkbox tree for series + Detail slider (decimation)
- Toolbar: folder picker, Lin/Log toggle, Export (PNG/SVG/CSV)
- Watches folder for new runs (polling), persists last folder via QSettings

Run it
- Dev mode (without install):
  - PowerShell: `$env:PYTHONPATH = "viewer"; python -m loadpull_viewer.app`
- After installing this package: `lp-view`

Structure
- `loadpull_viewer/app.py` — main window, docking layout, watcher
- `loadpull_viewer/ui/` — widgets: run browser, filters, metadata, issues, toolbar, plot area
- `loadpull_viewer/data/` — discovery, lazy loaders, stride decimation
- `loadpull_viewer/testtypes/` — per-test presets/layout (VectorReceiver example)


Bash
```
cd viewer
pip install -e .
lp-view

```
