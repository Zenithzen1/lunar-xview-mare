"""Debug helpers for the rig (runs INSIDE Unreal). Not used by the pipeline."""
import json

import unreal

import xview_rig


def readback(k=4):
    """Prints the post-process and capture settings camera k actually has."""
    comp = xview_rig.rig_actors()[k].capture_component2d
    pp = comp.get_editor_property("post_process_settings")
    out = {n: str(pp.get_editor_property(n)) for n in (
        "override_auto_exposure_method", "auto_exposure_method", "override_auto_exposure_bias",
        "auto_exposure_bias", "override_auto_exposure_apply_physical_camera_exposure",
        "auto_exposure_apply_physical_camera_exposure")}
    out["capture_source"] = str(comp.get_editor_property("capture_source"))
    out["blend_weight"] = comp.get_editor_property("post_process_blend_weight")
    out["flags"] = [(f.show_flag_name, f.enabled) for f in comp.get_editor_property("show_flag_settings")]
    print(xview_rig.REPLY + json.dumps(out))


def stats(k, source, eye_adaptation=None, bias=None, x0=0, y0=1300, w=2048, h=364):
    """Captures camera k with `source` (SceneCaptureSource name) and prints the
    max and median of the red channel over a strip of pixels (the near ground)."""
    comp = xview_rig.rig_actors()[k].capture_component2d
    comp.set_editor_property("capture_source", getattr(unreal.SceneCaptureSource, source))
    flags = [f for f in comp.get_editor_property("show_flag_settings") if f.show_flag_name != "EyeAdaptation"]
    if eye_adaptation is not None:
        flags.append(unreal.EngineShowFlagsSetting(show_flag_name="EyeAdaptation", enabled=eye_adaptation))
    comp.set_editor_property("show_flag_settings", flags)
    if bias is not None:
        pp = comp.get_editor_property("post_process_settings")
        pp.set_editor_property("auto_exposure_bias", float(bias))
        comp.set_editor_property("post_process_settings", pp)
    for _ in range(2):
        comp.capture_scene()
    rt = comp.texture_target
    vals = sorted(c.r for c in unreal.RenderingLibrary.read_render_target_raw_uv_area(
        xview_rig._world(), rt, unreal.Box2D(unreal.Vector2D(0.3, 0.85), unreal.Vector2D(0.7, 0.95)), False))
    print(xview_rig.REPLY + json.dumps({"source": source, "eye": eye_adaptation, "bias": bias,
                                        "n": len(vals), "median": vals[len(vals) // 2], "max": vals[-1]}))


MARKER_TAG = "XViewMarker"
CYLINDER = "/Engine/BasicShapes/Cylinder.Cylinder"   # 100 cm diameter, 100 cm tall, pivot at centre


def spawn_markers(markers):
    """Spawns transient (never saved) cylinders. markers: list of
    [label, X_cm, Y_cm, ground_z_cm, diameter_cm, height_cm]; each stands on the ground."""
    clear_markers()
    mesh = unreal.load_asset(CYLINDER)
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for label, X, Y, z0, diameter, height in markers:
        actor = sub.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(X, Y, z0 + height / 2),
                                           unreal.Rotator(0, 0, 0), transient=True)
        actor.static_mesh_component.set_static_mesh(mesh)
        actor.set_actor_scale3d(unreal.Vector(diameter / 100, diameter / 100, height / 100))
        actor.set_actor_label("XView_Marker_" + label)
        actor.tags = [MARKER_TAG]
    print(xview_rig.REPLY + json.dumps({"markers": len(markers)}))


def clear_markers():
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    found = unreal.GameplayStatics.get_all_actors_with_tag(xview_rig._world(), MARKER_TAG)
    for actor in found:
        sub.destroy_actor(actor)
    print(xview_rig.REPLY + json.dumps({"cleared": len(found)}))
