"""Connected mesh paths for surface-cut edge input."""

from collections.abc import Sequence
from heapq import heappop, heappush
from math import inf
from typing import Self

from mathutils import Vector

from .surface_picking import extend_stroke_along_edge

type _Adjacency = dict[int, list[tuple[int, float]]]


class _FaceTopology:
    """Vertex adjacency and edge-to-face incidence of a polygon list."""

    def __init__(
        self,
        faces: Sequence[Sequence[int]],
        adjacent: dict[int, set[int]],
        linked: dict[frozenset[int], set[int]],
    ) -> None:
        self._faces = faces
        self._adjacent = adjacent
        self._linked = linked

    @classmethod
    def from_faces(cls, faces: Sequence[Sequence[int]]) -> Self:
        """Index which vertices and faces meet at each vertex and edge."""
        adjacent: dict[int, set[int]] = {}
        linked: dict[frozenset[int], set[int]] = {}
        for index, face in enumerate(faces):
            for a, b in zip(face, (*face[1:], face[0]), strict=True):
                adjacent.setdefault(a, set()).add(b)
                adjacent.setdefault(b, set()).add(a)
                linked.setdefault(frozenset((a, b)), set()).add(index)
        return cls(faces, adjacent, linked)

    def _faces_at(self, a: int, b: int) -> set[int]:
        return self._linked[frozenset((a, b))]

    def following(self, previous: int, current: int) -> int | None:
        """Return the unique vertex continuing the loop, or None at a stop."""
        incident = self._linked.get(frozenset((previous, current)), set())
        neighbors = self._adjacent[current]
        if len(incident) == 1:
            # A boundary edge continues along the only other boundary edge.
            candidates = [
                other
                for other in neighbors
                if other != previous and len(self._faces_at(current, other)) == 1
            ]
        elif len(incident) == 2 and len(neighbors) == 4:
            vertex_faces = {
                face for other in neighbors for face in self._faces_at(current, other)
            }
            # Only a regular all-quad vertex has a well-defined opposite edge.
            if len(vertex_faces) != 4 or any(
                len(self._faces[face]) != 4 for face in vertex_faces
            ):
                return None
            candidates = [
                other
                for other in neighbors
                if not incident & self._faces_at(current, other)
                and len(self._faces_at(current, other)) == 2
            ]
        else:
            return None
        return candidates[0] if len(candidates) == 1 else None


def edge_loop(edge: tuple[int, int], faces: Sequence[Sequence[int]]) -> list[int]:
    """Follow opposite edges at regular quad vertices, stopping at poles.

    Boundary edges follow their boundary. Ambiguous or non-manifold
    junctions terminate the path instead of choosing an arbitrary
    branch.

    Args:
        edge: Starting edge as a vertex index pair.
        faces: Polygons as vertex index sequences.

    Returns:
        Vertex indices along the loop. A closed loop repeats its first
        vertex at the end.
    """
    topology = _FaceTopology.from_faces(faces)
    path = list(edge)
    # Grow forward, then reverse and grow from the other end.
    for _ in range(2):
        while True:
            other = topology.following(path[-2], path[-1])
            if other is None:
                break
            if other == path[0]:
                return [*path, other]
            if other in path:
                break
            path.append(other)
        path.reverse()
    return path


def _matches_edge(a: Vector, b: Vector, p: Vector, q: Vector, tolerance: float) -> bool:
    """Test whether segment a-b coincides with p-q in either direction."""
    return ((a - p).length <= tolerance and (b - q).length <= tolerance) or (
        (b - p).length <= tolerance and (a - q).length <= tolerance
    )


