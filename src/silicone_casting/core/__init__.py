"""Mesh processing that does not depend on ``bpy.ops`` or an interactive
context."""

from .color_mixing import (
    RGB,
    CalibratedColorant,
    SimulatedSiliconeAppearance,
    format_hex_color,
    format_linear_rgb,
    linear_rgb_to_hsl,
    linear_rgb_to_srgb8,
    parse_hex_color,
    saturated_hsl_to_linear_rgb,
    simulate_silicone_appearance,
    simulate_silicone_color,
)
from .drawn_surface import interpolate_cutting_surface
from .mixture import MixtureBreakdown, calculate_mixture
from .separate_loose_parts import separate_loose_parts
from .solidify import (
    MIN_THICKNESS_MM,
    MODIFIER_NAME,
    apply_solidify,
    ensure_solidify,
    find_solidify,
)
from .surface_cut import (
    MIN_SURFACE_CUT_THICKNESS_MM,
    SURFACE_CUT_MODIFIER_NAME,
    create_surface_cut,
)
from .units import cubic_units_to_ml, format_grams, format_ml, mm_to_units
from .volume import VolumeSummary, total_volume, world_volume

__all__ = [
    "CalibratedColorant",
    "MIN_THICKNESS_MM",
    "MIN_SURFACE_CUT_THICKNESS_MM",
    "MixtureBreakdown",
    "MODIFIER_NAME",
    "RGB",
    "SimulatedSiliconeAppearance",
    "SURFACE_CUT_MODIFIER_NAME",
    "VolumeSummary",
    "apply_solidify",
    "calculate_mixture",
    "cubic_units_to_ml",
    "create_surface_cut",
    "ensure_solidify",
    "find_solidify",
    "format_hex_color",
    "format_grams",
    "format_linear_rgb",
    "format_ml",
    "linear_rgb_to_hsl",
    "linear_rgb_to_srgb8",
    "mm_to_units",
    "interpolate_cutting_surface",
    "parse_hex_color",
    "separate_loose_parts",
    "saturated_hsl_to_linear_rgb",
    "simulate_silicone_appearance",
    "simulate_silicone_color",
    "total_volume",
    "world_volume",
]
