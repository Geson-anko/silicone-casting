"""Blender operators for color profiles, colorants, and material assignment."""

from typing import cast, override

import bpy

from ._color_adapter import (
    ColorProfileValues,
    ColorSimulatorSettings,
    active_color_profile,
)
from ._color_material import (
    ensure_color_preview_material,
    update_color_preview_material,
)
from ._operator import OperatorReturn, selected_meshes


def _color_settings(context: bpy.types.Context) -> ColorSimulatorSettings:
    return cast(ColorSimulatorSettings, context.scene.silicone_casting)


def _active_profile(context: bpy.types.Context) -> ColorProfileValues | None:
    return active_color_profile(_color_settings(context))


def _new_profile(settings: ColorSimulatorSettings) -> ColorProfileValues:
    """Append one profile and select it."""
    profile = settings.color_profiles.add()
    profile.profile_name = f"Profile {len(settings.color_profiles)}"
    profile.base_volume_ml = 100.0
    profile.base_color = (1.0, 1.0, 1.0)
    profile.transparency = 1.0
    profile.colorant_active_index = -1
    settings.color_profile_active_index = len(settings.color_profiles) - 1
    return profile


class SILCAST_OT_add_color_profile(bpy.types.Operator):
    """Add and select a named color profile."""

    bl_idname = "silicone_casting.add_color_profile"
    bl_label = "Add Color Profile"
    bl_options = {"REGISTER", "UNDO"}

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        profile = _new_profile(_color_settings(context))
        ensure_color_preview_material(profile)
        return {"FINISHED"}


class SILCAST_OT_remove_color_profile(bpy.types.Operator):
    """Remove the active profile without deleting its applied material."""

    bl_idname = "silicone_casting.remove_color_profile"
    bl_label = "Remove Color Profile"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        return _active_profile(context) is not None

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        settings = _color_settings(context)
        index = settings.color_profile_active_index
        settings.color_profiles.remove(index)
        settings.color_profile_active_index = min(
            index, len(settings.color_profiles) - 1
        )
        profile = active_color_profile(settings)
        if profile is not None:
            ensure_color_preview_material(profile)
        return {"FINISHED"}


class SILCAST_OT_add_colorant(bpy.types.Operator):
    """Add a zero-dose colorant to the active profile."""

    bl_idname = "silicone_casting.add_colorant"
    bl_label = "Add Colorant"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        return _active_profile(context) is not None

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        profile = _active_profile(context)
        if profile is None:
            return {"CANCELLED"}
        colorant = profile.colorants.add()
        colorant.enabled = True
        colorant.colorant_name = "Colorant"
        colorant.calibration_hue_degrees = 0.0
        colorant.calibration_lightness_percent = 50.0
        colorant.calibration_drops_per_ml = 1.0
        colorant.drops = 0.0
        profile.colorant_active_index = len(profile.colorants) - 1
        update_color_preview_material(profile)
        return {"FINISHED"}


class SILCAST_OT_remove_colorant(bpy.types.Operator):
    """Remove the active colorant from the active profile."""

    bl_idname = "silicone_casting.remove_colorant"
    bl_label = "Remove Colorant"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        profile = _active_profile(context)
        return profile is not None and 0 <= profile.colorant_active_index < len(
            profile.colorants
        )

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        profile = _active_profile(context)
        if profile is None:
            return {"CANCELLED"}
        index = profile.colorant_active_index
        profile.colorants.remove(index)
        profile.colorant_active_index = min(index, len(profile.colorants) - 1)
        update_color_preview_material(profile)
        return {"FINISHED"}


class SILCAST_OT_copy_mixture_volume_to_coloring(bpy.types.Operator):
    """Copy the enabled Mixture Calculator total to the active profile."""

    bl_idname = "silicone_casting.copy_mixture_volume_to_coloring"
    bl_label = "Use Mixture Total"
    bl_options = {"REGISTER", "UNDO"}

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        settings = _color_settings(context)
        profile = active_color_profile(settings)
        if profile is None:
            return {"CANCELLED"}
        total = sum(part.volume_ml for part in settings.mixture_parts if part.enabled)
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
        profile = _active_profile(context)
        return (
            context.mode == "OBJECT"
            and profile is not None
            and bool(selected_meshes(context))
        )

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        profile = _active_profile(context)
        if profile is None:
            return {"CANCELLED"}
        material = ensure_color_preview_material(profile)
        objects = selected_meshes(context)
        for obj in objects:
            mesh = cast(bpy.types.Mesh, obj.data)
            if len(mesh.materials) == 0:
                mesh.materials.append(material)
            else:
                obj.active_material = material
        self.report({"INFO"}, f"Applied to {len(objects)} object(s)")
        return {"FINISHED"}