def _extend_along_loop(
    stroke: Sequence[Vector],
    vertices: Sequence[Vector],
    path: Sequence[int],
    tolerance: float,
) -> list[Vector]:
    """Add a loop's unselected edges to the stroke, growing either end."""
    if not stroke:
        return [vertices[index].copy() for index in path]
    remaining = [
        (a, b)
        for a, b in zip(path, path[1:])
        if not any(
            _matches_edge(vertices[a], vertices[b], p, q, tolerance)
            for p, q in zip(stroke, stroke[1:])
        )
    ]
    result = list(stroke)
    # Edges may connect to either end in any order, so repeatedly take the
    # first one touching an end until none remain.
    while remaining:
        for pair in remaining:
            a, b = pair
            if any(
                (vertices[index] - endpoint).length <= tolerance
                for index in pair
                for endpoint in (result[0], result[-1])
            ):
                result = extend_stroke_along_edge(
                    result, vertices[a], vertices[b], tolerance
                )
                remaining.remove(pair)
                break
        else:
            raise ValueError("Select a loop connected to an end of the current stroke")
    return result


def _shortest_path_to_edge(
    adjacency: _Adjacency, start: int, edge: tuple[int, int]
) -> list[int]:
    """Find the nearest edge endpoint by length, then traverse that edge."""
    distances = {start: 0.0}
    parents: dict[int, int] = {}
    queue = [(0.0, start)]
    while queue:
        distance, current = heappop(queue)
        if distance != distances[current]:
            continue  # A shorter route to this vertex was already expanded.
        if current in edge:
            path = [current]
            while path[-1] != start:
                path.append(parents[path[-1]])
            path.reverse()
            path.append(edge[1] if current == edge[0] else edge[0])
            return path
        for other, length in adjacency.get(current, []):
            candidate = distance + length
            if candidate < distances.get(other, inf):
                distances[other] = candidate
                parents[other] = current
                heappush(queue, (candidate, other))
    raise ValueError("No connected path to that edge")


def _path_graph(
    vertices: Sequence[Vector],
    edges: Sequence[tuple[int, int]],
    target: tuple[int, int],
    blocked: set[int],
) -> _Adjacency:
    """Weight edges by length, leaving out the target and blocked vertices."""
    adjacency: _Adjacency = {}
    for a, b in edges:
        if {a, b} == set(target) or a in blocked or b in blocked:
            continue
        length = (vertices[a] - vertices[b]).length
        adjacency.setdefault(a, []).append((b, length))
        adjacency.setdefault(b, []).append((a, length))
    return adjacency


def extend_edge_path(
    stroke: Sequence[Vector],
    vertices: Sequence[Vector],
    edges: Sequence[tuple[int, int]],
    faces: Sequence[Sequence[int]],
    edge: tuple[int, int],
    *,
    loop: bool,
    tolerance: float,
) -> list[Vector]:
    """Extend a stroke by one whole loop or a shortest edge-length path.

    Args:
        stroke: Current open stroke. Not modified.
        vertices: Mesh vertex positions.
        edges: Mesh edges as vertex index pairs.
        faces: Mesh polygons, used only when *loop* is set.
        edge: Picked edge to reach or to start the loop from.
        loop: Add the edge loop through *edge* instead of a shortest path
            from the stroke's end.
        tolerance: Distance under which points are the same vertex.

    Returns:
        The extended stroke as a new list.

    Raises:
        ValueError: If the stroke is closed, does not end on a mesh vertex,
            or cannot be connected to *edge* without repeating itself.
    """
    if loop:
        return _extend_along_loop(stroke, vertices, edge_loop(edge, faces), tolerance)
    if not stroke:
        return [vertices[index].copy() for index in edge]
    if len(stroke) > 2 and (stroke[0] - stroke[-1]).length <= tolerance:
        raise ValueError("Close the current loop with C before selecting another edge")
    start = min(
        range(len(vertices)), key=lambda index: (vertices[index] - stroke[-1]).length
    )
    if (vertices[start] - stroke[-1]).length > tolerance:
        raise ValueError("Start the path from a mesh vertex or edge")
    # The path must not pass through the stroke, except at its current end.
    blocked = {
        index
        for index, point in enumerate(vertices)
        if any((point - other).length <= tolerance for other in stroke[:-1])
    }
    path = _shortest_path_to_edge(
        _path_graph(vertices, edges, edge, blocked), start, edge
    )
    result = list(stroke)
    for a, b in zip(path, path[1:]):
        result = extend_stroke_along_edge(result, vertices[a], vertices[b], tolerance)
    return result
