"""Interpolate an editable surface bounded by spatial closed loops.

The largest area-vector loop supplies a projection plane. All boundaries
must have simple, disjoint projections, with one outer boundary and
optional holes. Heights are interpolated with a discrete harmonic solve,
keeping the drawn boundary fixed. Surfaces folding over this plane need
a manually made cutter.
"""

from collections.abc import Sequence
from math import fsum, isfinite, radians
from typing import cast

# The bpy wheel initializes bmesh; keep this import order.
# isort: off
import bpy
import bmesh
# isort: on

from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt, intersect_point_line

_EPSILON = 1e-6
_GRID_SIZE = 18


def simplify_closed_loop(points: Sequence[Vector], tolerance: float) -> list[Vector]:
    """Remove redundant freehand samples within a world-space tolerance."""
    if len(points) < 4:
        return list(points)
    split = max(
        range(1, len(points)), key=lambda i: (points[i] - points[0]).length_squared
    )
    path = [*points, points[0]]
    keep = {0, split, len(points)}
    stack = [(0, split), (split, len(points))]
    while stack:
        first, last = stack.pop()
        direction = path[last] - path[first]
        if last - first < 2:
            continue
        distances: list[tuple[float, int]] = []
        for i in range(first + 1, last):
            factor = (
                (path[i] - path[first]).dot(direction) / direction.length_squared
                if direction.length_squared
                else 0.0
            )
            closest = path[first] + direction * max(0.0, min(1.0, factor))
            distances.append(((path[i] - closest).length, i))
        distance, index = max(distances)
        if distance > tolerance:
            keep.add(index)
            stack.extend(((first, index), (index, last)))
    return [path[i] for i in sorted(keep) if i < len(points)]


def _inside(point: Vector, loop: Sequence[Vector]) -> bool:
    """Test containment using an even-odd ray crossing rule."""
    inside = False
    for a, b in zip(loop, (*loop[1:], loop[0]), strict=True):
        if (a.y > point.y) != (b.y > point.y):
            crossing = a.x + (point.y - a.y) * (b.x - a.x) / (b.y - a.y)
            if point.x < crossing:
                inside = not inside
    return inside


def _area_vector(loop: Sequence[Vector]) -> Vector:
    # Accumulate Newell components in double precision. Summing float32
    # vectors tilts an otherwise planar projection at densely sampled rims.
    pairs = list(zip(loop, (*loop[1:], loop[0]), strict=True))
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


def _interpolate_heights(
    vertices: Sequence[Vector],
    faces: Sequence[Sequence[int]],
    fixed: dict[int, float],
) -> list[float]:
    """Solve the graph Laplacian with Dirichlet boundary heights."""
    neighbors: list[set[int]] = [set() for _ in vertices]
    for face in faces:
        for a, b in zip(face, (*face[1:], face[0]), strict=True):
            neighbors[a].add(b)
            neighbors[b].add(a)
    mean = sum(fixed.values()) / len(fixed)
    heights = [fixed.get(i, mean) for i in range(len(vertices))]
    free = [i for i, adjacent in enumerate(neighbors) if adjacent and i not in fixed]
    for _ in range(2000):
        change = 0.0
        for i in free:
            height = sum(heights[j] for j in neighbors[i]) / len(neighbors[i])
            change = max(change, abs(height - heights[i]))
            heights[i] = height
        if change < 1e-7:
            return heights
    raise ValueError("Surface interpolation did not converge; simplify the loops")


