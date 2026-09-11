"""Pick visible mesh vertices and edges near a screen-space cursor."""

from collections.abc import Callable, Sequence

from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import intersect_line_line


def pick_surface_element(
    mouse: Vector,
    vertices: Sequence[Vector],
    edges: Sequence[tuple[int, int]],
    project: Callable[[Vector], Vector | None],
    ray: Callable[[Vector], tuple[Vector, Vector]],
    surface: BVHTree,
    *,
    vertex_mode: bool,
    tolerance: float,
    radius: float = 12.0,
) -> tuple[int, ...] | None:
    """Return the nearest visible vertex or edge within a pixel radius.

    All geometry and rays use world space. Occlusion is checked at the
    candidate itself, so silhouette vertices remain pickable even when
    the cursor is just outside the mesh. The BVH's epsilon should be
    positive and smaller than tolerance to include hits at polygon rims.
    """
    projected = [project(point) for point in vertices]
    candidates: list[tuple[float, tuple[int, ...], Vector]] = []
    if vertex_mode:
        for i, pixel in enumerate(projected):
            if pixel is not None and (pixel - mouse).length <= radius:
                candidates.append(((pixel - mouse).length, (i,), vertices[i]))
    else:
        for a, b in edges:
            start, end = projected[a], projected[b]
            if start is None or end is None:
                continue
            screen_edge = end - start
            if screen_edge.length_squared == 0:
                continue
            factor = max(
                0.0,
                min(1.0, (mouse - start).dot(screen_edge) / screen_edge.length_squared),
            )
            pixel = start.lerp(end, factor)
            distance = (pixel - mouse).length
            if distance > radius:
                continue
            origin, direction = ray(pixel)
            closest = intersect_line_line(
                vertices[a], vertices[b], origin, origin + direction
            )
            if closest is None:
                continue
            edge = vertices[b] - vertices[a]
            factor = max(
                0.0,
                min(1.0, (closest[0] - vertices[a]).dot(edge) / edge.length_squared),
            )
            candidates.append((distance, (a, b), vertices[a].lerp(vertices[b], factor)))
    for _, indices, point in sorted(candidates, key=lambda candidate: candidate[0]):
        pixel = project(point)
        if pixel is None:
            continue
        origin, direction = ray(pixel)
        distance = (point - origin).dot(direction)
        if distance < 0:
            continue
        hit, _, _, _ = surface.ray_cast(
            origin, direction, max(0.0, distance - tolerance)
        )
        if hit is None:
            return indices
    return None


def extend_stroke_along_edge(
    stroke: Sequence[Vector], a: Vector, b: Vector, tolerance: float
) -> list[Vector]:
    """Append or prepend a connected edge, rejecting branches and repeats."""
    if not stroke:
        return [a.copy(), b.copy()]
    if len(stroke) > 2 and (stroke[0] - stroke[-1]).length <= tolerance:
        raise ValueError("Close the current loop with C before selecting another edge")
    for endpoint, other in ((a, b), (b, a)):
        if (stroke[-1] - endpoint).length <= tolerance:
            if len(stroke) < 3 and (stroke[0] - other).length <= tolerance:
                raise ValueError("This edge is already in the stroke")
            if any((point - other).length <= tolerance for point in stroke[1:]):
                raise ValueError("This edge would repeat or branch the stroke")
            return [*stroke, other.copy()]
        if (stroke[0] - endpoint).length <= tolerance:
            if len(stroke) < 3 and (stroke[-1] - other).length <= tolerance:
                raise ValueError("This edge is already in the stroke")
            if any((point - other).length <= tolerance for point in stroke[:-1]):
                raise ValueError("This edge would repeat or branch the stroke")
            return [other.copy(), *stroke]
    raise ValueError("Select an edge connected to either end of the current stroke")
