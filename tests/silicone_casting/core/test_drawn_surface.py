"""Drawn boundaries produce editable disks or perforated curved patches."""

from math import cos, pi, sin, sqrt

import bpy
import pytest
from _helpers import MeshInvariants, make_cube_mesh
from mathutils import Matrix, Vector

from silicone_casting.core.drawn_surface import (
    interpolate_cutting_surface,
    simplify_closed_loop,
)
from silicone_casting.core.surface_cut import create_surface_cut


def _ring(radius=1.0, height=0.0, count=48, wave=0.0):
    return [
        Vector(
            (
                radius * cos(2 * pi * i / count),
                radius * sin(2 * pi * i / count),
                height + wave * cos(4 * pi * i / count),
            )
        )
        for i in range(count)
    ]


def test_one_loop_retains_its_boundary_and_fills_an_editable_disk():
    loop = _ring()
    mesh, boundary, interior = interpolate_cutting_surface([loop])
    try:
        assert [mesh.vertices[i].co for i in boundary] == loop
        assert interior
        assert all(abs(vertex.co.z) < 1e-6 for vertex in mesh.vertices)
        result = MeshInvariants.from_mesh(mesh)
        assert result.vertex_count - result.edge_count + result.face_count == 1
        assert result.boundary_edge_count == 48
        assert result.loose_part_count == 1
    finally:
        bpy.data.meshes.remove(mesh)


@pytest.mark.parametrize("reverse", [False, True])
def test_nested_loops_make_one_annulus_without_a_mode_or_winding_requirement(reverse):
    outer = _ring(2.0, wave=0.3)
    inner = _ring(1.0, height=0.4, count=23, wave=0.2)
    loops = [inner[::-1], outer] if reverse else [outer, inner]
    mesh, boundary, interior = interpolate_cutting_surface(loops)
    try:
        assert [mesh.vertices[i].co for i in boundary] == [
            point for loop in loops for point in loop
        ]
        assert interior
        mesh.calc_loop_triangles()
        result = MeshInvariants.from_mesh(mesh)
        assert result.vertex_count - result.edge_count + result.face_count == 0
        assert result.boundary_edge_count == 71
        assert result.loose_part_count == 1
        assert all(poly.center.xy.length > 0.98 for poly in mesh.polygons)
    finally:
        bpy.data.meshes.remove(mesh)


def test_nonplanar_boundary_is_preserved_and_the_interior_is_curved():
    loop = _ring(wave=0.4)
    mesh, boundary, interior = interpolate_cutting_surface([loop])
    try:
        assert [mesh.vertices[i].co for i in boundary] == loop
        heights = [mesh.vertices[i].co.z for i in interior]
        assert min(heights) < -0.1
        assert max(heights) > 0.1
        assert min(heights) >= -0.4
        assert max(heights) <= 0.4
    finally:
        bpy.data.meshes.remove(mesh)


@pytest.mark.parametrize("radii", [(1.0,), (1.0, 0.85)])
@pytest.mark.parametrize("scale", [0.01, 1.0])
def test_smooth_saddle_is_interpolated_without_triangle_spacing_artifacts(radii, scale):
    # z = 0.2 * (x*x - y*y) has zero Laplacian, so its boundary values
    # determine the same smooth saddle on both a disk and a narrow annulus.
    loops = [
        [point * scale for point in _ring(radius, count=64, wave=0.2 * radius**2)]
        for radius in radii
    ]
    mesh, boundary, interior = interpolate_cutting_surface(loops)
    try:
        assert [mesh.vertices[i].co for i in boundary] == [
            point for loop in loops for point in loop
        ]
        assert interior
        for index in interior:
            point = mesh.vertices[index].co / scale
            assert point.z == pytest.approx(0.2 * (point.x**2 - point.y**2), abs=0.001)
        result = MeshInvariants.from_mesh(mesh)
        assert result.loose_part_count == 1
        assert result.boundary_edge_count == 64 * len(radii)
        assert result.vertex_count - result.edge_count + result.face_count == (
            2 - len(radii)
        )
    finally:
        bpy.data.meshes.remove(mesh)


def test_matching_rims_are_bridged_by_regular_editable_quad_rows():
    loops = [_ring(1, count=64, wave=0.2), _ring(0.85, count=64, wave=0.15)]
    mesh, boundary, interior = interpolate_cutting_surface(loops)
    try:
        assert all(len(face.vertices) == 4 for face in mesh.polygons)
        assert len(mesh.polygons) <= 4 * len(loops[0])
        degree = [0] * len(mesh.vertices)
        for edge in mesh.edges:
            for index in edge.vertices:
                degree[index] += 1
        assert interior
        assert all(degree[index] == 4 for index in interior)
        assert [mesh.vertices[i].co for i in boundary] == [
            point for loop in loops for point in loop
        ]
    finally:
        bpy.data.meshes.remove(mesh)


