"""RNA distance inputs backed by physical millimetres."""

from typing import cast

import bpy
from bpy.props import FloatProperty

from ..core.units import mm_to_units, units_to_mm


def distance_property(mm_field: str, name: str, description: str = "") -> object:
    """Declare a scene-unit distance input stored in millimetres.

    The millimetre field is the saved source of truth, so a wall authored as
    3 mm stays 3 mm when the scene's unit scale changes; this property only
    re-expresses it in the scene's distance units for display and editing.

    Args:
        mm_field: Name of the sibling FloatProperty holding the millimetres.
        name: UI label of the distance input.
        description: Tooltip of the distance input.

    Returns:
        The FloatProperty declaration, for use as an RNA annotation.
    """

    def _scale_length(settings: bpy.types.PropertyGroup) -> float:
        return cast(bpy.types.Scene, settings.id_data).unit_settings.scale_length

    def get_distance(settings: bpy.types.PropertyGroup) -> float:
        mm = cast(float, getattr(settings, mm_field))
        return mm_to_units(mm, _scale_length(settings))

    def set_distance(settings: bpy.types.PropertyGroup, value: float) -> None:
        setattr(settings, mm_field, units_to_mm(value, _scale_length(settings)))

    return FloatProperty(
        name=name,
        description=description,
        subtype="DISTANCE",
        unit="LENGTH",
        min=0.0,
        precision=4,
        get=get_distance,
        set=set_distance,
    )
