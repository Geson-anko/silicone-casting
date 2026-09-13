"""Persistent paired keys can be edited independently without baking mold
halves."""

from collections.abc import Iterator
from math import atan, pi, sin, sqrt

import bpy
import pytest
from _helpers import make_cube_mesh, mesh_data, mesh_invariants
from mathutils import Matrix, Vector

import silicone_casting
from silicone_casting.operators.key_editing import (
    is_registration_key,
    key_socket,
    load_key_settings,
)


@pytest.fixture(scope="module")
def registered() -> Iterator[None]:
    silicone_casting.register()
    yield
    silicone_casting.unregister()


@pytest.fixture
def halves(registered: None) -> Iterator[tuple[bpy.types.Object, bpy.types.Object]]:
    scene = bpy.context.scene
    original_objects = set(bpy.data.objects)
    original_meshes = set(bpy.data.meshes)
    original_scale = scene.unit_settings.scale_length
    original_cursor = scene.cursor.matrix.copy()
    for obj in scene.objects:
        obj.select_set(False)
    male = bpy.data.objects.new("Male half", make_cube_mesh(20, "Male mesh"))
    female = bpy.data.objects.new("Female half", make_cube_mesh(20, "Female mesh"))
    scene.collection.objects.link(male)
    scene.collection.objects.link(female)
    male.location.z = -10
    female.location.z = 10
    male.select_set(True)
    bpy.context.view_layer.objects.active = male
    scene.unit_settings.scale_length = 0.001
    scene.cursor.matrix = Matrix.Identity(4)
    p = scene.silicone_casting
    p.key_mate = female
    p.key_active = None
    p.key_axis = "Z"
    p.key_shape = "CYLINDER"
    p.key_width_mm = 4
    p.key_length_mm = 6
    p.key_height_mm = 3
    p.key_embed_mm = 1
    p.key_clearance_mm = 0.2
    p.key_depth_clearance_mm = 0.4
    p.key_taper = 0.2
    p.key_align_normal = True
    p.key_flip = False
    p.key_angle = 0
    bpy.context.view_layer.update()

    yield male, female

    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    p.key_active = None
    p.key_mate = None
    for obj in list(bpy.data.objects):
        if obj not in original_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        if mesh not in original_meshes:
            bpy.data.meshes.remove(mesh)
    scene.unit_settings.scale_length = original_scale
    scene.cursor.matrix = original_cursor


def _evaluated_mesh(obj: bpy.types.Object) -> bpy.types.Mesh:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    return bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))


def _add(location=(0, 0, 0), normal=(0, 0, 1)) -> bpy.types.Object:
    assert bpy.ops.silicone_casting.add_registration_key(
        location=location, normal=normal
    ) == {"FINISHED"}
    return bpy.context.scene.silicone_casting.key_active


def test_add_creates_a_hidden_editable_pair_and_preserves_source_meshes(halves) -> None:
    male, female = halves
    before = (mesh_data(male.data), mesh_data(female.data))

    pin = _add()

    socket = key_socket(pin)
    assert is_registration_key(pin)
    assert socket is not None
    assert pin.parent == male and socket.parent == female
    assert pin.hide_get() and socket.hide_get()
    assert male.modifiers[0].object == pin
    assert female.modifiers[0].object == socket
    assert (mesh_data(male.data), mesh_data(female.data)) == before
    male_result = mesh_invariants(_evaluated_mesh(male))
    female_result = mesh_invariants(_evaluated_mesh(female))
    assert male_result.is_watertight and female_result.is_watertight
    assert male_result.loose_part_count == female_result.loose_part_count == 1
    assert male_result.volume == pytest.approx(
        8000 + 32 * sin(pi / 32) * 4 * 3, abs=0.002
    )
    assert female_result.volume == pytest.approx(
        8000 - 32 * sin(pi / 32) * 2.2**2 * 3.4, abs=0.002
    )


def test_move_preserves_saved_dimensions_instead_of_applying_unrelated_ui_edits(
    halves,
) -> None:
    pin = _add()
    socket = key_socket(pin)
    before = (mesh_data(pin.data), mesh_data(socket.data))
    p = bpy.context.scene.silicone_casting
    p.key_width_mm = 8
    p.key_height_mm = 5
    p.key_clearance_mm = 0.8
    p.key_shape = "RECTANGLE"

    result = bpy.ops.silicone_casting.move_registration_key(
        key_name=pin.name, location=(4, 0, 0), normal=(0, 0, 1)
    )

    assert result == {"FINISHED"}
    assert (mesh_data(pin.data), mesh_data(socket.data)) == before
    assert tuple(pin.matrix_world.translation) == pytest.approx((4, 0, 0), abs=1e-6)
    assert tuple(socket.matrix_world.translation) == pytest.approx((4, 0, 0), abs=1e-6)
    assert len(halves[0].modifiers) == len(halves[1].modifiers) == 1


