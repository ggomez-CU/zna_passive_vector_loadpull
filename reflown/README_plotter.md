Plotter app quick info
- Purpose: standalone, read-only GUI (PySide6 + pyqtgraph) for browsing and plotting runs under `runs/<test_type>/<timestamp>/`. Source lives in `plotter/plotter`, launcher entrypoint is `plotter.app:main`
- Run without install: from repo root `PYTHONPATH=plotter python -m plotter.app` (PowerShell: `$env:PYTHONPATH = "plotter"; python -m plotter.app`). Install + CLI: `cd plotter && pip install -e . && lp-plotter`
- Database location: SQLite file `runs/plotter_database.sqlite` (path is resolved in `plotter/data/discovery.py`). If you move the repo, pass `--db` when populating to avoid the baked absolute default
- Reinstantiate the database:
  1) Remove or rename `runs/plotter_database.sqlite`
  2) From repo root, repopulate from on-disk runs: `python -m plotter.populate_db --root plotter --db runs/plotter_database.sqlite`
     - Script ingests `results.jsonl` (or `data.jsonl`/`data.csv`) from every run folder and refreshes per-test schemas
     - Output warns if runs exist on disk but not in the DB or vice versa
- Key modules: `plotter/data/discovery.py` (DB + FS discovery), `plotter/data/ingest.py` (ingest pipeline), `plotter/database/sqlite_store.py` (schema + writes), `plotter/plots/` (rendering)