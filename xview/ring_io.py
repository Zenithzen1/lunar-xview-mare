"""Read and write captured rings: 8 camera images (linear float) + meta.json.

EXR channels written by the capture: R, G, B = linear light (Unreal units, before
any exposure or tone curve); A = sky coverage (1 = the view ray hit nothing).
"""
import json
from pathlib import Path

import numpy as np
import OpenEXR


def read_exr_rgba(path):
    """EXR -> float32 array (H, W, 4)."""
    with OpenEXR.File(str(path)) as f:
        ch = f.channels()
        if "RGBA" in ch:
            px = ch["RGBA"].pixels
        else:
            px = np.stack([ch[c].pixels for c in "RGBA"], axis=-1)
    return np.asarray(px, dtype=np.float32)


def read_exr(path):
    """EXR -> float32 array (H, W, 3), linear light."""
    return read_exr_rgba(path)[..., :3]


def write_exr_rgba(path, rgba):
    """float (H, W, 4) -> half-float EXR, ZIP compressed (lossless)."""
    header = {"compression": OpenEXR.ZIP_COMPRESSION, "type": OpenEXR.scanlineimage}
    with OpenEXR.File(header, {"RGBA": np.ascontiguousarray(rgba, dtype=np.float16)}) as f:
        f.write(str(path))


def average_rounds(folder, n_cameras, rounds, keep_rounds=False):
    """cam_<k>_r<r>.exr (r = 0..rounds-1) -> cam_<k>.exr, the mean over rounds.
    Averaging the jittered renders = anti-aliasing."""
    folder = Path(folder)
    for k in range(n_cameras):
        parts = [folder / f"cam_{k}_r{r}.exr" for r in range(rounds)]
        mean = np.mean([read_exr_rgba(p) for p in parts], axis=0)
        write_exr_rgba(folder / f"cam_{k}.exr", mean)
        if not keep_rounds:
            for p in parts:
                p.unlink()


def load_ring(folder):
    """Returns (images, meta). images[k] is camera k, (height, width, 3) float32;
    meta["cameras"][k] has bearing_deg, hfov_deg, width, height."""
    folder = Path(folder)
    meta = json.loads((folder / "meta.json").read_text())
    images = [read_exr(folder / c["file"]) for c in meta["cameras"]]
    return images, meta


def load_sky_masks(folder):
    """Sky coverage per camera, (height, width) float32 in [0, 1]: 1 = sky."""
    folder = Path(folder)
    meta = json.loads((folder / "meta.json").read_text())
    return [read_exr_rgba(folder / c["file"])[..., 3] for c in meta["cameras"]]
