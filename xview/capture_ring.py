"""Capture the 8-camera ring at one map position. Needs the Unreal Editor open
on an XView level with the terrain loaded.

    python xview/capture_ring.py --geometry data/dirtest/dirtest_points.json \
        --x 0 --y 0 --sun 90 20 --out data/dirtest/ring_000

Writes <out>/cam_0.exr ... cam_7.exr (linear float RGB) and <out>/meta.json.
stitch.py turns these into the panorama.
"""
import argparse
import json
import time
from pathlib import Path

from frames import MapGeometry, studio_sun_azimuth, unreal_yaw
from ring_io import average_rounds
from ue_link import UnrealLink, set_sun_studio

# ring settings (stitch.py reads them back from meta.json)
RIG = {
    "n": 8,                 # cameras, one per 45-degree sector
    "width": 2048,          # px
    "height": 1664,         # px
    "hfov_deg": 50.0,       # horizontal field of view of each camera
}
CAMERA_HEIGHT_M = 2.5       # challenge: camera exactly 2.5 m above the ground
ROUNDS = 4                  # jittered renders per pose, averaged (anti-aliasing)


def load_geometry(path):
    g = json.loads(Path(path).read_text())
    g = g.get("geometry", g)
    return MapGeometry(width=g["width"], height=g["height"], res=g["res"], xmin=g["xmin"], ymax=g["ymax"])


def capture(link, geom, x, y, out, sun, rounds=ROUNDS, rig=RIG, keep_rounds=False):
    """Capture at map (x, y) in metres. sun = (compass azimuth, elevation) in degrees,
    required on purpose so every capture records its sun. Returns meta (also saved)."""
    out = Path(out).resolve()
    set_sun_studio(link, studio_sun_azimuth(sun[0]), sun[1])
    link.call("xview_rig", "ensure_rig", rig)
    X, Y = (float(v) for v in geom.map_to_unreal_cm(x, y))
    bearings = [360.0 * k / rig["n"] for k in range(rig["n"])]
    t0 = time.time()
    reply = link.call("xview_rig", "capture", X, Y, 100.0 * CAMERA_HEIGHT_M, bearings, rounds, str(out))
    average_rounds(out, rig["n"], rounds, keep_rounds)
    meta = {
        "map_xy_m": [x, y],
        "camera_height_m": CAMERA_HEIGHT_M,
        "sun": {"compass_azimuth_deg": sun[0], "elevation_deg": sun[1],
                "studio_azimuth_deg": studio_sun_azimuth(sun[0])},
        "rig": rig,
        "rounds": rounds,
        "cameras": [{"index": k, "file": f"cam_{k}.exr", "bearing_deg": b,
                     "hfov_deg": rig["hfov_deg"], "width": rig["width"], "height": rig["height"],
                     "unreal": reply["cameras"][k]}
                    for k, b in enumerate(bearings)],
        "unreal": {"X_cm": X, "Y_cm": Y, "ground_z_cm": reply["ground_z_cm"],
                   "ground_hit_class": reply["ground_hit_class"], "camera_z_cm": reply["camera_z_cm"],
                   "level": reply["level"]},
        "capture_seconds": round(time.time() - t0, 2),
    }
    # check the cameras actually ended up where we put them
    for k, cam in enumerate(meta["cameras"]):
        u = cam["unreal"]
        assert abs(u["X"] - X) < 0.1 and abs(u["Y"] - Y) < 0.1, f"camera {k} misplaced: {u}"
        assert abs((u["yaw"] - unreal_yaw(cam["bearing_deg"]) + 180) % 360 - 180) < 1e-3, f"camera {k} yaw: {u}"
        assert abs(u["pitch"]) < 1e-3 and abs(u["roll"]) < 1e-3, f"camera {k} tilted: {u}"
    if reply["ground_hit_class"] not in ("Landscape", "LandscapeStreamingProxy"):
        print(f"WARNING: ground trace hit {reply['ground_hit_class']}, not the Landscape")
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--geometry", required=True, help="JSON with width, height, res, xmin, ymax")
    ap.add_argument("--x", type=float, required=True)
    ap.add_argument("--y", type=float, required=True)
    ap.add_argument("--sun", type=float, nargs=2, metavar=("AZ", "EL"), required=True,
                    help="sun compass azimuth (light comes FROM) and elevation, degrees")
    ap.add_argument("--rounds", type=int, default=ROUNDS)
    ap.add_argument("--keep-rounds", action="store_true", help="keep each round's files (convergence tests)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    with UnrealLink() as link:
        meta = capture(link, load_geometry(a.geometry), a.x, a.y, a.out, a.sun, a.rounds,
                       keep_rounds=a.keep_rounds)
    print(json.dumps(meta["unreal"], indent=2), f"\n{meta['capture_seconds']} s")


if __name__ == "__main__":
    main()
