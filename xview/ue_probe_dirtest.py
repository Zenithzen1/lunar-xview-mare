"""Runs INSIDE the Unreal editor (python tools/ue_run.py xview/ue_probe_dirtest.py).

Read-only: traces straight down at each direction-test block's predicted Unreal
X, Y and prints its height above the ground at the camera point. If frames.py
is right, each block shows its own height (N 40, E 30, S 20, W 10, NE 60). A
mirror would show up as E and W swapped (or N and S).
"""
import json

import unreal

# __file__ isn't set when this runs inside Unreal, so full path. Change for your machine.
POINTS = r"C:\Users\Lenovo\Desktop\mare\data\dirtest\dirtest_points.json"

world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
print("level:", world.get_name())


def ground_z(X, Y):
    hit = unreal.SystemLibrary.line_trace_single(
        world, unreal.Vector(X, Y, 1e7), unreal.Vector(X, Y, -1e7),
        unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [], unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return None
    t = hit.to_tuple()
    return t[4].z, t[9].get_actor_label() if t[9] else "?"   # impact point, hit actor


points = json.load(open(POINTS))["points"]
cam = points["camera"]
base = ground_z(cam["unreal_X_cm"], cam["unreal_Y_cm"])
print(f"camera ground: {base}")
for name, p in points.items():
    if name == "camera":
        continue
    hit = ground_z(p["unreal_X_cm"], p["unreal_Y_cm"])
    if hit is None or base is None:
        print(f"{name:>2}: no hit")
        continue
    print(f"{name:>2}: expected {p['height_m']:5.1f} m, measured {(hit[0] - base[0]) / 100:6.2f} m  ({hit[1]})")
