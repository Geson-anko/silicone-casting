"""Mesh snapping respects visibility, screen distance, and stroke topology."""

import pytest
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from silicone_casting.core.surface_picking import (
    extend_stroke_along_edge,
    pick_surface_element,
)


def _pick(mouse, *, vertex_mode):
    # Rear elements come first: screen distance alone would pick through the top.
    vertices = [
        Vector((x, y, z))
        for z in (0, 1)
        for x, y in ((-20, -20), (20, -20), (20, 20), (-20, 20))
    ]
    edges = [(i + offset, (i + 1) % 4 + offset) for offset in (0, 4) for i in range(4)]
    surface = BVHTree.FromPolygons(vertices, [(0, 1, 2, 3), (4, 5, 6, 7)], epsilon=1e-6)
    return pick_surface_element(
        Vector(mouse),
        vertices,
        edges,
        lambda point: point.xy,
        lambda pixel: (Vector((pixel.x, pixel.y, 10)), Vector((0, 0, -1))),
        surface,
        vertex_mode=vertex_mode,
        tolerance=1e-5,
    )


def test_vertex_snap_near_silhouette_keeps_the_front_vertex():
    assert _pick((23, 22), vertex_mode=True) == (6,)


def test_edge_pick_uses_the_visible_edge_under_the_cursor():
    assert _pick((0, -18), vertex_mode=False) == (4, 5)


@pytest.mark.parametrize("vertex_mode", [True, False])
def test_distant_cursor_does_not_snap(vertex_mode):
    assert _pick((100, 100), vertex_mode=vertex_mode) is None


@pytest.mark.parametrize("vertex_mode", [True, False])
def test_an_occluded_candidate_is_rejected_even_without_a_nearby_front_candidate(
    vertex_mode,
):
    vertices = [
        Vector(p)
        for p in [
            (-10, 0, 0),
            (10, 0, 0),
            (-40, -40, 1),
            (40, -40, 1),
            (40, 40, 1),
            (-40, 40, 1),
        ]
    ]
    surface = BVHTree.FromPolygons(vertices, [(2, 3, 4, 5)], epsilon=1e-6)
    assert (
        pick_surface_element(
            Vector((0, 0)),
            vertices,
            [(0, 1)],
            lambda point: point.xy,
            lambda pixel: (Vector((pixel.x, pixel.y, 10)), Vector((0, 0, -1))),
            surface,
            vertex_mode=vertex_mode,
            tolerance=1e-5,
        )
        is None
    )


def test_perspective_edge_pick_uses_the_world_point_on_the_projected_edge():
    vertices = [Vector(p) for p in [(-1, 0, 1), (1, 0, -1), (0, 2, 0)]]
    surface = BVHTree.FromPolygons(vertices, [(0, 1, 2)])
    result = pick_surface_element(
        Vector((0, 1)),
        vertices,
        [(0, 1)],
        lambda p: Vector((100 * p.x / (5 - p.z), 100 * p.y / (5 - p.z))),
        lambda p: (Vector((0, 0, 5)), Vector((p.x / 100, p.y / 100, -1)).normalized()),
        surface,
        vertex_mode=False,
        tolerance=1e-5,
    )
    assert result == (0, 1)


@pytest.mark.parametrize("reverse", [False, True])
def test_connected_edges_can_extend_either_end_without_changing_the_input(reverse):
    a, b, c, d = (Vector((i, 0, 0)) for i in range(4))
    stroke = [b, c]
    edge = (d, c) if reverse else (c, d)
    extended = extend_stroke_along_edge(stroke, *edge, 1e-6)
    assert extended == [b, c, d]
    assert extend_stroke_along_edge(extended, a, b, 1e-6) == [a, b, c, d]
    assert stroke == [b, c]


def test_edge_can_close_a_loop_but_cannot_repeat_or_branch_it():
    a, b, c, d = (Vector(p) for p in [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)])
    closed = extend_stroke_along_edge([a, b, c, d], d, a, 1e-6)
    assert closed == [a, b, c, d, a]
    with pytest.raises(ValueError):
        extend_stroke_along_edge(closed, a, b, 1e-6)
    with pytest.raises(ValueError):
        extend_stroke_along_edge([a, b, c], c, b, 1e-6)
    with pytest.raises(ValueError):
        extend_stroke_along_edge([a, b], c, d, 1e-6)
    with pytest.raises(ValueError):
        extend_stroke_along_edge([a, b], a, b, 1e-6)
