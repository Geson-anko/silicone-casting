"""Interpolate an editable surface bounded by spatial closed loops.

The largest area-vector loop supplies a projection plane. All boundaries
must have simple, disjoint projections, with one outer boundary and
optional holes. Heights are interpolated with a discrete harmonic solve,
keeping the drawn boundary fixed. Surfaces folding over this plane need
a manually made cutter.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from math import fsum, inf, isfinite, radians
from typing import Final, NamedTuple, Self, cast

# The bpy wheel initializes bmesh; keep this import order.
# isort: off
import bpy
import bmesh
# isort: on

from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt, intersect_point_line

# Loops are normalized to a unit radius, so this is a relative tolerance for
# CDT merging and for point-on-edge tests.
_EPSILON: Final = 1e-6
# Grid samples closer than this to a rim edge would make slivers against it.
_SAMPLE_CLEARANCE: Final = _EPSILON * 10
# Grid divisions across the bounding box: enough interior vertices to shape
# by hand without making the patch needlessly dense.
_GRID_SIZE: Final = 18
# Twice the signed area below which a projected triangle counts as folded or
# degenerate. Dense freehand rims produce nearly collinear triangles.
_MIN_DOUBLE_AREA: Final = 1e-9
# Gauss-Seidel sweeps allowed before the loops are deemed too complex.
_MAX_RELAXATION_SWEEPS: Final = 2000
# Largest per-sweep height change, in normalized units, treated as converged.
_RELAXATION_TOLERANCE: Final = 1e-7
# Quad rows between two bridged rims, leaving two editable interior rings.
_BRIDGE_ROWS: Final = 3
# Keep triangles whose merged quad would bend or skew more than this.
_JOIN_ANGLE_LIMIT: Final = radians(40)

type _Polygon = tuple[int, ...]


class CuttingSurface(NamedTuple):
    """A generated cutting-surface mesh and its vertex roles.

    Attributes:
        mesh: Newly allocated mesh datablock owned by the caller.
        boundary: Vertex indices of the drawn loops, in input order.
        interior: Vertex indices meant for manual shaping. Excludes the
            boundary and the optional collar.
    """

    mesh: bpy.types.Mesh
    boundary: tuple[int, ...]
    interior: tuple[int, ...]


def simplify_closed_loop(points: Sequence[Vector], tolerance: float) -> list[Vector]:
    """Remove redundant freehand samples from a closed loop.

    This is Ramer-Douglas-Peucker on a closed path, split first at the point
    farthest from the start so neither half degenerates into a zero-length
    chord.

    Args:
        points: Loop samples without a repeated closing point.
        tolerance: Largest allowed deviation, in the points' space.

    Returns:
        The kept samples in their original order, starting at ``points[0]``.
    """
    count = len(points)
    if count < 4:
        return list(points)
    split = max(
        range(1, count), key=lambda index: (points[index] - points[0]).length_squared
    )
    path = [*points, points[0]]
    keep = {0, split, count}
    spans = [(0, split), (split, count)]
    while spans:
        first, last = spans.pop()
        if last - first < 2:
            continue
        distance, index = _farthest_from_chord(path, first, last)
        if distance > tolerance:
            keep.add(index)
            spans.extend(((first, index), (index, last)))
    return [path[index] for index in sorted(keep) if index < count]


def _farthest_from_chord(
    path: Sequence[Vector], first: int, last: int
) -> tuple[float, int]:
    """Return the largest distance to the first-last chord and its index."""
    direction = path[last] - path[first]
    distances: list[tuple[float, int]] = []
    for index in range(first + 1, last):
        factor = (
            (path[index] - path[first]).dot(direction) / direction.length_squared
            if direction.length_squared
            else 0.0
        )
        closest = path[first] + direction * max(0.0, min(1.0, factor))
        distances.append(((path[index] - closest).length, index))
    return max(distances)


def _closed_pairs[T](items: Sequence[T]) -> Iterator[tuple[T, T]]:
    """Yield consecutive pairs of a cyclic sequence, including the wrap."""
    return zip(items, (*items[1:], items[0]), strict=True)


def _inside(point: Vector, loop: Sequence[Vector]) -> bool:
    """Test containment using an even-odd ray crossing rule."""
    inside = False
    for a, b in _closed_pairs(loop):
        if (a.y > point.y) != (b.y > point.y):
            crossing = a.x + (point.y - a.y) * (b.x - a.x) / (b.y - a.y)
            if point.x < crossing:
                inside = not inside
    return inside


def _area_vector(loop: Sequence[Vector]) -> Vector:
    """Return the Newell area vector of a spatial loop."""
    # Accumulate Newell components in double precision. Summing float32
    # vectors tilts an otherwise planar projection at densely sampled rims.
    pairs = list(_closed_pairs(loop))
    return Vector(
        tuple(
            fsum(
                (a[(axis + 1) % 3] - b[(axis + 1) % 3])
                * (a[(axis + 2) % 3] + b[(axis + 2) % 3])
                for a, b in pairs
            )
            for axis in range(3)
        )
    )


def _cotangent_weights(
    vertices: Sequence[Vector], faces: Sequence[Sequence[int]]
) -> list[dict[int, float]]:
    """Accumulate cotangent Laplacian weights for each vertex's neighbors."""
    neighbors: list[dict[int, float]] = [{} for _ in vertices]
    for face in faces:
        for corner in range(3):
            a, b, c = (face[corner], face[(corner + 1) % 3], face[(corner + 2) % 3])
            u = vertices[a] - vertices[c]
            v = vertices[b] - vertices[c]
            weight = u.dot(v) / abs(u.x * v.y - u.y * v.x)
            neighbors[a][b] = neighbors[a].get(b, 0.0) + weight
            neighbors[b][a] = neighbors[b].get(a, 0.0) + weight
    return neighbors