@pytest.mark.parametrize("reverse", [False, True])
def test_unequal_shifted_rims_keep_a_quad_dominated_annulus(reverse):
    outer = _ring(1, count=64, wave=0.2)
    inner = _ring(0.85, count=47, wave=0.15)
    inner = inner[13:] + inner[:13]
    loops = [inner[::-1], outer] if reverse else [outer, inner]
    mesh, boundary, interior = interpolate_cutting_surface(loops)
    try:
        assert [mesh.vertices[i].co for i in boundary] == [
            point for loop in loops for point in loop
        ]
        assert interior
        assert sum(len(face.vertices) == 4 for face in mesh.polygons) > (
            0.8 * len(mesh.polygons)
        )
        assert all(face.area > 0 for face in mesh.polygons)
        result = MeshInvariants.from_mesh(mesh)
        assert result.vertex_count - result.edge_count + result.face_count == 0
        assert result.boundary_edge_count == 111
        assert result.loose_part_count == 1
    finally:
        bpy.data.meshes.remove(mesh)


def test_concave_annulus_falls_back_without_bridging_across_the_notch():
    outer = [
        Vector((x, y, 0.1 * x))
        for x, y in [
            (-3, -3),
            (3, -3),
            (3, -1),
            (-1, -1),
            (-1, 1),
            (3, 1),
            (3, 3),
            (-3, 3),
        ]
    ]
    inner = [point + Vector((-2, 0, 0)) for point in _ring(0.4, count=24)]
    mesh, boundary, _ = interpolate_cutting_surface([outer, inner])
    try:
        assert [mesh.vertices[i].co for i in boundary] == outer + inner
        assert all(
            face.center.x < -1 or abs(face.center.y) > 1 for face in mesh.polygons
        )
        result = MeshInvariants.from_mesh(mesh)
        assert result.vertex_count - result.edge_count + result.face_count == 0
        assert result.boundary_edge_count == 32
        assert result.loose_part_count == 1
    finally:
        bpy.data.meshes.remove(mesh)


def test_dense_pixel_sampled_boundary_keeps_a_clean_rim_for_the_cut_margin():
    # Screen-space sampling produces runs of collinear XY points with varying
    # surface heights. These must not add degenerate faces at the patch rim.
    loop = []
    for i in range(396):
        angle = 2 * pi * i / 396
        x = round(0.014 * cos(angle) / 0.00006) * 0.00006
        y = round(0.009 * sin(angle) / 0.00006) * 0.00006
        loop.append(Vector((x, y, sqrt(0.02**2 - x**2 - y**2))))
    simplified = simplify_closed_loop(loop, 0.000035)
    mesh, boundary, _ = interpolate_cutting_surface([simplified], margin=0.00014)
    try:
        assert [mesh.vertices[i].co for i in boundary] == simplified
        result = MeshInvariants.from_mesh(mesh)
        assert result.boundary_edge_count == len(simplified)
        assert result.vertex_count - result.edge_count + result.face_count == 1
        assert all(face.area > 1e-14 for face in mesh.polygons)
    finally:
        bpy.data.meshes.remove(mesh)


@pytest.mark.parametrize("scale", [0.001, 1.0, 1000.0])
def test_rotated_translated_and_scaled_boundaries_keep_their_shape(scale):
    transform = (
        Matrix.Translation((12, -7, 3))
        @ Matrix.Rotation(0.9, 4, "Y")
        @ Matrix.Scale(scale, 4)
    )
    loop = [transform @ p for p in _ring(wave=0.2)]
    mesh, boundary, interior = interpolate_cutting_surface([loop])
    try:
        assert [mesh.vertices[i].co for i in boundary] == loop
        assert interior
        result = MeshInvariants.from_mesh(mesh)
        assert result.vertex_count - result.edge_count + result.face_count == 1
    finally:
        bpy.data.meshes.remove(mesh)


@pytest.mark.parametrize(
    "loops",
    [
        [],
        [[Vector((0, 0, 0)), Vector((1, 0, 0))]],
        [[Vector((0, 0, 0)), Vector((1, 0, 0)), Vector((2, 0, 0))]],
        [
            [
                Vector((-1, -1, 0)),
                Vector((1, 1, 0)),
                Vector((-1, 1, 0)),
                Vector((1, -1, 0)),
            ]
        ],
        [_ring(), [p + Vector((3, 0, 0)) for p in _ring()]],
        [_ring(), _ring()],
        [_ring(3), _ring(2), _ring(1)],
    ],
)
def test_ambiguous_or_invalid_boundaries_fail_without_allocating_a_mesh(loops):
    before = set(bpy.data.meshes)
    with pytest.raises(ValueError):
        interpolate_cutting_surface(loops)
    assert set(bpy.data.meshes) == before


def test_two_holes_are_detected_with_the_same_input_contract():
    loops = [
        _ring(3),
        [p + Vector((-1.2, 0, 0)) for p in _ring(0.6)],
        [p + Vector((1.2, 0, 0)) for p in _ring(0.6)],
    ]
    mesh, _, _ = interpolate_cutting_surface(loops)
    try:
        result = MeshInvariants.from_mesh(mesh)
        assert result.vertex_count - result.edge_count + result.face_count == -1
        assert result.loose_part_count == 1
    finally:
        bpy.data.meshes.remove(mesh)


