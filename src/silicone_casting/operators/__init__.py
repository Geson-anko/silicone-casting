"""Operators exposed by the add-on."""

from .boolean_modifier import SILCAST_OT_add_boolean, SILCAST_OT_add_surface_cut
from .color_simulator import (
    SILCAST_OT_add_color_profile,
    SILCAST_OT_add_colorant,
    SILCAST_OT_apply_color_material,
    SILCAST_OT_copy_mixture_volume_to_coloring,
    SILCAST_OT_remove_color_profile,
    SILCAST_OT_remove_colorant,
)
from .copy_value import SILCAST_OT_copy_value
from .draw_air_vents import SILCAST_OT_draw_air_vents, cancel_air_vent_drawing
from .draw_surface_cut import (
    SILCAST_OT_draw_surface_cut,
    SILCAST_OT_edit_cutting_surface,
    cancel_surface_drawing,
)
from .export_stl import SILCAST_OT_export_stl
from .inherit_shape import SILCAST_OT_inherit_shape
from .key_editing import (
    SILCAST_OT_add_registration_key,
    SILCAST_OT_delete_registration_key,
    SILCAST_OT_edit_registration_key,
    SILCAST_OT_move_registration_key,
)
from .key_placement import (
    SILCAST_OT_place_key,
    SILCAST_OT_start_key_placement,
    SILCAST_OT_stop_key_placement,
    SILCAST_WST_registration_keys,
    cancel_key_gesture,
)
from .measure_volume import SILCAST_OT_measure_volume
from .mixture_parts import (
    SILCAST_OT_add_mixture_part,
    SILCAST_OT_move_mixture_parts,
    SILCAST_OT_remove_mixture_parts,
    SILCAST_OT_select_mixture_part,
)
from .recipe_io import SILCAST_OT_export_recipes, SILCAST_OT_import_recipes
from .registration_keys import (
    SILCAST_OT_cancel_registration_key,
    SILCAST_OT_commit_registration_key,
    SILCAST_OT_preview_registration_key,
)
from .separate_loose_parts import SILCAST_OT_separate_loose_parts
from .solidify import SILCAST_OT_apply_solidify, SILCAST_OT_solidify

__all__ = [
    "SILCAST_OT_add_registration_key",
    "SILCAST_OT_move_registration_key",
    "SILCAST_OT_edit_registration_key",
    "SILCAST_OT_delete_registration_key",
    "SILCAST_OT_start_key_placement",
    "SILCAST_OT_stop_key_placement",
    "SILCAST_OT_place_key",
    "SILCAST_WST_registration_keys",
    "cancel_key_gesture",
    "SILCAST_OT_preview_registration_key",
    "SILCAST_OT_commit_registration_key",
    "SILCAST_OT_cancel_registration_key",
    "SILCAST_OT_export_recipes",
    "SILCAST_OT_import_recipes",
    "SILCAST_OT_add_boolean",
    "SILCAST_OT_add_color_profile",
    "SILCAST_OT_add_colorant",
    "SILCAST_OT_add_surface_cut",
    "SILCAST_OT_apply_solidify",
    "SILCAST_OT_apply_color_material",
    "SILCAST_OT_add_mixture_part",
    "SILCAST_OT_copy_value",
    "SILCAST_OT_copy_mixture_volume_to_coloring",
    "SILCAST_OT_export_stl",
    "SILCAST_OT_draw_surface_cut",
    "SILCAST_OT_draw_air_vents",
    "cancel_air_vent_drawing",
    "SILCAST_OT_edit_cutting_surface",
    "SILCAST_OT_inherit_shape",
    "SILCAST_OT_measure_volume",
    "SILCAST_OT_move_mixture_parts",
    "SILCAST_OT_remove_color_profile",
    "SILCAST_OT_remove_colorant",
    "SILCAST_OT_remove_mixture_parts",
    "SILCAST_OT_select_mixture_part",
    "SILCAST_OT_separate_loose_parts",
    "SILCAST_OT_solidify",
    "cancel_surface_drawing",
]
