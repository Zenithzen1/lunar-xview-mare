"""X-View panorama capture rig. Runs INSIDE the Unreal Editor.

Unreal's embedded Python has no numpy, so this file uses only `unreal` and the
standard library. It is sent to the editor by xview/ue_link.py (host side),
which puts this folder on the editor's sys.path; nothing is copied into MARE.

8 SceneCapture2D actors, one per 45 deg. They're spawned transient so they never
get saved into the level (by us or by Terrain Studio); after an editor restart
ensure_rig() just spawns them again.

Replies to the host are printed lines: REPLY + JSON.
"""
import json
import os

import unreal

REPLY = "XVIEW_JSON "
LABEL = "XView_Cam_{}"
TAG = "XViewRig"

# What the cameras record: SCS_SCENE_COLOR_HDR is the scene's linear light
# (Unreal's luminance units, cd/m2 for our lux sun) BEFORE any post-processing:
# no exposure, eye adaptation, bloom, lens flare, vignette, grain or tone curve.
# The "final colour" modes clip at 100 / 1.0 and ignored manual exposure when I
# tested them, so not using those. 8-bit conversion happens on the host.
CAPTURE_SOURCE = unreal.SceneCaptureSource.SCS_SCENE_COLOR_HDR
# Show flags turned off for the captures. Fog is the only one that acts before
# post-processing (the level has none, but a copied level might).
SHOW_FLAGS_OFF = ("Fog",)


def _reply(obj):
    print(REPLY + json.dumps(obj))


def _world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def _actor_sub():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def rig_actors():
    """{camera index: SceneCapture2D actor} for the rig cameras in the open level."""
    # get_all_level_actors() skips transient actors, so search the world by tag.
    # A duplicate index (left by an earlier run) is destroyed.
    rig = {}
    for actor in unreal.GameplayStatics.get_all_actors_with_tag(_world(), TAG):
        k = int(actor.get_actor_label().rsplit("_", 1)[1])
        if k in rig:
            _actor_sub().destroy_actor(actor)
        else:
            rig[k] = actor
    return rig


def _render_target(component, width, height):
    """The camera's float16 RGBA render target (a transient object): reused if it
    already has the right size, else created."""
    rt = component.get_editor_property("texture_target")
    if rt is None or rt.size_x != width or rt.size_y != height:
        rt = unreal.RenderingLibrary.create_render_target2d(
            _world(), width, height, unreal.TextureRenderTargetFormat.RTF_RGBA16F,
            unreal.LinearColor(0, 0, 0, 1), False)
    return rt


def _configure(component, cfg, target):
    component.set_editor_property("texture_target", target)
    component.set_editor_property("fov_angle", float(cfg["hfov_deg"]))   # horizontal FOV
    component.set_editor_property("capture_source", CAPTURE_SOURCE)
    # Render only when asked (capture_scene), never on tick or on movement.
    component.set_editor_property("capture_every_frame", False)
    component.set_editor_property("capture_on_movement", False)
    # Keep the camera's view state (temporal history, shadow and GI caches)
    # between captures, so repeated captures of the same pose can converge.
    component.set_editor_property("always_persist_rendering_state", True)

    flags = [unreal.EngineShowFlagsSetting(show_flag_name=name, enabled=False) for name in SHOW_FLAGS_OFF]
    flags += [unreal.EngineShowFlagsSetting(show_flag_name=name, enabled=on)
              for name, on in cfg.get("show_flags", {}).items()]
    component.set_editor_property("show_flag_settings", flags)


def ensure_rig(cfg):
    """Spawns (if needed) and configures the rig. cfg: n, width, height, hfov_deg,
    optional show_flags {name: bool}."""
    rig = rig_actors()
    if sorted(rig) != list(range(cfg["n"])):
        for actor in rig.values():
            _actor_sub().destroy_actor(actor)
        rig = {}
        for k in range(cfg["n"]):
            actor = _actor_sub().spawn_actor_from_class(
                unreal.SceneCapture2D, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), transient=True)
            actor.set_actor_label(LABEL.format(k))
            actor.tags = [TAG]
            rig[k] = actor
    for k, actor in rig.items():
        component = actor.capture_component2d
        _configure(component, cfg, _render_target(component, cfg["width"], cfg["height"]))
    _reply({"rig": sorted(rig), "cfg": cfg})


def ground_z(X, Y):
    """Height (cm) of the surface under Unreal X, Y, traced straight down, ignoring the rig."""
    hit = unreal.SystemLibrary.line_trace_single(
        _world(), unreal.Vector(X, Y, 1e7), unreal.Vector(X, Y, -1e7),
        unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, list(rig_actors().values()),
        unreal.DrawDebugTrace.NONE, True)
    if hit is None:
        return None, None
    t = hit.to_tuple()
    actor = t[9]
    return t[4].z, (actor.get_class().get_name() if actor else None)


def capture(X, Y, height_cm, bearings_deg, rounds, out_dir):
    """Places the rig at Unreal X, Y (cm), height_cm above the ground, camera k facing
    compass bearing bearings_deg[k] (yaw = 90 + bearing, pitch = roll = 0), renders
    `rounds` times and exports every round of every camera to out_dir/cam_<k>_r<round>.exr.
    Each render is shifted by a sub-pixel jitter, so the host averages the rounds
    (anti-aliasing). EXR channels: RGB = linear light, A = 1 where nothing was hit (sky)."""
    z0, hit_class = ground_z(X, Y)
    if z0 is None:
        _reply({"error": "no ground under the capture point"})
        return
    rig = rig_actors()
    Z = z0 + height_cm
    for k, bearing in enumerate(bearings_deg):
        rig[k].set_actor_location_and_rotation(
            unreal.Vector(X, Y, Z), unreal.Rotator(roll=0.0, pitch=0.0, yaw=90.0 + bearing), False, True)

    options = unreal.ImageWriteOptions()
    options.set_editor_property("format", unreal.DesiredImageFormat.EXR)
    options.set_editor_property("compression_quality", 0)   # EXR: 0 = default (lossless), 1 = uncompressed
    options.set_editor_property("overwrite_file", True)
    options.set_editor_property("async_", False)
    os.makedirs(out_dir, exist_ok=True)

    files = []
    for r in range(rounds):
        for k in range(len(bearings_deg)):
            rig[k].capture_component2d.capture_scene()
        for k in range(len(bearings_deg)):
            path = os.path.join(out_dir, f"cam_{k}_r{r}.exr")
            unreal.ImageWriteBlueprintLibrary.export_to_disk(
                rig[k].capture_component2d.texture_target, path, options)
            files.append(path)

    cams = []
    for k in range(len(bearings_deg)):
        loc = rig[k].capture_component2d.get_world_location()
        rot = rig[k].capture_component2d.get_world_rotation()
        cams.append({"X": loc.x, "Y": loc.y, "Z": loc.z, "yaw": rot.yaw, "pitch": rot.pitch, "roll": rot.roll})
    _reply({"ground_z_cm": z0, "ground_hit_class": hit_class, "camera_z_cm": Z,
            "cameras": cams, "files": files, "level": _world().get_name()})


def destroy_rig():
    """Removes the rig cameras (ensure_rig spawns them again, freshly configured)."""
    rig = rig_actors()
    for actor in rig.values():
        _actor_sub().destroy_actor(actor)
    _reply({"destroyed": len(rig)})
