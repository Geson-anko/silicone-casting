"""Mesh topology determines loop and shortest-path input."""

import pytest
from mathutils import Vector

from silicone_casting.core.edge_paths import edge_loop, extend_edge_path


def _grid():
    vertices = [Vector((x, y, 0)) for y in range(5) for x in range(5)]
    faces = [
        (y * 5 + x, y * 5 + x + 1, (y + 1) * 5 + x + 1, (y + 1) * 5 + x)
        for y in range(4)
        for x in range(4)
    ]
    edges = sorted(
        {
            tuple(sorted((a, b)))
            for face in faces
            for a, b in zip(face, (*face[1:], face[0]))
        }
    )
    return vertices, edges, faces


def test_quad_loop_crosses_the_grid_and_stops_at_the_boundary():
    _, _, faces = _grid()
    path = edge_loop((11, 12), faces)
    assert path in [list(range(10, 15)), list(range(14, 9, -1))]


def test_boundary_loop_closes_without_entering_the_grid():
    _, _, faces = _grid()
    path = edge_loop((0, 1), faces)
    assert path[0] == path[-1]
    assert len(path) == 17
    assert set(path) == {0, 1, 2, 3, 4, 5, 9, 10, 14, 15, 19, 20, 21, 22, 23, 24}


def test_loop_can_extend_an_already_selected_edge_in_one_operation():
    vertices, edges, faces = _grid()
    stroke = [vertices[11], vertices[12]]
    result = extend_edge_path(
        stroke, vertices, edges, faces, (11, 12), loop=True, tolerance=1e-6
    )
    assert result == vertices[10:15]
    assert stroke == vertices[11:13]


def test_shortest_path_uses_edge_lengths_instead_of_number_of_edges():
    vertices = [
        Vector(p)
        for p in [(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0), (4, 0, 0), (1, 10, 0)]
    ]
    edges = [(0, 1), (1, 2), (2, 3), (3, 4), (1, 5), (5, 3)]
    result = extend_edge_path(
        vertices[:2], vertices, edges, [], (3, 4), loop=False, tolerance=1e-6
    )
    assert result == vertices[:5]


def test_shortest_path_can_complete_a_closed_loop():
    vertices = [
        Vector((0, 0, 0)),
        Vector((1, 0, 0)),
        Vector((1, 1, 0)),
        Vector((0, 1, 0)),
    ]
    result = extend_edge_path(
        vertices[:2],
        vertices,
        [(0, 1), (1, 2), (2, 3), (3, 0)],
        [],
        (3, 0),
        loop=False,
        tolerance=1e-6,
    )
    assert result == [*vertices, vertices[0]]


def test_disconnected_path_is_rejected_without_changing_the_stroke():
    vertices, edges, faces = _grid()
    vertices += [Vector((10, 10, 0)), Vector((11, 10, 0))]
    stroke = vertices[:2]
    with pytest.raises(ValueError, match="connected"):
        extend_edge_path(
            stroke,
            vertices,
            [*edges, (25, 26)],
            faces,
            (25, 26),
            loop=False,
            tolerance=1e-6,
        )
    assert stroke == vertices[:2]


def test_nonmanifold_junction_stops_loop_traversal():
    faces = [(0, 1, 2, 3), (1, 0, 4, 5), (0, 1, 6, 7)]
    assert edge_loop((0, 1), faces) == [0, 1]
