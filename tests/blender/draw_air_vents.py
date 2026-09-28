"""Exercise planar vent drawing through real mouse and keyboard events."""

import json
import sys
import tempfile
import traceback
import types
from math import pi, sin
from pathlib import Path

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Quaternion, Vector


def _external_deletion_case(state, window, area, region, event, operator_name, removed):
    """Cancel after Outliner-style deletions and start another drawing."""
    selected = tuple(bpy.context.selected_objects)
    active = bpy.context.active_object
    props = bpy.context.scene.silicone_casting
    input_mode = props.surface_cut_input_mode
    fixtures = []
    fixture_meshes = []
    for obj in selected:
        obj.select_set(False)
    for index, x in enumerate((-3.2, 0, 3.2)):
        with bpy.context.temp_override(window=window, area=area, region=region):
            bpy.ops.mesh.primitive_cube_add(size=2, location=(x, 0, -1))
        obj = bpy.context.active_object
        obj.name = f"External deletion target {index}"
        obj.show_wire = index != 1
        obj.show_all_edges = index == 2
        fixtures.append(obj.name)
        fixture_meshes.append(obj.data.name)
    targets = [bpy.data.objects[name] for name in fixtures]
    for obj in targets:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = targets[1]
    wire = {obj.name: (obj.show_wire, obj.show_all_edges) for obj in targets}
    props.surface_cut_input_mode = "EDGE"
    objects, meshes = set(bpy.data.objects), set(bpy.data.meshes)
    operator = getattr(bpy.ops.silicone_casting, operator_name)

    try:
        with bpy.context.temp_override(window=window, area=area, region=region):
            assert operator("INVOKE_DEFAULT") == {"RUNNING_MODAL"}
        yield
        preview = next(obj for obj in bpy.data.objects if obj not in objects)
        if operator_name == "draw_air_vents" and removed == "preview":
            event("MOUSEMOVE", "NOTHING", (-0.5, 0, 0))
            yield
            event("LEFTMOUSE", point=(-0.5, 0, 0))
            yield
            event("MOUSEMOVE", "NOTHING", (0.5, 0, 0))
            yield
            event("LEFTMOUSE", "RELEASE", (0.5, 0, 0))
            yield
            assert preview.data.polygons, "Create a replacement preview mesh first"

        if removed == "preview":
            preview_mesh_name = preview.data.name
            bpy.data.objects.remove(preview, do_unlink=True)
            survivors = fixtures
        else:
            target = targets[1 if removed == "active target" else 0]
            survivors = [name for name in fixtures if name != target.name]
            objects.remove(target)
            bpy.data.objects.remove(target, do_unlink=True)
        event("ESC")
        for _ in range(5):
            yield

        assert set(bpy.data.objects) == objects
        assert set(bpy.data.meshes) == meshes
        if removed == "preview":
            assert bpy.data.meshes.get(preview_mesh_name) is None
        for name in survivors:
            obj = bpy.data.objects[name]
            assert (obj.show_wire, obj.show_all_edges) == wire[name]
            assert obj.select_get(), "Restore surviving selections after cancellation"
        bpy.context.view_layer.objects.active = bpy.data.objects[survivors[0]]
        with bpy.context.temp_override(window=window, area=area, region=region):
            assert bpy.ops.silicone_casting.draw_air_vents.poll()
            assert bpy.ops.silicone_casting.draw_surface_cut.poll()
            assert operator("INVOKE_DEFAULT") == {"RUNNING_MODAL"}
        yield
        event("ESC")
        for _ in range(5):
            yield
        assert set(bpy.data.objects) == objects
        assert set(bpy.data.meshes) == meshes
        with bpy.context.temp_override(window=window, area=area, region=region):
            assert bpy.ops.silicone_casting.draw_air_vents.poll()
            assert bpy.ops.silicone_casting.draw_surface_cut.poll()
        state.checks.append(
            f"{operator_name}: deleting {removed} allows cancel/restart"
        )
    finally:
        for name in fixtures:
            obj = bpy.data.objects.get(name)
            if obj is not None:
                bpy.data.objects.remove(obj, do_unlink=True)
        for name in fixture_meshes:
            mesh = bpy.data.meshes.get(name)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        props.surface_cut_input_mode = input_mode
        for obj in selected:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = active


