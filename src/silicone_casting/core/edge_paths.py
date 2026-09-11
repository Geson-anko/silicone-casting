"""Connected mesh paths for surface-cut edge input."""

from collections.abc import Sequence
from heapq import heappop, heappush

from mathutils import Vector

from .surface_picking import extend_stroke_along_edge


def edge_loop(edge: tuple[int, int], faces: Sequence[Sequence[int]]) -> list[int]:
    """Follow opposite edges at regular quad vertices, stopping at poles.

    Boundary edges follow their boundary. Ambiguous or non-manifold
    junctions terminate the path instead of choosing an arbitrary
    branch.
    """
    adjacent: dict[int, set[int]] = {}
    linked: dict[frozenset[int], set[int]] = {}
    for index, face in enumerate(faces):
        for a, b in zip(face, (*face[1:], face[0]), strict=True):
            adjacent.setdefault(a, set()).add(b)
            adjacent.setdefault(b, set()).add(a)
            linked.setdefault(frozenset((a, b)), set()).add(index)

    def following(previous: int, current: int) -> int | None:
        incident = linked.get(frozenset((previous, current)), set())
        if len(incident) == 1:
            candidates = [
                other
                for other in adjacent[current]
                if other != previous and len(linked[frozenset((current, other))]) == 1
            ]
        elif len(incident) == 2 and len(adjacent[current]) == 4:
            vertex_faces = {
                i
                for other in adjacent[current]
                for i in linked[frozenset((current, other))]
            }
            if len(vertex_faces) != 4 or any(len(faces[i]) != 4 for i in vertex_faces):
                return None
            candidates = [
                other
                for other in adjacent[current]
                if not incident & linked[frozenset((current, other))]
                and len(linked[frozenset((current, other))]) == 2
            ]
        else:
            return None
        return candidates[0] if len(candidates) == 1 else None

    path = list(edge)
    for _ in range(2):
        while True:
            other = following(path[-2], path[-1])
            if other is None:
                break
            if other == path[0]:
                return [*path, other]
            if other in path:
                break
            path.append(other)
        path.reverse()
    return path


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
    """Extend a stroke by one whole loop or a shortest edge-length path."""
    if loop:
        path = edge_loop(edge, faces)
        if not stroke:
            return [vertices[i].copy() for i in path]
        # Reuse selected edges and grow both ends as for manual input.
        remaining = [
            (a, b)
            for a, b in zip(path, path[1:])
            if not any(
                (
                    (vertices[a] - p).length <= tolerance
                    and (vertices[b] - q).length <= tolerance
                )
                or (
                    (vertices[b] - p).length <= tolerance
                    and (vertices[a] - q).length <= tolerance
                )
                for p, q in zip(stroke, stroke[1:])
            )
        ]
        result = list(stroke)
        while remaining:
            for pair in remaining:
                a, b = pair
                if any(
                    (vertices[i] - endpoint).length <= tolerance
                    for i in pair
                    for endpoint in (result[0], result[-1])
                ):
                    result = extend_stroke_along_edge(
                        result, vertices[a], vertices[b], tolerance
                    )
                    remaining.remove(pair)
                    break
            else:
                raise ValueError(
                    "Select a loop connected to an end of the current stroke"
                )
        return result
    if not stroke:
        return [vertices[i].copy() for i in edge]
    if len(stroke) > 2 and (stroke[0] - stroke[-1]).length <= tolerance:
        raise ValueError("Close the current loop with C before selecting another edge")
    start = min(range(len(vertices)), key=lambda i: (vertices[i] - stroke[-1]).length)
    if (vertices[start] - stroke[-1]).length > tolerance:
        raise ValueError("Start the path from a mesh vertex or edge")
    blocked = {
        i
        for i, p in enumerate(vertices)
        if any((p - q).length <= tolerance for q in stroke[:-1])
    }
    adjacency: dict[int, list[tuple[int, float]]] = {}
    for a, b in edges:
        if {a, b} == set(edge) or a in blocked or b in blocked:
            continue
        length = (vertices[a] - vertices[b]).length
        adjacency.setdefault(a, []).append((b, length))
        adjacency.setdefault(b, []).append((a, length))
    distances = {start: 0.0}
    parents: dict[int, int] = {}
    queue = [(0.0, start)]
    while queue:
        distance, current = heappop(queue)
        if distance != distances[current]:
            continue
        if current in edge:
            path = [current]
            while path[-1] != start:
                path.append(parents[path[-1]])
            path.reverse()
            path.append(edge[1] if current == edge[0] else edge[0])
            result = list(stroke)
            for a, b in zip(path, path[1:]):
                result = extend_stroke_along_edge(
                    result, vertices[a], vertices[b], tolerance
                )
            return result
        for other, length in adjacency.get(current, []):
            candidate = distance + length
            if candidate < distances.get(other, float("inf")):
                distances[other] = candidate
                parents[other] = current
                heappush(queue, (candidate, other))
    raise ValueError("No connected path to that edge")
