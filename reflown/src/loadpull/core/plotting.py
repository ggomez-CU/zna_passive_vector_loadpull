from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List
import json
import matplotlib.pyplot as plt
from .results import JsonlWriter


def _get(record: Dict[str, Any], keypath: str, default: Any = None) -> Any:
    cur: Any = record
    for part in keypath.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur

@dataclass
class _PanelState:
    ax: Any
    title: str
    x_key: str
    y_key: str
    xs: List[float]
    ys: List[float]
    line: Any | None = None


class LivePlotWriter(JsonlWriter):
    """Live-updating plot writer with dynamic subplot grid.


    Pass a layout dict from testspec['plot']: {'rows','cols','panels': [...]}
    Each panel is either a string keypath (plotted vs index) or a dict with x/y keypaths.
    """
    def __init__(self, path: Path, layout: Dict[str, Any]):
        super().__init__(path)
        self.layout = layout or {}
        rows = int(self.layout.get('rows', 1))
        cols = int(self.layout.get('cols', 1))
        panels = self.layout.get('panels', [])
        plt.ion()
        self.fig, axs = plt.subplots(rows, cols, figsize=(4*cols, 3*rows))
        if not isinstance(axs, (list, tuple)):
            # axs is a single Axes when rows==cols==1
            axs = [axs]
        else:
            axs = [ax for sub in (axs if isinstance(axs, list) else axs.ravel()) for ax in (sub if isinstance(sub, list) else [sub])]
        self.panels: List[_PanelState] = []
        # Build panel states
        for i, p in enumerate(panels):
            ax = axs[i]
            if isinstance(p, str):
                title = p
                x_key = None
                y_key = p
            else:
                title = p.get('title', f'panel_{i}')
                x_key = p.get('x')
                y_key = p.get('y')
            ax.set_title(title)
            ax.grid(True, which='both', linestyle=':')
            self.panels.append(_PanelState(ax=ax, title=title, x_key=x_key, y_key=y_key, xs=[], ys=[], line=None))
        self._panel_count = len(self.panels)
        self._idx = 0 # fallback x when no x_key

    def write_point(self, test: str, step: str, data: dict) -> None:
    # Save line to JSONL first
    super().write_point(test, step, data)
    # Update live plots
    rec = data # already includes sweep vars
    for st in self.panels:
        # Determine x, y
        if st.y_key:
            y = _get(rec, st.y_key)
        else:
            y = None
        if st.x_key:
            x = _get(rec, st.x_key)
        else:
            x = self._idx
        if y is None:
            continue
        try:
            st.xs.append(float(x))
            st.ys.append(float(y))
        except (TypeError, ValueError):
            # Skip non-numeric points
            continue
        if st.line is None:
            (st.line,) = st.ax.plot(st.xs, st.ys, marker='o', linewidth=1)
            st.ax.set_xlabel(st.x_key or 'index')
            st.ax.set_ylabel(st.y_key or st.title)
        else:
            st.line.set_data(st.xs, st.ys)
            st.ax.relim(); st.ax.autoscale_view()
    self._idx += 1
    self.fig.canvas.draw_idle()
    plt.pause(0.01)


    def snapshot(self, suffix):  # save PNG
        self.fig.savefig(self.path.with_name(f"{self.path.stem}_{suffix}.png"), dpi=150)
    def reset(self):             # close & reinit
        import matplotlib.pyplot as plt; plt.close(self.fig); self.__init__(self.path, self.layout)

    def close(self):
        try:
            # Save a snapshot alongside results
            out_png = self.path.with_suffix('.png')
            self.fig.savefig(out_png, dpi=150, bbox_inches='tight')
        except Exception:
            pass
            finally:
                try:
                    plt.ioff()
                except Exception:
                    pass
            super().close()