def _steps(state):
    assert bpy.app.use_event_simulate
    addon = sys.modules["bl_ext.user_default.silicone_casting"]
    window = bpy.context.window
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    space = area.spaces.active
    view = space.region_3d
    for obj in bpy.context.scene.objects:
        obj.select_set(False)
        obj.hide_set(True)
    targets = []
    for index, x in enumerate((0, 3.2, -3.2)):
        with bpy.context.temp_override(window=window, area=area, region=region):
            bpy.ops.mesh.primitive_cube_add(size=2, location=(x, 0, -1))
        obj = bpy.context.active_object
        obj.name = f"Vent Test {index}"
        targets.append(obj)
    for obj in targets:
        obj.select_set(obj != targets[2])
    target_names = [obj.name for obj in targets]
    bpy.context.view_layer.objects.active = targets[0]
    view.view_rotation = Quaternion((1, 0, 0, 0))
    view.view_location = (1.2, 0, 0)
    view.view_distance = 9
    view.view_perspective = "ORTHO"
    space.show_region_ui = False
    space.clip_start = 0.00001
    props = bpy.context.scene.silicone_casting
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 0.001
    props.air_vent_diameter = 0.2
    original_meshes = [obj.data for obj in targets]
    objects = set(bpy.data.objects)
    meshes = set(bpy.data.meshes)
    yield

    def invoke():
        with bpy.context.temp_override(window=window, area=area, region=region):
            assert bpy.ops.silicone_casting.draw_air_vents("INVOKE_DEFAULT") == {
                "RUNNING_MODAL"
            }
            assert not bpy.ops.silicone_casting.draw_surface_cut.poll()

    def event(kind, value="PRESS", point=None, pixel=None, **modifiers):
        if pixel is None:
            pixel = (region.width / 2, region.height / 2)
            if point is not None:
                pixel = location_3d_to_region_2d(region, view, Vector(point))
        x, y = round(region.x + pixel[0]), round(region.y + pixel[1])
        window.event_simulate(type=kind, value=value, x=x, y=y, **modifiers)
        if value == "PRESS" and kind not in {"LEFTMOUSE", "MOUSEMOVE"}:
            window.event_simulate(type=kind, value="RELEASE", x=x, y=y, **modifiers)

    # An initial click in empty space does not fix the plane or make a tube.
    invoke()
    yield
    preview = next(obj for obj in bpy.data.objects if obj not in objects)
    event("MOUSEMOVE", "NOTHING", (1.6, 2, 0))
    yield
    event("LEFTMOUSE", point=(1.6, 2, 0))
    yield
    event("LEFTMOUSE", "RELEASE", (1.6, 2, 0))
    yield
    assert not preview.data.vertices
    event("RET")
    yield
    assert not any(obj.modifiers for obj in targets)
    event("ESC")
    yield
    assert set(bpy.data.objects) == objects
    assert set(bpy.data.meshes) == meshes
    state.checks.append("empty click and cancel")

    with bpy.context.temp_override(window=window, area=area, region=region):
        assert bpy.ops.silicone_casting.draw_surface_cut("INVOKE_DEFAULT") == {
            "RUNNING_MODAL"
        }
        assert not bpy.ops.silicone_casting.draw_air_vents.poll()
    yield
    event("ESC")
    yield
    assert set(bpy.data.objects) == objects
    assert set(bpy.data.meshes) == meshes
    state.checks.append("surface cuts and air vents cannot draw simultaneously")

    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.ed.undo_push(message="Before drawing air vents")
    invoke()
    yield
    preview = next(obj for obj in bpy.data.objects if obj not in objects)
    event("MOUSEMOVE", "NOTHING", (-0.8, 0, 0))
    yield
    for i in range(41):
        t = i / 40
        point = (-0.8 + 5.2 * t, 0.35 * sin(pi * t), 0)
        event(
            "LEFTMOUSE" if i == 0 else "MOUSEMOVE",
            "PRESS" if i == 0 else "NOTHING",
            point,
        )
        yield
    event("LEFTMOUSE", "RELEASE", (4.4, 0, 0))
    yield
    assert preview.data.polygons, "The curved stroke did not generate a pipe"
    assert max(v.co.x for v in preview.data.vertices) > 4.3
    assert abs(max(v.co.z for v in preview.data.vertices) - 0.1) < 1e-4
    assert abs(min(v.co.z for v in preview.data.vertices) + 0.1) < 1e-4
    assert not any(obj.modifiers for obj in targets)
    state.checks.append("curved tube extends beyond the clicked face")

    props.air_vent_diameter = 0.3
    for _ in range(5):
        yield
    assert abs(max(v.co.z for v in preview.data.vertices) - 0.15) < 1e-4
    state.checks.append("live unit-aware diameter")
    # Make a right-angle line with Ctrl-click, then exceed its bend radius.
    for i, point in enumerate(((-0.7, -0.7, 0), (0, -0.7, 0), (0, 0, 0))):
        event("MOUSEMOVE", "NOTHING", point)
        yield
        event("LEFTMOUSE", point=point, ctrl=i > 0)
        yield
        event("LEFTMOUSE", "RELEASE", point, ctrl=i > 0)
        yield
    assert preview.data.polygons
    props.air_vent_diameter = 2
    for _ in range(5):
        yield
    assert not preview.data.polygons
    event("RET")
    yield
    assert not any(obj.modifiers for obj in targets)
    event("BACK_SPACE")
    yield
    props.air_vent_diameter = 0.3
    for _ in range(5):
        yield
    assert preview.data.polygons
    state.checks.append("invalid diameter cannot commit a stale tube")
    before_navigation = [v.co.copy() for v in preview.data.vertices]
    event("NUMPAD_1")
    for _ in range(15):
        yield
    assert (view.view_rotation @ Vector((0, 0, 1)) - Vector((0, -1, 0))).length < 1e-4
    event("MOUSEMOVE", "NOTHING")
    yield
    event("LEFTMOUSE")
    yield
    event("LEFTMOUSE", "RELEASE")
    yield
    assert [v.co.copy() for v in preview.data.vertices] == before_navigation
    event("NUMPAD_7")
    for _ in range(15):
        yield
    state.checks.append("view navigation preserves the fixed plane")

    event("S")
    yield
    assert preview.data.polygons
    smooth_mesh = [v.co.copy() for v in preview.data.vertices]
    event("Z", ctrl=True)
    yield
    assert [v.co.copy() for v in preview.data.vertices] == before_navigation
    event("Z", ctrl=True, shift=True)
    yield
    assert [v.co.copy() for v in preview.data.vertices] == smooth_mesh
    state.checks.append("smooth and stroke undo/redo")

    # A second stroke lies on the same plane even when it starts in empty space.
    event("MOUSEMOVE", "NOTHING", (1.6, -1.5, 0))
    yield
    event("LEFTMOUSE", point=(1.6, -1.5, 0))
    yield
    event("MOUSEMOVE", "NOTHING", (1.6, 1.5, 0))
    yield
    event("LEFTMOUSE", "RELEASE", (1.6, 1.5, 0))
    yield
    assert preview.data.polygons
    second_count = len(preview.data.vertices)
    assert second_count > len(smooth_mesh)
    event("BACK_SPACE")
    yield
    assert [v.co.copy() for v in preview.data.vertices] == smooth_mesh
    event("Z", ctrl=True)
    yield
    assert len(preview.data.vertices) == second_count
    state.checks.append("multiple strokes and removal")

    event("RET")
    for _ in range(5):
        yield
    assert len(targets[0].modifiers) == len(targets[1].modifiers) == 1
    assert not targets[2].modifiers
    cutter = targets[0].modifiers[-1].object
    assert targets[1].modifiers[-1].object == cutter
    assert cutter.hide_render
    assert [obj.data for obj in targets] == original_meshes
    assert set(bpy.context.selected_objects) == set(targets[:2])
    state.checks.append("shared Boolean cuts only the original targets")

    from bl_ext.user_default.silicone_casting.core.volume import world_volume

    depsgraph = bpy.context.evaluated_depsgraph_get()
    for target in targets[:2]:
        assert 7 < world_volume(target, depsgraph) < 8
    state.checks.append("both cut meshes remain closed with reduced volume")
    cutter_name = cutter.name
    event("Z", ctrl=True)
    for _ in range(10):
        yield
    assert bpy.data.objects.get(cutter_name) is None
    assert not bpy.data.objects[target_names[0]].modifiers
    assert not bpy.data.objects[target_names[1]].modifiers
    event("Z", ctrl=True, shift=True)
    for _ in range(10):
        yield
    assert bpy.data.objects.get(cutter_name) is not None
    assert len(bpy.data.objects[target_names[0]].modifiers) == 1
    state.checks.append("native undo/redo restores the complete operation")

    objects, meshes = set(bpy.data.objects), set(bpy.data.meshes)
    invoke()
    yield
    event("MOUSEMOVE", "NOTHING", (0, -0.5, 0))
    yield
    event("LEFTMOUSE", point=(0, -0.5, 0))
    yield
    event("MOUSEMOVE", "NOTHING", (0.5, -0.5, 0))
    yield
    event("LEFTMOUSE", "RELEASE", (0.5, -0.5, 0))
    yield
    event("ESC")
    yield
    assert set(bpy.data.objects) == objects
    assert set(bpy.data.meshes) == meshes
    state.checks.append("cancel after drawing leaves no orphan meshes")

    for operator_name in ("draw_air_vents", "draw_surface_cut"):
        for removed in ("preview", "active target", "selected target"):
            yield from _external_deletion_case(
                state, window, area, region, event, operator_name, removed
            )
    assert set(bpy.data.objects) == objects
    assert set(bpy.data.meshes) == meshes

    # Disabling the extension must clean up an active modal preview as well.
    invoke()
    yield
    addon.unregister()
    yield
    assert set(bpy.data.objects) == objects
    assert set(bpy.data.meshes) == meshes
    addon.register()
    state.checks.append("extension disable removes an unfinished drawing")


def run():
    """Start the GUI checks without blocking Blender's event loop."""
    state = types.ModuleType("silcast_air_vent_gui_test")
    state.checks = []
    state.status = "running"
    state.error = ""
    sys.modules[state.__name__] = state
    steps = _steps(state)
    result = Path(tempfile.gettempdir()) / "silcast-air-vents-gui.json"

    def tick():
        try:
            next(steps)
            return 0.12
        except StopIteration:
            state.status = "passed"
        except Exception:
            state.status = "failed"
            state.error = traceback.format_exc()
            print(state.error)
        result.write_text(
            json.dumps(
                {"status": state.status, "checks": state.checks, "error": state.error},
                indent=2,
            )
        )
        print(f"Air vent GUI checks: {state.status}; {result}")
        return None

    bpy.app.timers.register(tick, first_interval=0.2)


if __name__ == "__main__":
    run()
