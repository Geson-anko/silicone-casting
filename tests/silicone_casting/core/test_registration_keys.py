"""Registration keys provide printable solids and explicit mating clearance."""

from dataclasses import replace
from math import pi, sin

import bpy
import pytest
from _helpers import MeshInvariants
from conftest import MakeObject
from mathutils import Vector

from silicone_casting.core.registration_keys import (
    KeyDimensions,
    placement_matrix,
)


@pytest.fixture
def dimensions() -> KeyDimensions:
    return KeyDimensions.from_mm(
        shape="CYLINDER",
        width=4.0,
        length=6.0,
        height=3.0,
        embed=1.0,
        clearance=0.2,
        depth_clearance=0.4,
        scale_length=0.001,
        taper=0.2,
    )


@pytest.mark.parametrize("shape", ["CYLINDER", "TAPERED", "RECTANGLE"])
@pytest.mark.parametrize("socket", [False, True])
def test_each_key_and_socket_is_one_watertight_outward_solid(
    dimensions: KeyDimensions, make_object: MakeObject, shape: str, socket: bool
) -> None:
    mesh = replace(dimensions, shape=shape).create_mesh("Key", socket=socket)
    make_object(mesh)

    invariants = MeshInvariants.from_mesh(mesh)
    assert invariants.is_watertight
    assert invariants.loose_part_count == 1
    # Every face of these convex solids must point away from their interior.
    center = Vector((0.0, 0.0, 1.0))
    assert all(face.normal.dot(face.center - center) > 0 for face in mesh.polygons)


@pytest.mark.parametrize(
    ("shape", "socket", "lower", "upper", "volume"),
    [
        ("CYLINDER", False, (-2, -2, -1), (2, 2, 3), 32 * sin(pi / 32) * 4 * 4),
        (
            "CYLINDER",
            True,
            (-2.2, -2.2, -1),
            (2.2, 2.2, 3.4),
            32 * sin(pi / 32) * 2.2**2 * 4.4,
        ),
        ("RECTANGLE", False, (-2, -3, -1), (2, 3, 3), 4 * 6 * 4),
        ("RECTANGLE", True, (-2.2, -3.2, -1), (2.2, 3.2, 3.4), 4.4 * 6.4 * 4.4),
    ],
)
def test_socket_adds_clearance_per_side_and_only_extends_the_tip(
    dimensions: KeyDimensions,
    make_object: MakeObject,
    shape: str,
    socket: bool,
    lower: tuple[float, float, float],
    upper: tuple[float, float, float],
    volume: float,
) -> None:
    mesh = replace(dimensions, shape=shape).create_mesh("Key", socket=socket)
    make_object(mesh)

    invariants = MeshInvariants.from_mesh(mesh)
    assert invariants.bbox_min == pytest.approx(lower)
    assert invariants.bbox_max == pytest.approx(upper)
    assert invariants.volume == pytest.approx(volume)


def test_tapered_key_narrows_toward_the_tip(
    dimensions: KeyDimensions, make_object: MakeObject
) -> None:
    mesh = replace(dimensions, shape="TAPERED").create_mesh("Key")
    make_object(mesh)

    top = [vertex.co.xy.length for vertex in mesh.vertices if vertex.co.z == 3.0]
    assert top
    assert top == pytest.approx([1.6] * len(top))
    # One unit of straight root plus three units of polygonal frustum.
    assert MeshInvariants.from_mesh(mesh).volume == pytest.approx(
        32 * sin(pi / 32) * (2**2 + (2**2 + 2 * 1.6 + 1.6**2))
    )


def test_tapered_socket_continues_the_slope_at_the_extended_tip(
    dimensions: KeyDimensions, make_object: MakeObject
) -> None:
    mesh = replace(dimensions, shape="TAPERED").create_mesh("Socket", socket=True)
    make_object(mesh)

    top = [vertex.co.xy.length for vertex in mesh.vertices if vertex.co.z > 3]
    # The male loses 0.4 radius over 3 height. Continuing that slope over
    # the extra 0.4 socket depth retains 0.2 radial clearance.
    assert top
    assert top == pytest.approx([1.6 - 0.4 * 0.4 / 3 + 0.2] * len(top))


@pytest.mark.parametrize("shape", ["CYLINDER", "TAPERED", "RECTANGLE"])
def test_zero_clearance_socket_has_the_same_dimensions_as_the_key(
    dimensions: KeyDimensions, make_object: MakeObject, shape: str
) -> None:
    dimensions = replace(dimensions, shape=shape, clearance=0, depth_clearance=0)
    male = dimensions.create_mesh("Key")
    female = dimensions.create_mesh("Socket", socket=True)
    make_object(male)
    make_object(female)

    assert MeshInvariants.from_mesh(male) == MeshInvariants.from_mesh(female)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("width", 0),
        ("length", -1),
        ("height", 0),
        ("embed", -1),
        ("clearance", -0.1),
        ("depth_clearance", -0.1),
        ("taper", -0.1),
        ("taper", 0.91),
        ("width", float("nan")),
        ("length", float("inf")),
        ("height", float("nan")),
        ("embed", float("inf")),
        ("clearance", float("nan")),
        ("depth_clearance", float("inf")),
        ("taper", float("nan")),
    ],
)
def test_invalid_dimensions_are_rejected_without_creating_meshes(
    dimensions: KeyDimensions, field: str, value: float
) -> None:
    before = set(bpy.data.meshes)

    with pytest.raises(ValueError):
        replace(dimensions, **{field: value}).create_mesh("Invalid")

    assert set(bpy.data.meshes) == before


def test_socket_depth_cannot_extend_a_taper_past_its_apex(
    dimensions: KeyDimensions,
) -> None:
    with pytest.raises(ValueError):
        replace(dimensions, shape="TAPERED", depth_clearance=30).create_mesh(
            "Invalid", socket=True
        )


@pytest.mark.parametrize("normal", [(0, 0, 1), (0, 0, -1), (2, -3, 4)])
def test_placement_preserves_size_and_points_the_key_out_of_the_face(
    normal: tuple[float, float, float],
) -> None:
    matrix = placement_matrix(Vector((2, 3, -4)), Vector(normal))

    assert tuple(matrix.translation) == pytest.approx((2, 3, -4))
    assert tuple(matrix.to_3x3() @ Vector((0, 0, 1))) == pytest.approx(
        tuple(Vector(normal).normalized()), abs=1e-6
    )
    assert matrix.to_3x3().determinant() == pytest.approx(1.0)
    for column in matrix.to_3x3().col:
        assert column.length == pytest.approx(1.0)


def test_in_plane_rotation_turns_a_rectangular_key_around_the_same_normal() -> None:
    position = Vector((2, 3, -4))
    normal = Vector((2, -3, 4))
    original = placement_matrix(position, normal).to_3x3()
    rotated = placement_matrix(position, normal, pi / 2).to_3x3()

    assert tuple(rotated @ Vector((1, 0, 0))) == pytest.approx(
        tuple(original @ Vector((0, 1, 0))), abs=1e-6
    )
    assert tuple(rotated @ Vector((0, 0, 1))) == pytest.approx(
        tuple(original @ Vector((0, 0, 1))), abs=1e-6
    )


def test_a_zero_normal_cannot_define_a_perpendicular_placement() -> None:
    with pytest.raises(ValueError):
        placement_matrix(Vector((0, 0, 0)), Vector((0, 0, 0)))
