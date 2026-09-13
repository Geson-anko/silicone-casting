"""Air vents stay round, capped and subtract from every requested mold half."""

from math import cos, pi, sin

import bpy
import pytest
from _helpers import make_cube_mesh, mesh_invariants
from mathutils import Matrix, Vector

from silicone_casting.core.air_vents import (
    add_air_vent_cutters,
    create_air_vent_mesh,
    simplify_vent_path,
    smooth_vent_path,
)


def test_straight_vent_has_requested_diameter_length_and_outward_caps():
    mesh = create_air_vent_mesh(
        "Vent", [[Vector((0, 0, -2)), Vector((0, 0, 2))]], Vector((1, 0, 0)), 0.4
    )
    try:
        shape = mesh_invariants(mesh)
        assert shape.is_watertight
        assert shape.loose_part_count == 1
        assert shape.volume == pytest.approx(pi * 0.2**2 * 4, rel=0.002)
        assert shape.bbox_min == pytest.approx((-0.2, -0.2, -2))
        assert shape.bbox_max == pytest.approx((0.2, 0.2, 2))
    finally:
        bpy.data.meshes.remove(mesh)


@pytest.mark.parametrize("reverse", [False, True])
def test_curved_vent_is_one_closed_pipe_on_a_rotated_plane(reverse):
    rotation = Matrix.Rotation(0.73, 4, Vector((1, 2, -1)))
    path = [Vector((2 * cos(i * pi / 32), 2 * sin(i * pi / 32), 0)) for i in range(17)]
    if reverse:
        path.reverse()
    mesh = create_air_vent_mesh(
        "Arc",
        [[rotation @ p for p in path]],
        rotation.to_3x3() @ Vector((0, 0, 1)),
        0.2,
    )
    try:
        shape = mesh_invariants(mesh)
        assert shape.is_watertight
        assert shape.loose_part_count == 1
        # Quarter circle of radius 2 has length pi, swept by a radius 0.1 disc.
        assert shape.volume == pytest.approx(pi * 0.1**2 * pi, rel=0.004)
    finally:
        bpy.data.meshes.remove(mesh)


def test_duplicate_mouse_samples_do_not_create_degenerate_faces():
    mesh = create_air_vent_mesh(
        "Vent",
        [[Vector((0, 0, 0)), Vector((0, 0, 0)), Vector((2, 0, 0))]],
        Vector((0, 0, 1)),
        0.2,
    )
    try:
        assert mesh_invariants(mesh).is_watertight
        assert all(face.area > 0 for face in mesh.polygons)
    finally:
        bpy.data.meshes.remove(mesh)


@pytest.mark.parametrize(
    "points,normal,diameter",
    [
        ([(0, 0, 0)], (0, 0, 1), 1),
        ([(0, 0, 0), (0, 0, 0)], (0, 0, 1), 1),
        ([(0, 0, 0), (1, 0, 0)], (0, 0, 0), 1),
        ([(0, 0, 0), (1, 0, 0)], (0, 0, 1), 0),
        ([(0, 0, 0), (1, 0, 0)], (0, 0, 1), float("nan")),
        ([(0, 0, 0), (float("inf"), 0, 0)], (0, 0, 1), 1),
        ([(0, 0, 0), (1, 0, 1)], (0, 0, 1), 1),
        ([(0, 0, 0), (1, 0, 0), (0, 0, 0)], (0, 0, 1), 1),
        ([(0, 0, 0), (0.1, 0, 0), (0.1, 0.1, 0)], (0, 0, 1), 1),
    ],
)
def test_invalid_or_folded_tubes_are_rejected_without_leaking_meshes(
    points, normal, diameter
):
    before = set(bpy.data.meshes)
    with pytest.raises(ValueError):
        create_air_vent_mesh(
            "Invalid", [[Vector(p) for p in points]], Vector(normal), diameter
        )
    assert set(bpy.data.meshes) == before


def test_drawing_noise_is_removed_without_moving_endpoints_or_real_corners():
    points = [Vector(p) for p in [(0, 0, 0), (1, 0.001, 0), (2, 0, 0), (2, 1, 0)]]
    assert simplify_vent_path(points, 0.01) == [points[0], points[2], points[3]]


def test_smoothing_rounds_a_corner_in_the_plane_without_shortening_the_ends():
    points = [Vector(p) for p in [(0, 0, 2), (2, 0, 2), (2, 2, 2)]]
    smoothed = smooth_vent_path(points)
    assert smoothed[0] == points[0]
    assert smoothed[-1] == points[-1]
    assert points[1] not in smoothed
    assert all(p.z == 2 for p in smoothed)
    assert any(0 < p.x < 2 and 0 < p.y < 2 for p in smoothed)


def test_shared_vent_cuts_all_targets_with_world_space_diameter(make_object):
    first = make_object(make_cube_mesh(2, "First"))
    second = make_object(make_cube_mesh(2, "Second"))
    second.location.z = 3
    second.scale = (2, 0.5, 1)
    untouched = make_object(make_cube_mesh(2, "Untouched"))
    cutter = make_object(
        create_air_vent_mesh(
            "Vent", [[Vector((0, 0, -2)), Vector((0, 0, 5))]], Vector((1, 0, 0)), 0.4
        )
    )
    original = (first.data, second.data)
    add_air_vent_cutters([first, second], cutter)
    bpy.context.view_layer.update()
    for obj in (first, second):
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        try:
            shape = mesh_invariants(mesh)
            assert shape.is_watertight
            assert shape.loose_part_count == 1
            assert shape.volume == pytest.approx(8 - pi * 0.2**2 * 2, rel=0.001)
        finally:
            evaluated.to_mesh_clear()
    assert (first.data, second.data) == original
    assert not untouched.modifiers


def test_crossing_vents_subtract_the_union_without_internal_walls(make_object):
    target = make_object(make_cube_mesh(2, "Target"))
    cutter = make_object(
        create_air_vent_mesh(
            "Cross",
            [
                [Vector((-2, 0, 0)), Vector((2, 0, 0))],
                [Vector((0, -2, 0)), Vector((0, 2, 0))],
            ],
            Vector((0, 0, 1)),
            0.4,
        )
    )
    add_air_vent_cutters([target], cutter)
    bpy.context.view_layer.update()
    evaluated = target.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        shape = mesh_invariants(mesh)
        assert shape.is_watertight
        assert shape.loose_part_count == 1
        # Two perpendicular cylinders overlap in a Steinmetz solid, 16 r^3 / 3.
        assert shape.volume == pytest.approx(
            8 - 4 * pi * 0.2**2 + 16 * 0.2**3 / 3, rel=0.001
        )
    finally:
        evaluated.to_mesh_clear()


def test_invalid_later_target_does_not_leave_an_earlier_target_cut(make_object):
    target = make_object(make_cube_mesh(2, "Target"))
    cutter = make_object(make_cube_mesh(1, "Cutter"))
    with pytest.raises(ValueError):
        add_air_vent_cutters([target, cutter], cutter)
    assert not target.modifiers
