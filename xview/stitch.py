"""Stitch one captured ring (8 pinhole cameras) into a challenge-format panorama.

    python xview/stitch.py <ring folder> <out.png> [--projection cyl|equirect]

Output: 6965 x 706, 8-bit grayscale PNG, North at column 3482, East to the right,
horizon at row 352.5. Also writes pano_gray.npy (float linear gray) into the ring
folder, so the 8-bit mapping can change later without re-stitching.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates

import ring_io

H, W = 706, 6965
N_CAMS = 8
CAM_SPACING = 360 / N_CAMS

CENTRE_COL = W // 2            # 3482: looks North
DEG_PER_COL = 360 / W

HORIZON_ROW = (H - 1) / 2      # 352.5: between rows 352 and 353

# anti-aliasing: 4 samples per output pixel, averaged
SUBSAMPLES = [(-0.25, -0.25), (-0.25, 0.25), (0.25, -0.25), (0.25, 0.25)]

# 8-bit conversion, placeholder for now. Same WHITE for every panorama, picked so
# lit ground in the dirtest ring (90th pct ~4860) lands around 200.
WHITE = 8000.0
GAMMA = 1 / 2.2


def col_to_bearing(cols):
    bearing = (cols - CENTRE_COL) * DEG_PER_COL
    return bearing


def row_to_elevation(rows, projection):
    offset = HORIZON_ROW - rows

    if projection == "equirect":
        elevation = offset * DEG_PER_COL
    elif projection == "cyl":
        R = W / (2 * np.pi)       # cylinder radius in pixels, 1108.5
        elevation = np.degrees(np.arctan(offset / R))
    else:
        raise ValueError(f"unknown projection: {projection}")

    return elevation


def pick_camera(bearing):
    k = np.round(bearing / CAM_SPACING).astype(int) % N_CAMS
    alpha = bearing - CAM_SPACING * k  # basically how far off-center it is, how much you gotta turn yer head to look at said point
    alpha = (alpha + 180) % 360 - 180  # gotta tell the software about directions somehow
    return k, alpha


def direction_to_pixel(alpha, elevation, cam):
    cam_w = cam["width"]
    cam_h = cam["height"]
    hfov = np.radians(cam["hfov_deg"])

    f = (cam_w / 2) / np.tan(hfov / 2)
    cx = (cam_w - 1) / 2
    cy = (cam_h - 1) / 2

    a = np.radians(alpha)
    e = np.radians(elevation)

    u = cx + f * np.tan(a)
    v = cy - f * np.tan(e) / np.cos(a)

    if not (u.min() >= 0 and u.max() <= cam_w - 1 and v.min() >= 0 and v.max() <= cam_h - 1):
        raise ValueError(f"pixel outside camera image: u {u.min():.1f}..{u.max():.1f}, "
                         f"v {v.min():.1f}..{v.max():.1f}")
    return u, v


def to_gray(image):
    return 0.2126 * image[:, :, 0] + 0.7152 * image[:, :, 1] + 0.0722 * image[:, :, 2]


def sample(grays, k, u, v):
    pano = np.full(k.shape, np.nan, dtype=np.float32)
    for c in range(N_CAMS):
        mask = k == c
        pano[mask] = map_coordinates(grays[c], [v[mask], u[mask]], order=1)
    return pano


def render(cols, rows, grays, cam, projection):
    bearing = col_to_bearing(cols)
    elevation = row_to_elevation(rows, projection)
    k, alpha = pick_camera(bearing)
    u, v = direction_to_pixel(alpha, elevation, cam)
    return sample(grays, k, u, v)


def check_rig(meta):
    """The maths above assumes 8 identical cameras with camera k at bearing 45k."""
    cams = meta["cameras"]
    if len(cams) != N_CAMS:
        raise ValueError(f"expected {N_CAMS} cameras, got {len(cams)}")
    for k, c in enumerate(cams):
        if abs(c["bearing_deg"] - CAM_SPACING * k) > 1e-6:
            raise ValueError(f"camera {k} bearing {c['bearing_deg']}, expected {CAM_SPACING * k}")
        for key in ("width", "height", "hfov_deg"):
            if c[key] != cams[0][key]:
                raise ValueError(f"camera {k} {key} differs from camera 0")
    return cams[0]


def stitch(images, meta, projection):
    """8 linear RGB images -> float32 (H, W) linear gray panorama."""
    cam = check_rig(meta)
    grays = [to_gray(im).astype(np.float32) for im in images]   # gray first: sample once, not 3x
    rows, cols = np.indices((H, W), dtype=np.float64)
    pano = np.zeros((H, W), dtype=np.float64)
    for dr, dc in SUBSAMPLES:
        pano += render(cols + dc, rows + dr, grays, cam, projection)
    pano /= len(SUBSAMPLES)
    if np.isnan(pano).any():
        raise ValueError("some panorama pixels were not filled")
    return pano.astype(np.float32)


def to_uint8(gray):
    """linear -> 8-bit (fixed white, gamma 1/2.2). TODO match real histograms."""
    x = np.clip(gray / WHITE, 0.0, 1.0) ** GAMMA
    return np.rint(255 * x).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ring", help="ring folder with meta.json and cam_<k>.exr")
    ap.add_argument("out", help="output PNG path")
    ap.add_argument("--projection", choices=["cyl", "equirect"], default="cyl")
    a = ap.parse_args()

    ring = Path(a.ring)
    images, meta = ring_io.load_ring(ring)
    pano = stitch(images, meta, a.projection)
    np.save(ring / "pano_gray.npy", pano)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(to_uint8(pano), mode="L").save(out)
    print(out)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:          # non-zero exit so make_batch.py stops
        print(f"stitch failed: {e}", file=sys.stderr)
        sys.exit(1)
