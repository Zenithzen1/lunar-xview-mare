"""Make a procedural terrain for a synthetic batch, using Terrain Studio's generator.

    python xview/make_terrain.py --out data/batch01 --size 1200 --seed 1

Writes to <out>/terrain/:
    dem_northup.npy   north-up DEM (row 0 = north), metres; used for map.png
    dem_unreal.npy    np.flipud of it; this is the file sent to Terrain Studio (resolution 5.0)
    geometry.json     width, height, res, xmin, ymax (map frame, (0, 0) at the centre)
    terrain.json      generator parameters, seed, crater count, elevation range

Stopgap until we have real 5 m DEMs (the challenge uses perturbed real DEMs).

Why CRATER_DEPTH_RATIO is scaled: Terrain Studio computes crater depth as
radius_in_PIXELS * ratio, so its defaults (tuned at 1 m/px) give craters 5x too
shallow at 5 m/px. We multiply the ratio by the resolution, so depth = 0.25 *
radius in metres, as at 1 m/px: rim-to-floor depth / diameter about 0.16.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

from frames import MapGeometry, dem_for_unreal

MARE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MARE / "Unreal-Moon-Terrain-Generation" / "Terrain_Studio" / "generator"))
import terrain_core  # noqa: E402

RES = 5.0
MIN_ELEVATION_M = 100.0   # Terrain Studio treats elevation exactly 0 as no-data; keep well clear


def make(out, size, seed):
    params = terrain_core.default_params()
    params.update({
        "ROWS": size, "COLS": size,
        "RESOLUTION_M_PER_PX": RES,
        "CRATER_DEPTH_RATIO": params["CRATER_DEPTH_RATIO"] * RES,   # see module docstring
    })
    result = terrain_core.generate_terrain(params, seed=seed,
                                           progress=lambda m, f: print(f"  {f:4.0%} {m}"))
    dem = result["elevation"]
    dem = dem - dem.min() + MIN_ELEVATION_M          # shift only: shapes unchanged

    # The generator's grid has no north: we declare row 0 = north.
    geom = MapGeometry.centred(size, size, RES)
    tdir = Path(out) / "terrain"
    tdir.mkdir(parents=True, exist_ok=True)
    np.save(tdir / "dem_northup.npy", dem)
    np.save(tdir / "dem_unreal.npy", dem_for_unreal(dem))
    (tdir / "geometry.json").write_text(json.dumps(
        {"width": geom.width, "height": geom.height, "res": geom.res, **geom.bounds()}, indent=2))
    info = {
        "source": "Terrain Studio terrain_core.generate_terrain (procedural)",
        "seed": result["seed"],
        "crater_count": result["crater_count"],
        "params": params,
        "elevation_min_m": float(dem.min()), "elevation_max_m": float(dem.max()),
        "extent_m": [geom.res * size, geom.res * size],
    }
    (tdir / "terrain.json").write_text(json.dumps(info, indent=2))
    print(f"{size} x {size} px at {RES} m/px = {size * RES / 1000:.1f} km square, "
          f"{result['crater_count']} craters, elevation {dem.min():.1f} to {dem.max():.1f} m")
    print(f"wrote {tdir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="batch folder, e.g. data/batch01")
    ap.add_argument("--size", type=int, default=1200, help="DEM width = height in px (1200 = 6 km)")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    make(a.out, a.size, a.seed)