def test_edit_updates_selected_pair_dimensions_at_the_same_contact(halves) -> None:
    pin = _add(location=(2, 3, 0))
    p = bpy.context.scene.silicone_casting
    p.key_shape = "RECTANGLE"
    p.key_width_mm = 6
    p.key_length_mm = 8
    p.key_height_mm = 4
    p.key_clearance_mm = 0.3
    p.key_depth_clearance_mm = 0.5
    before_count = (len(bpy.data.objects), len(bpy.data.meshes))

    assert bpy.ops.silicone_casting.edit_registration_key() == {"FINISHED"}

    pin = p.key_active
    socket = key_socket(pin)
    assert tuple(pin.matrix_world.translation) == pytest.approx((2, 3, 0), abs=1e-6)
    assert mesh_invariants(pin.data).bbox_max == pytest.approx((3, 4, 4))
    assert mesh_invariants(socket.data).bbox_max == pytest.approx((3.3, 4.3, 4.5))
    assert (len(bpy.data.objects), len(bpy.data.meshes)) == before_count


@pytest.mark.parametrize("visibility", [(False, True), (True, False), (False, False)])
def test_editing_a_disabled_key_preserves_each_modifier_visibility(
    halves, visibility
) -> None:
    pin = _add()
    socket = key_socket(pin)
    male_modifier = halves[0].modifiers[0]
    female_modifier = halves[1].modifiers[0]
    male_modifier.show_viewport, female_modifier.show_viewport = visibility
    bpy.context.scene.silicone_casting.key_width_mm = 6

    assert bpy.ops.silicone_casting.edit_registration_key() == {"FINISHED"}

    assert (male_modifier.show_viewport, female_modifier.show_viewport) == visibility
    assert max(vertex.co.x for vertex in pin.data.vertices) == pytest.approx(3)
    assert max(vertex.co.x for vertex in socket.data.vertices) == pytest.approx(3.2)


def test_editing_and_deleting_one_pair_does_not_modify_a_second_pair(halves) -> None:
    first = _add(location=(-4, 0, 0))
    bpy.context.view_layer.objects.active = halves[0]
    second = _add(location=(4, 0, 0))
    second_socket = key_socket(second)
    second_before = (mesh_data(second.data), mesh_data(second_socket.data))
    bpy.context.scene.silicone_casting.key_width_mm = 5

    bpy.ops.silicone_casting.edit_registration_key(key_name=first.name)
    assert (mesh_data(second.data), mesh_data(second_socket.data)) == second_before
    assert bpy.ops.silicone_casting.delete_registration_key(key_name=first.name) == {
        "FINISHED"
    }

    assert len(halves[0].modifiers) == len(halves[1].modifiers) == 1
    assert halves[0].modifiers[0].object == second
    assert halves[1].modifiers[0].object == second_socket
    assert (mesh_data(second.data), mesh_data(second_socket.data)) == second_before


def test_delete_removes_pair_data_and_restores_original_mold_geometry(halves) -> None:
    before = (set(bpy.data.objects), set(bpy.data.meshes))
    _add()

    assert bpy.ops.silicone_casting.delete_registration_key() == {"FINISHED"}

    assert (set(bpy.data.objects), set(bpy.data.meshes)) == before
    assert not halves[0].modifiers and not halves[1].modifiers
    assert bpy.context.scene.silicone_casting.key_active is None


def test_renamed_objects_keep_their_pair_and_edit_after_parent_motion(halves) -> None:
    pin = _add(location=(2, 0, 0))
    socket = key_socket(pin)
    pin.name = "Renamed pin"
    socket.name = "Renamed socket"
    halves[0].name = "Renamed male"
    halves[1].name = "Renamed female"
    for half in halves:
        half.location += Vector((30, 5, 0))
    bpy.context.view_layer.update()
    p = bpy.context.scene.silicone_casting
    p.key_width_mm = 5

    assert key_socket(pin) == socket
    assert bpy.ops.silicone_casting.edit_registration_key(key_name=pin.name) == {
        "FINISHED"
    }

    assert tuple(pin.matrix_world.translation) == pytest.approx((32, 5, 0), abs=1e-5)
    assert tuple(socket.matrix_world.translation) == pytest.approx((32, 5, 0), abs=1e-5)
    assert halves[0].modifiers[0].object == pin
    assert halves[1].modifiers[0].object == socket


