"""Silicone Casting -- generate 3D-printable resin molds for silicone casting.

Packaged as a Blender Extension: metadata lives in
``blender_manifest.toml``, not in a ``bl_info`` dict.
"""

import bpy
from bpy.app.handlers import persistent

from .operators import (
    SILCAST_OT_add_boolean,
    SILCAST_OT_add_color_profile,
    SILCAST_OT_add_colorant,
    SILCAST_OT_add_mixture_part,
    SILCAST_OT_add_registration_key,
    SILCAST_OT_add_surface_cut,
    SILCAST_OT_apply_color_material,
    SILCAST_OT_apply_solidify,
    SILCAST_OT_cancel_registration_key,
    SILCAST_OT_commit_registration_key,
    SILCAST_OT_copy_mixture_volume_to_coloring,
    SILCAST_OT_copy_value,
    SILCAST_OT_delete_registration_key,
    SILCAST_OT_draw_air_vents,
    SILCAST_OT_draw_surface_cut,
    SILCAST_OT_edit_cutting_surface,
    SILCAST_OT_edit_registration_key,
    SILCAST_OT_export_recipes,
    SILCAST_OT_export_stl,
    SILCAST_OT_import_recipes,
    SILCAST_OT_inherit_shape,
    SILCAST_OT_measure_volume,
    SILCAST_OT_move_mixture_parts,
    SILCAST_OT_move_registration_key,
    SILCAST_OT_place_key,
    SILCAST_OT_preview_registration_key,
    SILCAST_OT_remove_color_profile,
    SILCAST_OT_remove_colorant,
    SILCAST_OT_remove_mixture_parts,
    SILCAST_OT_select_mixture_part,
    SILCAST_OT_separate_loose_parts,
    SILCAST_OT_solidify,
    SILCAST_OT_start_key_placement,
    SILCAST_OT_stop_key_placement,
    SILCAST_WST_registration_keys,
    cancel_air_vent_drawing,
    cancel_key_gesture,
    cancel_surface_drawing,
)
from .ui import (
    SILCAST_PT_color_simulator,
    SILCAST_PT_coloring,
    SILCAST_PT_main,
    SILCAST_PT_measurement,
    SILCAST_PT_mixture_calculator,
    SILCAST_PT_processing,
    SILCAST_UL_color_profiles,
    SILCAST_UL_colorants,
    SILCAST_UL_mixture_parts,
    SiliconeCastingColorant,
    SiliconeCastingColorProfile,
    SiliconeCastingMixturePart,
    SiliconeCastingProperties,
)

# The order matters: SILCAST_PT_main has to be registered before its child
# panels, because Blender resolves `bl_parent_id` at registration time and
# raises RuntimeError when the parent is not there yet, which would fail
# register() as a whole. The Scene pointer is attached after the loop, since
# PointerProperty needs SiliconeCastingProperties already registered.
_CLASSES = (
    SiliconeCastingColorant,
    SiliconeCastingColorProfile,
    SiliconeCastingMixturePart,
    SiliconeCastingProperties,
    SILCAST_OT_preview_registration_key,
    SILCAST_OT_commit_registration_key,
    SILCAST_OT_cancel_registration_key,
    SILCAST_OT_add_registration_key,
    SILCAST_OT_move_registration_key,
    SILCAST_OT_edit_registration_key,
    SILCAST_OT_delete_registration_key,
    SILCAST_OT_start_key_placement,
    SILCAST_OT_stop_key_placement,
    SILCAST_OT_place_key,
    SILCAST_OT_add_boolean,
    SILCAST_OT_add_surface_cut,
    SILCAST_OT_draw_surface_cut,
    SILCAST_OT_draw_air_vents,
    SILCAST_OT_edit_cutting_surface,
    SILCAST_OT_solidify,
    SILCAST_OT_apply_solidify,
    SILCAST_OT_measure_volume,
    SILCAST_OT_copy_value,
    SILCAST_OT_export_stl,
    SILCAST_OT_export_recipes,
    SILCAST_OT_import_recipes,
    SILCAST_OT_inherit_shape,
    SILCAST_OT_separate_loose_parts,
    SILCAST_OT_add_mixture_part,
    SILCAST_OT_remove_mixture_parts,
    SILCAST_OT_move_mixture_parts,
    SILCAST_OT_select_mixture_part,
    SILCAST_OT_add_color_profile,
    SILCAST_OT_remove_color_profile,
    SILCAST_OT_add_colorant,
    SILCAST_OT_remove_colorant,
    SILCAST_OT_copy_mixture_volume_to_coloring,
    SILCAST_OT_apply_color_material,
    SILCAST_UL_mixture_parts,
    SILCAST_UL_color_profiles,
    SILCAST_UL_colorants,
    SILCAST_PT_main,
    SILCAST_PT_measurement,
    SILCAST_PT_mixture_calculator,
    SILCAST_PT_color_simulator,
    SILCAST_PT_coloring,
    SILCAST_PT_processing,
)


#: Name of the scene attribute the settings are exposed under. Blender adds
#: it to the Scene RNA type at register time, so it is set and cleared with
#: setattr/delattr rather than as a static attribute.
_SCENE_ATTR = "silicone_casting"


@persistent
def _reset_transient_selection_state(_unused: object) -> None:
    """Clear transient UI-list state after loading a file."""
    for scene in bpy.data.scenes:
        props = getattr(scene, _SCENE_ATTR, None)
        if props is not None:
            props.mixture_selection_anchor = -1
            props.mixture_active_index = -1
            for profile in props.color_profiles:
                profile.colorant_active_index = -1


def register() -> None:
    """Register every class and attach the scene-level settings."""
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    setattr(
        bpy.types.Scene,
        _SCENE_ATTR,
        bpy.props.PointerProperty(type=SiliconeCastingProperties),
    )
    bpy.utils.register_tool(
        SILCAST_WST_registration_keys, after={"builtin.transform"}, separator=True
    )
    if _reset_transient_selection_state not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_reset_transient_selection_state)


def unregister() -> None:
    """Detach the scene-level settings and unregister every class."""
    cancel_key_gesture()
    bpy.utils.unregister_tool(SILCAST_WST_registration_keys)
    cancel_surface_drawing()
    cancel_air_vent_drawing()
    if _reset_transient_selection_state in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_reset_transient_selection_state)
    delattr(bpy.types.Scene, _SCENE_ATTR)
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
