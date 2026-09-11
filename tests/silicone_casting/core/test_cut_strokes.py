"""Stroke editing retains surface contact and rejects gaps."""

import pytest
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from silicone_casting.core.cut_strokes import (
    project_straight_segment,
    smooth_surface_stroke,
)


def _surface():
    return BVHTree.FromPolygons(
        [(-100, -100, 0), (100, -100, 0), (100, 100, 100), (-100, 100, 0)],
        [(0, 1, 2), (0, 2, 3)],
    )


def test_screen_line_follows_a_bent_surface():
    surface = _surface()

    def project(p):
        return surface.ray_cast(Vector((p.x, p.y, 200)), Vector((0, 0, -1)))[0]

    points = project_straight_segment(Vector((-50, 0)), Vector((50, 0)), project, 5)
    assert points[0].x == pytest.approx(-50)
    assert points[-1].x == pytest.approx(50)
    assert all(abs(p.y) < 1e-6 for p in points)
    assert max(p.z for p in points) > min(p.z for p in points) + 20
    assert all(surface.find_nearest(p)[3] < 1e-4 for p in points)


@pytest.mark.parametrize("end,max_gap", [(Vector((150, 0)), 5), (Vector((50, 0)), 0.1)])
def test_straight_line_rejects_misses_and_jumps(end, max_gap):
    surface = _surface()

    def project(p):
        return surface.ray_cast(Vector((p.x, p.y, 200)), Vector((0, 0, -1)))[0]

    with pytest.raises(ValueError):
        project_straight_segment(Vector((-50, 0)), end, project, max_gap)


def test_smoothing_reduces_noise_preserves_endpoints_and_surface_contact():
    surface = _surface()
    points = [Vector((-50 + i * 10, 5 * (-1) ** i, 0)) for i in range(11)]
    points = [surface.find_nearest(p)[0] for p in points]
    before = [p.copy() for p in points]
    result = smooth_surface_stroke(points, surface, closed=False)
    assert result[0] == points[0]
    assert result[-1] == points[-1]
    assert sum((result[i + 1] - result[i]).length for i in range(10)) < sum(
        (points[i + 1] - points[i]).length for i in range(10)
    )
    assert all(surface.find_nearest(p)[3] < 1e-4 for p in result)
    assert points == before


def test_closed_smoothing_also_softens_the_seam():
    surface = _surface()
    points = [
        Vector((-40, -40, 0)),
        Vector((-20, -40, 0)),
        Vector((-20, -20, 0)),
        Vector((-40, -20, 0)),
    ]
    points = [surface.find_nearest(p)[0] for p in points]
    result = smooth_surface_stroke(points, surface, closed=True)
    assert all((a - b).length > 1 for a, b in zip(points, result, strict=True))
    assert all(surface.find_nearest(p)[3] < 1e-4 for p in result)