def _interpolate_heights(
    vertices: Sequence[Vector],
    faces: Sequence[Sequence[int]],
    fixed: dict[int, float],
) -> list[float]:
    """Solve the cotangent Laplacian with Dirichlet boundary heights.

    Geometric weights prevent uneven triangle spacing from imprinting
    bumps on the interpolated surface.

    Raises:
        ValueError: If Gauss-Seidel relaxation does not converge.
    """
    neighbors = _cotangent_weights(vertices, faces)
    mean = sum(fixed.values()) / len(fixed)
    heights = [fixed.get(index, mean) for index in range(len(vertices))]
    free = [
        index
        for index, adjacent in enumerate(neighbors)
        if adjacent and index not in fixed
    ]
    for _ in range(_MAX_RELAXATION_SWEEPS):
        change = 0.0
        for index in free:
            weights = neighbors[index]
            height = sum(
                heights[other] * weight for other, weight in weights.items()
            ) / sum(weights.values())
            change = max(change, abs(height - heights[index]))
            heights[index] = height
        if change < _RELAXATION_TOLERANCE:
            return heights
    raise ValueError("Surface interpolation did not converge; simplify the loops")


def _clean_loops(loops: Sequence[Sequence[Vector]]) -> list[list[Vector]]:
    """Drop repeated closing points and reject short or non-finite loops."""
    cleaned = [list(loop) for loop in loops]
    for loop in cleaned:
        if len(loop) > 1 and loop[0] == loop[-1]:
            loop.pop()
        if len(loop) < 3 or any(
            len(point) != 3 or not all(isfinite(value) for value in point)
            for point in loop
        ):
            raise ValueError("Each loop needs at least three finite 3D points")
    return cleaned


def _loop_edges(loops: Sequence[Sequence[Vector]]) -> list[tuple[int, int]]:
    """Return closed-loop edges indexing into the flattened loop points."""
    edges: list[tuple[int, int]] = []
    offset = 0
    for loop in loops:
        edges.extend(
            (offset + index, offset + (index + 1) % len(loop))
            for index in range(len(loop))
        )
        offset += len(loop)
    return edges


def _require_simple_projection(
    vertices: list[Vector], edges: list[tuple[int, int]]
) -> None:
    """Reject crossing, touching or degenerate projected loops.

    CDT reports crossings as new vertices and touching or degenerate
    points as merged origins. This must run before classifying holes or
    adding interior points.
    """
    _, _, _, originals, edge_origins, _ = delaunay_2d_cdt(
        vertices, edges, [], 0, _EPSILON
    )
    if (
        len(originals) != len(vertices)
        or any(len(ids) != 1 for ids in originals)
        or any(len(ids) > 1 for ids in edge_origins)
    ):
        raise ValueError("Loops cross, touch or fold in projection; redraw them")


