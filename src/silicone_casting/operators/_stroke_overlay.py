"""Small screen-space markers for the current snapping candidate."""

from collections.abc import Sequence
from typing import Final

import gpu

# Blender's stub leaves the optional indices argument untyped.
from gpu_extras.batch import (
    batch_for_shader,  # pyright: ignore[reportUnknownVariableType]
)
from mathutils import Vector

_CROSS_HALF_SIZE_PX: Final = 5
# Orange stands out against both the gray mesh and Blender's selection colors.
_HINT_COLOR: Final = (1.0, 0.6, 0.05, 1.0)


def draw_snap_hint(points: Sequence[Vector]) -> None:
    """Highlight a vertex with a cross, or an edge with endpoint crosses."""
    size = _CROSS_HALF_SIZE_PX
    lines: list[tuple[float, float]] = []
    for point in points:
        lines.extend(
            (
                (point.x - size, point.y),
                (point.x + size, point.y),
                (point.x, point.y - size),
                (point.x, point.y + size),
            )
        )
    if len(points) == 2:
        lines.extend((point.x, point.y) for point in points)
    if not lines:
        return
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    batch = batch_for_shader(shader, "LINES", {"pos": lines})
    shader.bind()
    shader.uniform_float("color", _HINT_COLOR)
    batch.draw(shader)
