"""Blender operators for color profiles, colorants, and material assignment."""

from typing import cast, override

import bpy

from ..properties.settings import scene_settings
from ._operator import OperatorReturn, selected_meshes


class SILCAST_OT_add_color_profile(bpy.types.Operator):
    """Add and select a named color profile."""

    bl_idname = "silicone_casting.add_color_profile"
    bl_label = "Add Color Profile"
    bl_options = {"REGISTER", "UNDO"}

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        scene_settings(context).add_color_profile()
        return {"FINISHED"}


class SILCAST_OT_remove_color_profile(bpy.types.Operator):
    """Remove the active profile without deleting its applied material."""

    bl_idname = "silicone_casting.remove_color_profile"
    bl_label = "Remove Color Profile"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        return scene_settings(context).active_color_profile() is not None

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        removed = scene_settings(context).remove_active_color_profile()
        return {"FINISHED"} if removed else {"CANCELLED"}


class SILCAST_OT_add_colorant(bpy.types.Operator):
    """Add a zero-dose colorant to the active profile."""

    bl_idname = "silicone_casting.add_colorant"
    bl_label = "Add Colorant"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        return scene_settings(context).active_color_profile() is not None

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        profile = scene_settings(context).active_color_profile()
        if profile is None:
            return {"CANCELLED"}
        profile.add_colorant()
        return {"FINISHED"}


class SILCAST_OT_remove_colorant(bpy.types.Operator):
    """Remove the active colorant from the active profile."""

    bl_idname = "silicone_casting.remove_colorant"
    bl_label = "Remove Colorant"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        profile = scene_settings(context).active_color_profile()
        return profile is not None and profile.active_colorant() is not None

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        profile = scene_settings(context).active_color_profile()
        if profile is None:
            return {"CANCELLED"}
        profile.remove_active_colorant()
        return {"FINISHED"}


class SILCAST_OT_copy_mixture_volume_to_coloring(bpy.types.Operator):
    """Copy the enabled Mixture Calculator total to the active profile."""

    bl_idname = "silicone_casting.copy_mixture_volume_to_coloring"
    bl_label = "Use Mixture Total"
    bl_options = {"REGISTER", "UNDO"}

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        settings = scene_settings(context)
        profile = settings.active_color_profile()
        if profile is None:
            return {"CANCELLED"}
        total = settings.mixture.total_volume()
        if total <= 0.0:
            self.report({"ERROR"}, "Mixture total must be greater than zero")
            return {"CANCELLED"}
        profile.base_volume_ml = total
        return {"FINISHED"}


class SILCAST_OT_apply_color_material(bpy.types.Operator):
    """Assign the active profile's shared material to selected meshes."""

    bl_idname = "silicone_casting.apply_color_material"
    bl_label = "Apply to Selected"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        profile = scene_settings(context).active_color_profile()
        return (
            context.mode == "OBJECT"
            and profile is not None
            and bool(selected_meshes(context))
        )

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        profile = scene_settings(context).active_color_profile()
        if profile is None:
            return {"CANCELLED"}
        material = profile.ensure_preview_material()
        objects = selected_meshes(context)
        for obj in objects:
            mesh = cast(bpy.types.Mesh, obj.data)
            if len(mesh.materials) == 0:
                mesh.materials.append(material)
            else:
                obj.active_material = material
        self.report({"INFO"}, f"Applied to {len(objects)} object(s)")
        return {"FINISHED"}
