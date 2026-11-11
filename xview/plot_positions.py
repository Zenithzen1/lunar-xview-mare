"""Draw a batch's labelled positions on its map.png (visual check + something to show).

    python xview/plot_positions.py --batch data/batch01

Writes <batch>/extras/positions_on_map.png: map in gray, each panorama position as
a red dot with its number, the position box in yellow, and an arrow from the camera
towards the sun of that panorama (compass azimuth). Pixel position uses the kit's
formula u = (x - xmin)/5 - 0.5, v = (ymax - y)/5 - 0.5.
"""
import argparse
import csv
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch", required=True)
    ap.add_argument("--split", default="train")
    a = ap.parse_args()
    b = Path(a.batch)
    mdir = b / "public_release" / a.split / "map"
    bounds = json.loads((mdir / f"{a.split}_map_metadata.json").read_text())["bounds_metres"]
    im = Image.open(mdir / "map.png").convert("RGB")
    d = ImageDraw.Draw(im)

    def px(x, y):
        return (x - bounds["xmin"]) / 5.0 - 0.5, (bounds["ymax"] - y) / 5.0 - 0.5

    box = json.loads((b / "extras" / "batch.json").read_text())["position_box_m"]
    (u0, v0), (u1, v1) = px(box["xmin"], box["ymax"]), px(box["xmax"], box["ymin"])
    d.rectangle([u0, v0, u1, v1], outline=(255, 210, 0), width=2)

    with open(b / "extras" / "poses.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            u, v = px(float(r["x"]), float(r["y"]))
            az = math.radians(float(r["sun_compass_az_deg"]))
            # Compass az: East = +u, North = -v on the image.
            d.line([u, v, u + 14 * math.sin(az), v - 14 * math.cos(az)], fill=(255, 140, 0), width=2)
            d.ellipse([u - 4, v - 4, u + 4, v + 4], fill=(230, 30, 30))
            d.text((u + 6, v - 6), str(int(r["panorama_id"][:5])), fill=(255, 255, 255))
    out = b / "extras" / "positions_on_map.png"
    im.save(out)
    print(out)


if __name__ == "__main__":
    main()
