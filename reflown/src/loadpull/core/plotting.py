from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List
import json
import matplotlib.pyplot as plt
from .results import JsonlWriter
import numpy as np


def _get(record: Dict[str, Any], keypath: str, default: Any = None) -> Any:
    """Resolve dotted key paths from nested dicts, with a fallback to flat dotted keys.

    Supports both structures:
      - nested: {"wave_data": {"a1": {"real": [...]}}}
      - flattened: {"wave_data.a1.real": [...]}
    """
    if isinstance(record, dict) and keypath in record:
        return record[keypath]
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
    angle_keys: List[str]
    mag_keys: List[str]
    refresh: bool
    polar: bool
    x_vals: List[float]
    y_series: List[List[float]]
    angles_series: List[List[float]]
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
                angle_keys: List[str] = []
                mag_keys: List[str] = []
                refresh = True
                polar = False
            else:
                title = p.get('title', f'panel_{i}')
                x_key = p.get('x')
                raw_y = p.get('y')
                raw_angles = p.get('angle_rad')
                raw_mags = p.get('mag')
                if isinstance(raw_y, (list, tuple)):
                    y_keys = [str(k) for k in raw_y]
                elif raw_y is None:
                    y_keys = []
                else:
                    y_keys = [str(raw_y)]
                if isinstance(raw_angles, (list, tuple)):
                    angle_keys = [str(k) for k in raw_angles]
                elif raw_angles is None:
                    angle_keys = []
                else:
                    angle_keys = [str(raw_angles)]
                if isinstance(raw_mags, (list, tuple)):
                    mag_keys = [str(k) for k in raw_mags]
                elif raw_mags is None:
                    mag_keys = []
                else:
                    mag_keys = [str(raw_mags)]
                if angle_keys or mag_keys:
                    if len(angle_keys) != len(mag_keys):
                        raise ValueError("Polar panels must define equal counts of 'mag' and 'angle_rad' entries")
                refresh = p.get('refresh', True)
                polar = bool(p.get('polar', False) or (angle_keys and mag_keys))

            # Replace axis with polar projection if requested
            if polar:
                try:
                    self.fig.delaxes(ax)
                except Exception:
                    pass
                ax = self.fig.add_subplot(rows, cols, i + 1, projection='polar')
                # Enforce unit circle (r in [0,1])
                try:
                    ax.set_rlim(0, 1)
                except Exception:
                    pass

            ax.set_title(title)
            ax.grid(True, which='both', linestyle=':')
            self.panels.append(
                _PanelState(
                    ax=ax,
                    title=title,
                    x_key=x_key,
                    y_keys=y_keys,
                    angle_keys=angle_keys if polar else [],
                    mag_keys=mag_keys if polar else [],
                    refresh=refresh,
                    polar=polar,
                    x_vals=[],
                    y_series=[[] for _ in (mag_keys if polar else y_keys)],
                    angles_series=[[] for _ in (mag_keys if polar else [])],
                    lines=[],
                )
            )
        self._panel_count = len(self.panels)
        self._idx = 0 # fallback x when no x_key

    def write_point(self, test: str, step: str, data: dict) -> None:
        # Save line to JSONL first
        super().write_point(test, step, data)
        # Update live plots
        rec = data # already includes sweep vars
        for st in self.panels:
            if not st.y_keys and not (st.polar and st.angle_keys and st.mag_keys):
                continue
            if st.polar and st.angle_keys and st.mag_keys:
                # New polar input: angle/mag pairs
                angles_list: List[List[float]] = []
                mags_list: List[List[float]] = []
                labels: List[str] = []
                for a_key, m_key in zip(st.angle_keys, st.mag_keys):
                    ang_val = _get(rec, a_key)
                    mag_val = _get(rec, m_key)
                    try:
                        angs = [float(v) for v in ang_val]
                    except TypeError:
                        try:
                            angs = [float(ang_val)]
                        except (TypeError, ValueError):
                            continue
                    try:
                        mags = [float(v) for v in mag_val]
                    except TypeError:
                        try:
                            mags = [float(mag_val)]
                        except (TypeError, ValueError):
                            continue
                    if len(angs) != len(mags):
                        continue
                    angles_list.append(angs)
                    mags_list.append(mags)
                    labels.append(m_key)
                if not angles_list:
                    continue
                st.angles_series = angles_list
                st.y_series = mags_list
                # Keep labels aligned with filtered pairs
                st.mag_keys = labels
                if len(st.lines) and len(st.lines) != len(st.y_series):
                    st.lines = []
            else:
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
                        st.y_series = [[] for _ in st.y_keys]
                    for i, yv in enumerate(y_scalars):
                        st.y_series[i].append(yv)

            # Draw or update lines
            if not st.lines:
                labels = st.mag_keys if (st.polar and st.mag_keys) else [yk for yk in st.y_keys]
                st.lines = []
                if st.polar:
                    import numpy as _np
                    data_pairs = zip(st.angles_series, st.y_series)
                    for angs, mags, label in zip(st.angles_series, st.y_series, labels):
                        offs = _np.c_[angs, mags]
                        coll = st.ax.scatter(offs[:, 0], offs[:, 1], s=16, label=label)
                        st.lines.append(coll)
                else:
                    for ys, label in zip(st.y_series, labels):
                        (line,) = st.ax.plot(st.x_vals, ys, marker='o', linewidth=1, label=label)
                        st.lines.append(line)
                if not st.polar:
                    st.ax.set_xlabel(st.x_key or 'index')
                    st.ax.set_ylabel(st.title)
                if len(st.lines) > 1:
                    st.ax.legend(loc='best', fontsize='small')
                if not st.polar:
                    st.ax.relim(); st.ax.autoscale_view(tight=True)
            else:
                if st.polar:
                    import numpy as _np
                    for coll, angs, mags in zip(st.lines, st.angles_series, st.y_series):
                        offs = _np.c_[angs, mags]
                        coll.set_offsets(offs)
                else:
                    for line, ys in zip(st.lines, st.y_series):
                        line.set_data(st.x_vals, ys)
                if not st.polar:
                    st.ax.relim(); st.ax.autoscale_view(tight=True)
        self._idx += 1
        self.fig.canvas.draw_idle()
        # self.fig.canvas.draw()
        # self.fig.canvas.flush_events()
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