def interpolate_cutting_surface(
    loops: Sequence[Sequence[Vector]],
    *,
    margin: float = 0.0,
) -> tuple[bpy.types.Mesh, tuple[int, ...], tuple[int, ...]]:
    """Create a curved patch, returning mesh, boundary and interior indices.

    Coordinates and margin use the same space (world space for drawn strokes).
    Loop order and winding do not assign roles. A single outer loop is filled;
    nested loops become holes. Boundary coordinates are preserved exactly.
    A small optional collar extends past the boundary so a Boolean can cut
    through the target skin. It is excluded from the editable interior group.

    Raises:
        ValueError: For degenerate, crossing, touching, folded projections,
            multiple outer loops, nested holes or an overlapping collar.
    """
    if not loops or not isfinite(margin) or margin < 0:
        raise ValueError("Draw at least one closed loop and use a nonnegative margin")
    cleaned = [list(loop) for loop in loops]
    for loop in cleaned:
        if len(loop) > 1 and loop[0] == loop[-1]:
            loop.pop()
        if len(loop) < 3 or any(
            len(p) != 3 or not all(isfinite(v) for v in p) for p in loop
        ):
            raise ValueError("Each loop needs at least three finite 3D points")
    points = [p for loop in cleaned for p in loop]
    origin = Vector(
        tuple(fsum(p[axis] for p in points) / len(points) for axis in range(3))
    )
    scale = max((p - origin).length for p in points)
    if scale == 0:
        raise ValueError("The loop has no area")
    normalized = [[(p - origin) / scale for p in loop] for loop in cleaned]
    normal = max((_area_vector(loop) for loop in normalized), key=lambda n: n.length)
    if normal.length < _EPSILON:
        raise ValueError("The loops have no usable projection; redraw the boundary")
    normal.normalize()
    u = normal.orthogonal().normalized()
    v = cast(Vector, normal.cross(u))
    projected = [[Vector((p.dot(u), p.dot(v))) for p in loop] for loop in normalized]
    vertices = [p for loop in projected for p in loop]
    edges: list[tuple[int, int]] = []
    offset = 0
    for loop in projected:
        edges.extend(
            (offset + i, offset + (i + 1) % len(loop)) for i in range(len(loop))
        )
        offset += len(loop)

    # CDT reports crossings as new vertices and touching/degenerate points as
    # merged origins. Validate before classifying holes or adding interior points.
    _, _, _, originals, edge_origins, _ = delaunay_2d_cdt(
        vertices, edges, [], 0, _EPSILON
    )
    if (
        len(originals) != len(vertices)
        or any(len(ids) != 1 for ids in originals)
        or any(len(ids) > 1 for ids in edge_origins)
    ):
        raise ValueError("Loops cross, touch or fold in projection; redraw them")
    depths = [
        sum(_inside(loop[0], other) for j, other in enumerate(projected) if i != j)
        for i, loop in enumerate(projected)
    ]
    if depths.count(0) != 1 or any(depth > 1 for depth in depths):
        raise ValueError("Draw one outer boundary and its holes for each cut")

    def in_patch(point: Vector) -> bool:
        return sum(_inside(point, loop) for loop in projected) % 2 == 1

    # Uniform interior samples make the automatically filled patch editable,
    # including the interior of a triangular or strongly concave boundary.
    low = Vector((min(p.x for p in vertices), min(p.y for p in vertices)))
    high = Vector((max(p.x for p in vertices), max(p.y for p in vertices)))
    for x in range(1, _GRID_SIZE):
        for y in range(1, _GRID_SIZE):
            point = Vector(
                (
                    low.x + (high.x - low.x) * x / _GRID_SIZE,
                    low.y + (high.y - low.y) * y / _GRID_SIZE,
                )
            )
            on_edge = False
            for a, b in edges:
                closest, factor = intersect_point_line(point, vertices[a], vertices[b])
                if (
                    -_EPSILON <= factor <= 1 + _EPSILON
                    and (point - closest).length < _EPSILON * 10
                ):
                    on_edge = True
                    break
            if not on_edge and in_patch(point):
                vertices.append(point)
    coords, _, triangles, originals, _, _ = delaunay_2d_cdt(
        vertices, edges, [], 0, _EPSILON
    )
    # Dense freehand boundaries can produce nearly collinear CDT triangles.
    # Use the original boundary coordinates and omit zero-area faces before
    # classifying the rim; otherwise a degenerate triangle reverses its edges.
    for i, ids in enumerate(originals):
        for source in ids:
            if source < len(points):
                coords[i] = vertices[source]
                break

    def has_area(face: Sequence[int]) -> bool:
        a, b, c = (coords[i] for i in face)
        return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x) > 1e-9

    faces = [
        face
        for face in triangles
        if has_area(face)
        and in_patch(sum((coords[i] for i in face), Vector((0.0, 0.0))) / len(face))
    ]
    if not faces:
        raise ValueError("The loops do not enclose a cutting surface")
    boundary_map = {
        source: i
        for i, ids in enumerate(originals)
        for source in ids
        if source < len(points)
    }
    if len(boundary_map) != len(points):
        raise ValueError("The boundary could not be preserved")
    fixed = {
        i: ((points[source] - origin) / scale).dot(normal)
        for source, i in boundary_map.items()
    }
    # A chord between two fixed boundary vertices otherwise isolates an ear
    # from the interior solve. Split these chords with free vertices so the
    # interpolated surface leaves the target skin instead of making slivers.
    edge_counts: dict[tuple[int, int], int] = {}
    for face in faces:
        for a, b in zip(face, (*face[1:], face[0]), strict=True):
            key = (min(a, b), max(a, b))
            edge_counts[key] = edge_counts.get(key, 0) + 1
    expected_rim = {
        (min(boundary_map[a], boundary_map[b]), max(boundary_map[a], boundary_map[b]))
        for a, b in edges
    }
    if {edge for edge, count in edge_counts.items() if count == 1} != expected_rim:
        raise ValueError(
            "The boundary could not be triangulated; simplify or redraw the stroke"
        )
    split_edges: dict[tuple[int, int], int] = {}
    for (a, b), count in edge_counts.items():
        if count == 2 and a in fixed and b in fixed:
            split_edges[a, b] = len(coords)
            coords.append((coords[a] + coords[b]) / 2)
    refined_faces: list[list[int]] = []
    for face in faces:
        polygon: list[int] = []
        for a, b in zip(face, (*face[1:], face[0]), strict=True):
            polygon.append(a)
            midpoint = split_edges.get((min(a, b), max(a, b)))
            if midpoint is not None:
                polygon.append(midpoint)
        if len(polygon) == 3:
            refined_faces.append(face)
        else:
            center = len(coords)
            coords.append(sum((coords[i] for i in face), Vector((0.0, 0.0))) / 3)
            refined_faces.extend(
                [a, b, center]
                for a, b in zip(polygon, (*polygon[1:], polygon[0]), strict=True)
            )
    faces = refined_faces
    heights = _interpolate_heights(coords, faces, fixed)
    used = sorted({i for face in faces for i in face})
    if not set(boundary_map.values()).issubset(used):
        raise ValueError("The boundary is too finely sampled; simplify the stroke")
    remap = {old: new for new, old in enumerate(used)}
    positions = [
        origin + scale * (u * coords[i].x + v * coords[i].y + normal * heights[i])
        for i in used
    ]
    boundary = tuple(remap[boundary_map[i]] for i in range(len(points)))
    for source, index in enumerate(boundary):
        positions[index] = points[source].copy()
    polygons = [tuple(remap[i] for i in face) for face in faces]
    interior = tuple(remap[i] for i in used if i not in fixed)
    if not interior:
        # Very narrow patches may miss the regular grid. Add triangle centers
        # so manual interior shaping is still possible without subdivision.
        refined: list[tuple[int, ...]] = []
        start = len(positions)
        for a, b, c in polygons:
            index = len(positions)
            positions.append((positions[a] + positions[b] + positions[c]) / 3)
            refined.extend(((a, b, index), (b, c, index), (c, a, index)))
        polygons = refined
        interior = tuple(range(start, len(positions)))
    polygons = _join_interior_triangles(positions, polygons)
    if margin:
        _extend_boundary(positions, polygons, boundary, margin, normal)
    mesh = bpy.data.meshes.new("Drawn Cutting Surface")
    try:
        mesh.from_pydata(positions, [], polygons)
        mesh.update()
    except Exception:
        bpy.data.meshes.remove(mesh)
        raise
    return mesh, boundary, interior


