"""Surface-constrained straight segments and stroke smoothing."""

from collections.abc import Callable, Sequence
from math import ceil
from typing import Final

from mathutils import Vector
from mathutils.bvhtree import BVHTree

# Screen pixels between samples of a straight segment: dense enough to follow
# surface bends without sampling every pixel.
_SEGMENT_SAMPLE_SPACING: Final = 3
# Passes of the 1-2-1 smoothing kernel. Each pass is snapped back onto the
# surface, so a few passes soften hand jitter without shrinking the stroke.
_SMOOTHING_PASSES: Final = 8


def project_straight_segment(
    start: Vector,
    end: Vector,
    project: Callable[[Vector], Vector | None],
    max_gap: float,
) -> list[Vector]:
    """Sample a screen-space line onto the surface.

    Args:
        start: Segment start in screen pixels.
        end: Segment end in screen pixels.
        project: Maps a pixel to its surface hit, or None on a miss.
        max_gap: Largest allowed distance between consecutive hits.

    Returns:
        Surface points from *start* to *end*, both included.

    Raises:
        ValueError: If a sample misses the surface or jumps across a gap.
    """
    count = max(1, ceil((end - start).length / _SEGMENT_SAMPLE_SPACING))
    points: list[Vector] = []
    for step in range(count + 1):
        point = project(start.lerp(end, step / count))
        if point is None:
            raise ValueError("The straight line must stay on the visible mesh")
        if points and (point - points[-1]).length > max_gap:
            raise ValueError("The straight line cannot jump across the mesh")
        points.append(point)
    return points


def smooth_surface_stroke(
    points: Sequence[Vector], surface: BVHTree, *, closed: bool
) -> list[Vector]:
    """Soften a stroke while keeping it on the surface.

    Args:
        points: Stroke points on *surface*. Not modified.
        surface: Surface each smoothed point is snapped back onto.
        closed: Whether the stroke wraps around. Open strokes keep their
            endpoints fixed.

    Returns:
        New smoothed points, one per input point.

    Raises:
        ValueError: If a smoothed point cannot be snapped onto the surface.
    """
    result = [point.copy() for point in points]
    if len(result) < 3:
        return result
    for _ in range(_SMOOTHING_PASSES):
        previous = result
        result = [point.copy() for point in previous]
        indices = range(len(previous)) if closed else range(1, len(previous) - 1)
        for index in indices:
            average = (
                previous[index] * 0.5
                + previous[index - 1] * 0.25
                + previous[(index + 1) % len(previous)] * 0.25
            )
            point, _, _, _ = surface.find_nearest(average)
            if point is None:
                raise ValueError("Could not smooth the stroke on the mesh")
            result[index] = point
    return result