def _nesting_depths(loops: Sequence[Sequence[Vector]]) -> list[int]:
    """Count how many other disjoint loops enclose each loop."""
    return [
        sum(
            _inside(loop[0], other)
            for other_index, other in enumerate(loops)
            if other_index != index
        )
        for index, loop in enumerate(loops)
    ]


@dataclass(frozen=True)
class _ProjectedBoundary:
    """Validated planar loops and the frame that restores world positions.

    Projected coordinates live in a frame centered on the points and
    scaled to unit radius, so tolerances are independent of the
    drawing's size.
    """

    points: list[Vector]
    origin: Vector
    scale: float
    normal: Vector
    u: Vector
    v: Vector
    projected: list[list[Vector]]
    edges: list[tuple[int, int]]
    depths: list[int]

    @classmethod
    def from_loops(cls, loops: Sequence[Sequence[Vector]]) -> Self:
        """Normalize the loops and reject crossing or nested projections.

        Raises:
            ValueError: For degenerate, crossing, touching or folded loops,
                multiple outer loops or nested holes.
        """
        cleaned = _clean_loops(loops)
        points = [point for loop in cleaned for point in loop]
        origin = Vector(
            tuple(
                fsum(point[axis] for point in points) / len(points) for axis in range(3)
            )
        )
        scale = max((point - origin).length for point in points)
        if scale == 0:
            raise ValueError("The loop has no area")
        normalized = [[(point - origin) / scale for point in loop] for loop in cleaned]
        normal = max(
            (_area_vector(loop) for loop in normalized), key=lambda area: area.length
        )
        if normal.length < _EPSILON:
            raise ValueError("The loops have no usable projection; redraw the boundary")
        normal.normalize()
        u = normal.orthogonal().normalized()
        v = cast(Vector, normal.cross(u))
        projected = [
            [Vector((point.dot(u), point.dot(v))) for point in loop]
            for loop in normalized
        ]
        edges = _loop_edges(projected)
        _require_simple_projection(
            [point for loop in projected for point in loop], edges
        )
        depths = _nesting_depths(projected)
        if depths.count(0) != 1 or any(depth > 1 for depth in depths):
            raise ValueError("Draw one outer boundary and its holes for each cut")
        return cls(points, origin, scale, normal, u, v, projected, edges, depths)

    @property
    def vertices(self) -> list[Vector]:
        """Projected rim points, in the same order as ``points``."""
        return [point for loop in self.projected for point in loop]

    def contains(self, point: Vector) -> bool:
        """Test containment inside the outer rim, excluding its holes."""
        return sum(_inside(point, loop) for loop in self.projected) % 2 == 1

    def height_of(self, point: Vector) -> float:
        """Return a world point's normalized height above the plane."""
        return ((point - self.origin) / self.scale).dot(self.normal)

    def to_world(self, coord: Vector, height: float) -> Vector:
        """Lift a projected coordinate at a height back to world space."""
        return self.origin + self.scale * (
            self.u * coord.x + self.v * coord.y + self.normal * height
        )

    def sample_interior(self) -> list[Vector]:
        """Sample the patch on a regular grid, keeping clear of its rim."""
        # Uniform interior samples make the automatically filled patch editable,
        # including the interior of a triangular or strongly concave boundary.
        vertices = self.vertices
        low = Vector((min(p.x for p in vertices), min(p.y for p in vertices)))
        high = Vector((max(p.x for p in vertices), max(p.y for p in vertices)))
        samples: list[Vector] = []
        for column in range(1, _GRID_SIZE):
            for row in range(1, _GRID_SIZE):
                point = Vector(
                    (
                        low.x + (high.x - low.x) * column / _GRID_SIZE,
                        low.y + (high.y - low.y) * row / _GRID_SIZE,
                    )
                )
                if not self._touches_rim(point, vertices) and self.contains(point):
                    samples.append(point)
        return samples

    def _touches_rim(self, point: Vector, vertices: Sequence[Vector]) -> bool:
        """Test whether a point is within sample clearance of the rim."""
        for a, b in self.edges:
            closest, factor = intersect_point_line(point, vertices[a], vertices[b])
            if (
                -_EPSILON <= factor <= 1 + _EPSILON
                and (point - closest).length < _SAMPLE_CLEARANCE
            ):
                return True
        return False