@pytest.mark.parametrize("operation", ["move", "edit"])
@pytest.mark.parametrize("visible", [False, True])
def test_invalid_move_or_edit_restores_both_helpers_and_modifiers(
    halves, operation, visible
) -> None:
    pin = _add()
    socket = key_socket(pin)
    halves[0].modifiers[0].show_viewport = visible
    halves[1].modifiers[0].show_viewport = visible
    before = (mesh_data(pin.data), mesh_data(socket.data))
    matrices = (pin.matrix_world.copy(), socket.matrix_world.copy())
    counts = (len(bpy.data.objects), len(bpy.data.meshes))

    if operation == "move":
        with pytest.raises(RuntimeError):
            bpy.ops.silicone_casting.move_registration_key(
                key_name=pin.name, location=(100, 0, 0), normal=(0, 0, 1)
            )
    else:
        bpy.context.scene.silicone_casting.key_width_mm = 100
        bpy.context.scene.silicone_casting.key_height_mm = 100
        with pytest.raises(RuntimeError):
            bpy.ops.silicone_casting.edit_registration_key(key_name=pin.name)

    assert (mesh_data(pin.data), mesh_data(socket.data)) == before
    assert (pin.matrix_world, socket.matrix_world) == matrices
    assert (len(bpy.data.objects), len(bpy.data.meshes)) == counts
    assert len(halves[0].modifiers) == len(halves[1].modifiers) == 1
    assert halves[0].modifiers[0].show_viewport == visible
    assert halves[1].modifiers[0].show_viewport == visible
    assert pin.hide_get() and socket.hide_get()


def test_invalid_add_leaves_no_helpers_or_modifiers(halves) -> None:
    before = (set(bpy.data.objects), set(bpy.data.meshes))

    with pytest.raises(RuntimeError):
        bpy.ops.silicone_casting.add_registration_key(
            location=(100, 0, 0), normal=(0, 0, 1)
        )

    assert (set(bpy.data.objects), set(bpy.data.meshes)) == before
    assert not halves[0].modifiers and not halves[1].modifiers


@pytest.mark.parametrize(
    ("axis", "direction"), [("X", (1, 0, 0)), ("Y", (0, 1, 0)), ("Z", (0, 0, 1))]
)
def test_fixed_axis_ignores_cursor_rotation_and_saved_settings_can_be_reloaded(
    halves, axis, direction
) -> None:
    # Rotate the mating plane together with both halves for each world axis.
    rotation = Vector(direction).to_track_quat("Z", "Y").to_matrix().to_4x4()
    for half in halves:
        half.matrix_world = rotation @ half.matrix_world
    bpy.context.view_layer.update()
    p = bpy.context.scene.silicone_casting
    p.key_align_normal = False
    p.key_axis = axis
    p.key_shape = "RECTANGLE"
    p.key_angle = 0.3
    p.key_width_mm = 5
    bpy.context.scene.cursor.matrix = Matrix.Rotation(pi / 3, 4, "X")

    pin = _add(normal=(0, 0, 1))

    assert tuple(pin.matrix_world.to_3x3() @ Vector((0, 0, 1))) == pytest.approx(
        direction, abs=1e-6
    )
    p.key_axis = "Z"
    p.key_align_normal = True
    p.key_shape = "CYLINDER"
    p.key_angle = 0
    p.key_width_mm = 8
    load_key_settings(bpy.context, pin)
    assert p.key_axis == axis
    assert not p.key_align_normal
    assert p.key_shape == "RECTANGLE"
    assert p.key_angle == pytest.approx(0.3)
    assert p.key_width_mm == pytest.approx(5)


@pytest.mark.parametrize("scale", [0.001, 1.0])
def test_taper_angle_builds_matching_slopes_and_survives_reselection(halves, scale):
    p = bpy.context.scene.silicone_casting
    bpy.context.scene.unit_settings.scale_length = scale
    p.key_shape = "TAPERED"
    p.key_width_mm = 8
    p.key_taper_angle = pi / 6
    pin = _add()
    socket = key_socket(pin)
    assert socket is not None
    unit = 0.001 / scale
    # A 30-degree sidewall retreats height / sqrt(3) from the base radius.
    pin_top = max(v.co.x for v in pin.data.vertices if v.co.z > 0)
    socket_top = max(v.co.x for v in socket.data.vertices if v.co.z > 0)
    assert pin_top == pytest.approx((4 - sqrt(3)) * unit)
    assert socket_top == pytest.approx((4.2 - 3.4 / sqrt(3)) * unit)
    assert mesh_invariants(pin.data).is_watertight
    assert mesh_invariants(socket.data).is_watertight

    p.key_taper = 0
    load_key_settings(bpy.context, pin)
    assert p.key_taper_angle == pytest.approx(pi / 6)
    p.key_taper_angle = 0
    assert bpy.ops.silicone_casting.edit_registration_key() == {"FINISHED"}
    assert max(v.co.x for v in pin.data.vertices if v.co.z > 0) == pytest.approx(
        4 * unit
    )


def test_taper_angle_tracks_dimensions_and_limits_tip_reduction(halves):
    p = bpy.context.scene.silicone_casting
    p.key_shape = "TAPERED"
    p.key_depth_clearance_mm = 0
    p.key_taper_angle = pi / 6
    p.key_height_mm = 6
    assert p.key_taper_angle == pytest.approx(atan(0.5 / sqrt(3)))
    p.key_taper_angle = pi / 3
    pin = _add()
    # Requested 60 degrees cannot fit: retain a 10% tip and show the actual angle.
    assert p.key_taper_angle == pytest.approx(atan(1.8 / 6))
    assert max(v.co.x for v in pin.data.vertices if v.co.z > 0) == pytest.approx(0.2)
