"""Exercise vertex and edge input with real window events in a disposable
GUI."""

import tempfile
import traceback
from pathlib import Path

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Quaternion, Vector


def _steps():
    assert bpy.app.use_event_simulate
    window = bpy.context.window
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    view = area.spaces.active.region_3d
    for obj in bpy.context.scene.objects:
        obj.hide_set(True)
        obj.select_set(False)
    mesh = bpy.data.meshes.new("Snap Target")
    rim = [
        Vector(p)
        for p in [
            (-0.02, -0.02, 0),
            (0.02, -0.02, 0),
            (0.02, 0.02, 0),
            (-0.02, 0.02, 0),
        ]
    ]
    faces = []
    for i in range(4):
        j = (i + 1) % 4
        faces.extend(((i, j, 4), (j, i, 5)))
    mesh.from_pydata([*rim, (0, 0, 0.03), (0, 0, -0.03)], [], faces)
    mesh.update()
    target = bpy.data.objects.new("Snap Target", mesh)
    bpy.context.scene.collection.objects.link(target)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    view.view_rotation = Quaternion((1, 0, 0, 0))
    view.view_location = (0, 0, 0)
    view.view_distance = 0.16
    view.view_perspective = "ORTHO"
    area.spaces.active.clip_start = 0.00001
    bpy.context.scene.unit_settings.scale_length = 1
    props = bpy.context.scene.silicone_casting
    props.surface_cut_margin_mm = 0.2
    yield

    def event(kind, value="PRESS", point=None, offset=(0, 0), ctrl=False):
        pixel = location_3d_to_region_2d(region, view, point or Vector((0, 0, 0)))
        window.event_simulate(
            type=kind,
            value=value,
            ctrl=ctrl,
            x=round(region.x + pixel.x + offset[0]),
            y=round(region.y + pixel.y + offset[1]),
        )

    def click(point, offset=(0, 0)):
        event("MOUSEMOVE", "NOTHING", point, offset)
        yield
        event("LEFTMOUSE", point=point, offset=offset)
        yield
        event("LEFTMOUSE", "RELEASE", point, offset)
        yield

    objects = set(bpy.data.objects)
    for mode in ("VERTEX", "EDGE"):
        props.surface_cut_input_mode = mode
        with bpy.context.temp_override(window=window, area=area, region=region):
            assert bpy.ops.silicone_casting.draw_surface_cut("INVOKE_DEFAULT") == {
                "RUNNING_MODAL"
            }
        yield
        preview = next(obj for obj in bpy.data.objects if obj not in objects)
        if mode == "VERTEX":
            # A cursor offset must still store the exact original vertices.
            for point in rim[:2]:
                yield from click(point, (3, 2))
            props.surface_cut_input_mode = "EDGE"
            yield from click((rim[1] + rim[2]) / 2)
            props.surface_cut_input_mode = "VERTEX"
            for point in [rim[3], rim[0]]:
                yield from click(point, (3, 2))
        else:
            for i in range(4):
                yield from click((rim[i] + rim[(i + 1) % 4]) / 2)
            # Undo a picked edge and re-add it without losing the earlier edges.
            event("Z", ctrl=True)
            yield
            assert len(preview.data.edges) == 3
            yield from click((rim[3] + rim[0]) / 2)
        assert len(preview.data.vertices) == 5
        assert all(
            any((vertex.co - point).length < 1e-8 for point in rim)
            for vertex in preview.data.vertices
        )
        event("C")
        yield
        event("SPACE")
        yield
        assert preview.data.polygons
        group = preview.vertex_groups["Cut Boundary"].index
        boundary = [
            vertex.co
            for vertex in preview.data.vertices
            if any(item.group == group for item in vertex.groups)
        ]
        assert len(boundary) == 4
        assert all(
            any((point - expected).length < 1e-8 for expected in rim)
            for point in boundary
        )
        event("ESC")
        yield
        assert set(bpy.data.objects) == objects
        assert not target.show_wire and not target.show_all_edges
        assert bpy.context.active_object == target
    props.surface_cut_input_mode = "FREEHAND"
    print("PASS: vertex snapping, connected edge input, undo, preview, cancel")


def main():
    steps = _steps()
    result = Path(tempfile.gettempdir()) / "silcast-snap-gui-result.txt"
    result.write_text("RUNNING\n")

    def tick():
        try:
            next(steps)
        except StopIteration:
            result.write_text("PASS\n")
            return None
        except Exception:
            error = traceback.format_exc()
            print(error)
            result.write_text(error)
            return None
        return 0.1

    bpy.app.timers.register(tick, first_interval=0.5)


if __name__ == "__main__":
    main()
