"""Coordinate frames for the X-View data generator. Every other script uses these.

Map frame (same as the challenge): x = East, y = North, metres. map.png and the
DEM we keep are north-up: row 0 is the north edge, column 0 the west edge.
Pixel (u, v) centre:  x = xmin + res*(u + 0.5),  y = ymax - res*(v + 0.5).

Unreal frame: Terrain Studio puts DEM column j at X = -j*res and DEM row i at
Y = +i*res (metres; Unreal uses cm). Imported as-is, a north-up DEM would come
out mirrored, so we send np.flipud(dem). North-up row v then sits at
Y = (H-1-v)*res, which gives:
    X_cm = -100 * (x - xmin - res/2)      (East = -X)
    Y_cm = +100 * (y - ymin - res/2)      (North = +Y)
Checked in Unreal with the direction test terrain (ue_probe_dirtest.py, ue_probe_edges.py).
"""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MapGeometry:
    width: int          # map / DEM columns
    height: int         # map / DEM rows
    res: float = 5.0    # metres per pixel
    xmin: float = 0.0   # outer image edges, metres
    ymax: float = 0.0

    @classmethod
    def centred(cls, width, height, res=5.0):
        """Bounds chosen so that (0, 0) is the centre of the image."""
        return cls(width, height, res, xmin=-res * width / 2, ymax=res * height / 2)

    @property
    def xmax(self):
        return self.xmin + self.res * self.width

    @property
    def ymin(self):
        return self.ymax - self.res * self.height

    def bounds(self):
        """The challenge's metadata block (outer image edges)."""
        return {"xmin": self.xmin, "xmax": self.xmax, "ymin": self.ymin, "ymax": self.ymax}

    def pixel_to_map(self, u, v):
        return self.xmin + self.res * (np.asarray(u) + 0.5), self.ymax - self.res * (np.asarray(v) + 0.5)

    def map_to_pixel(self, x, y):
        return (np.asarray(x) - self.xmin) / self.res - 0.5, (self.ymax - np.asarray(y)) / self.res - 0.5

    def map_to_unreal_cm(self, x, y):
        """Map metres -> Unreal X, Y in cm, for a DEM sent as np.flipud(dem_north_up)."""
        return (-100.0 * (np.asarray(x) - self.xmin - self.res / 2),
                100.0 * (np.asarray(y) - self.ymin - self.res / 2))


def dem_for_unreal(dem_north_up):
    """The array to hand to Terrain Studio (see the module docstring)."""
    return np.ascontiguousarray(np.flipud(dem_north_up))


# --- Directions ------------------------------------------------------------
# Compass bearing b: degrees clockwise from North (0 = N, 90 = E), horizontal
# direction (East, North) = (sin b, cos b). In Unreal that is (X, Y) = (-sin b, cos b).

def unreal_yaw(bearing_deg):
    """Unreal yaw (deg) of a camera looking along compass bearing b: atan2(cos b, -sin b) = 90 + b."""
    return (90.0 + bearing_deg) % 360.0


def studio_sun_azimuth(compass_deg):
    """Terrain Studio's sun azimuth for a sun at compass azimuth c (the direction the
    light comes FROM). Studio convention (unreal_sun.py): 0 = -Y, 90 = -X, clockwise
    from the top of the DEM image. With our frame (North = +Y, East = -X) -Y is South,
    -X is East, so studio = (180 - c) mod 360: N -> 180, E -> 90, S -> 0, W -> 270."""
    return (180.0 - compass_deg) % 360.0