def _counterclockwise_rings(
    loops: Sequence[Sequence[Vector]], depths: Sequence[int]
) -> tuple[list[int], list[int]]:
    """Return the outer and inner rims as counterclockwise index rings."""
    rings: list[list[int]] = []
    offset = 0
    for loop in loops:
        ring = list(range(offset, offset + len(loop)))
        area = sum(a.x * b.y - a.y * b.x for a, b in _closed_pairs(loop))
        if area < 0:
            ring.reverse()
        rings.append(ring)
        offset += len(loop)
    return rings[depths.index(0)], rings[depths.index(1)]


def _arc_fractions(coords: Sequence[Vector], ring: Sequence[int]) -> list[float]:
    """Return cumulative arc length fractions, from 0 to 1 at the wrap."""
    lengths = [0.0]
    for a, b in _closed_pairs(ring):
        lengths.append(lengths[-1] + (coords[b] - coords[a]).length)
    return [length / lengths[-1] for length in lengths]


def _march_rims(
    outer: Sequence[int], inner: Sequence[int], coords: Sequence[Vector]
) -> Iterator[tuple[tuple[int, int], tuple[int, int]]]:
    """Pair rim vertices by arc length, yielding each strip cell's two sides.

    Each side is an ``(outer, inner)`` vertex pair. Sides whose next
    fractions nearly coincide advance both rims together, so equal rims
    produce only quads.
    """
    outer_t, inner_t = _arc_fractions(coords, outer), _arc_fractions(coords, inner)
    i = j = 0
    while i < len(outer) or j < len(inner):
        next_outer = outer_t[i + 1] if i < len(outer) else inf
        next_inner = inner_t[j + 1] if j < len(inner) else inf
        # "Nearly" is relative to half the shorter of the two current steps.
        aligned = abs(next_outer - next_inner) < 0.5 * min(
            next_outer - outer_t[i], next_inner - inner_t[j]
        )
        start = (outer[i % len(outer)], inner[j % len(inner)])
        if aligned or next_outer < next_inner:
            i += 1
        if aligned or next_inner < next_outer:
            j += 1
        yield start, (outer[i % len(outer)], inner[j % len(inner)])


def _positive_fan(
    coords: Sequence[Vector], polygons: Sequence[_Polygon]
) -> list[list[int]] | None:
    """Fan-triangulate the cells, or return None if any triangle folds."""
    triangles: list[list[int]] = []
    for face in polygons:
        cell = [[face[0], face[k], face[k + 1]] for k in range(1, len(face) - 1)]
        for a, b, c in cell:
            # Subtracts in float32 Vectors, unlike _has_area's double-precision
            # components, so the two tests are not interchangeable.
            u, v = coords[b] - coords[a], coords[c] - coords[a]
            if u.x * v.y - u.y * v.x <= _MIN_DOUBLE_AREA:
                return None
        triangles.extend(cell)
    return triangles


@dataclass(frozen=True)
class _AnnulusBridge:
    """Quad rows spanning an outer rim and its single hole.

    ``coords`` starts with the rim points in input order, followed by the
    spoke vertices between them.
    """

    coords: list[Vector]
    triangles: list[list[int]]
    polygons: list[_Polygon]

    @classmethod
    def from_boundary(cls, boundary: _ProjectedBoundary) -> Self | None:
        """Bridge two rims with quad rows, or return None when the strip folds.

        Match arc lengths after aligning the starting points. Unequal
        vertex counts need occasional triangles, but all intermediate
        rows stay quads. Original rim vertices are neither moved nor
        resampled.
        """
        if len(boundary.projected) != 2:
            return None
        coords = boundary.vertices
        outer, inner = _counterclockwise_rings(boundary.projected, boundary.depths)
        start = min(
            range(len(inner)),
            key=lambda index: (coords[inner[index]] - coords[outer[0]]).length_squared,
        )
        inner = inner[start:] + inner[:start]
        spokes: dict[tuple[int, int], list[int]] = {}

        def spoke(pair: tuple[int, int]) -> list[int]:
            # Neighboring cells share a spoke, so its interior vertices are
            # created once, in the order the march first reaches them.
            if pair not in spokes:
                a, b = pair
                middle = len(coords)
                coords.extend(
                    coords[a].lerp(coords[b], step / _BRIDGE_ROWS)
                    for step in range(1, _BRIDGE_ROWS)
                )
                spokes[pair] = [a, *range(middle, middle + _BRIDGE_ROWS - 1), b]
            return spokes[pair]

        polygons: list[_Polygon] = []
        for left_pair, right_pair in _march_rims(outer, inner, coords):
            left, right = spoke(left_pair), spoke(right_pair)
            for row in range(_BRIDGE_ROWS):
                face = (left[row], right[row], right[row + 1], left[row + 1])
                # A rim that does not advance collapses the cell to a triangle.
                polygons.append(tuple(dict.fromkeys(face)))

        # A positive triangulation of every strip cell guarantees a locally
        # unfolded bridge. Difficult concave rims use the general CDT patch.
        triangles = _positive_fan(coords, polygons)
        if triangles is None:
            return None
        return cls(coords, triangles, polygons)


