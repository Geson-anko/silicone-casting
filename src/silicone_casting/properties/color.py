"""Color profile RNA types and their synchronized derived values."""

from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

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

from ..core.color_mixing import (
    RGB,
    CalibratedColorant,
    SimulatedSiliconeAppearance,
    format_hex_color,
    linear_rgb_to_hsl,
    parse_hex_color,
    saturated_hsl_to_linear_rgb,
)
from ._material import MATERIAL_PREFIX, configure_material

if TYPE_CHECKING:
    from .settings import SiliconeCastingProperties

_MIN_COLORING_VOLUME_ML = 0.001
_MIN_CALIBRATION_DROPS_PER_ML = 0.001
_CALIBRATION_HUE_KEY = "_calibration_hue_degrees"
_CALIBRATION_LIGHTNESS_KEY = "_calibration_lightness_percent"
_COLOR_SYNC_TOLERANCE = 1e-7


class SiliconeCastingColorant(bpy.types.PropertyGroup):
    """One calibrated dye dose inside a named color profile."""

    def calibrated(self) -> CalibratedColorant:
        """Read this RNA row as an immutable input to the mixing
        calculation."""
        return CalibratedColorant(
            calibration_color=self._calibration_rgb(),
            calibration_drops_per_ml=self.calibration_drops_per_ml,
            drops=self.drops,
            enabled=self.enabled,
        )

    def _calibration_rgb(self) -> RGB:
        """Read the calibration color from its RNA vector."""
        color = self.calibration_color
        return color[0], color[1], color[2]

    def _stored_float(self, key: str, fallback: float) -> float:
        """Read one optional ID-property-backed HSL value."""
        value = self.get(key)
        return float(value) if isinstance(value, int | float) else fallback

    def _derived_calibration_hsl(self) -> tuple[float, float]:
        """Derive hue and lightness from an older saved calibration color."""
        hue, _saturation, lightness = linear_rgb_to_hsl(self._calibration_rgb())
        return hue, lightness * 100.0

    def _get_calibration_hue(self) -> float:
        """Return saved hue, deriving it for colorants from older blend
        files."""
        derived_hue, _derived_lightness = self._derived_calibration_hsl()
        return self._stored_float(_CALIBRATION_HUE_KEY, derived_hue)

    def _set_calibration_hue(self, value: float) -> None:
        """Save hue and rebuild the saturated calibration color."""
        hue = value % 360.0
        lightness = self._get_calibration_lightness()
        self[_CALIBRATION_HUE_KEY] = hue
        self.calibration_color = saturated_hsl_to_linear_rgb(hue, lightness / 100.0)

    def _get_calibration_lightness(self) -> float:
        """Return saved lightness, deriving it for older blend files."""
        _derived_hue, derived_lightness = self._derived_calibration_hsl()
        return self._stored_float(_CALIBRATION_LIGHTNESS_KEY, derived_lightness)

    def _set_calibration_lightness(self, value: float) -> None:
        """Save lightness and rebuild the saturated calibration color."""
        hue = self._get_calibration_hue()
        lightness = min(max(value, 0.0), 100.0)
        self[_CALIBRATION_LIGHTNESS_KEY] = lightness
        self.calibration_color = saturated_hsl_to_linear_rgb(hue, lightness / 100.0)

    def _get_calibration_hex(self) -> str:
        """Return the picker color as conventional sRGB ``#RRGGBB`` text."""
        return format_hex_color(self._calibration_rgb())

    def _set_calibration_hex(self, value: str) -> None:
        """Apply valid sRGB hex text; invalid edits keep the previous color."""
        try:
            color = parse_hex_color(value)
        except ValueError:
            return
        self.calibration_color = color

    def _update_colorant(self, _context: bpy.types.Context) -> None:
        """Find this colorant's owning profile and refresh only that
        material."""
        scene = cast(bpy.types.Scene, self.id_data)
        settings = cast("SiliconeCastingProperties", getattr(scene, "silicone_casting"))
        pointer = self.as_pointer()
        for profile in settings.color_profiles:
            if any(item.as_pointer() == pointer for item in profile.colorants):
                profile.update_preview_material()
                return

    def _update_calibration_color(self, context: bpy.types.Context) -> None:
        """Normalize picker input to saturated HSL and refresh its material."""
        color = self._calibration_rgb()
        hue, saturation, lightness = linear_rgb_to_hsl(color)
        if saturation <= _COLOR_SYNC_TOLERANCE:
            hue = self._stored_float(_CALIBRATION_HUE_KEY, hue)
        normalized = saturated_hsl_to_linear_rgb(hue, lightness)
        self[_CALIBRATION_HUE_KEY] = hue
        self[_CALIBRATION_LIGHTNESS_KEY] = lightness * 100.0
        if any(
            abs(actual - expected) > _COLOR_SYNC_TOLERANCE
            for actual, expected in zip(color, normalized, strict=True)
        ):
            self.calibration_color = normalized
            return
        self._update_colorant(context)

    if TYPE_CHECKING:
        enabled: bool
        is_opacifier: bool
        colorant_name: str
        calibration_color: Sequence[float]
        calibration_hex: str
        calibration_hue_degrees: float
        calibration_lightness_percent: float
        calibration_drops_per_ml: float
        drops: float
    else:
        enabled: BoolProperty(
            name="Enabled",
            description="Include this colorant in the simulated result",
            default=True,
            update=_update_colorant,
        )

        is_opacifier: BoolProperty(
            name="Legacy White / Lighten",
            description=(
                "Legacy saved value; white is now detected automatically from "
                "Lightness 100%"
            ),
            default=False,
            options={"HIDDEN"},
        )

        colorant_name: StringProperty(
            name="Name",
            default="Colorant",
        )

        calibration_color: FloatVectorProperty(
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

        calibration_hex: StringProperty(
            name="Hex (sRGB)",
            description=(
                "Enter a #RRGGBB color; it is converted to the saturated dye color"
            ),
            get=_get_calibration_hex,
            set=_set_calibration_hex,
            options={"SKIP_SAVE"},
        )

        calibration_hue_degrees: FloatProperty(
            name="Hue (degrees)",
            description="Dye hue from 0 to 360 degrees; saturation is fixed at 100%",
            min=0.0,
            max=360.0,
            precision=1,
            step=100,
            get=_get_calibration_hue,
            set=_set_calibration_hue,
        )

        calibration_lightness_percent: FloatProperty(
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

        calibration_drops_per_ml: FloatProperty(
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

        drops: FloatProperty(
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

    def appearance(self) -> SimulatedSiliconeAppearance:
        """Calculate this profile's color and transparency from its saved
        inputs."""
        base = self.base_color
        return SimulatedSiliconeAppearance.from_mixture(
            (base[0], base[1], base[2]),
            self.base_volume_ml,
            self.transparency,
            (colorant.calibrated() for colorant in self.colorants),
        )

    def active_colorant(self) -> SiliconeCastingColorant | None:
        """Return the selected colorant when its row still exists."""
        index = self.colorant_active_index
        return self.colorants[index] if 0 <= index < len(self.colorants) else None

    def add_colorant(self) -> SiliconeCastingColorant:
        """Append a default zero-dose colorant and select its row."""
        colorant = self.colorants.add()
        self.colorant_active_index = len(self.colorants) - 1
        self.update_preview_material()
        return colorant

    def remove_active_colorant(self) -> None:
        """Remove the selected row and refresh the remaining mixture."""
        index = self.colorant_active_index
        self.colorants.remove(index)
        self.colorant_active_index = min(index, len(self.colorants) - 1)
        self.update_preview_material()

    def ensure_preview_material(self) -> bpy.types.Material:
        """Create this profile's shared material on demand and refresh it."""
        material = self.preview_material
        if material is None:
            material = bpy.data.materials.new(f"{MATERIAL_PREFIX}{self.profile_name}")
            self.preview_material = material
        configure_material(material, self.profile_name, self.appearance())
        return material

    def update_preview_material(self) -> None:
        """Refresh an existing material without allocating hidden data."""
        material = self.preview_material
        if material is not None:
            configure_material(material, self.profile_name, self.appearance())

    def _update_color_profile(self, _context: bpy.types.Context) -> None:
        """Refresh this profile's material after a saved input changes."""
        self.update_preview_material()

    def _get_base_volume(self) -> float:
        """Read the original RNA storage key, including existing blend
        files."""
        return float(self.get("base_volume_ml", 100.0))

    def _set_base_volume(self, value: float) -> None:
        """Scale every dye dose with volume to preserve its concentration."""
        previous = self._get_base_volume()
        volume = max(value, _MIN_COLORING_VOLUME_ML)
        self["base_volume_ml"] = volume
        for colorant in self.colorants:
            colorant.drops *= volume / previous

    def _get_result_color(self) -> RGB:
        """Calculate the result swatch without storing duplicate color data."""
        return self.appearance().color

    def _ignore_result_color_edit(self, _value: Sequence[float]) -> None:
        """Keep the calculated swatch read-only while allowing full-color
        drawing."""

    if TYPE_CHECKING:
        profile_name: str
        base_volume_ml: float
        base_color: Sequence[float]
        transparency: float
        cloudiness: float
        result_color: Sequence[float]
        colorants: bpy.types.bpy_prop_collection_idprop[SiliconeCastingColorant]
        colorant_active_index: int
        preview_material: bpy.types.Material | None
    else:
        profile_name: StringProperty(
            name="Profile Name",
            default="Profile",
            update=_update_color_profile,
        )

        base_volume_ml: FloatProperty(
            name="Base Volume (mL)",
            description="Scale base volume and all dye drops together",
            get=_get_base_volume,
            set=_set_base_volume,
            default=100.0,
            min=_MIN_COLORING_VOLUME_ML,
            precision=2,
            update=_update_color_profile,
        )

        base_color: FloatVectorProperty(
            name="Base Color",
            description="Untinted silicone color, including any natural yellow cast",
            subtype="COLOR",
            size=3,
            min=0.0,
            max=1.0,
            default=(1.0, 1.0, 1.0),
            update=_update_color_profile,
        )

        transparency: FloatProperty(
            name="Base Transparency",
            description="Original silicone: 1.0 is clear and 0.0 is opaque",
            default=1.0,
            min=0.0,
            max=1.0,
            subtype="FACTOR",
            update=_update_color_profile,
        )

        cloudiness: FloatProperty(
            name="Legacy Base Cloudiness",
            description="Legacy saved value; cloudiness is no longer simulated",
            default=0.0,
            min=0.0,
            max=1.0,
            options={"HIDDEN"},
        )

        result_color: FloatVectorProperty(
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

        colorants: CollectionProperty(
            type=SiliconeCastingColorant,
        )

        colorant_active_index: IntProperty(
            name="Active Colorant",
            default=-1,
            min=-1,
            options={"HIDDEN", "SKIP_SAVE"},
        )

        preview_material: PointerProperty(
            name="Preview Material",
            type=bpy.types.Material,
        )
