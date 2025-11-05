from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import List


def _parse_radii(s: str) -> List[float]:
    if not s:
        return []
    return [float(x) for x in s.split(',') if x.strip()]


def _points_for_radius(radius: float, max_radius: float, mode: str, fixed_n: int | None, deg_step: float | None, span_deg: float) -> int:
    mode = (mode or 'coarse').strip().lower()
    outer = 54 if mode == 'ultra' else 36 if mode == 'fine' else 18
    if max_radius <= 0:
        return 1
    if fixed_n is not None and fixed_n > 0:
        return max(1, int(fixed_n))
    if deg_step is not None and deg_step > 0:
        n = int(max(1, round(abs(span_deg) / float(deg_step))))
        return n
    # Scale linearly with radius; ensure at least 6 for nonzero radii
    n = int(round(outer * (radius / max_radius)))
    return max(6, n)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a CSV of Gamma (S11) points for load-pull sweeps.")
    ap.add_argument('--center-mag', type=float, required=True, help='Center |Gamma| (0..1)')
    ap.add_argument('--center-deg', type=float, required=True, help='Center angle (deg)')
    ap.add_argument('--radii', type=str, required=True, help='Comma-separated radii relative to center, e.g., 0.0,0.05,0.1,0.2')
    ap.add_argument('--angle-start', type=float, default=-180.0, help='Start angle (deg) for rings')
    ap.add_argument('--angle-stop', type=float, default=180.0, help='Stop angle (deg) for rings')
    ap.add_argument('--resolution', type=str, choices=['coarse','fine','ultra'], default='coarse', help='Angular resolution preset (ignored if --points-per-ring or --deg-step provided)')
    ap.add_argument('--points-per-ring', type=int, default=None, help='Fixed number of points per non-zero radius ring (overrides --resolution)')
    ap.add_argument('--deg-step', type=float, default=None, help='Fixed angular step in degrees for all rings (overrides --resolution if provided)')
    ap.add_argument('--out', type=str, required=True, help='Output CSV filepath')

    args = ap.parse_args()

    center_mag = float(args.center_mag)
    center_deg = float(args.center_deg)
    center_rad = math.radians(center_deg)
    center = complex(center_mag * math.cos(center_rad), center_mag * math.sin(center_rad))

    radii = _parse_radii(args.radii)
    if 0.0 not in radii:
        radii = [0.0] + radii
    max_r = max(radii) if radii else 0.0

    start = float(args.angle_start)
    stop = float(args.angle_stop)
    # Normalize angle span; avoid duplicate endpoint
    span = stop - start
    if abs(span) <= 0:
        span = 360.0

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open('w', newline='', encoding='utf-8') as fp:
        w = csv.writer(fp)
        w.writerow(['mag','deg','real','imag'])

        # Always write center point once
        w.writerow([
            f"{center_mag:.10g}",
            f"{center_deg:.10g}",
            f"{center.real:.10g}",
            f"{center.imag:.10g}",
        ])

        for r in radii:
            if r <= 0:
                continue
            n = _points_for_radius(r, max_r, args.resolution, args.points_per_ring, args.deg_step, span)
            # Evenly spaced over [start, stop) in degrees
            for i in range(n):
                ang_deg = start + (span * i / n)
                ang = math.radians(ang_deg)
                vec = complex(math.cos(ang), math.sin(ang))
                g = center + r * vec
                mag = abs(g)
                if mag > 1.0 + 1e-12:
                    # drop points outside unit circle
                    continue
                # Convert to principal angle degrees for output
                out_deg = math.degrees(math.atan2(g.imag, g.real))
                w.writerow([
                    f"{mag:.10g}",
                    f"{out_deg:.10g}",
                    f"{g.real:.10g}",
                    f"{g.imag:.10g}",
                ])

    print(f"Wrote {out_path}")


if __name__ == '__main__':
    main()
