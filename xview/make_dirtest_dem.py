"""Direction test terrain: flat ground with blocks at known compass positions.

2005 m square at 5 m/px (401 x 401), camera point (0, 0) at the centre pixel.
Each block has a different height, so we can tell which one is which:
    N  (0, +100)        40 m tall, 25 m wide (5 px)
    E  (+100, 0)        30 m
    S  (0, -100)        20 m
    W  (-100, 0)        10 m
    NE (+105, +105)     60 m tall, 45 m wide (9 px) (the "tall block to the NE")
Writes to data/dirtest/:
    dirtest_northup.npy   north-up DEM (row 0 = north), used for map.png
    dirtest_unreal.npy    np.flipud of it, sent to Terrain Studio
    dirtest_points.json   each block's map x, y and predicted Unreal X, Y
"""
import json
from pathlib import Path

import numpy as np

from frames import MapGeometry, dem_for_unreal

BASE_M = 100.0  # Terrain Studio treats elevation exactly 0 as no-data
BLOCKS = {  # name: (x_m, y_m, height_m, half_width_px)
    "N": (0.0, 100.0, 40.0, 2),
    "E": (100.0, 0.0, 30.0, 2),
    "S": (0.0, -100.0, 20.0, 2),
    "W": (-100.0, 0.0, 10.0, 2),
    "NE": (105.0, 105.0, 60.0, 4),
}

out = Path(__file__).resolve().parent.parent / "data" / "dirtest"
out.mkdir(parents=True, exist_ok=True)

g = MapGeometry.centred(401, 401)
dem = np.full((g.height, g.width), BASE_M)
points = {"geometry": {"width": g.width, "height": g.height, "res": g.res, **g.bounds()}, "points": {}}

for name, (x, y, h, hw) in BLOCKS.items():
    u, v = (int(round(float(a))) for a in g.map_to_pixel(x, y))
    dem[v - hw:v + hw + 1, u - hw:u + hw + 1] = BASE_M + h
    X, Y = g.map_to_unreal_cm(x, y)
    points["points"][name] = {"x": x, "y": y, "height_m": h, "u": u, "v": v,
                              "unreal_X_cm": float(X), "unreal_Y_cm": float(Y)}

X, Y = g.map_to_unreal_cm(0.0, 0.0)
points["points"]["camera"] = {"x": 0.0, "y": 0.0, "height_m": 0.0,
                              "unreal_X_cm": float(X), "unreal_Y_cm": float(Y)}

np.save(out / "dirtest_northup.npy", dem)
np.save(out / "dirtest_unreal.npy", dem_for_unreal(dem))
(out / "dirtest_points.json").write_text(json.dumps(points, indent=2))
print(json.dumps(points, indent=2))
