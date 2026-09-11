"""Color profile RNA types and their synchronized derived values."""

from collections.abc import Sequence
from typing import Protocol, cast

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

from ..core import (
    RGB,
    format_hex_color,
    linear_rgb_to_hsl,
    parse_hex_color,
    saturated_hsl_to_linear_rgb,
)

_MIN_COLORING_VOLUME_ML = 0.001
_MIN_CALIBRATION_DROPS_PER_ML = 0.001
_CALIBRATION_HUE_KEY = "_calibration_hue_degrees"
_CALIBRATION_LIGHTNESS_KEY = "_calibration_lightness_percent"
_COLOR_SYNC_TOLERANCE = 1e-7


class _ColorantHSLState(Protocol):
    """Stored calibration color and hidden HSL endpoint state."""

    calibration_color: Sequence[float]

    def get(self, key: str, default: object | None = None) -> object: ...

    def __setitem__(self, key: str, value: float) -> None: ...


def _update_color_profile(
    profile: bpy.types.PropertyGroup, _context: bpy.types.Context
) -> None:
    """Refresh a profile material after one of its saved inputs changes."""
    from ..operators._color_adapter import ColorProfileValues
    from ..operators._color_material import update_color_preview_material

    update_color_preview_material(cast(ColorProfileValues, profile))


def _update_colorant(
    colorant: bpy.types.PropertyGroup, _context: bpy.types.Context
) -> None:
    """Find the colorant's owning profile and refresh only that material."""
    from ..operators._color_material import update_color_preview_material

    settings = getattr(colorant.id_data, "silicone_casting", None)
    if settings is None:
        return
    pointer = colorant.as_pointer()
    for profile in settings.color_profiles:
        if any(item.as_pointer() == pointer for item in profile.colorants):
            update_color_preview_material(profile)
            return


def _update_calibration_color(
    colorant: bpy.types.PropertyGroup,
    context: bpy.types.Context,
) -> None:
    """Normalize picker input to saturated HSL and refresh its material."""
    state = cast(_ColorantHSLState, colorant)
    color = cast(RGB, tuple(state.calibration_color[:3]))
    hue, saturation, lightness = linear_rgb_to_hsl(color)
    if saturation <= _COLOR_SYNC_TOLERANCE:
        hue = _stored_float(state, _CALIBRATION_HUE_KEY, hue)
    normalized = saturated_hsl_to_linear_rgb(hue, lightness)
    state[_CALIBRATION_HUE_KEY] = hue
    state[_CALIBRATION_LIGHTNESS_KEY] = lightness * 100.0
    if any(
        abs(actual - expected) > _COLOR_SYNC_TOLERANCE
        for actual, expected in zip(color, normalized, strict=True)
    ):
        state.calibration_color = normalized
        return
    _update_colorant(colorant, context)


def _get_result_color(profile: bpy.types.PropertyGroup) -> tuple[float, float, float]:
    """Calculate the result swatch without storing duplicate color data."""
    from ..operators._color_adapter import ColorProfileValues, calculate_profile_color

    return calculate_profile_color(cast(ColorProfileValues, profile))


def _ignore_result_color_edit(
    _profile: bpy.types.PropertyGroup,
    _value: Sequence[float],
) -> None:
    """Keep the calculated swatch read-only while allowing full-color
    drawing."""


def _derived_calibration_hsl(
    colorant: bpy.types.PropertyGroup,
) -> tuple[float, float]:
    """Derive hue and lightness from an older saved calibration color."""
    state = cast(_ColorantHSLState, colorant)
    hue, _saturation, lightness = linear_rgb_to_hsl(
        cast(RGB, tuple(state.calibration_color[:3]))
    )
    return hue, lightness * 100.0


def _stored_float(
    state: _ColorantHSLState,
    key: str,
    fallback: float,
) -> float:
    """Read one optional ID-property-backed HSL value."""
    value = state.get(key)
    return float(value) if isinstance(value, int | float) else fallback


def _get_calibration_hue(colorant: bpy.types.PropertyGroup) -> float:
    """Return saved hue, deriving it for colorants from older blend files."""
    state = cast(_ColorantHSLState, colorant)
    derived_hue, _derived_lightness = _derived_calibration_hsl(colorant)
    return _stored_float(state, _CALIBRATION_HUE_KEY, derived_hue)


def _set_calibration_hue(
    colorant: bpy.types.PropertyGroup,
    value: float,
) -> None:
    """Save hue and rebuild the saturated calibration color."""
    state = cast(_ColorantHSLState, colorant)
    hue = value % 360.0
    _derived_hue, derived_lightness = _derived_calibration_hsl(colorant)
    lightness = _stored_float(
        state,
        _CALIBRATION_LIGHTNESS_KEY,
        derived_lightness,
    )
    state[_CALIBRATION_HUE_KEY] = hue
    state.calibration_color = saturated_hsl_to_linear_rgb(hue, lightness / 100.0)


def _get_calibration_lightness(colorant: bpy.types.PropertyGroup) -> float:
    """Return saved lightness, deriving it for older blend files."""
    state = cast(_ColorantHSLState, colorant)
    _derived_hue, derived_lightness = _derived_calibration_hsl(colorant)
    return _stored_float(state, _CALIBRATION_LIGHTNESS_KEY, derived_lightness)


