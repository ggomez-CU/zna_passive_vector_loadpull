from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List
import json
import matplotlib.pyplot as plt
from .results import JsonlWriter
import numpy as np


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
    x_key: str | None
    y_keys: List[str]
    refresh: bool
    x_vals: List[float]
    y_series: List[List[float]]
    lines: List[Any]


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
        if not isinstance(axs, (list, tuple, np.ndarray)):
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
                y_keys = [p]
                refresh = True
            else:
                title = p.get('title', f'panel_{i}')
                x_key = p.get('x')
                raw_y = p.get('y')
                if isinstance(raw_y, (list, tuple)):
                    y_keys = [str(k) for k in raw_y]
                elif raw_y is None:
                    y_keys = []
                else:
                    y_keys = [str(raw_y)]
                refresh = p.get('refresh', True)
            ax.set_title(title)
            ax.grid(True, which='both', linestyle=':')
            self.panels.append(_PanelState(ax=ax, title=title, x_key=x_key, y_keys=y_keys, refresh=refresh, x_vals=[], y_series=[[] for _ in y_keys], lines=[]))
        self._panel_count = len(self.panels)
        self._idx = 0 # fallback x when no x_key

    def write_point(self, test: str, step: str, data: dict) -> None:
        # Save line to JSONL first
        super().write_point(test, step, data)
        # Update live plots
        rec = data # already includes sweep vars
        for st in self.panels:
            if not st.y_keys:
                continue
            # Resolve x value
            x_val = _get(rec, st.x_key) if st.x_key else self._idx
            if st.refresh:
                # Expect sequences for refresh mode
                try:
                    xs = [float(xd) for xd in x_val]
                except TypeError:
                    # Single scalar, coerce to list
                    try:
                        xs = [float(x_val)]
                    except (TypeError, ValueError):
                        continue
                y_lists: List[List[float]] = []
                ok = True
                for y_key in st.y_keys:
                    y_val = _get(rec, y_key)
                    try:
                        ys = [float(yd) for yd in y_val]
                    except TypeError:
                        try:
                            ys = [float(y_val)]
                        except (TypeError, ValueError):
                            ok = False
                            break
                    y_lists.append(ys)
                if not ok:
                    continue
                st.x_vals = xs
                # Resize y_series container if needed
                if len(st.y_series) != len(y_lists):
                    st.y_series = [[] for _ in range(len(y_lists))]
                for i, ys in enumerate(y_lists):
                    st.y_series[i] = ys
            else:
                # Append scalar point
                try:
                    x_scalar = float(x_val)
                except (TypeError, ValueError):
                    continue
                st.x_vals.append(x_scalar)

                y_scalars: List[float] = []
                ok = True
                for y_key in st.y_keys:
                    y_val = _get(rec, y_key)
                    try:
                        y_scalars.append(float(y_val))
                    except (TypeError, ValueError):
                        ok = False
                        break
                if not ok:
                    continue

                # Ensure container size
                if len(st.y_series) != len(st.y_keys):
                    print("y reformat")
                    st.y_series = [[] for _ in st.y_keys]
                for i, yv in enumerate(y_scalars):
                    st.y_series[i].append(yv)

            # Draw or update lines
            if not st.lines:
                labels = [yk for yk in st.y_keys]
                st.lines = []
                for ys, label in zip(st.y_series, labels):
                    (line,) = st.ax.plot(st.x_vals, ys, marker='o', linewidth=1, label=label)
                    st.lines.append(line)
                st.ax.set_xlabel(st.x_key or 'index')
                st.ax.set_ylabel(st.title)
                if len(st.lines) > 1:
                    st.ax.legend(loc='best', fontsize='small')
                st.ax.relim(); st.ax.autoscale_view(tight=True)
            else:
                for line, ys in zip(st.lines, st.y_series):
                    line.set_data(st.x_vals, ys)
                st.ax.relim(); st.ax.autoscale_view(tight=True)
        self._idx += 1
        # self.fig.canvas.draw_idle()
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()
        plt.pause(1)


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