def test_curved_generated_surface_splits_a_solid_and_manual_interior_edits_stay_live(
    make_object,
):
    target = make_object(make_cube_mesh(2.0, "DrawTarget"))
    loop = [
        Vector((-1, -1, 0.2)),
        Vector((1, -1, -0.2)),
        Vector((1, 1, 0.2)),
        Vector((-1, 1, -0.2)),
    ]
    mesh, _, interior = interpolate_cutting_surface([loop], margin=0.05)
    surface = make_object(mesh)
    modifier = create_surface_cut(target, surface, 0.01, minimum_thickness=0.001)
    group = modifier.node_group
    try:
        bpy.context.view_layer.update()
        evaluated = target.evaluated_get(bpy.context.evaluated_depsgraph_get())
        before_mesh = bpy.data.meshes.new_from_object(evaluated)
        before = MeshInvariants.from_mesh(before_mesh)
        bpy.data.meshes.remove(before_mesh)
        assert before.is_watertight
        assert before.loose_part_count == 2
        for index in interior:
            mesh.vertices[index].co.z += 0.3
        mesh.update()
        bpy.context.view_layer.update()
        after_mesh = bpy.data.meshes.new_from_object(
            target.evaluated_get(bpy.context.evaluated_depsgraph_get())
        )
        after = MeshInvariants.from_mesh(after_mesh)
        bpy.data.meshes.remove(after_mesh)
        assert after.is_watertight
        assert after.loose_part_count == 2
        assert after.volume != pytest.approx(before.volume, abs=1e-5)
        assert len(target.modifiers) == 1
    finally:
        target.modifiers.remove(modifier)
        bpy.data.node_groups.remove(group)


@pytest.mark.parametrize("scale", [0.01, 1.0])
def test_two_drawn_loops_split_a_hollow_mold_into_two_watertight_parts(
    make_object, scale
):
    count = 48
    rings = [_ring(2, -1), _ring(2, 1), _ring(1, -1), _ring(1, 1)]
    points = [p * scale for ring in rings for p in ring]
    faces = []
    for i in range(count):
        j = (i + 1) % count
        faces.extend(
            (
                (i, j, j + count, i + count),
                (i + 2 * count, i + 3 * count, j + 3 * count, j + 2 * count),
                (i, i + 2 * count, j + 2 * count, j),
                (i + count, j + count, j + 3 * count, i + 3 * count),
            )
        )
    target_mesh = bpy.data.meshes.new("HollowMold")
    target_mesh.from_pydata(points, [], faces)
    target_mesh.update()
    target = make_object(target_mesh)
    loops = [
        [p * scale for p in _ring(2, wave=0.2)],
        [p * scale for p in _ring(1, wave=0.1)],
    ]
    mesh, _, _ = interpolate_cutting_surface(loops, margin=0.02 * scale)
    surface = make_object(mesh)
    modifier = create_surface_cut(
        target, surface, 0.0001 * scale, minimum_thickness=0.0001 * scale
    )
    group = modifier.node_group
    try:
        bpy.context.view_layer.update()
        evaluated = target.evaluated_get(bpy.context.evaluated_depsgraph_get())
        result_mesh = bpy.data.meshes.new_from_object(evaluated)
        try:
            result = MeshInvariants.from_mesh(result_mesh)
            assert result.is_watertight
            assert result.loose_part_count == 2
            assert 0 < result.volume < MeshInvariants.from_mesh(target_mesh).volume
        finally:
            bpy.data.meshes.remove(result_mesh)
    finally:
        target.modifiers.remove(modifier)
        bpy.data.node_groups.remove(group)


@pytest.mark.parametrize("holes", [False, True])
def test_editable_patch_prefers_quads_and_keeps_boundary_and_hole_topology(holes):
    loops = [_ring(2, wave=0.2)]
    if holes:
        loops.append(_ring(0.7, count=23, wave=0.1))
    mesh, boundary, interior = interpolate_cutting_surface(loops, margin=0.02)
    try:
        assert [mesh.vertices[i].co for i in boundary] == [
            p for loop in loops for p in loop
        ]
        assert interior
        assert all(len(face.vertices) in {3, 4} for face in mesh.polygons)
        assert sum(len(face.vertices) == 4 for face in mesh.polygons) > 0.6 * len(
            mesh.polygons
        )
        result = MeshInvariants.from_mesh(mesh)
        assert result.vertex_count - result.edge_count + result.face_count == (
            0 if holes else 1
        )
        assert result.boundary_edge_count == sum(len(loop) for loop in loops)
        assert result.loose_part_count == 1
        collar = [
            face
            for face in mesh.polygons
            if any(i not in set(boundary) | set(interior) for i in face.vertices)
        ]
        assert len(collar) == sum(len(loop) for loop in loops)
        assert all(len(face.vertices) == 4 for face in collar)
        assert all(face.area > 0 for face in mesh.polygons)
    finally:
        bpy.data.meshes.remove(mesh)
