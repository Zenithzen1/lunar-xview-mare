"""Format checks for a generated batch. Same rules as the starter kit
(labels.csv header, no BOM, 5-digit names, 6965x706 grayscale, map bounds at 5 m/px).

    python xview/check_batch.py --batch data/batch01

Ends with ALL OK, or lists every failure.
"""
import argparse
import csv
import json
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image

PANO_SIZE = (6965, 706)   # PIL size: (width, height)
RES = 5.0


def check(batch, split="train"):
    root = Path(batch) / "public_release" / split
    fails = []

    def expect(ok, msg):
        if not ok:
            fails.append(msg)

    # Map + metadata
    mp = root / "map" / "map.png"
    meta = json.loads((root / "map" / f"{split}_map_metadata.json").read_text(encoding="utf-8"))
    b = meta["bounds_metres"]
    with Image.open(mp) as im:
        expect(im.mode == "L", f"map mode {im.mode}, want L")
        w, h = im.size
    expect(math.isclose(b["xmax"] - b["xmin"], RES * w, abs_tol=1e-6), "map x bounds != 5 m/px")
    expect(math.isclose(b["ymax"] - b["ymin"], RES * h, abs_tol=1e-6), "map y bounds != 5 m/px")

    # labels.csv
    raw = (root / "labels.csv").read_bytes()
    expect(not raw.startswith(b"\xef\xbb\xbf"), "labels.csv has a BOM")
    text = raw.decode("utf-8")
    expect(text.splitlines()[0] == "panorama_id,x,y", f"header {text.splitlines()[0]!r}")
    rows = list(csv.DictReader(text.splitlines()))
    ids = [r["panorama_id"] for r in rows]
    expect(len(ids) == len(set(ids)), "duplicate panorama_id")
    for r in rows:
        x, y = float(r["x"]), float(r["y"])
        expect(re.fullmatch(r"\d{5}\.png", r["panorama_id"]) is not None, f"bad id {r['panorama_id']}")
        expect(math.isfinite(x) and math.isfinite(y), f"{r['panorama_id']}: non-finite label")
        expect(b["xmin"] <= x <= b["xmax"] and b["ymin"] <= y <= b["ymax"],
               f"{r['panorama_id']}: label ({x}, {y}) outside map bounds")

    # Panoramas: same set as labels, right format
    pngs = sorted(q for q in (root / "panoramas").rglob("*") if q.suffix.lower() == ".png")
    names = [q.name for q in pngs]
    expect(len(names) == len({n.lower() for n in names}), "duplicate PNG basenames")
    expect(set(names) == set(ids),
           f"labels vs PNGs: {len(set(ids) - set(names))} labels without PNG, "
           f"{len(set(names) - set(ids))} PNGs without label")
    for q in pngs:
        with Image.open(q) as im:
            ok = im.mode == "L" and im.size == PANO_SIZE
            expect(ok, f"{q.name}: mode {im.mode}, size {im.size}; want L, {PANO_SIZE}")
            if ok:
                a = np.asarray(im)
                expect(a.max() > a.min(), f"{q.name}: constant image")

    # Coordinate round trip on the map grid (kit's xy/pixel formulas)
    for x, y in [(b["xmin"] + 2.5, b["ymax"] - 2.5), (0.0, 0.0), (b["xmax"] - 0.01, b["ymin"] + 0.01)]:
        u, v = (x - b["xmin"]) / RES - 0.5, (b["ymax"] - y) / RES - 0.5
        x2, y2 = b["xmin"] + RES * (u + 0.5), b["ymax"] - RES * (v + 0.5)
        expect(math.isclose(x, x2, abs_tol=1e-9) and math.isclose(y, y2, abs_tol=1e-9), "round trip")

    print(f"{split}: map {w} x {h}, {len(rows)} labels, {len(pngs)} panoramas")
    for f in fails:
        print("FAIL", f)
    print("ALL OK" if not fails else f"{len(fails)} failure(s)")
    return not fails


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch", required=True)
    a = ap.parse_args()
    raise SystemExit(0 if check(a.batch) else 1)
