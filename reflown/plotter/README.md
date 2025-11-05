Loadpull Plotter (modular)
==========================

Standalone, read-only GUI to browse and plot measurement runs under
`runs/<test_type>/<YYYYMMDD_HHMMSS>/` using PySide6 + pyqtgraph.

Highlights
- Dock panels: Runs (check to select), Filters, Metadata, Issues
- Center plot deck with per–test type multi-plot layouts (tabs)
- Large file handling: lazy, stride decimation, progress bar
- Toolbar: root folder picker, Lin/Log toggle, Export PNG/SVG/CSV
- Watches folder periodically; persists last root

Run
- Dev (no install):
  - PowerShell: `$env:PYTHONPATH = "plotter"; python -m plotter.app`
- Install: `cd plotter && pip install -e . && lp-plotter`

Structure
- plotter/app.py           — Main window, docks, wiring
- plotter/settings.py      — QSettings wrapper
- plotter/data/            — discovery, models, loaders
- plotter/ui/              — toolbar and panels (runs/filters/metadata/issues)
- plotter/plots/           — plot deck (tabs) and rendering
- plotter/testtypes/       — per-test presets (tabs/specs)


