"""Starting or cancelling a drawing preserves the selected mold objects."""

import bpy
import pytest

import silicone_casting
from silicone_casting.operators.draw_air_vents import (
    SILCAST_OT_draw_air_vents,
    cancel_air_vent_drawing,
)


@pytest.fixture(scope="module", autouse=True)
def registered():
    silicone_casting.register()
    yield
    silicone_casting.unregister()


@pytest.fixture
def drawing_context(cube_object):
    selected = tuple(bpy.context.selected_objects)
    active = bpy.context.view_layer.objects.active
    for obj in selected:
        obj.select_set(False)
    cube_object.select_set(True)
    bpy.context.view_layer.objects.active = cube_object
    area = next(a for a in bpy.context.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(area=area, region=region):
        yield cube_object
        cancel_air_vent_drawing()
    cube_object.select_set(False)
    for obj in selected:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active


def test_drawing_requires_selected_meshes_in_object_mode(drawing_context):
    assert SILCAST_OT_draw_air_vents.poll(bpy.context)
    drawing_context.select_set(False)
    assert not SILCAST_OT_draw_air_vents.poll(bpy.context)
    drawing_context.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        assert not SILCAST_OT_draw_air_vents.poll(bpy.context)
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
