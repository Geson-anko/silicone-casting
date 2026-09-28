"""Closed circular tubes along planar paths and shared Boolean cutters."""

from collections.abc import Sequence
from math import cos, isfinite, pi, sin
from typing import cast

import bpy
from mathutils import Vector


def simplify_vent_path(points: Sequence[Vector], tolerance: float) -> list[Vector]:
    """Remove drawing noise within a distance tolerance, keeping endpoints."""
    if len(points) < 3:
        return [point.copy() for point in points]
    keep = {0, len(points) - 1}
    pending = [(0, len(points) - 1)]
    while pending:
        start, end = pending.pop()
        line = points[end] - points[start]
        length_squared = line.length_squared
        farthest, distance = start, tolerance
        for i in range(start + 1, end):
            factor = (
                min(
                    1.0,
                    max(0.0, (points[i] - points[start]).dot(line) / length_squared),
                )
                if length_squared > 0
                else 0.0
            )
            error = (points[i] - (points[start] + line * factor)).length
            if error > distance:
                farthest, distance = i, error
        if farthest != start:
            keep.add(farthest)
            pending.extend(((start, farthest), (farthest, end)))
    return [points[i].copy() for i in sorted(keep)]


def smooth_vent_path(points: Sequence[Vector]) -> list[Vector]:
    """Round polyline corners with two corner-cutting passes, keeping ends."""
    result = [point.copy() for point in points]
    if len(result) < 3:
        return result
    for _ in range(2):
        previous = result
        result = [previous[0]]
        for a, b in zip(previous, previous[1:], strict=False):
            result.extend((a.lerp(b, 0.25), a.lerp(b, 0.75)))
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
        if abs((point - origin).dot(normal)) > max(epsilon, 1e-7):
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
    for i in range(len(points)):
        before = directions[max(0, i - 1)]
        after = directions[min(i, len(directions) - 1)]
        tangent = (before + after).normalized()
        alignment = tangent.dot(after)
        if alignment < 1e-3:
            raise ValueError("A vent cannot double back; smooth the bend")
        sides.append(cast(Vector, tangent.cross(normal)) / alignment)
    for i, direction in enumerate(directions):
        overlap = radius * abs((sides[i + 1] - sides[i]).dot(direction))
        if (points[i + 1] - points[i]).length <= overlap + epsilon:
            raise ValueError("Bend too tight: smooth the line or reduce Diameter")
    return sides


def create_air_vent_mesh(
    name: str,
    paths: Sequence[Sequence[Vector]],
    normal: Vector,
    diameter: float,
) -> bpy.types.Mesh:
    """Sweep capped 64-sided tubes, with mitred joins preserving diameter.

    All coordinates are in one world-space plane. Tight bends that fold
    neighboring rings through each other are rejected before allocating
    data. Separate paths may intersect: the Exact Boolean uses self
    intersection handling when subtracting the shared cutter.
    """
    if not isfinite(diameter) or diameter <= 0:
        raise ValueError("Vent diameter must be finite and positive")
    if not all(isfinite(v) for v in normal) or normal.length_squared < 1e-20:
        raise ValueError("Drawing plane needs a nonzero normal")
    if not paths or any(len(path) < 2 for path in paths):
        raise ValueError("Draw at least two points per vent")
    normal = normal.normalized()
    origin = paths[0][0]
    radius = diameter / 2
    epsilon = diameter * 1e-6
    count = 64
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    for path in paths:
        points = _clean_vent_path(path, normal, origin, epsilon)
        sides = _vent_sides(points, normal, radius, epsilon)
        base = len(vertices)
        for point, side in zip(points, sides, strict=True):
            for i in range(count):
                angle = 2 * pi * i / count
                vertex = point + radius * (normal * cos(angle) + side * sin(angle))
                vertices.append((vertex.x, vertex.y, vertex.z))
        faces.append(tuple(base + i for i in reversed(range(count))))
        for ring in range(len(points) - 1):
            for i in range(count):
                a = base + ring * count + i
                b = base + ring * count + (i + 1) % count
                faces.append((a, b, b + count, a + count))
        last = base + (len(points) - 1) * count
        faces.append(tuple(last + i for i in range(count)))
    mesh = bpy.data.meshes.new(name)
    try:
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
    except Exception:
        bpy.data.meshes.remove(mesh)
        raise
    return mesh


def add_air_vent_cutters(
    targets: Sequence[bpy.types.Object], cutter: bpy.types.Object
) -> list[bpy.types.BooleanModifier]:
    """Subtract one shared cutter from every target, rolling back on
    failure."""
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
                target.modifiers.new(name="Air Vents", type="BOOLEAN"),
            )
            created.append((target, modifier))
            modifier.operation = "DIFFERENCE"
            modifier.solver = "EXACT"
            modifier.use_self = True
            modifier.object = cutter
    except Exception:
        for target, modifier in reversed(created):
            target.modifiers.remove(modifier)
        raise
    return [modifier for _, modifier in created]
