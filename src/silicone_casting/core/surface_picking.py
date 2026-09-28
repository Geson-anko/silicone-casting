"""Pick visible mesh vertices and edges near a screen-space cursor."""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Final, NamedTuple, Self, cast

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import intersect_line_line

# Snapping BVH epsilon relative to the surface size. Positive so rays grazing
# a polygon rim still hit it, yet far below any picking tolerance.
_SNAP_EPSILON_FACTOR: Final = 1e-7

type _Project = Callable[[Vector], Vector | None]
type _Ray = Callable[[Vector], tuple[Vector, Vector]]


@dataclass
class SurfaceSnapshot:
    """Evaluated world geometry shared by ray drawing and topology snapping.

    Attributes:
        vertices: World-space vertex positions of all captured objects.
        edges: Edges indexing into ``vertices``.
        faces: Polygons indexing into ``vertices``.
        bvh: Exact surface for drawing rays.
        size: Diagonal of the world bounding box, for relative tolerances.
    """

    vertices: tuple[Vector, ...]
    edges: tuple[tuple[int, int], ...]
    faces: tuple[tuple[int, ...], ...]
    bvh: BVHTree
    size: float
    _snap_bvh: BVHTree | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_objects(
        cls, objects: Sequence[bpy.types.Object], depsgraph: bpy.types.Depsgraph
    ) -> Self:
        """Capture the evaluated meshes of *objects* in world space.

        Each temporary evaluated mesh is released before returning.

        Args:
            objects: Mesh objects to capture.
            depsgraph: Depsgraph used to evaluate modifiers.

        Returns:
            One snapshot combining all objects.

        Raises:
            ValueError: If the objects have no faces.
        """
        vertices: list[Vector] = []
        edges: list[tuple[int, int]] = []
        faces: list[tuple[int, ...]] = []
        for obj in objects:
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            try:
                offset = len(vertices)
                vertices.extend(evaluated.matrix_world @ v.co for v in mesh.vertices)
                for edge in mesh.edges:
                    a, b = cast(Sequence[int], edge.vertices)
                    edges.append((offset + a, offset + b))
                faces.extend(
                    tuple(offset + i for i in cast(Sequence[int], face.vertices))
                    for face in mesh.polygons
                )
            finally:
                evaluated.to_mesh_clear()
        if not faces:
            raise ValueError("Choose meshes with faces to draw on")
        low = Vector(tuple(min(p[axis] for p in vertices) for axis in range(3)))
        high = Vector(tuple(max(p[axis] for p in vertices) for axis in range(3)))
        return cls(
            tuple(vertices),
            tuple(edges),
            tuple(faces),
            BVHTree.FromPolygons([(p.x, p.y, p.z) for p in vertices], faces),
            (high - low).length,
        )

    @property
    def snap_bvh(self) -> BVHTree:
        """Surface for occluding snap candidates, built on first use.

        Its positive epsilon counts silhouette edges as hits, which
        suits visibility tests of vertices and edges but not drawing
        rays.
        """
        if self._snap_bvh is None:
            self._snap_bvh = BVHTree.FromPolygons(
                [(p.x, p.y, p.z) for p in self.vertices],
                self.faces,
                epsilon=self.size * _SNAP_EPSILON_FACTOR,
            )
        return self._snap_bvh


class _Candidate(NamedTuple):
    """A pickable element and the world point used to test its visibility."""

    screen_distance: float
    indices: tuple[int, ...]
    point: Vector


def _vertex_candidates(
    mouse: Vector,
    vertices: Sequence[Vector],
    projected: Sequence[Vector | None],
    radius: float,
) -> Iterator[_Candidate]:
    """Yield vertices projected within *radius* pixels of the cursor."""
    for index, pixel in enumerate(projected):
        if pixel is not None and (pixel - mouse).length <= radius:
            yield _Candidate((pixel - mouse).length, (index,), vertices[index])


def _edge_candidates(
    mouse: Vector,
    vertices: Sequence[Vector],
    edges: Sequence[tuple[int, int]],
    projected: Sequence[Vector | None],
    ray: _Ray,
    radius: float,
) -> Iterator[_Candidate]:
    """Yield edges within *radius* pixels, at the world point under the cursor.

    The closest screen point is cast back to the edge, so perspective
    does not shift the tested point away from what the cursor covers.
    """
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
        yield _Candidate(distance, (a, b), vertices[a].lerp(vertices[b], factor))


