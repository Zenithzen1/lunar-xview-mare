"""Runs INSIDE Unreal. Read-only. Checks the NE block (9 px = vertices u-4..u+4)
lands on the exact vertices: 4 px from its centre must be block, 5 px must be ground,
along +x (East), -x, +y (North), -y. Uses frames.py's prediction for Unreal X, Y."""
import json

import unreal

# full path, __file__ isn't set inside Unreal. change for your machine
P = json.load(open(r"C:\Users\Lenovo\Desktop\mare\data\dirtest\dirtest_points.json"))["points"]
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def z(X, Y):
    hit = unreal.SystemLibrary.line_trace_single(
        world, unreal.Vector(X, Y, 1e7), unreal.Vector(X, Y, -1e7),
        unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [], unreal.DrawDebugTrace.NONE, True)
    return hit.to_tuple()[4].z / 100 if hit else float("nan")


base = z(P["camera"]["unreal_X_cm"], P["camera"]["unreal_Y_cm"])
ne = P["NE"]
# Map direction (dx, dy) in metres -> Unreal (dX, dY) cm: East = -X, North = +Y.
for label, (dx, dy) in {"East": (1, 0), "West": (-1, 0), "North": (0, 1), "South": (0, -1)}.items():
    row = []
    for px in (4, 5):
        X = ne["unreal_X_cm"] - 100 * 5 * px * dx
        Y = ne["unreal_Y_cm"] + 100 * 5 * px * dy
        row.append(f"{px} px: {z(X, Y) - base:5.1f} m")
    print(f"NE block, {label:5}: " + ", ".join(row))
