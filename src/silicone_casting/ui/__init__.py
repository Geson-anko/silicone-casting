"""View registration; persistent state belongs to properties."""

from . import color, mixture, sidebar

CLASSES = (
    mixture.SILCAST_UL_mixture_parts,
    color.SILCAST_UL_color_profiles,
    color.SILCAST_UL_colorants,
    sidebar.SILCAST_PT_main,
    sidebar.SILCAST_PT_measurement,
    mixture.SILCAST_PT_mixture_calculator,
    color.SILCAST_PT_color_simulator,
    sidebar.SILCAST_PT_coloring,
    sidebar.SILCAST_PT_processing,
)