def _delaunay_patch(
    boundary: _ProjectedBoundary,
) -> tuple[list[Vector], list[list[int]], list[list[int]]]:
    """Triangulate the rim with grid samples via constrained Delaunay."""
    vertices = [*boundary.vertices, *boundary.sample_interior()]
    coords, _, triangles, originals, _, _ = delaunay_2d_cdt(
        vertices, boundary.edges, [], 0, _EPSILON
    )
    return coords, triangles, originals


def _snap_to_rim(
    coords: Sequence[Vector], originals: Sequence[Sequence[int]], rim: Sequence[Vector]
) -> list[Vector]:
    """Snap CDT output coordinates back to their exact rim points."""
    snapped = list(coords)
    for index, ids in enumerate(originals):
        source = next((source for source in ids if source < len(rim)), None)
        if source is not None:
            snapped[index] = rim[source]
    return snapped


def _has_area(coords: Sequence[Vector], face: Sequence[int]) -> bool:
    """Test for a counterclockwise projected triangle with nonzero area."""
    a, b, c = (coords[index] for index in face)
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x) > _MIN_DOUBLE_AREA


def _edge_uses(faces: Sequence[Sequence[int]]) -> dict[tuple[int, int], int]:
    """Count the faces using each undirected edge, keyed by sorted indices."""
    uses: dict[tuple[int, int], int] = {}
    for face in faces:
        for a, b in _closed_pairs(face):
            key = (min(a, b), max(a, b))
            uses[key] = uses.get(key, 0) + 1
    return uses


def _split_boundary_chords(
    coords: Sequence[Vector],
    faces: Sequence[list[int]],
    edge_uses: dict[tuple[int, int], int],
    fixed: dict[int, float],
) -> tuple[list[Vector], list[list[int]]]:
    """Split interior chords between fixed vertices at their midpoints.

    A chord between two fixed boundary vertices otherwise isolates an
    ear from the interior solve. Free midpoints let the interpolated
    surface leave the target skin instead of making slivers. Splitting
    only at the midpoints, without a separate triangle center, keeps
    narrow annular patches from gaining unnecessary faces.
    """
    split_coords = list(coords)
    midpoints: dict[tuple[int, int], int] = {}
    for (a, b), count in edge_uses.items():
        if count == 2 and a in fixed and b in fixed:
            midpoints[a, b] = len(split_coords)
            split_coords.append((split_coords[a] + split_coords[b]) / 2)
    split_faces = [
        triangle for face in faces for triangle in _split_at(face, midpoints)
    ]
    return split_coords, split_faces


def _split_at(
    face: Sequence[int], midpoints: dict[tuple[int, int], int]
) -> list[list[int]]:
    """Split one triangle at each of its edges that has a midpoint."""
    triangles = [list(face)]
    for a, b in _closed_pairs(face):
        midpoint = midpoints.get((min(a, b), max(a, b)))
        if midpoint is None:
            continue
        for triangle in triangles:
            if a in triangle and b in triangle:
                opposite = next(index for index in triangle if index not in (a, b))
                triangles.remove(triangle)
                triangles.extend(([a, midpoint, opposite], [midpoint, b, opposite]))
                break
    return triangles


def _open_edges(polygons: Sequence[_Polygon]) -> list[tuple[int, int]]:
    """Return edges used by one polygon, directed as in that polygon."""
    edge_faces: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for face in polygons:
        for a, b in _closed_pairs(face):
            edge_faces.setdefault((min(a, b), max(a, b)), []).append((a, b))
    return [linked[0] for linked in edge_faces.values() if len(linked) == 1]


