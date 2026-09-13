"""RNA distance inputs backed by physical millimetres."""

from typing import cast

import bpy
from bpy.props import FloatProperty

from ..core.units import mm_to_units


def distance_property(mm_field: str, name: str, description: str = "") -> object:
    """Expose stored millimetres in the owning scene's distance units."""

    def get_distance(settings: bpy.types.PropertyGroup) -> float:
        scene = cast(bpy.types.Scene, settings.id_data)
        return mm_to_units(
            cast(float, getattr(settings, mm_field)),
            scene.unit_settings.scale_length,
        )

    def set_distance(settings: bpy.types.PropertyGroup, value: float) -> None:
        scene = cast(bpy.types.Scene, settings.id_data)
        setattr(settings, mm_field, value * scene.unit_settings.scale_length * 1000)

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
