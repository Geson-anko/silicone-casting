"""Split one mesh object into objects for its disconnected components."""

from typing import cast

# The PyPI `bpy` wheel registers `bmesh` from inside bpy's C initialiser.
# Keep this order fixed for the tier-1 environment.
# isort: off
import bpy
import bmesh

# isort: on


def _vertex_components(mesh: bpy.types.Mesh) -> tuple[frozenset[int], ...]:
    """Return connected vertex-index sets in source order."""
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        seen: set[int] = set()
        components: list[frozenset[int]] = []

        for start in bm.verts:
            if start.index in seen:
                continue
            component: set[int] = set()
            stack = [start]
            while stack:
                vertex = stack.pop()
                if vertex.index in seen:
                    continue
                seen.add(vertex.index)
                component.add(vertex.index)
                stack.extend(edge.other_vert(vertex) for edge in vertex.link_edges)
            components.append(frozenset(component))
        return tuple(components)
    finally:
        bm.free()


def _copy_component(
    source: bpy.types.Mesh, vertex_indices: frozenset[int]
) -> bpy.types.Mesh:
    """Copy *source* while retaining only one connected component."""
    part = source.copy()
    bm = bmesh.new()
    try:
        bm.from_mesh(part)
        bm.verts.ensure_lookup_table()
        removed: list[bmesh.types.BMVert | bmesh.types.BMEdge | bmesh.types.BMFace] = [
            vertex for vertex in bm.verts if vertex.index not in vertex_indices
        ]
        bmesh.ops.delete(bm, geom=removed, context="VERTS")
        bm.to_mesh(part)
        part.update()
    finally:
        bm.free()
    return part


def separate_loose_parts(
    obj: bpy.types.Object,
) -> tuple[bpy.types.Object, ...]:
    """Separate every disconnected component of one mesh object.

    The original object keeps the first component. Additional objects copy
    its object-level settings and are linked to every collection containing
    the original. A mesh with zero or one component is returned unchanged.

    Args:
        obj: Mesh object whose base mesh should be separated.

    Returns:
        The original object followed by any newly created objects.

    Raises:
        ValueError: If *obj* is not a mesh object.
    """
    if obj.type != "MESH":
        raise ValueError(f"{obj.name!r} is not a mesh object")

    source = cast(bpy.types.Mesh, obj.data)
    components = _vertex_components(source)
    if len(components) <= 1:
        return (obj,)

    part_meshes: list[bpy.types.Mesh] = []
    try:
        part_meshes.extend(
            _copy_component(source, component) for component in components
        )
    except Exception:
        # Cleanup only: whatever failed, drop the partial copies and re-raise.
        for mesh in part_meshes:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        raise

    source_name = source.name
    was_selected = obj.select_get()
    collections = tuple(obj.users_collection)
    obj.data = part_meshes[0]
    parts = [obj]

    for mesh in part_meshes[1:]:
        part = obj.copy()
        part.data = mesh
        for collection in collections:
            collection.objects.link(part)
        part.select_set(was_selected)
        parts.append(part)

    if source.users == 0:
        bpy.data.meshes.remove(source)
        part_meshes[0].name = source_name

    return tuple(parts)