@dataclass(frozen=True)
class _EditableGeometry:
    """World-space patch geometry with its boundary and interior vertices."""

    positions: list[Vector]
    polygons: list[_Polygon]
    boundary: tuple[int, ...]
    interior: tuple[int, ...]

    def with_triangle_centers(self) -> Self:
        """Split every triangle at its center and make the centers interior."""
        positions = list(self.positions)
        polygons: list[_Polygon] = []
        start = len(positions)
        for a, b, c in self.polygons:
            index = len(positions)
            positions.append((positions[a] + positions[b] + positions[c]) / 3)
            polygons.extend(((a, b, index), (b, c, index), (c, a, index)))
        return replace(
            self,
            positions=positions,
            polygons=polygons,
            interior=tuple(range(start, len(positions))),
        )

    def with_joined_quads(self) -> Self:
        """Prefer editable quads without moving vertices or bridging the rim.

        Keep triangles where joining would create a sharply bent or
        distorted quad. Joining after interpolation preserves the solved
        vertex heights.
        """
        bm = bmesh.new()
        try:
            vertices = [
                bm.verts.new((point.x, point.y, point.z)) for point in self.positions
            ]
            indices = {vertex: index for index, vertex in enumerate(vertices)}
            for face in self.polygons:
                bm.faces.new([vertices[index] for index in face])
            bm.normal_update()
            bmesh.ops.join_triangles(
                bm,
                faces=list(bm.faces),
                angle_face_threshold=_JOIN_ANGLE_LIMIT,
                angle_shape_threshold=_JOIN_ANGLE_LIMIT,
            )
            polygons = [
                tuple(indices[vertex] for vertex in face.verts) for face in bm.faces
            ]
        finally:
            bm.free()
        return replace(self, polygons=polygons)

    def with_collar(self, margin: float, projection_normal: Vector) -> Self:
        """Extend the rim outward in the projection plane by *margin*.

        The drawn boundary stays in place and gains one quad per rim edge.
        Tiny boundary triangles can follow the target skin rather than the
        interpolated interior, so their normals must not steer the collar.

        Raises:
            ValueError: If adjacent collar quads would overlap.
        """
        rim = _open_edges(self.polygons)
        offsets = {index: Vector((0.0, 0.0, 0.0)) for index in self.boundary}
        for a, b in rim:
            outward = cast(
                Vector,
                (self.positions[b] - self.positions[a]).cross(projection_normal),
            ).normalized()
            offsets[a] += outward
            offsets[b] += outward
        positions = list(self.positions)
        collar: dict[int, int] = {}
        for index in self.boundary:
            collar[index] = len(positions)
            positions.append(positions[index] + offsets[index].normalized() * margin)
        polygons = list(self.polygons)
        for a, b in rim:
            outer_a, outer_b = collar[a], collar[b]
            if (
                cast(
                    Vector,
                    (positions[outer_b] - positions[a]).cross(
                        positions[b] - positions[a]
                    ),
                ).dot(projection_normal)
                <= 0
            ):
                raise ValueError(
                    "The cut margin overlaps; use a thinner cut or wider loops"
                )
            polygons.append((b, a, outer_a, outer_b))
        return replace(self, positions=positions, polygons=polygons)

    def to_mesh(self) -> CuttingSurface:
        """Allocate the mesh datablock, removing it again if building fails."""
        mesh = bpy.data.meshes.new("Drawn Cutting Surface")
        try:
            mesh.from_pydata(self.positions, [], self.polygons)
            mesh.update()
        except Exception:
            # Re-raised: only ensures a failed build leaks no datablock.
            bpy.data.meshes.remove(mesh)
            raise
        return CuttingSurface(mesh, self.boundary, self.interior)


