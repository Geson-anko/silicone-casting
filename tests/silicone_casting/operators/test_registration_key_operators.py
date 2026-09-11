"""Paired key placement previews and editable Boolean results in real
Blender."""

from collections.abc import Iterator
from math import pi, sin

import bpy
import pytest
from _helpers import make_cube_mesh, mesh_data, mesh_invariants
from mathutils import Matrix, Vector

import silicone_casting
from silicone_casting.operators.registration_keys import (
    SILCAST_OT_commit_registration_key,
    SILCAST_OT_preview_registration_key,
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
    bpy.ops.silicone_casting.cancel_registration_key()
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


def test_preview_snaps_to_the_face_without_changing_either_half(halves) -> None:
    male, female = halves
    before = (mesh_data(male.data), mesh_data(female.data))
    bpy.context.scene.cursor.location = (2, 3, 0.7)

    assert bpy.ops.silicone_casting.preview_registration_key() == {"FINISHED"}

    p = bpy.context.scene.silicone_casting
    assert tuple(p.key_preview_pin.matrix_world.translation) == pytest.approx((2, 3, 0))
    assert p.key_preview_pin.show_in_front
    assert p.key_preview_socket.display_type == "WIRE"
    assert not male.modifiers and not female.modifiers
    assert (mesh_data(male.data), mesh_data(female.data)) == before


def test_updating_preview_replaces_helpers_and_applies_new_dimensions(halves) -> None:
    bpy.ops.silicone_casting.preview_registration_key()
    p = bpy.context.scene.silicone_casting
    count = (len(bpy.data.objects), len(bpy.data.meshes))
    p.key_width_mm = 6
    bpy.context.scene.cursor.location = (4, 0, 0)

    bpy.ops.silicone_casting.preview_registration_key()

    assert (len(bpy.data.objects), len(bpy.data.meshes)) == count
    assert tuple(p.key_preview_pin.matrix_world.translation) == pytest.approx(
        (4, 0, 0), abs=1e-6
    )
    assert mesh_invariants(p.key_preview_pin.data).bbox_max == pytest.approx((3, 3, 3))


def test_cancelling_preview_removes_both_objects_and_meshes(halves) -> None:
    male, female = halves
    before = (set(bpy.data.objects), set(bpy.data.meshes))
    bpy.ops.silicone_casting.preview_registration_key()

    assert bpy.ops.silicone_casting.cancel_registration_key() == {"FINISHED"}

    assert (set(bpy.data.objects), set(bpy.data.meshes)) == before
    assert not male.modifiers and not female.modifiers
    assert not SILCAST_OT_commit_registration_key.poll(bpy.context)


@pytest.mark.parametrize(
    ("shape", "added", "removed"),
    [
        ("CYLINDER", 32 * sin(pi / 32) * 4 * 3, 32 * sin(pi / 32) * 2.2**2 * 3.4),
        ("RECTANGLE", 4 * 6 * 3, 4.4 * 6.4 * 3.4),
        (
            "TAPERED",
            32 * sin(pi / 32) * (4 + 2 * 1.6 + 1.6**2),
            3.4
            / 3
            * 32
            * sin(pi / 32)
            * (
                2.2**2
                + 2.2 * (1.6 - 0.4 * 0.4 / 3 + 0.2)
                + (1.6 - 0.4 * 0.4 / 3 + 0.2) ** 2
            ),
        ),
    ],
)
def test_confirm_creates_one_closed_pin_and_socket_with_requested_clearance(
    halves, shape: str, added: float, removed: float
) -> None:
    male, female = halves
    before = (mesh_data(male.data), mesh_data(female.data))
    bpy.context.scene.silicone_casting.key_shape = shape
    bpy.ops.silicone_casting.preview_registration_key()

    assert bpy.ops.silicone_casting.commit_registration_key() == {"FINISHED"}

    assert (mesh_data(male.data), mesh_data(female.data)) == before
    assert male.modifiers[0].operation == "UNION"
    assert female.modifiers[0].operation == "DIFFERENCE"
    assert male.modifiers[0].object.hide_get()
    assert female.modifiers[0].object.hide_get()
    assert not SILCAST_OT_commit_registration_key.poll(bpy.context)
    male_result = mesh_invariants(_evaluated_mesh(male))
    female_result = mesh_invariants(_evaluated_mesh(female))
    assert male_result.is_watertight and female_result.is_watertight
    assert male_result.loose_part_count == female_result.loose_part_count == 1
    assert male_result.volume == pytest.approx(8000 + added, abs=0.002)
    assert female_result.volume == pytest.approx(8000 - removed, abs=0.002)


def test_repeated_placement_retains_two_independent_pairs(halves) -> None:
    male, female = halves
    bpy.context.scene.cursor.location.x = -4
    bpy.ops.silicone_casting.preview_registration_key()
    bpy.ops.silicone_casting.commit_registration_key()
    first_pin = male.modifiers[0].object
    bpy.context.scene.cursor.location.x = 4
    bpy.ops.silicone_casting.preview_registration_key()

    bpy.ops.silicone_casting.commit_registration_key()

    assert len(male.modifiers) == len(female.modifiers) == 2
    assert male.modifiers[0].object == first_pin
    assert male.modifiers[1].object != first_pin
    result = mesh_invariants(_evaluated_mesh(male))
    assert result.is_watertight and result.loose_part_count == 1
    assert result.volume == pytest.approx(
        8000 + 2 * 32 * sin(pi / 32) * 4 * 3, abs=0.002
    )


def test_scaled_rotated_target_keeps_world_size_and_world_face_normal(halves) -> None:
    male, _female = halves
    male.scale = (2, 0.5, 1.5)
    male.rotation_euler = (0.4, -0.3, 0.2)
    bpy.context.view_layer.update()
    surface_point = male.matrix_world @ Vector((0, 0, 10))
    normal = (
        male.matrix_world.to_3x3().inverted().transposed() @ Vector((0, 0, 1))
    ).normalized()
    bpy.context.scene.cursor.location = surface_point + normal * 0.1

    bpy.ops.silicone_casting.preview_registration_key()

    pin = bpy.context.scene.silicone_casting.key_preview_pin
    assert tuple(pin.matrix_world.translation) == pytest.approx(
        tuple(surface_point), abs=1e-5
    )
    assert tuple(pin.matrix_world.to_3x3() @ Vector((0, 0, 1))) == pytest.approx(
        tuple(normal), abs=1e-6
    )
    assert tuple(pin.matrix_world.to_scale()) == pytest.approx((1, 1, 1))
    assert mesh_invariants(pin.data).bbox_max == pytest.approx((2, 2, 3))


def test_preview_uses_the_evaluated_surface_including_modifiers(halves) -> None:
    male, _female = halves
    modifier = male.modifiers.new("Surface thickness", "SOLIDIFY")
    modifier.thickness = 0.5
    modifier.offset = 1
    modifier.use_even_offset = True
    bpy.context.scene.cursor.location = (0, 0, 1)

    bpy.ops.silicone_casting.preview_registration_key()

    pin = bpy.context.scene.silicone_casting.key_preview_pin
    assert pin.matrix_world.translation.z == pytest.approx(0.5, abs=1e-5)
    assert len(male.modifiers) == 1


@pytest.mark.parametrize("flip", [False, True])
def test_cursor_orientation_and_flip_control_key_direction(halves, flip: bool) -> None:
    p = bpy.context.scene.silicone_casting
    p.key_align_normal = False
    p.key_flip = flip
    bpy.context.scene.cursor.matrix = Matrix.Rotation(pi / 2, 4, "Y")

    bpy.ops.silicone_casting.preview_registration_key()

    axis = p.key_preview_pin.matrix_world.to_3x3() @ Vector((0, 0, 1))
    assert tuple(axis) == pytest.approx(((-1) ** flip, 0, 0), abs=1e-6)


def test_confirm_failure_keeps_preview_and_rolls_back_both_modifiers(halves) -> None:
    male, female = halves
    female.location.x = 100
    bpy.context.view_layer.update()
    bpy.ops.silicone_casting.preview_registration_key()
    p = bpy.context.scene.silicone_casting
    pin, socket = p.key_preview_pin, p.key_preview_socket

    with pytest.raises(RuntimeError):
        bpy.ops.silicone_casting.commit_registration_key()

    assert not male.modifiers and not female.modifiers
    assert p.key_preview_pin == pin and p.key_preview_socket == socket
    assert not pin.hide_get() and not socket.hide_get()


def test_confirm_rejects_a_key_entirely_inside_the_male(halves) -> None:
    male, female = halves
    bpy.ops.silicone_casting.preview_registration_key()
    bpy.context.scene.silicone_casting.key_preview_pin.location.z = -5
    bpy.context.view_layer.update()

    with pytest.raises(RuntimeError):
        bpy.ops.silicone_casting.commit_registration_key()

    assert not male.modifiers and not female.modifiers


def test_preview_requires_distinct_mesh_halves_and_object_mode(halves) -> None:
    male, _female = halves
    p = bpy.context.scene.silicone_casting
    p.key_mate = male
    assert not SILCAST_OT_preview_registration_key.poll(bpy.context)
    p.key_mate = None
    assert not SILCAST_OT_preview_registration_key.poll(bpy.context)
    p.key_mate = halves[1]
    bpy.ops.object.mode_set(mode="EDIT")
    assert not SILCAST_OT_preview_registration_key.poll(bpy.context)


def test_empty_target_is_rejected_without_allocating_preview_objects(halves) -> None:
    male, _female = halves
    male.data = bpy.data.meshes.new("Empty surface")
    bpy.context.view_layer.update()
    before = set(bpy.data.objects)

    with pytest.raises(RuntimeError):
        bpy.ops.silicone_casting.preview_registration_key()

    assert set(bpy.data.objects) == before


@pytest.mark.parametrize("moving_half", [0, 1])
def test_confirmed_key_follows_its_half_when_moved_and_rotated(
    halves, moving_half: int
) -> None:
    bpy.ops.silicone_casting.preview_registration_key()
    bpy.ops.silicone_casting.commit_registration_key()
    moving = halves[moving_half]
    stationary = halves[1 - moving_half]
    before = mesh_invariants(_evaluated_mesh(moving))
    stationary_before = mesh_data(_evaluated_mesh(stationary))
    stationary_matrix = stationary.matrix_world.copy()

    moving.location += Vector((35, -12, 7))
    moving.rotation_euler = (0.3, -0.4, 0.6)
    bpy.context.view_layer.update()

    after = mesh_invariants(_evaluated_mesh(moving))
    assert after.is_watertight
    assert after.loose_part_count == 1
    assert after.volume == pytest.approx(before.volume, abs=0.002)
    assert after.bbox_min == pytest.approx(before.bbox_min, abs=1e-5)
    assert after.bbox_max == pytest.approx(before.bbox_max, abs=1e-5)
    assert mesh_data(_evaluated_mesh(stationary)) == stationary_before
    assert stationary.matrix_world == stationary_matrix


def test_rectangle_keeps_cursor_xy_orientation_and_adds_local_angle(halves) -> None:
    p = bpy.context.scene.silicone_casting
    p.key_shape = "RECTANGLE"
    p.key_align_normal = False
    p.key_angle = pi / 6
    cursor = Matrix.Rotation(pi / 3, 4, "Y") @ Matrix.Rotation(pi / 4, 4, "Z")
    bpy.context.scene.cursor.matrix = cursor

    bpy.ops.silicone_casting.preview_registration_key()

    pin = p.key_preview_pin
    expected = (cursor @ Matrix.Rotation(pi / 6, 4, "Z")).to_3x3()
    for axis in (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))):
        assert tuple(pin.matrix_world.to_3x3() @ axis) == pytest.approx(
            tuple(expected @ axis), abs=1e-6
        )
    assert mesh_invariants(pin.data).bbox_max == pytest.approx((2, 3, 3))
