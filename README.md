# Lunar X-View synthetic data with MARE

Scripts to generate synthetic training data for the ESA Kelvins [Lunar X-View](https://kelvins.esa.int/lunar-x-view/) challenge using SpaceR's [MARE](https://github.com/raulcastar/MARE-Lunar-Simulator) lunar simulator (Unreal Engine 5.7) and [Terrain Studio](https://github.com/raulcastar/Unreal-Moon-Terrain-Generation).

The output follows the challenge's format: 360° grayscale panoramas (6965 × 706, North at the centre column, camera 2.5 m above the ground), a top-down `map.png` at 5 m/px lit from azimuth 90° / elevation 20°, `labels.csv` with exact ground-truth positions, and the map metadata JSON.

> Work in progress. The 8-bit tone mapping and the projection are placeholders until the real challenge data is released.

## How it works

1. **Terrain**: `make_terrain.py` makes a DEM with Terrain Studio's generator (north-up, 5 m/px). The flipped copy (`dem_unreal.npy`) is sent to Unreal through Terrain Studio with `resolution=5.0`.
2. **Map**: `render_map.py` renders `map.png` offline from the DEM (cast shadows + Lambert shading), so the map is exactly one pixel per DEM cell.
3. **Capture**: `capture_ring.py` places 8 scene-capture cameras (45° apart) at the chosen position inside the open Unreal Editor and saves linear-light EXRs. The Unreal side lives in `xview/unreal_side/` and is driven over Python Remote Execution (`ue_link.py`).
4. **Stitch**: `stitch.py` reprojects the 8 images into one cylindrical (or equirectangular) panorama.
5. **Check**: `check_batch.py` checks the batch against the challenge format; `plot_positions.py` draws the positions on the map.

`frames.py` holds all the coordinate conventions (map x/y ↔ pixels ↔ Unreal X/Y, compass bearing ↔ Unreal yaw, sun azimuth conversion). Terrain Studio would mirror a north-up DEM, which is why the DEM is flipped before import.

## Setup

- Windows, Unreal Engine 5.7 with the MARE project open (Python Editor Script Plugin + Remote Execution enabled)
- Python 3.11: `pip install -r requirements.txt`
- Clone Terrain Studio into the repo root (scripts import its generator and its `remote_execution.py`):
  ```
  git clone https://github.com/raulcastar/Unreal-Moon-Terrain-Generation
  ```

## Usage

```bash
# 1. terrain + map
python xview/make_terrain.py --out data/batch01 --size 1200 --seed 1
python xview/render_map.py --batch data/batch01
# send data/batch01/terrain/dem_unreal.npy to Unreal with Terrain Studio (resolution 5.0)

# 2. panoramas (Unreal open on the batch level)
python xview/make_batch.py plan    --batch data/batch01 --n 40 --seed 1
python xview/make_batch.py capture --batch data/batch01
python xview/make_batch.py stitch  --batch data/batch01

# 3. checks
python xview/check_batch.py --batch data/batch01
python xview/plot_positions.py --batch data/batch01
```

Output layout matches the challenge:

```
data/batch01/public_release/train/labels.csv
data/batch01/public_release/train/panoramas/00001.png ...
data/batch01/public_release/train/map/map.png
data/batch01/public_release/train/map/train_map_metadata.json
data/batch01/extras/          # sun angles per panorama, raw camera EXRs, Unreal poses
```

## Test scripts

- `make_dirtest_dem.py`: flat terrain with blocks at N/E/S/W and NE, to check directions end to end
- `ue_probe_dirtest.py`, `ue_probe_edges.py`: run inside Unreal (`python tools/ue_run.py <file>`) to check the DEM lands where `frames.py` predicts
- `check_ring_geometry.py`: checks camera yaw, FOV, pitch and roll with marker cylinders

## Credits

MARE, Terrain Studio and the Unreal plugins are by Raúl Castilla Arquillo / SpaceR (University of Luxembourg), MIT licence. This repo only contains the X-View data generation scripts on top of them, also under the MIT licence (see `LICENSE`).
