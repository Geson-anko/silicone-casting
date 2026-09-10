"""Drawing is cancellable and the generated interior can be edited directly."""

import bpy
import pytest
from mathutils import Vector

import silicone_casting
from silicone_casting.core import create_surface_cut, interpolate_cutting_surface
from silicone_casting.operators import (
    SILCAST_OT_draw_surface_cut,
    SILCAST_OT_edit_cutting_surface,
    cancel_surface_drawing,
)


@pytest.fixture(scope="module", autouse=True)
def registered():
    silicone_casting.register()
    yield
    silicone_casting.unregister()


@pytest.fixture
def active_cube(cube_object):
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    cube_object.select_set(True)
    bpy.context.view_layer.objects.active = cube_object
    yield cube_object
    cancel_surface_drawing()
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def test_drawing_needs_a_mesh_and_a_3d_view(active_cube):
    area = next(a for a in bpy.context.screen.areas if a.type == "VIEW_3D")
    with bpy.context.temp_override(area=area):
        assert SILCAST_OT_draw_surface_cut.poll(bpy.context)
        bpy.context.view_layer.objects.active = None
        assert not SILCAST_OT_draw_surface_cut.poll(bpy.context)


def test_edit_surface_selects_only_interior_without_applying_the_cut(
    active_cube, make_object
):
    loop = [
        Vector((-1, -1, 0)),
        Vector((1, -1, 0)),
        Vector((1, 1, 0)),
        Vector((-1, 1, 0)),
    ]
    mesh, boundary, interior = interpolate_cutting_surface([loop], margin=0.05)
    surface = make_object(mesh)
    surface.display_type = "WIRE"
    surface.vertex_groups.new(name="Cut Boundary").add(boundary, 1.0, "REPLACE")
    surface.vertex_groups.new(name="Cut Interior").add(interior, 1.0, "REPLACE")
    original = active_cube.data
    modifier = create_surface_cut(active_cube, surface, 0.01, minimum_thickness=0.001)
    node_group = modifier.node_group
    try:
        assert SILCAST_OT_edit_cutting_surface.poll(bpy.context)
        assert bpy.ops.silicone_casting.edit_cutting_surface() == {"FINISHED"}
        assert bpy.context.mode == "EDIT_MESH"
        assert bpy.context.view_layer.objects.active == surface
        assert surface.display_type == "SOLID"
        bpy.ops.object.mode_set(mode="OBJECT")
        assert {vertex.index for vertex in mesh.vertices if vertex.select} == set(
            interior
        )
        assert active_cube.data == original
        assert len(active_cube.modifiers) == 1
    finally:
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        active_cube.modifiers.remove(modifier)
        bpy.data.node_groups.remove(node_group)
