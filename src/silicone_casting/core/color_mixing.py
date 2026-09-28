"""Spectral subtractive mixing for calibrated silicone colorants."""

from collections.abc import Iterable
from colorsys import hls_to_rgb, rgb_to_hls
from dataclasses import dataclass
from math import fsum
from string import hexdigits
from typing import Self

from ._spectral import RGB as RGB, mix_spectral_reflectance


@dataclass(frozen=True, slots=True)
class CalibratedColorant:
    """One colorant dose calibrated against the current silicone base."""

    calibration_color: RGB
    calibration_drops_per_ml: float
    drops: float
    enabled: bool = True

    def concentration_factor(self, base_volume_ml: float) -> float:
        """Return concentration relative to this colorant's calibration.

        The caller supplies a positive silicone base volume in
        millilitres.
        """
        if self.calibration_drops_per_ml <= 0.0:
            raise ValueError("Calibration drops per mL must be greater than zero")
        return self.drops / (base_volume_ml * self.calibration_drops_per_ml)


@dataclass(frozen=True, slots=True)
class SimulatedSiliconeAppearance:
    """Calculated color and optical appearance of one silicone mixture."""

    color: RGB
    transparency: float

    @classmethod
    def from_mixture(
        cls,
        base_color: RGB,
        base_volume_ml: float,
        base_transparency: float,
        colorants: Iterable[CalibratedColorant],
    ) -> Self:
        """Calculate color and transparency from calibrated colorant doses.

        Representative reflectances mix by a concentration-weighted
        geometric mean. Every active colorant also reduces transparency,
        using the same concentration relative to its calibration. The
        iterable is consumed once.
        """
        if base_volume_ml <= 0.0:
            raise ValueError("Base volume must be greater than zero")
        weighted_colors = [
            (colorant.calibration_color, colorant.concentration_factor(base_volume_ml))
            for colorant in colorants
            if colorant.enabled and colorant.drops > 0.0
        ]
        total_concentration = fsum(weight for _color, weight in weighted_colors)
        color = base_color
        if weighted_colors:
            color = mix_spectral_reflectance(
                [(base_color, max(1.0 - total_concentration, 0.0)), *weighted_colors]
            )
        opacity_factor = _clamp_unit(total_concentration)
        transparency = _clamp_unit(base_transparency) * (1.0 - opacity_factor)
        return cls(color=color, transparency=transparency)


def _clamp_unit(value: float) -> float:
    """Clamp one scalar to the inclusive zero-to-one range."""
    return min(max(value, 0.0), 1.0)


def _linear_channel_to_srgb(channel: float) -> float:
    """Convert one scene-linear channel to an sRGB channel."""
    linear = _clamp_unit(channel)
    return (
        12.92 * linear if linear <= 0.0031308 else 1.055 * linear ** (1.0 / 2.4) - 0.055
    )


def _srgb_channel_to_linear(channel: float) -> float:
    """Convert one sRGB channel to a scene-linear channel."""
    srgb = _clamp_unit(channel)
    return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4


def saturated_hsl_to_linear_rgb(hue_degrees: float, lightness: float) -> RGB:
    """Create scene-linear RGB from HSL with saturation fixed at 100%."""
    hue = (hue_degrees % 360.0) / 360.0
    srgb = hls_to_rgb(hue, _clamp_unit(lightness), 1.0)
    return (
        _srgb_channel_to_linear(srgb[0]),
        _srgb_channel_to_linear(srgb[1]),
        _srgb_channel_to_linear(srgb[2]),
    )


def linear_rgb_to_hsl(color: RGB) -> tuple[float, float, float]:
    """Return conventional sRGB HSL as degrees, saturation, and lightness."""
    srgb = tuple(_linear_channel_to_srgb(channel) for channel in color)
    hue, lightness, saturation = rgb_to_hls(*srgb)
    return (hue * 360.0, saturation, lightness)


def linear_rgb_to_srgb8(color: RGB) -> tuple[int, int, int]:
    """Convert scene-linear RGB to conventional 8-bit sRGB values."""

    def convert(channel: float) -> int:
        srgb = _linear_channel_to_srgb(channel)
        return int(srgb * 255.0 + 0.5)

    return (convert(color[0]), convert(color[1]), convert(color[2]))


def format_hex_color(color: RGB) -> str:
    """Format scene-linear RGB as a copy-ready sRGB hex color code."""
    red, green, blue = linear_rgb_to_srgb8(color)
    return f"#{red:02X}{green:02X}{blue:02X}"


def parse_hex_color(value: str) -> RGB:
    """Parse ``#RRGGBB`` sRGB text into a scene-linear RGB color."""
    digits = value.strip().removeprefix("#")
    if len(digits) != 6 or any(character not in hexdigits for character in digits):
        raise ValueError("Hex color must use the #RRGGBB format")
    channels = tuple(int(digits[index : index + 2], 16) for index in (0, 2, 4))
    return (
        _srgb_channel_to_linear(channels[0] / 255.0),
        _srgb_channel_to_linear(channels[1] / 255.0),
        _srgb_channel_to_linear(channels[2] / 255.0),
    )


def format_linear_rgb(color: RGB) -> str:
    """Format scene-linear RGB as a stable copy-ready triplet."""
    return ", ".join(f"{_clamp_unit(channel):.4f}" for channel in color)