@dataclass(frozen=True)
class _SurfacePatch:
    """A projected triangulation whose rim vertices have fixed heights."""

    _boundary: _ProjectedBoundary
    _coords: list[Vector]
    _faces: list[list[int]]
    # Maps each drawn point index to its vertex in ``_coords``.
    _rim: dict[int, int]
    _fixed: dict[int, float]
    # Quad rows to output instead of joined triangles, for a bridged annulus.
    _bridge_faces: list[_Polygon] | None

    @classmethod
    def from_boundary(cls, boundary: _ProjectedBoundary) -> Self:
        """Sample and triangulate a patch without changing its drawn rim.

        Raises:
            ValueError: If the triangulation encloses nothing or cannot keep
                every drawn point and rim edge.
        """
        points = boundary.points
        bridge = _AnnulusBridge.from_boundary(boundary)
        if bridge is None:
            coords, triangles, originals = _delaunay_patch(boundary)
        else:
            coords, triangles = bridge.coords, bridge.triangles
            originals = [
                [index] if index < len(points) else [] for index in range(len(coords))
            ]
        # Dense freehand boundaries can produce nearly collinear CDT triangles.
        # Use the original boundary coordinates and omit zero-area faces before
        # classifying the rim; otherwise a degenerate triangle reverses its edges.
        coords = _snap_to_rim(coords, originals, boundary.vertices)
        faces = [
            face
            for face in triangles
            if _has_area(coords, face)
            and boundary.contains(
                sum((coords[index] for index in face), Vector((0.0, 0.0))) / len(face)
            )
        ]
        if not faces:
            raise ValueError("The loops do not enclose a cutting surface")
        rim = {
            source: index
            for index, ids in enumerate(originals)
            for source in ids
            if source < len(points)
        }
        if len(rim) != len(points):
            raise ValueError("The boundary could not be preserved")
        fixed = {
            index: boundary.height_of(points[source]) for source, index in rim.items()
        }
        edge_uses = _edge_uses(faces)
        expected_rim = {
            (min(rim[a], rim[b]), max(rim[a], rim[b])) for a, b in boundary.edges
        }
        if {edge for edge, count in edge_uses.items() if count == 1} != expected_rim:
            raise ValueError(
                "The boundary could not be triangulated; simplify or redraw the stroke"
            )
        coords, faces = _split_boundary_chords(coords, faces, edge_uses, fixed)
        return cls(
            boundary,
            coords,
            faces,
            rim,
            fixed,
            None if bridge is None else bridge.polygons,
        )

    def solve(self) -> _EditableGeometry:
        """Interpolate heights and compact the patch into world-space geometry.

        Raises:
            ValueError: If the height solve does not converge or a rim vertex
                is left without faces.
        """
        points = self._boundary.points
        heights = _interpolate_heights(self._coords, self._faces, self._fixed)
        used = sorted({index for face in self._faces for index in face})
        if not set(self._rim.values()).issubset(used):
            raise ValueError("The boundary is too finely sampled; simplify the stroke")
        remap = {old: new for new, old in enumerate(used)}
        positions = [
            self._boundary.to_world(self._coords[index], heights[index])
            for index in used
        ]
        boundary = tuple(remap[self._rim[source]] for source in range(len(points)))
        # Restore the drawn points exactly; the frame round trip is lossy.
        for source, index in enumerate(boundary):
            positions[index] = points[source].copy()
        geometry = _EditableGeometry(
            positions,
            [tuple(remap[index] for index in face) for face in self._faces],
            boundary,
            tuple(remap[index] for index in used if index not in self._fixed),
        )
        if not geometry.interior:
            # Very narrow patches may miss the regular grid. Add triangle centers
            # so manual interior shaping is still possible without subdivision.
            geometry = geometry.with_triangle_centers()
        if self._bridge_faces is None:
            return geometry.with_joined_quads()
        return replace(
            geometry,
            polygons=[
                tuple(remap[index] for index in face) for face in self._bridge_faces
            ],
        )


def interpolate_cutting_surface(
    loops: Sequence[Sequence[Vector]],
    *,
    margin: float = 0.0,
) -> CuttingSurface:
    """Create a curved patch bounded by the drawn loops.

    Loop order and winding do not assign roles. A single outer loop is
    filled; nested loops become holes. Boundary coordinates are preserved
    exactly.

    Args:
        loops: Closed loops of 3D points, e.g. world-space drawn strokes. A
            repeated closing point is ignored.
        margin: Width of an optional collar extending past the boundary so a
            Boolean can cut through the target skin. Uses the loops' space.
            The collar is excluded from the interior indices.

    Returns:
        The new mesh with its boundary and editable interior indices. The
        caller owns the mesh.

    Raises:
        ValueError: For no loops, a negative or non-finite margin, degenerate,
            crossing, touching or folded projections, multiple outer loops,
            nested holes, a failed interpolation or an overlapping collar.
            No mesh is allocated in that case.
    """
    if not loops or not isfinite(margin) or margin < 0:
        raise ValueError("Draw at least one closed loop and use a nonnegative margin")
    boundary = _ProjectedBoundary.from_loops(loops)
    geometry = _SurfacePatch.from_boundary(boundary).solve()
    if margin:
        geometry = geometry.with_collar(margin, boundary.normal)
    return geometry.to_mesh()
