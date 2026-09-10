"""Exercise freehand input in a GUI started with --enable-event-simulate.

Run after installing the extension, in a disposable Blender window.
Unlike the background integration suite, this drives real window events
and leaves the final curved cut visible for inspection. The timer prints
a final result and writes it to the temporary directory for automation.
"""

import tempfile
import traceback
from math import cos, pi, sin
from pathlib import Path

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Quaternion, Vector


def _assert_split(target):
    evaluated = target.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        edges = {}
        adjacent = [set() for _ in mesh.vertices]
        for polygon in mesh.polygons:
            face = list(polygon.vertices)
            for a, b in zip(face, face[1:] + face[:1]):
                key = tuple(sorted((a, b)))
                edges[key] = edges.get(key, 0) + 1
                adjacent[a].add(b)
                adjacent[b].add(a)
        assert edges and all(count == 2 for count in edges.values())
        remaining = set(range(len(adjacent)))
        parts = 0
        while remaining:
            parts += 1
            stack = [remaining.pop()]
            while stack:
                neighbors = adjacent[stack.pop()] & remaining
                remaining.difference_update(neighbors)
                stack.extend(neighbors)
        assert parts == 2, f"Expected two parts, got {parts}"
    finally:
        evaluated.to_mesh_clear()


def _steps():
    assert bpy.app.use_event_simulate, "Start Blender with --enable-event-simulate"
    window = bpy.context.window
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    view = area.spaces.active.region_3d
    for obj in bpy.context.scene.objects:
        obj.hide_set(True)
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=0.02)
    sphere = bpy.context.active_object
    sphere.name = "Draw Test - Curved Solid"
    view.view_rotation = Quaternion((1, 0, 0, 0))
    view.view_location = (0, 0, 0)
    view.view_distance = 0.12
    view.view_perspective = "ORTHO"
    area.spaces.active.clip_start = 0.00001
    area.tag_redraw()
    bpy.context.scene.silicone_casting.surface_cut_thickness_mm = 0.001
    yield

    def invoke():
        with bpy.context.temp_override(window=window, area=area, region=region):
            assert bpy.ops.silicone_casting.draw_surface_cut("INVOKE_DEFAULT") == {
                "RUNNING_MODAL"
            }

    def event(kind, value="PRESS", point=None):
        pixel = (
            location_3d_to_region_2d(region, view, point)
            if point is not None
            else Vector((region.width / 2, region.height / 2))
        )
        assert pixel is not None
        window.event_simulate(
            type=kind,
            value=value,
            x=round(region.x + pixel.x),
            y=round(region.y + pixel.y),
        )

    def stroke(rx, ry):
        start = Vector((rx, 0, 0))
        event("LEFTMOUSE", point=start)
        yield
        for i in range(1, 121):
            angle = 2 * pi * i / 120
            event("MOUSEMOVE", "NOTHING", Vector((rx * cos(angle), ry * sin(angle), 0)))
            yield
        event("LEFTMOUSE", "RELEASE", start)
        yield
        event("C")
        yield

    # Cancel after actual input, then start a fresh drawing without leaked data.
    objects = set(bpy.data.objects)
    meshes = set(bpy.data.meshes)
    invoke()
    yield
    event("LEFTMOUSE", point=Vector((0.01, 0, 0)))
    yield
    event("MOUSEMOVE", "NOTHING", Vector((0.01, 0.002, 0)))
    yield
    event("LEFTMOUSE", "RELEASE", Vector((0.01, 0.002, 0)))
    yield
    event("ESC")
    yield
    assert set(bpy.data.objects) == objects
    assert set(bpy.data.meshes) == meshes
    assert len(sphere.modifiers) == 0
    assert set(bpy.context.selected_objects) == {sphere}

    invoke()
    yield
    yield from stroke(0.014, 0.009)
    event("SPACE")
    yield
    preview = next(obj for obj in bpy.data.objects if obj not in objects)
    assert preview.data.polygons
    assert preview.vertex_groups.get("Cut Interior") is not None
    assert len(sphere.modifiers) == 0
    event("RET")
    yield
    assert len(sphere.modifiers) == 1
    _assert_split(sphere)
    with bpy.context.temp_override(window=window, area=area, region=region):
        assert bpy.ops.silicone_casting.edit_cutting_surface() == {"FINISHED"}
        assert bpy.context.mode == "EDIT_MESH"
        # Shape the center with a smooth falloff. Translating every interior
        # vertex uniformly would lift the rim-adjacent vertices through the
        # spherical skin and intentionally create additional intersections.
        bpy.ops.mesh.select_all(action="DESELECT")
        center = location_3d_to_region_2d(region, view, Vector((0, 0, 0)))
        bpy.ops.view3d.select(location=(round(center.x), round(center.y)))
        bpy.ops.transform.translate(
            value=(0, 0, 0.001),
            use_proportional_edit=True,
            proportional_size=0.006,
            proportional_edit_falloff="SMOOTH",
        )
        bpy.ops.object.mode_set(mode="OBJECT")
    yield
    _assert_split(sphere)
    sphere.hide_set(True)
    preview.hide_set(True)

    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.03, minor_radius=0.01, major_segments=128, minor_segments=48
        )
    torus = bpy.context.active_object
    torus.name = "Draw Test - Hollow Mold"
    view.view_distance = 0.22
    area.tag_redraw()
    yield
    objects = set(bpy.data.objects)
    invoke()
    yield
    yield from stroke(0.038, 0.038)
    yield from stroke(0.022, 0.022)
    event("SPACE")
    yield
    preview = next(obj for obj in bpy.data.objects if obj not in objects)
    assert preview.data.polygons
    assert len(torus.modifiers) == 0
    event("RET")
    yield
    assert len(torus.modifiers) == 1
    _assert_split(torus)
    area.spaces.active.show_region_ui = True
    print("PASS: freehand cancel, curved solid, interior edit, hollow two-loop cut")


def main():
    steps = _steps()
    result = Path(tempfile.gettempdir()) / "silcast-draw-gui-result.txt"
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
        return 0.03

    bpy.app.timers.register(tick, first_interval=0.5)


if __name__ == "__main__":
    main()
