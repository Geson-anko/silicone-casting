"""Small screen-space markers for the current snapping candidate."""

from collections.abc import Sequence

import gpu

# Blender's stub leaves the optional indices argument untyped.
from gpu_extras.batch import (
    batch_for_shader,  # pyright: ignore[reportUnknownVariableType]
)
from mathutils import Vector


def draw_snap_hint(points: Sequence[Vector]) -> None:
    """Highlight a vertex with a cross, or an edge with endpoint crosses."""
    lines: list[tuple[float, float]] = []
    for point in points:
        lines.extend(
            (
                (point.x - 5, point.y),
                (point.x + 5, point.y),
                (point.x, point.y - 5),
                (point.x, point.y + 5),
            )
        )
    if len(points) == 2:
        lines.extend((point.x, point.y) for point in points)
    if lines:
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        batch = batch_for_shader(shader, "LINES", {"pos": lines})
        shader.bind()
        shader.uniform_float("color", (1.0, 0.6, 0.05, 1.0))
        batch.draw(shader)