def _join_interior_triangles(
    positions: Sequence[Vector], faces: Sequence[Sequence[int]]
) -> list[tuple[int, ...]]:
    """Prefer editable quads without moving vertices or bridging the rim.

    Keep triangles where joining would create a sharply bent or
    distorted quad. Joining after interpolation preserves the solved
    vertex heights.
    """
    bm = bmesh.new()
    try:
        vertices = [bm.verts.new((point.x, point.y, point.z)) for point in positions]
        indices = {vertex: i for i, vertex in enumerate(vertices)}
        for face in faces:
            bm.faces.new([vertices[i] for i in face])
        bm.normal_update()
        bmesh.ops.join_triangles(
            bm,
            faces=list(bm.faces),
            angle_face_threshold=radians(40),
            angle_shape_threshold=radians(40),
        )
        return [tuple(indices[vertex] for vertex in face.verts) for face in bm.faces]
    finally:
        bm.free()


def _extend_boundary(
    positions: list[Vector],
    faces: list[tuple[int, ...]],
    boundary: Sequence[int],
    margin: float,
    projection_normal: Vector,
) -> None:
    """Extend in the projection plane, preserving the drawn boundary.

    Tiny boundary triangles can follow the target skin rather than the
    interpolated interior. Their normals must not control the extension.
    """
    edge_faces: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for face in faces:
        for i, j in zip(face, (*face[1:], face[0]), strict=True):
            edge_faces.setdefault((min(i, j), max(i, j)), []).append((i, j))
    rim = [linked[0] for linked in edge_faces.values() if len(linked) == 1]
    offsets = {i: Vector((0.0, 0.0, 0.0)) for i in boundary}
    for i, j in rim:
        outward = cast(
            Vector, (positions[j] - positions[i]).cross(projection_normal)
        ).normalized()
        offsets[i] += outward
        offsets[j] += outward
    added: dict[int, int] = {}
    for i in boundary:
        added[i] = len(positions)
        positions.append(positions[i] + offsets[i].normalized() * margin)
    for i, j in rim:
        a, b = added[i], added[j]
        if (
            cast(
                Vector, (positions[b] - positions[i]).cross(positions[j] - positions[i])
            ).dot(projection_normal)
            <= 0
        ):
            raise ValueError(
                "The cut margin overlaps; use a thinner cut or wider loops"
            )
        faces.append((j, i, a, b))
