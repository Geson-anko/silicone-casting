"""Operator registration and cleanup for active tools."""

from . import (
    boolean_modifier,
    color_simulator,
    copy_value,
    draw_air_vents,
    draw_surface_cut,
    export_stl,
    inherit_shape,
    key_editing,
    key_placement,
    measure_volume,
    mixture_parts,
    recipe_io,
    separate_loose_parts,
    solidify,
)

CLASSES = (
    key_editing.SILCAST_OT_edit_registration_key,
    key_editing.SILCAST_OT_delete_registration_key,
    key_placement.SILCAST_OT_start_key_placement,
    key_placement.SILCAST_OT_stop_key_placement,
    key_placement.SILCAST_OT_place_key,
    boolean_modifier.SILCAST_OT_add_boolean,
    boolean_modifier.SILCAST_OT_add_surface_cut,
    draw_surface_cut.SILCAST_OT_draw_surface_cut,
    draw_air_vents.SILCAST_OT_draw_air_vents,
    draw_surface_cut.SILCAST_OT_edit_cutting_surface,
    solidify.SILCAST_OT_solidify,
    solidify.SILCAST_OT_apply_solidify,
    measure_volume.SILCAST_OT_measure_volume,
    copy_value.SILCAST_OT_copy_value,
    export_stl.SILCAST_OT_export_stl,
    recipe_io.SILCAST_OT_export_recipes,
    recipe_io.SILCAST_OT_import_recipes,
    inherit_shape.SILCAST_OT_inherit_shape,
    separate_loose_parts.SILCAST_OT_separate_loose_parts,
    mixture_parts.SILCAST_OT_add_mixture_part,
    mixture_parts.SILCAST_OT_remove_mixture_parts,
    mixture_parts.SILCAST_OT_move_mixture_parts,
    mixture_parts.SILCAST_OT_select_mixture_part,
    color_simulator.SILCAST_OT_add_color_profile,
    color_simulator.SILCAST_OT_remove_color_profile,
    color_simulator.SILCAST_OT_add_colorant,
    color_simulator.SILCAST_OT_remove_colorant,
    color_simulator.SILCAST_OT_copy_mixture_volume_to_coloring,
    color_simulator.SILCAST_OT_apply_color_material,
)


def cancel_active_tools() -> None:
    """Release previews and event handlers before unregistering their types."""
    key_placement.cancel_key_gesture()
    draw_surface_cut.cancel_surface_drawing()
    draw_air_vents.cancel_air_vent_drawing()
