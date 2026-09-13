"""Operator that bakes selected meshes into loose-part objects."""

from typing import cast, override

import bpy

from ..core import separate_loose_parts
from ._operator import OperatorReturn, selected_meshes


class SILCAST_OT_separate_loose_parts(bpy.types.Operator):
    """Bake each selected mesh and output one object per loose part."""

    bl_idname = "silicone_casting.separate_loose_parts"
    bl_label = "Separate Loose Parts"
    bl_description = (
        "Apply all modifiers to copies of the selected meshes, separate their "
        "loose parts beside the originals, and hide the originals"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT" and bool(selected_meshes(context))

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        objects = selected_meshes(context)
        generated: list[bpy.types.Object] = []
        for source in objects:
            mesh = _mesh_with_all_modifiers(context, source)

            baked = bpy.data.objects.new(source.name, mesh)
            baked.matrix_world = source.matrix_world.copy()
            for collection in source.users_collection:
                collection.objects.link(baked)
            parts = separate_loose_parts(baked)
            generated.extend(parts)

            source.select_set(False)
            source.hide_set(True)

        for part in generated:
            part.select_set(True)
        if generated:
            context.view_layer.objects.active = generated[0]

        self.report(
            {"INFO"},
            f"Baked {len(objects)} mesh(es) into {len(generated)} part(s)",
        )
        return {"FINISHED"}


def _mesh_with_all_modifiers(
    context: bpy.types.Context,
    source: bpy.types.Object,
) -> bpy.types.Mesh:
    """Copy the evaluated shape while restoring the source stack exactly."""
    visibility = [(modifier, modifier.show_viewport) for modifier in source.modifiers]
    try:
        for modifier, _was_visible in visibility:
            modifier.show_viewport = True
        context.view_layer.update()
        evaluated = source.evaluated_get(context.evaluated_depsgraph_get())
        mesh = bpy.data.meshes.new_from_object(evaluated)
    finally:
        for modifier, was_visible in visibility:
            modifier.show_viewport = was_visible
        context.view_layer.update()

    source_mesh = cast(bpy.types.Mesh, source.data)
    mesh.name = f"{source_mesh.name}.applied"
    # Evaluated meshes retain data-linked materials only. Bake object-level
    # overrides into the independent output so the separated parts keep
    # their visible colors, including deliberately empty material slots.
    for index, slot in enumerate(source.material_slots):
        if slot.link == "OBJECT":
            mesh.materials[index] = slot.material
    return mesh
