"""Geometry check of the capture rig (yaw, field of view, pitch, roll). Needs the
editor open on XView_DirTest. Spawns temporary marker cylinders, captures one
ring, checks it, removes the markers.

    python xview/check_ring_geometry.py

predict() below uses the same pinhole projection as stitch.py (step 5).

Why markers and not the terrain blocks: a Landscape cuts each grid square into two
triangles along a fixed diagonal, so a block's sloped sides are not mirror-symmetric
and its silhouette centre is off by up to ~9 px (except when seen along the diagonal).
A cylinder looks the same from every side.

Two captures:
A. Yaw and field of view: capture point (-500, -500) m, well away from the blocks. Markers 2 m wide, 80 m
tall, standing on the flat ground. Measured in image row 100 (about 18 deg up),
where only markers can appear (the blocks are > 600 m away and < 5 deg high).
B. Pitch and roll: capture point (0, 0), no markers. In the cameras with no block
(3, 5, 7: they look diagonally across flat ground) the sky/ground boundary must be
level (spread <= 2 px across the image: roll) and a few px below the centre row
(the terrain ends ~1.4 km away and the camera is 2.5 m up: pitch).
"""
import math
import sys
from pathlib import Path

import numpy as np

import capture_ring as cr
from ring_io import load_sky_masks
from ue_link import UnrealLink

MARE = Path(__file__).resolve().parent.parent
GEOMETRY = MARE / "data" / "dirtest" / "dirtest_points.json"
OUT = MARE / "data" / "dirtest" / "ring_geometry_check"
OUT_CENTRE = MARE / "data" / "dirtest" / "ring_horizon_check"
CAM_XY = (-500.0, -500.0)
GROUND_Z_CM = 10000.0            # flat base of the test terrain (100 m)
DIAMETER, HEIGHT = 200.0, 8000.0
MARKERS = {                      # label: (compass bearing deg, distance m)
    "N": (0, 50), "E": (90, 50), "S": (180, 50), "W": (270, 50),
    "b20": (20, 60), "b200": (200, 60), "b345": (345, 60), "b110": (110, 70),
}
ROW = 100
TOLERANCE_PX = 0.5


def predict(bearing, distance, cam):
    """Expected silhouette centre column of a marker in camera `cam` (pinhole model).
    The silhouette edges are the two tangent rays at bearing +- asin(r / d); their
    image columns are averaged (not the same as projecting the axis, by < 0.4 px)."""
    w, hfov = cam["width"], math.radians(cam["hfov_deg"])
    f = (w / 2) / math.tan(hfov / 2)
    half = math.asin((DIAMETER / 200) / distance)
    cols = []
    for b in (bearing - math.degrees(half), bearing + math.degrees(half)):
        d = math.radians((b - cam["bearing_deg"] + 180) % 360 - 180)
        cols.append((w - 1) / 2 + f * math.tan(d))
    return sum(cols) / 2


def runs(solid):
    """(first, last) column of every run of True."""
    edges = np.flatnonzero(np.diff(np.concatenate([[0], solid.astype(np.int8), [0]])))
    return list(zip(edges[::2], edges[1::2] - 1))


def measure(sky_row, expected):
    """Sub-pixel silhouette centre of the run nearest `expected`. Edge pixels are
    partly covered (sky alpha is averaged over jittered renders), so each edge is
    refined by its coverage."""
    solid = 1.0 - sky_row
    candidates = runs(solid > 0.5)
    if not candidates:
        return None
    first, last = min(candidates, key=lambda r: abs((r[0] + r[1]) / 2 - expected))
    # Edge = pixel boundary, moved inward by the missing coverage of the first/last
    # pixel and outward by the coverage of the pixel just outside the run.
    left = first - 0.5 + (1 - solid[first]) - (solid[first - 1] if first > 0 else 0)
    right = last + 0.5 - (1 - solid[last]) + (solid[last + 1] if last + 1 < len(solid) else 0)
    return (left + right) / 2


def main():
    geom = cr.load_geometry(GEOMETRY)
    with UnrealLink() as link:
        markers = []
        for label, (b, d) in MARKERS.items():
            x = CAM_XY[0] + d * math.sin(math.radians(b))
            y = CAM_XY[1] + d * math.cos(math.radians(b))
            X, Y = (float(v) for v in geom.map_to_unreal_cm(x, y))
            markers.append([label, X, Y, GROUND_Z_CM, DIAMETER, HEIGHT])
        link.call("xview_debug", "spawn_markers", markers)
        try:
            meta = cr.capture(link, geom, *CAM_XY, OUT, sun=(90, 20))
        finally:
            link.call("xview_debug", "clear_markers")
        meta_c = cr.capture(link, geom, 0.0, 0.0, OUT_CENTRE, sun=(90, 20))
    sky = load_sky_masks(OUT)
    ok = True
    for label, (b, d) in MARKERS.items():
        for k, cam in enumerate(meta["cameras"]):
            off = (b - cam["bearing_deg"] + 180) % 360 - 180
            if abs(off) > cam["hfov_deg"] / 2 - 1:
                continue
            exp = predict(b, d, cam)
            got = measure(sky[k][ROW], exp)
            good = got is not None and abs(got - exp) <= TOLERANCE_PX
            ok &= good
            print(f"marker {label:5} (bearing {b:3}, {off:+6.1f} deg in cam {k}): expected col {exp:8.2f}, "
                  f"measured {got if got is None else round(got, 2)} -> {'OK' if good else 'FAIL'}")
    sky_c = load_sky_masks(OUT_CENTRE)
    for k in (3, 5, 7):
        cam = meta_c["cameras"][k]
        boundary = (sky_c[k] < 0.5).argmax(axis=0)      # first non-sky row in each column
        spread = int(boundary.max() - boundary.min())
        below = boundary.mean() - (cam["height"] - 1) / 2
        good = spread <= 2 and 0 < below < 15
        ok &= good
        print(f"cam {k} at (0, 0): horizon rows {boundary.min()}-{boundary.max()} (spread {spread} px), "
              f"{below:.1f} px below centre -> {'OK' if good else 'FAIL'}")
    print("ALL OK" if ok else "SOME CHECKS FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
