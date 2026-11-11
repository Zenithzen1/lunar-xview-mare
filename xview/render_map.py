"""Render the nadir map (map.png) of a batch's terrain, offline, from the north-up DEM.

    python xview/render_map.py --batch data/batch01 [--split train]

Writes <batch>/public_release/<split>/map/map.png and <split>_map_metadata.json.

How: Terrain Studio's sun_shadows.py (pure numpy): cast shadows by sweeping
along the light, then Lambert shading (cosine of the incidence angle on the
local slope). The map is one pixel per DEM cell, so it is exactly 5 m/px and
pixel (u, v) is DEM cell (u, v): no resampling, no registration error.

Sun: compass azimuth 90 deg (from the East), elevation 20 deg, as the challenge
states for its maps. sun_shadows' azimuth is clockwise from the top of the
image, which for a north-up DEM is the compass azimuth, so no conversion.
TODO: check on the real map that their "90" actually means East.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from frames import MapGeometry

MARE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MARE / "Unreal-Moon-Terrain-Generation" / "Terrain_Studio" / "generator"))
import sun_shadows  # noqa: E402

MAP_SUN = (90.0, 20.0)   # compass azimuth, elevation (challenge Data page)


def to_uint8(light):
    """Placeholder: linear 0..1 -> gamma 1/2.2 -> 0..255. Flat ground at 20 deg sun
    comes out ~157, shadows 0. Match to the real map.png when the data is out."""
    return np.rint(255.0 * np.clip(light, 0.0, 1.0) ** (1 / 2.2)).astype(np.uint8)


def render(dem, res, sun=MAP_SUN):
    shadow = sun_shadows.cast_shadows(dem, res, *sun)
    return sun_shadows.illumination(dem, res, *sun, shadow=shadow), shadow


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch", required=True)
    ap.add_argument("--split", default="train")
    a = ap.parse_args()
    batch = Path(a.batch)
    g = json.loads((batch / "terrain" / "geometry.json").read_text())
    geom = MapGeometry(g["width"], g["height"], g["res"], g["xmin"], g["ymax"])
    dem = np.load(batch / "terrain" / "dem_northup.npy")
    assert dem.shape == (geom.height, geom.width)

    light, shadow = render(dem, geom.res)
    out = batch / "public_release" / a.split / "map"
    out.mkdir(parents=True, exist_ok=True)
    Image.fromarray(to_uint8(light), mode="L").save(out / "map.png")
    (out / f"{a.split}_map_metadata.json").write_text(
        json.dumps({"bounds_metres": geom.bounds()}, indent=2))
    print(f"map {geom.width} x {geom.height} px, sun {MAP_SUN}, "
          f"{shadow.mean():.1%} of cells in cast shadow -> {out}")


if __name__ == "__main__":
    main()
