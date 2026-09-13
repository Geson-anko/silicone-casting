"""Check live boundary extension and view shortcuts using real GUI events."""

import tempfile
import traceback
from math import cos, pi, sin
from pathlib import Path

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Quaternion, Vector


def _steps():
    assert bpy.app.use_event_simulate
    window = bpy.context.window
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    space = area.spaces.active
    view = space.region_3d
    for obj in bpy.context.scene.objects:
        obj.hide_set(True)
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=0.02)
    target = bpy.context.active_object
    view.view_rotation = Quaternion((1, 0, 0, 0))
    view.view_location = (0, 0, 0)
    view.view_distance = 0.12
    view.view_perspective = "ORTHO"
    space.clip_start = 0.00001
    space.show_region_ui = False
    space.show_gizmo = True
    space.show_gizmo_navigate = True
    bpy.context.preferences.view.mini_axis_type = "GIZMO"
    props = bpy.context.scene.silicone_casting
    props.surface_cut_margin_mm = 0
    bpy.context.scene.unit_settings.scale_length = 0.1
    objects = set(bpy.data.objects)
    yield

    def event(kind, value="PRESS", point=None, pixel=None):
        if pixel is None:
            pixel = (region.width / 2, region.height / 2)
            if point is not None:
                pixel = location_3d_to_region_2d(region, view, Vector(point))
        window.event_simulate(
            type=kind,
            value=value,
            x=round(region.x + pixel[0]),
            y=round(region.y + pixel[1]),
        )

        if value == "PRESS" and kind not in {"LEFTMOUSE", "MOUSEMOVE"}:
            window.event_simulate(
                type=kind,
                value="RELEASE",
                x=round(region.x + pixel[0]),
                y=round(region.y + pixel[1]),
            )

    with bpy.context.temp_override(window=window, area=area, region=region):
        assert bpy.ops.silicone_casting.draw_surface_cut("INVOKE_DEFAULT") == {
            "RUNNING_MODAL"
        }
    yield
    event("MOUSEMOVE", "NOTHING", (0.014, 0, 0))
    yield
    for i in range(121):
        angle = 2 * pi * i / 120
        event(
            "LEFTMOUSE" if i == 0 else "MOUSEMOVE",
            "PRESS" if i == 0 else "NOTHING",
            (0.014 * cos(angle), 0.009 * sin(angle), 0),
        )
        yield
    event("LEFTMOUSE", "RELEASE", (0.014, 0, 0))
    yield
    event("C")
    yield
    preview = next(obj for obj in bpy.data.objects if obj not in objects)
    stroke = [v.co.copy() for v in preview.data.vertices]
    # Start exactly on a tessellation seam and stay on the visible hemisphere.
    # Empty strokes must not make all following preservation checks vacuous.
    assert len(stroke) >= 3
    assert len(preview.data.edges) == len(stroke)
    assert all(point.z > 0 for point in stroke)

    # Axis shortcuts must pass through without consuming or changing strokes.
    for key, direction in [
        ("NUMPAD_1", (0, -1, 0)),
        ("NUMPAD_3", (1, 0, 0)),
        ("NUMPAD_7", (0, 0, 1)),
    ]:
        event(key)
        for _ in range(15):
            yield
        actual = view.view_rotation @ Vector((0, 0, 1))
        assert (actual - Vector(direction)).length < 1e-4, (key, tuple(actual))
        assert [v.co.copy() for v in preview.data.vertices] == stroke

    event("N")
    for _ in range(15):
        yield
    assert space.show_region_ui
    panel = next(r for r in area.regions if r.type == "UI")
    scale = bpy.context.preferences.system.ui_scale
    size = bpy.context.preferences.view.gizmo_size_navigate_v3d
    x_axis = (
        panel.x - region.x - (10 + size * 0.1) * scale,
        panel.y + panel.height - region.y - (10 + size / 2) * scale,
    )
    event("MOUSEMOVE", "NOTHING", pixel=x_axis)
    yield
    event("LEFTMOUSE", pixel=x_axis)
    yield
    event("LEFTMOUSE", "RELEASE", pixel=x_axis)
    for _ in range(20):
        yield
    actual = view.view_rotation @ Vector((0, 0, 1))
    assert (actual - Vector((1, 0, 0))).length < 1e-4
    assert [v.co.copy() for v in preview.data.vertices] == stroke
    event("NUMPAD_7")
    for _ in range(15):
        yield
    # Backspace over the sidebar belongs to UI editing, not drawing history.
    event(
        "BACK_SPACE",
        pixel=(
            panel.x - region.x + panel.width / 2,
            panel.y - region.y + panel.height / 2,
        ),
    )
    yield
    assert [v.co.copy() for v in preview.data.vertices] == stroke
    props.surface_cut_margin_mm = 0.03
    for _ in range(5):
        yield
    event("SPACE")
    yield
    assert preview.data.polygons

    def extension(distance):
        boundary = preview.vertex_groups["Cut Boundary"].index
        indices = {
            v.index
            for v in preview.data.vertices
            if any(g.group == boundary for g in v.groups)
        }
        collar = {v.index for v in preview.data.vertices if not v.groups}
        edges = [
            e
            for e in preview.data.edges
            if len(set(e.vertices) & indices) == 1
            and len(set(e.vertices) & collar) == 1
        ]
        if distance == 0:
            assert not collar
        else:
            assert len(edges) == len(indices)
            for edge in edges:
                a, b = (preview.data.vertices[i].co for i in edge.vertices)
                assert abs((a - b).length - distance) < 1e-7
        return [v.co.copy() for v in preview.data.vertices if v.index in indices]

    boundary = extension(0.0003)
    for millimetres, units in [(0.05, 0.0005), (0, 0), (0.03, 0.0003)]:
        props.surface_cut_margin_mm = millimetres
        for _ in range(5):
            yield
        assert extension(units) == boundary
        assert preview.vertex_groups.get("Cut Interior") is not None
    event("NUMPAD_ENTER")
    yield
    assert len(target.modifiers) == 1
    assert preview.name.endswith(".Cutting Surface")
    with bpy.context.temp_override(window=window, area=area, region=region):
        assert bpy.ops.silicone_casting.draw_surface_cut.poll()


def main():
    bpy.context.preferences.use_preferences_save = False
    bpy.context.preferences.view.show_splash = False
    steps = _steps()
    result = Path(tempfile.gettempdir()) / "silcast-controls-gui-result.txt"
    result.write_text("RUNNING\n")

    def tick():
        try:
            next(steps)
        except StopIteration:
            result.write_text("PASS\n")
            bpy.ops.wm.quit_blender()
            return None
        except Exception:
            error = traceback.format_exc()
            print(error)
            result.write_text(error)
            bpy.ops.wm.quit_blender()
            return None
        return 0.03

    bpy.app.timers.register(tick, first_interval=0.5)


if __name__ == "__main__":
    main()
