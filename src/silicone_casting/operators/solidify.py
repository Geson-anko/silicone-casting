"""Operators that add, update, and bake the add-on's Solidify modifier."""

from typing import override

import bpy

from ..core.solidify import apply_solidify, ensure_solidify, find_solidify
from ..core.units import mm_to_units
from ..properties.settings import scene_settings
from ._operator import OperatorReturn, selected_meshes


class SILCAST_OT_solidify(bpy.types.Operator):
    """Add or update the add-on's Solidify modifier on every selected mesh."""

    bl_idname = "silicone_casting.solidify"
    bl_label = "Solidify"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT" and bool(selected_meshes(context))

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        props = scene_settings(context)
        thickness = mm_to_units(
            props.solidify_thickness_mm,
            context.scene.unit_settings.scale_length,
        )
        objects = selected_meshes(context)
        for obj in objects:
            ensure_solidify(
                obj,
                thickness,
                flip=props.solidify_flip,
                even_thickness=props.solidify_even_thickness,
            )

        self.report({"INFO"}, f"Solidified {len(objects)} object(s)")
        return {"FINISHED"}


class SILCAST_OT_apply_solidify(bpy.types.Operator):
    """Bake the add-on's Solidify modifier into every selected mesh."""

    bl_idname = "silicone_casting.apply_solidify"
    # Spelled out because the F3 search menu shows the label on its own,
    # where a bare "Apply" says nothing about what is applied.
    bl_label = "Apply Solidify"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT" and any(
            find_solidify(obj) is not None for obj in selected_meshes(context)
        )

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        depsgraph = context.evaluated_depsgraph_get()
        applied = 0
        for obj in selected_meshes(context):
            try:
                apply_solidify(obj, depsgraph)
            except ValueError as exc:
                # `core.apply_solidify` already names the object in its
                # message, so prefixing it here would repeat the name.
                self.report({"WARNING"}, str(exc))
                continue
            applied += 1

        if applied == 0:
            return {"CANCELLED"}

        self.report({"INFO"}, f"Applied to {applied} object(s)")
        return {"FINISHED"}
