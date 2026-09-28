"""World-space volume of evaluated mesh objects.

Volume is only defined for a closed surface, so every function here
refuses to produce a number for a mesh that is not watertight rather
than returning the meaningless value ``calc_volume`` would give for an
open one. Measuring is strictly read-only: objects, meshes and the
scene are left exactly as they were found.

Like the rest of ``core``, this module stays on the data API -- no
``bpy.ops``, no ``Depsgraph.update()``, and no user-facing wording. The
caller receives object *names* and decides how to phrase them.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Self

# The PyPI `bpy` wheel registers `bmesh` as a builtin module from inside
# bpy's own C initialiser, so a bare `import bmesh` raises
# ModuleNotFoundError in a fresh interpreter; inside Blender both are
# always present. isort would sort `bmesh` ahead of `bpy` and break the
# tier-1 suite, so the order is pinned here.
# isort: off
import bpy
import bmesh

# isort: on


@dataclass(frozen=True)
class VolumeSummary:
    """Outcome of measuring a group of objects.

    Both halves of the outcome travel together because the caller needs
    them together: the names are what an error message is built from,
    and the count is what a success message reports.
    """

    #: Summed world-space volume of the objects that could be measured,
    #: in cubic Blender units. Zero when nothing was measured.
    volume: float
    #: Number of objects whose volume could be measured.
    measured_count: int
    #: Names of the mesh objects that were not watertight, in the order
    #: they were encountered.
    non_watertight_names: tuple[str, ...]

    @classmethod
    def from_objects(
        cls, objects: Iterable[bpy.types.Object], depsgraph: bpy.types.Depsgraph
    ) -> Self:
        """Measure a group, collecting volumes and non-watertight object names.

        Non-mesh objects are skipped silently and counted nowhere. Meshes that
        are not watertight contribute their name instead of a number, which lets
        the caller refuse to report a partial total.

        Args:
            objects: Objects to walk once. May contain non-mesh objects, so a
                selection can be passed straight through. Each element must
                be linked into the view layer.
            depsgraph: Dependency graph shared by every measurement.
        """
        volume = 0.0
        measured_count = 0
        non_watertight_names: list[str] = []
        for obj in objects:
            if obj.type != "MESH":
                continue
            measured = world_volume(obj, depsgraph)
            if measured is None:
                non_watertight_names.append(obj.name)
                continue
            volume += measured
            measured_count += 1
        return cls(
            volume=volume,
            measured_count=measured_count,
            non_watertight_names=tuple(non_watertight_names),
        )


def world_volume(obj: bpy.types.Object, depsgraph: bpy.types.Depsgraph) -> float | None:
    """Return the world-space volume of *obj* after modifier evaluation.

    The volume is measured on the temporary mesh Blender evaluates for
    the viewport, so modifiers -- the addon's Solidify among them --
    are included, while a modifier with ``show_viewport`` off is not.
    Local volume is converted to world space by multiplying with the
    absolute determinant of the object's linear transform, which is
    exact for an affine transform and, unlike transforming every vertex
    first, costs nothing per vertex and loses less precision. Taking the
    absolute value is what keeps a mirrored (negatively scaled) object
    from reporting a negative volume.

    Args:
        obj: Object to measure. Must be a mesh object and must be linked
            into the view layer, since the result comes from evaluating
            it -- both are the caller's responsibility.
        depsgraph: Dependency graph to evaluate against, typically
            ``context.evaluated_depsgraph_get()``.

    Returns:
        The volume in cubic Blender units, always non-negative, or
        ``None`` when the evaluated mesh is not watertight and therefore
        has no volume. A mesh without any edges at all satisfies the
        condition vacuously and measures 0.0.
    """
    evaluated = obj.evaluated_get(depsgraph)
    bm = bmesh.new()
    try:
        # `to_mesh()` leaves the mesh owned by the evaluated object instead of
        # registering it in `bpy.data.meshes` the way `core.solidify` has to,
        # so measuring cannot leave an orphan datablock behind in the .blend.
        bm.from_mesh(evaluated.to_mesh())
        # Watertight means every edge is shared by exactly two faces,
        # which rules out boundary edges (fewer than two) and
        # non-manifold ones (more than two) in a single pass.
        if any(len(edge.link_faces) != 2 for edge in bm.edges):
            return None
        # calc_volume defaults to signed=False, so the shell of a
        # solidified object -- an outer part plus an inward-facing inner
        # part -- yields the volume of the wall between them.
        return bm.calc_volume() * abs(obj.matrix_world.to_3x3().determinant())
    finally:
        # Both releases also run on the early return above, and
        # to_mesh_clear() is harmless even if to_mesh() never succeeded.
        bm.free()
        evaluated.to_mesh_clear()
