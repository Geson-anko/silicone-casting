"""Paired key models preserve physical geometry and transactional ownership."""

from collections.abc import Iterator
from math import pi, sin

import bpy
import pytest
from _helpers import MeshData, MeshInvariants, make_cube_mesh
from mathutils import Matrix, Vector

import silicone_casting
from silicone_casting.operators.key_models import KeyPair, KeySettings
from silicone_casting.operators.key_placement import SILCAST_OT_start_key_placement


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
def test_creation_adds_one_closed_pin_and_socket_with_requested_clearance(
    halves, shape: str, added: float, removed: float
) -> None:
    male, female = halves
    before = (MeshData.from_mesh(male.data), MeshData.from_mesh(female.data))
    bpy.context.scene.silicone_casting.key_shape = shape
    KeyPair.create(
        bpy.context,
        KeySettings.from_context(bpy.context),
        Vector((0, 0, 0)),
        Vector((0, 0, 1)),
    )

    assert (MeshData.from_mesh(male.data), MeshData.from_mesh(female.data)) == before
    assert male.modifiers[0].operation == "UNION"
    assert female.modifiers[0].operation == "DIFFERENCE"
    assert male.modifiers[0].object.hide_get()
    assert female.modifiers[0].object.hide_get()
    male_result = MeshInvariants.from_mesh(_evaluated_mesh(male))
    female_result = MeshInvariants.from_mesh(_evaluated_mesh(female))
    assert male_result.is_watertight and female_result.is_watertight
    assert male_result.loose_part_count == female_result.loose_part_count == 1
    assert male_result.volume == pytest.approx(8000 + added, abs=0.002)
    assert female_result.volume == pytest.approx(8000 - removed, abs=0.002)


def test_repeated_placement_retains_two_independent_pairs(halves) -> None:
    male, female = halves
    settings = KeySettings.from_context(bpy.context)
    first = KeyPair.create(bpy.context, settings, Vector((-4, 0, 0)), Vector((0, 0, 1)))
    first_pin = first.pin
    KeyPair.create(bpy.context, settings, Vector((4, 0, 0)), Vector((0, 0, 1)))

    assert len(male.modifiers) == len(female.modifiers) == 2
    assert male.modifiers[0].object == first_pin
    assert male.modifiers[1].object != first_pin
    result = MeshInvariants.from_mesh(_evaluated_mesh(male))
    assert result.is_watertight and result.loose_part_count == 1
    assert result.volume == pytest.approx(
        8000 + 2 * 32 * sin(pi / 32) * 4 * 3, abs=0.002
    )


def test_scaled_rotated_target_keeps_world_size_and_world_face_normal(halves) -> None:
    male, female = halves
    transform = Matrix.Rotation(0.4, 4, "X") @ Matrix.Diagonal((2, 0.5, 1.5, 1))
    for half in (male, female):
        half.matrix_world = transform @ half.matrix_world
    bpy.context.view_layer.update()
    surface_point = male.matrix_world @ Vector((0, 0, 10))
    normal = (
        male.matrix_world.to_3x3().inverted().transposed() @ Vector((0, 0, 1))
    ).normalized()

    pair = KeyPair.create(
        bpy.context, KeySettings.from_context(bpy.context), surface_point, normal
    )
    pin = pair.pin
    assert tuple(pin.matrix_world.translation) == pytest.approx(
        tuple(surface_point), abs=1e-5
    )
    assert tuple(pin.matrix_world.to_3x3() @ Vector((0, 0, 1))) == pytest.approx(
        tuple(normal), abs=1e-6
    )
    assert tuple(pin.matrix_world.to_scale()) == pytest.approx((1, 1, 1))
    assert MeshInvariants.from_mesh(pin.data).bbox_max == pytest.approx((2, 2, 3))


def test_a_missed_mate_rolls_back_both_modifiers_and_helper_datablocks(halves) -> None:
    male, female = halves
    female.location.x = 100
    bpy.context.view_layer.update()
    before = (set(bpy.data.objects), set(bpy.data.meshes))

    with pytest.raises(ValueError):
        KeyPair.create(
            bpy.context,
            KeySettings.from_context(bpy.context),
            Vector((0, 0, 0)),
            Vector((0, 0, 1)),
        )

    assert not male.modifiers and not female.modifiers
    assert (set(bpy.data.objects), set(bpy.data.meshes)) == before