def _is_visible(
    point: Vector,
    project: _Project,
    ray: _Ray,
    surface: BVHTree,
    tolerance: float,
) -> bool:
    """Test that nothing on *surface* lies between the view and *point*."""
    pixel = project(point)
    if pixel is None:
        return False
    origin, direction = ray(pixel)
    distance = (point - origin).dot(direction)
    if distance < 0:
        return False
    # Stop short of the point itself so its own faces do not occlude it.
    hit, _, _, _ = surface.ray_cast(origin, direction, max(0.0, distance - tolerance))
    return hit is None


def pick_surface_element(
    mouse: Vector,
    vertices: Sequence[Vector],
    edges: Sequence[tuple[int, int]],
    project: _Project,
    ray: _Ray,
    surface: BVHTree,
    *,
    vertex_mode: bool,
    tolerance: float,
    radius: float = 12.0,
) -> tuple[int, ...] | None:
    """Return the nearest visible vertex or edge within a pixel radius.

    All geometry and rays use world space. Occlusion is checked at the
    candidate itself, so silhouette vertices remain pickable even when
    the cursor is just outside the mesh.

    Args:
        mouse: Cursor position in screen pixels.
        vertices: World-space vertex positions.
        edges: Edges indexing into *vertices*.
        project: Maps a world point to screen pixels, or None if off-view.
        ray: Maps a pixel to a world-space ray origin and unit direction.
        surface: Occluding surface. Its epsilon should be positive and
            smaller than *tolerance* to include hits at polygon rims.
        vertex_mode: Pick vertices instead of edges.
        tolerance: World distance in front of a candidate ignored by the
            occlusion test.
        radius: Largest screen distance to the cursor, in pixels.

    Returns:
        ``(vertex,)`` or ``(a, b)`` of the nearest visible element, or None.
    """
    projected = [project(point) for point in vertices]
    if vertex_mode:
        candidates = _vertex_candidates(mouse, vertices, projected, radius)
    else:
        candidates = _edge_candidates(mouse, vertices, edges, projected, ray, radius)
    for candidate in sorted(candidates, key=lambda c: c.screen_distance):
        if _is_visible(candidate.point, project, ray, surface, tolerance):
            return candidate.indices
    return None


def _reject_repeat(
    new_point: Vector,
    far_end: Vector,
    others: Sequence[Vector],
    stroke_length: int,
    tolerance: float,
) -> None:
    """Raise if joining *new_point* would duplicate or branch the stroke."""
    if stroke_length < 3 and (far_end - new_point).length <= tolerance:
        raise ValueError("This edge is already in the stroke")
    if any((point - new_point).length <= tolerance for point in others):
        raise ValueError("This edge would repeat or branch the stroke")


def extend_stroke_along_edge(
    stroke: Sequence[Vector], a: Vector, b: Vector, tolerance: float
) -> list[Vector]:
    """Append or prepend a connected edge to an open stroke.

    Reaching the stroke's other end closes the loop; any other repeated
    point is rejected.

    Args:
        stroke: Current stroke. Not modified.
        a: One edge endpoint.
        b: The other edge endpoint.
        tolerance: Distance under which points are the same vertex.

    Returns:
        The extended stroke as a new list.

    Raises:
        ValueError: If the stroke is closed, the edge is not connected to
            an end, or the edge would repeat or branch the stroke.
    """
    if not stroke:
        return [a.copy(), b.copy()]
    if len(stroke) > 2 and (stroke[0] - stroke[-1]).length <= tolerance:
        raise ValueError("Close the current loop with C before selecting another edge")
    for endpoint, other in ((a, b), (b, a)):
        if (stroke[-1] - endpoint).length <= tolerance:
            _reject_repeat(other, stroke[0], stroke[1:], len(stroke), tolerance)
            return [*stroke, other.copy()]
        if (stroke[0] - endpoint).length <= tolerance:
            _reject_repeat(other, stroke[-1], stroke[:-1], len(stroke), tolerance)
            return [other.copy(), *stroke]
    raise ValueError("Select an edge connected to either end of the current stroke")
