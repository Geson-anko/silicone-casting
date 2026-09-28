"""Closed circular tubes along planar paths and shared Boolean cutters."""

from collections.abc import Sequence
from math import cos, isfinite, pi, sin
from typing import Final, cast

import bpy
from mathutils import Vector

# 64 sides keep the printed channel visibly round at typical vent diameters.
_RING_SEGMENTS: Final = 64
# Relative to the diameter: points closer than this are the same sample.
_COINCIDENT_FRACTION: Final = 1e-6
# Absolute floor for the on-plane check, so tiny diameters still tolerate
# float round-off in world-space coordinates.
_MIN_PLANE_TOLERANCE: Final = 1e-7
# Squared length below which a plane normal has no usable direction.
_MIN_NORMAL_LENGTH_SQUARED: Final = 1e-20
# A mitre whose tangent is this close to perpendicular to the next segment
# means the path turns back on itself, and the mitre scale would explode.
_MIN_MITRE_ALIGNMENT: Final = 1e-3
# Two Chaikin passes round a hand-drawn corner without drifting the path.
_SMOOTHING_PASSES: Final = 2
_CHAIKIN_NEAR: Final = 0.25
_CHAIKIN_FAR: Final = 0.75
_CUTTER_MODIFIER_NAME: Final = "Air Vents"


def simplify_vent_path(points: Sequence[Vector], tolerance: float) -> list[Vector]:
    """Remove drawing noise with Ramer-Douglas-Peucker, keeping endpoints.

    Args:
        points: The drawn polyline.
        tolerance: Points closer than this to the simplified line are dropped.

    Returns:
        Copies of the kept points, in their original order.
    """
    if len(points) < 3:
        return [point.copy() for point in points]
    keep = {0, len(points) - 1}
    pending = [(0, len(points) - 1)]
    while pending:
        start, end = pending.pop()
        farthest, distance = start, tolerance
        for index in range(start + 1, end):
            error = _distance_to_segment(points[index], points[start], points[end])
            if error > distance:
                farthest, distance = index, error
        if farthest != start:
            keep.add(farthest)
            pending.extend(((start, farthest), (farthest, end)))
    return [points[index].copy() for index in sorted(keep)]


def _distance_to_segment(point: Vector, start: Vector, end: Vector) -> float:
    line = end - start
    length_squared = line.length_squared
    factor = (
        min(1.0, max(0.0, (point - start).dot(line) / length_squared))
        if length_squared > 0
        else 0.0
    )
    return (point - (start + line * factor)).length


def smooth_vent_path(points: Sequence[Vector]) -> list[Vector]:
    """Round polyline corners by corner cutting, keeping both ends in place.

    Args:
        points: The polyline to smooth.

    Returns:
        A new, denser polyline. Paths with fewer than three points are
        returned as copies.
    """
    result = [point.copy() for point in points]
    if len(result) < 3:
        return result
    for _ in range(_SMOOTHING_PASSES):
        previous = result
        result = [previous[0]]
        for a, b in zip(previous, previous[1:], strict=False):
            result.extend((a.lerp(b, _CHAIKIN_NEAR), a.lerp(b, _CHAIKIN_FAR)))
        result.append(previous[-1])
    return result


def _clean_vent_path(
    path: Sequence[Vector], normal: Vector, origin: Vector, epsilon: float
) -> list[Vector]:
    """Validate one planar path and discard consecutive duplicate points."""
    points: list[Vector] = []
    for point in path:
        if not all(isfinite(v) for v in point):
            raise ValueError("Vent points must be finite")
        if abs((point - origin).dot(normal)) > max(epsilon, _MIN_PLANE_TOLERANCE):
            raise ValueError("Vent paths must stay on the drawing plane")
        if not points or (point - points[-1]).length > epsilon:
            points.append(point)
    if len(points) < 2:
        raise ValueError("The vent path has no length")
    return points


def _vent_sides(
    points: Sequence[Vector], normal: Vector, radius: float, epsilon: float
) -> list[Vector]:
    """Find mitred ring directions and reject overlapping neighboring rings."""
    directions = [
        (b - a).normalized() for a, b in zip(points, points[1:], strict=False)
    ]
    sides: list[Vector] = []
    for index in range(len(points)):
        before = directions[max(0, index - 1)]
        after = directions[min(index, len(directions) - 1)]
        tangent = (before + after).normalized()
        alignment = tangent.dot(after)
        if alignment < _MIN_MITRE_ALIGNMENT:
            raise ValueError("A vent cannot double back; smooth the bend")
        # Dividing by the alignment stretches the mitre so the tube keeps its
        # diameter measured perpendicular to each segment.
        sides.append(cast(Vector, tangent.cross(normal)) / alignment)
    for index, direction in enumerate(directions):
        overlap = radius * abs((sides[index + 1] - sides[index]).dot(direction))
        if (points[index + 1] - points[index]).length <= overlap + epsilon:
            raise ValueError("Bend too tight: smooth the line or reduce Diameter")
    return sides


