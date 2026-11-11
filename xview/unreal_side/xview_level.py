"""Editor side: our levels in /Game/XView/. Runs inside Unreal (no numpy).

describe()                      -> current level path, dirty packages, actors (class, label)
open_level(path)                -> loads one of our levels (refuses outside /Game/XView/)
clone_without_landscape(src, dst)
    Save-As of `src` to `dst`, then removes the Landscape from `dst` so Terrain Studio
    can build a new one there. `src` is left untouched on disk.
"""
import json

import unreal

OURS = "/Game/XView/"
REPLY = "XVIEW_JSON "


def _reply(obj):
    print(REPLY + json.dumps(obj))


def _les():
    return unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)


def _eas():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def _level_path():
    return _world().get_path_name().split(".")[0]


def describe():
    dirty = [p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    actors = [{"class": a.get_class().get_name(), "label": a.get_actor_label()}
              for a in _eas().get_all_level_actors()]
    _reply({"level": _level_path(), "dirty_maps": dirty, "actors": actors})


def open_level(path):
    if not path.startswith(OURS):
        _reply({"error": f"refusing to open {path}: not one of our levels"})
        return
    if unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages():
        _reply({"error": "current level has unsaved changes; not switching"})
        return
    ok = _les().load_level(path)
    _reply({"ok": bool(ok), "level": _level_path()})


def clone_without_landscape(src, dst):
    if not (src.startswith(OURS) and dst.startswith(OURS)):
        _reply({"error": "both levels must be under " + OURS})
        return
    if unreal.EditorAssetLibrary.does_asset_exist(dst):
        _reply({"error": f"{dst} already exists"})
        return
    if _level_path() != src:
        if unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages():
            _reply({"error": "current level has unsaved changes; not switching"})
            return
        _les().load_level(src)
    # Save As first: from here on the open level is dst, and src on disk is never modified.
    if not unreal.EditorLoadingAndSavingUtils.save_map(_world(), dst):
        _reply({"error": "save_map failed"})
        return
    if _level_path() != dst:
        _les().load_level(dst)
    if _level_path() != dst:
        _reply({"error": f"expected to be in {dst}, am in {_level_path()}"})
        return
    removed = []
    for a in _eas().get_all_level_actors():
        if isinstance(a, (unreal.Landscape, unreal.LandscapeProxy)):
            removed.append(a.get_actor_label())
            _eas().destroy_actor(a)
    _les().save_current_level()
    _reply({"level": _level_path(), "removed": removed})