def _set_calibration_lightness(
    colorant: bpy.types.PropertyGroup,
    value: float,
) -> None:
    """Save lightness and rebuild the saturated calibration color."""
    state = cast(_ColorantHSLState, colorant)
    derived_hue, _derived_lightness = _derived_calibration_hsl(colorant)
    hue = _stored_float(state, _CALIBRATION_HUE_KEY, derived_hue)
    lightness = min(max(value, 0.0), 100.0)
    state[_CALIBRATION_LIGHTNESS_KEY] = lightness
    state.calibration_color = saturated_hsl_to_linear_rgb(hue, lightness / 100.0)


def _get_calibration_hex(colorant: bpy.types.PropertyGroup) -> str:
    """Return the picker color as conventional sRGB ``#RRGGBB`` text."""
    state = cast(_ColorantHSLState, colorant)
    return format_hex_color(cast(RGB, tuple(state.calibration_color[:3])))


def _set_calibration_hex(
    colorant: bpy.types.PropertyGroup,
    value: str,
) -> None:
    """Apply valid sRGB hex text; invalid edits keep the previous color."""
    try:
        color = parse_hex_color(value)
    except ValueError:
        return
    cast(_ColorantHSLState, colorant).calibration_color = color


class SiliconeCastingColorant(bpy.types.PropertyGroup):
    """One calibrated dye dose inside a named color profile."""

    enabled: BoolProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Enabled",
        description="Include this colorant in the simulated result",
        default=True,
        update=_update_colorant,
    )

    is_opacifier: BoolProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Legacy White / Lighten",
        description=(
            "Legacy saved value; white is now detected automatically from "
            "Lightness 100%"
        ),
        default=False,
        options={"HIDDEN"},
    )

    colorant_name: StringProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Name",
        default="Colorant",
    )

    calibration_color: FloatVectorProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Calibration Color",
        description=(
            "Dye color preview and picker; selections are normalized to 100% "
            "HSL saturation"
        ),
        subtype="COLOR",
        size=3,
        min=0.0,
        max=1.0,
        default=(1.0, 0.0, 0.0),
        update=_update_calibration_color,
    )

    calibration_hex: StringProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Hex (sRGB)",
        description=(
            "Enter a #RRGGBB color; it is converted to the saturated dye color"
        ),
        get=_get_calibration_hex,
        set=_set_calibration_hex,
        options={"SKIP_SAVE"},
    )

    calibration_hue_degrees: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Hue (degrees)",
        description="Dye hue from 0 to 360 degrees; saturation is fixed at 100%",
        min=0.0,
        max=360.0,
        precision=1,
        step=100,
        get=_get_calibration_hue,
        set=_set_calibration_hue,
    )

    calibration_lightness_percent: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Lightness",
        subtype="PERCENTAGE",
        description=(
            "Dye lightness: 100% is white and lightens other colors, 0% is "
            "black, and intermediate values include colors such as brown"
        ),
        min=0.0,
        max=100.0,
        precision=1,
        step=100,
        get=_get_calibration_lightness,
        set=_set_calibration_lightness,
    )

    calibration_drops_per_ml: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Calibration Drops / mL",
        description=(
            "Dye concentration that produced Calibration Color; 1.0 drop/mL is "
            "only a starting estimate and can vary by dye"
        ),
        default=1.0,
        min=_MIN_CALIBRATION_DROPS_PER_ML,
        precision=2,
        step=100,
        update=_update_colorant,
    )

    drops: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Drops",
        description="Colorant amount; decimals support toothpick-sized doses",
        default=0.0,
        min=0.0,
        precision=2,
        step=100,
        update=_update_colorant,
    )


class SiliconeCastingColorProfile(bpy.types.PropertyGroup):
    """A named silicone base, calibrated colorants, and preview material."""

    profile_name: StringProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Profile Name",
        default="Profile",
        update=_update_color_profile,
    )

    base_volume_ml: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Base Volume (mL)",
        default=100.0,
        min=_MIN_COLORING_VOLUME_ML,
        precision=2,
        update=_update_color_profile,
    )

    base_color: FloatVectorProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Base Color",
        description="Untinted silicone color, including any natural yellow cast",
        subtype="COLOR",
        size=3,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0),
        update=_update_color_profile,
    )

    transparency: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Base Transparency",
        description="Original silicone: 1.0 is clear and 0.0 is opaque",
        default=1.0,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
        update=_update_color_profile,
    )

    cloudiness: FloatProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Legacy Base Cloudiness",
        description="Legacy saved value; cloudiness is no longer simulated",
        default=0.0,
        min=0.0,
        max=1.0,
        options={"HIDDEN"},
    )

    result_color: FloatVectorProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Result Color",
        description="Calculated mixed color; change the base or dyes to edit it",
        subtype="COLOR",
        size=3,
        min=0.0,
        max=1.0,
        get=_get_result_color,
        set=_ignore_result_color_edit,
        options={"SKIP_SAVE"},
    )

    colorants: CollectionProperty(  # pyright: ignore[reportInvalidTypeForm]
        type=SiliconeCastingColorant,
    )

    colorant_active_index: IntProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Active Colorant",
        default=-1,
        min=-1,
        options={"HIDDEN", "SKIP_SAVE"},
    )

    preview_material: PointerProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Preview Material",
        type=bpy.types.Material,
    )
