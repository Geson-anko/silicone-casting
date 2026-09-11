"""Surface-constrained straight segments and stroke smoothing."""

from collections.abc import Callable, Sequence
from math import ceil

from mathutils import Vector
from mathutils.bvhtree import BVHTree


def project_straight_segment(
    start: Vector,
    end: Vector,
    project: Callable[[Vector], Vector | None],
    max_gap: float,
) -> list[Vector]:
    """Sample a screen line, rejecting missing hits and surface
    discontinuities."""
    count = max(1, ceil((end - start).length / 3))
    points: list[Vector] = []
    for i in range(count + 1):
        point = project(start.lerp(end, i / count))
        if point is None:
            raise ValueError("The straight line must stay on the visible mesh")
        if points and (point - points[-1]).length > max_gap:
            raise ValueError("The straight line cannot jump across the mesh")
        points.append(point)
    return points


def smooth_surface_stroke(
    points: Sequence[Vector], surface: BVHTree, *, closed: bool
) -> list[Vector]:
    """Soften a stroke on the surface, preserving open endpoints."""
    result = [point.copy() for point in points]
    if len(result) < 3:
        return result
    for _ in range(8):
        previous = result
        result = [point.copy() for point in previous]
        indices = range(len(previous)) if closed else range(1, len(previous) - 1)
        for i in indices:
            average = (
                previous[i] * 0.5
                + previous[i - 1] * 0.25
                + previous[(i + 1) % len(previous)] * 0.25
            )
            point, _, _, _ = surface.find_nearest(average)
            if point is None:
                raise ValueError("Could not smooth the stroke on the mesh")
            result[i] = point
    return result
