"""Generate a synthetic batch in the challenge's layout, in three resumable stages.

    python xview/make_batch.py plan    --batch data/batch01 --n 40 --seed 1
    python xview/make_batch.py capture --batch data/batch01      # Unreal open on the batch level
    python xview/make_batch.py stitch  --batch data/batch01      # needs xview/stitch.py

Before this: make_terrain.py (terrain/) and render_map.py (map/), and the
terrain sent to Unreal (dem_unreal.npy, resolution 5.0).

Layout (same as the challenge's public_release/train, plus our extras):
    <batch>/public_release/train/labels.csv          panorama_id,x,y  (UTF-8, no BOM)
    <batch>/public_release/train/panoramas/00001.png ...
    <batch>/public_release/train/map/map.png + train_map_metadata.json
    <batch>/extras/poses.csv                         + sun (compass az, el) per panorama
    <batch>/extras/rings/00001/                      cam_*.exr + meta.json (Unreal pose readback)
    <batch>/extras/batch.json                        plan settings

Ground truth is exact: the label is the position we picked and the camera is put
exactly there (2.5 m above the line-traced ground). Positions are rounded to 0.01 m
before capture so labels.csv and the camera agree.
"""
import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from capture_ring import capture, load_geometry

XVIEW = Path(__file__).resolve().parent


def paths(batch):
    b = Path(batch)
    train = b / "public_release" / "train"
    return {"geometry": b / "terrain" / "geometry.json", "labels": train / "labels.csv",
            "panoramas": train / "panoramas", "extras": b / "extras",
            "poses": b / "extras" / "poses.csv", "rings": b / "extras" / "rings"}


def read_poses(p):
    with open(p["poses"], newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def plan(batch, n, seed, margin_m, az_range, el_range):
    """Random positions at least margin_m from the edge (need terrain out to the
    horizon) and a random sun for each one."""
    p = paths(batch)
    if p["poses"].exists():
        sys.exit(f"{p['poses']} exists; delete extras/ and labels.csv to re-plan")
    geom = load_geometry(p["geometry"])
    rng = np.random.default_rng(seed)
    xlo, xhi = geom.xmin + margin_m, geom.xmax - margin_m
    ylo, yhi = geom.ymin + margin_m, geom.ymax - margin_m
    assert xlo < xhi and ylo < yhi, "margin leaves no room; use a bigger terrain"
    xs = np.round(rng.uniform(xlo, xhi, n), 2)
    ys = np.round(rng.uniform(ylo, yhi, n), 2)
    az = np.round(rng.uniform(*az_range, n), 2) % 360.0
    el = np.round(rng.uniform(*el_range, n), 2)

    p["extras"].mkdir(parents=True, exist_ok=True)
    p["labels"].parent.mkdir(parents=True, exist_ok=True)
    ids = [f"{i + 1:05d}.png" for i in range(n)]
    # plain utf-8 (no BOM) + LF, otherwise the kit's baseline.py rejects the header
    with open(p["labels"], "w", newline="", encoding="utf-8") as f:
        f.write("panorama_id,x,y\n")
        for i, x, y in zip(ids, xs, ys):
            f.write(f"{i},{x:.2f},{y:.2f}\n")
    with open(p["poses"], "w", newline="", encoding="utf-8") as f:
        f.write("panorama_id,x,y,sun_compass_az_deg,sun_el_deg\n")
        for row in zip(ids, xs, ys, az, el):
            f.write("{},{:.2f},{:.2f},{:.2f},{:.2f}\n".format(*row))
    (p["extras"] / "batch.json").write_text(json.dumps({
        "n": n, "seed": seed, "margin_m": margin_m,
        "sun_compass_az_range_deg": az_range, "sun_el_range_deg": el_range,
        "position_box_m": {"xmin": xlo, "xmax": xhi, "ymin": ylo, "ymax": yhi},
    }, indent=2))
    print(f"planned {n} panoramas in x [{xlo:.0f}, {xhi:.0f}], y [{ylo:.0f}, {yhi:.0f}] m; "
          f"sun az {az_range}, el {el_range}")


def capture_all(batch):
    from ue_link import UnrealLink
    p = paths(batch)
    geom = load_geometry(p["geometry"])
    poses = read_poses(p)
    todo = [r for r in poses if not (p["rings"] / r["panorama_id"][:-4] / "meta.json").exists()]
    print(f"{len(poses) - len(todo)} already captured, {len(todo)} to go")
    t0 = time.time()
    with UnrealLink() as link:
        for i, r in enumerate(todo):
            out = p["rings"] / r["panorama_id"][:-4]
            meta = capture(link, geom, float(r["x"]), float(r["y"]), out,
                           (float(r["sun_compass_az_deg"]), float(r["sun_el_deg"])))
            left = (time.time() - t0) / (i + 1) * (len(todo) - i - 1)
            print(f"{r['panorama_id']}  ({r['x']}, {r['y']})  sun {r['sun_compass_az_deg']}/"
                  f"{r['sun_el_deg']}  ground {meta['unreal']['ground_hit_class']}  "
                  f"{meta['capture_seconds']} s  ~{left / 60:.0f} min left", flush=True)


def stitch_all(batch, projection):
    """Run stitch.py on every captured ring (skips ones already done)."""
    p = paths(batch)
    p["panoramas"].mkdir(parents=True, exist_ok=True)
    for r in read_poses(p):
        ring, png = p["rings"] / r["panorama_id"][:-4], p["panoramas"] / r["panorama_id"]
        if png.exists():
            continue
        if not (ring / "meta.json").exists():
            print(f"{r['panorama_id']}: not captured yet, skipped")
            continue
        subprocess.run([sys.executable, str(XVIEW / "stitch.py"), str(ring), str(png),
                        "--projection", projection], check=True)
        print(png)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["plan", "capture", "stitch"])
    ap.add_argument("--batch", required=True)
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--margin", type=float, default=2000.0, help="min distance to terrain edge, m")
    ap.add_argument("--az", type=float, nargs=2, default=[0.0, 360.0], help="sun compass azimuth range")
    ap.add_argument("--el", type=float, nargs=2, default=[5.0, 30.0], help="sun elevation range")
    ap.add_argument("--projection", default="cyl")
    a = ap.parse_args()
    if a.stage == "plan":
        plan(a.batch, a.n, a.seed, a.margin, a.az, a.el)
    elif a.stage == "capture":
        capture_all(a.batch)
    else:
        stitch_all(a.batch, a.projection)


if __name__ == "__main__":
    main()