def test_a_key_entirely_inside_the_male_is_rejected_without_partial_data(
    halves,
) -> None:
    male, female = halves
    before = (set(bpy.data.objects), set(bpy.data.meshes))

    with pytest.raises(ValueError):
        KeyPair.create(
            bpy.context,
            KeySettings.from_context(bpy.context),
            Vector((0, 0, -5)),
            Vector((0, 0, 1)),
        )

    assert not male.modifiers and not female.modifiers
    assert (set(bpy.data.objects), set(bpy.data.meshes)) == before


def test_placement_requires_distinct_mesh_halves_and_object_mode(halves) -> None:
    male, _female = halves
    p = bpy.context.scene.silicone_casting
    p.key_mate = male
    assert not SILCAST_OT_start_key_placement.poll(bpy.context)
    p.key_mate = None
    assert not SILCAST_OT_start_key_placement.poll(bpy.context)
    p.key_mate = halves[1]
    bpy.ops.object.mode_set(mode="EDIT")
    assert not SILCAST_OT_start_key_placement.poll(bpy.context)


@pytest.mark.parametrize("flip", [False, True])
def test_flipping_the_key_reverses_its_face_normal_without_moving_contact(
    halves, flip: bool
) -> None:
    props = bpy.context.scene.silicone_casting
    props.key_flip = flip
    normal = Vector((2, -3, 4)).normalized()

    matrix = KeySettings.from_context(bpy.context).placement(Vector((1, 2, 3)), normal)

    assert tuple(matrix.translation) == pytest.approx((1, 2, 3))
    assert tuple(matrix.to_3x3() @ Vector((0, 0, 1))) == pytest.approx(
        tuple(normal * (-1) ** flip), abs=1e-6
    )


def test_empty_target_is_rejected_without_allocating_helpers(halves) -> None:
    male, _female = halves
    male.data = bpy.data.meshes.new("Empty surface")
    bpy.context.view_layer.update()
    before = set(bpy.data.objects)

    with pytest.raises(ValueError):
        KeyPair.create(
            bpy.context,
            KeySettings.from_context(bpy.context),
            Vector((0, 0, 0)),
            Vector((0, 0, 1)),
        )

    assert set(bpy.data.objects) == before


@pytest.mark.parametrize("moving_half", [0, 1])
def test_confirmed_key_follows_its_half_when_moved_and_rotated(
    halves, moving_half: int
) -> None:
    KeyPair.create(
        bpy.context,
        KeySettings.from_context(bpy.context),
        Vector((0, 0, 0)),
        Vector((0, 0, 1)),
    )
    moving = halves[moving_half]
    stationary = halves[1 - moving_half]
    before = MeshInvariants.from_mesh(_evaluated_mesh(moving))
    stationary_before = MeshData.from_mesh(_evaluated_mesh(stationary))
    stationary_matrix = stationary.matrix_world.copy()

    moving.location += Vector((35, -12, 7))
    moving.rotation_euler = (0.3, -0.4, 0.6)
    bpy.context.view_layer.update()

    after = MeshInvariants.from_mesh(_evaluated_mesh(moving))
    assert after.is_watertight
    assert after.loose_part_count == 1
    assert after.volume == pytest.approx(before.volume, abs=0.002)
    assert after.bbox_min == pytest.approx(before.bbox_min, abs=1e-5)
    assert after.bbox_max == pytest.approx(before.bbox_max, abs=1e-5)
    assert MeshData.from_mesh(_evaluated_mesh(stationary)) == stationary_before
    assert stationary.matrix_world == stationary_matrix


@pytest.mark.parametrize("scale", [1.0, 0.1, 0.001])
def test_native_distance_inputs_set_pair_dimensions_in_scene_units(halves, scale):
    scene = bpy.context.scene
    scene.unit_settings.scale_length = scale
    p = scene.silicone_casting
    p.key_shape = "RECTANGLE"
    p.key_width = 0.004 / scale
    p.key_length = 0.006 / scale
    p.key_height = 0.003 / scale
    p.key_embed = 0.001 / scale
    p.key_clearance = 0.0002 / scale
    p.key_depth_clearance = 0.0004 / scale

    pair = KeyPair.create(
        bpy.context,
        KeySettings.from_context(bpy.context),
        Vector((0, 0, 0)),
        Vector((0, 0, 1)),
    )

    pin = MeshInvariants.from_mesh(pair.pin.data)
    socket = MeshInvariants.from_mesh(pair.socket.data)
    assert pin.bbox_min == pytest.approx(
        (-0.002 / scale, -0.003 / scale, -0.001 / scale)
    )
    assert pin.bbox_max == pytest.approx((0.002 / scale, 0.003 / scale, 0.003 / scale))
    assert socket.bbox_max == pytest.approx(
        (0.0022 / scale, 0.0032 / scale, 0.0034 / scale)
    )