def _append_tube(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
    points: Sequence[Vector],
    sides: Sequence[Vector],
    normal: Vector,
    radius: float,
) -> None:
    """Append one capped tube whose rings span ``normal`` and each side."""
    base = len(vertices)
    for point, side in zip(points, sides, strict=True):
        for segment in range(_RING_SEGMENTS):
            angle = 2 * pi * segment / _RING_SEGMENTS
            vertex = point + radius * (normal * cos(angle) + side * sin(angle))
            vertices.append((vertex.x, vertex.y, vertex.z))
    faces.append(tuple(base + i for i in reversed(range(_RING_SEGMENTS))))
    for ring in range(len(points) - 1):
        start = base + ring * _RING_SEGMENTS
        for segment in range(_RING_SEGMENTS):
            a = start + segment
            b = start + (segment + 1) % _RING_SEGMENTS
            faces.append((a, b, b + _RING_SEGMENTS, a + _RING_SEGMENTS))
    last = base + (len(points) - 1) * _RING_SEGMENTS
    faces.append(tuple(last + i for i in range(_RING_SEGMENTS)))


def create_air_vent_mesh(
    name: str,
    paths: Sequence[Sequence[Vector]],
    normal: Vector,
    diameter: float,
) -> bpy.types.Mesh:
    """Sweep capped round tubes, with mitred joins preserving diameter.

    All coordinates are in one world-space plane. Tight bends that fold
    neighboring rings through each other are rejected before allocating
    data. Separate paths may intersect: the Exact Boolean uses self
    intersection handling when subtracting the shared cutter.

    Args:
        name: Name of the new mesh datablock.
        paths: One polyline per vent, all on the plane through
            ``paths[0][0]`` with the given normal.
        normal: Normal of the drawing plane; need not be unit length.
        diameter: Tube diameter in world units.

    Returns:
        A new mesh datablock owned by the caller.

    Raises:
        ValueError: If the inputs are not finite, a path leaves the plane or
            has no length, or a bend is too tight for the diameter. No mesh
            is left behind in that case.
    """
    if not isfinite(diameter) or diameter <= 0:
        raise ValueError("Vent diameter must be finite and positive")
    if (
        not all(isfinite(v) for v in normal)
        or normal.length_squared < _MIN_NORMAL_LENGTH_SQUARED
    ):
        raise ValueError("Drawing plane needs a nonzero normal")
    if not paths or any(len(path) < 2 for path in paths):
        raise ValueError("Draw at least two points per vent")
    normal = normal.normalized()
    origin = paths[0][0]
    radius = diameter / 2
    epsilon = diameter * _COINCIDENT_FRACTION
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    for path in paths:
        points = _clean_vent_path(path, normal, origin, epsilon)
        sides = _vent_sides(points, normal, radius, epsilon)
        _append_tube(vertices, faces, points, sides, normal, radius)
    mesh = bpy.data.meshes.new(name)
    try:
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
    except Exception:
        # Roll back the datablock whatever went wrong, then re-raise.
        bpy.data.meshes.remove(mesh)
        raise
    return mesh


def add_air_vent_cutters(
    targets: Sequence[bpy.types.Object], cutter: bpy.types.Object
) -> list[bpy.types.BooleanModifier]:
    """Subtract one shared cutter from every target.

    Args:
        targets: Mesh objects to cut; duplicates are ignored.
        cutter: The vent mesh object used as every Boolean operand.

    Returns:
        The added modifiers, in target order.

    Raises:
        ValueError: If there are no targets, or a target or the cutter is not
            an editable mesh distinct from the cutter. Nothing is modified.
    """
    targets = tuple(dict.fromkeys(targets))
    if cutter.type != "MESH" or not targets:
        raise ValueError("Choose mesh targets and a mesh vent cutter")
    for target in targets:
        if target == cutter or target.type != "MESH" or not target.is_editable:
            raise ValueError(f"Cannot add air vents to {target.name}")
    created: list[tuple[bpy.types.Object, bpy.types.BooleanModifier]] = []
    try:
        for target in targets:
            modifier = cast(
                bpy.types.BooleanModifier,
                target.modifiers.new(name=_CUTTER_MODIFIER_NAME, type="BOOLEAN"),
            )
            created.append((target, modifier))
            modifier.operation = "DIFFERENCE"
            modifier.solver = "EXACT"
            modifier.use_self = True
            modifier.object = cutter
    except Exception:
        # Leave every target untouched whatever went wrong, then re-raise.
        for target, modifier in reversed(created):
            target.modifiers.remove(modifier)
        raise
    return [modifier for _, modifier in created]
