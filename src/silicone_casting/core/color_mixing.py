"""Spectral subtractive mixing for calibrated silicone colorants."""

from collections.abc import Iterable
from colorsys import hls_to_rgb, rgb_to_hls
from dataclasses import dataclass
from math import fsum
from string import hexdigits
from typing import Final, NamedTuple, Self

from ._spectral import clamp_unit, mix_spectral_reflectance

type RGB = tuple[float, float, float]

# IEC 61966-2-1 sRGB transfer function constants.
_SRGB_LINEAR_SLOPE: Final = 12.92
_SRGB_LINEAR_CUTOFF: Final = 0.0031308
_SRGB_ENCODED_CUTOFF: Final = 0.04045
_SRGB_GAMMA: Final = 2.4
_SRGB_SCALE: Final = 1.055
_SRGB_OFFSET: Final = 0.055

_SRGB8_MAX: Final = 255.0


class HSL(NamedTuple):
    """Conventional sRGB hue, saturation, and lightness."""

    hue_degrees: float
    saturation: float
    lightness: float


class SRGB8(NamedTuple):
    """Conventional 8-bit sRGB channel values."""

    red: int
    green: int
    blue: int


@dataclass(frozen=True, slots=True)
class CalibratedColorant:
    """One colorant dose calibrated against the current silicone base."""

    calibration_color: RGB
    calibration_drops_per_ml: float
    drops: float
    enabled: bool = True

    def concentration_factor(self, base_volume_ml: float) -> float:
        """Return this dose's concentration relative to its calibration.

        Args:
            base_volume_ml: Positive silicone base volume in millilitres.

        Returns:
            1.0 when the dose matches the calibration concentration.

        Raises:
            ValueError: If the calibration concentration is not positive.
        """
        if self.calibration_drops_per_ml <= 0.0:
            raise ValueError("Calibration drops per mL must be greater than zero")
        return self.drops / (base_volume_ml * self.calibration_drops_per_ml)

    def contributes(self) -> bool:
        """Return whether this row takes part in the mixture."""
        return self.enabled and self.drops > 0.0


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

        Representative reflectances mix by a concentration-weighted geometric
        mean. Every active colorant also reduces transparency by the same
        concentration relative to its calibration, so the mixture is opaque
        once the concentrations add up to one.

        Args:
            base_color: Scene-linear color of the untinted silicone.
            base_volume_ml: Silicone base volume in millilitres.
            base_transparency: Transparency of the untinted silicone.
            colorants: Colorant rows; the iterable is consumed once.

        Returns:
            The simulated appearance.

        Raises:
            ValueError: If the base volume or a contributing calibration
                concentration is not positive.
        """
        if base_volume_ml <= 0.0:
            raise ValueError("Base volume must be greater than zero")
        weighted_colors = [
            (colorant.calibration_color, colorant.concentration_factor(base_volume_ml))
            for colorant in colorants
            if colorant.contributes()
        ]
        total_concentration = fsum(weight for _color, weight in weighted_colors)
        color = base_color
        if weighted_colors:
            base_weight = max(1.0 - total_concentration, 0.0)
            color = mix_spectral_reflectance(
                [(base_color, base_weight), *weighted_colors]
            )
        opacity = clamp_unit(total_concentration)
        transparency = clamp_unit(base_transparency) * (1.0 - opacity)
        return cls(color=color, transparency=transparency)


def _linear_channel_to_srgb(channel: float) -> float:
    """Encode one scene-linear channel with the sRGB transfer function."""
    linear = clamp_unit(channel)
    if linear <= _SRGB_LINEAR_CUTOFF:
        return _SRGB_LINEAR_SLOPE * linear
    return _SRGB_SCALE * linear ** (1.0 / _SRGB_GAMMA) - _SRGB_OFFSET


def _srgb_channel_to_linear(channel: float) -> float:
    """Decode one sRGB channel to scene-linear."""
    srgb = clamp_unit(channel)
    if srgb <= _SRGB_ENCODED_CUTOFF:
        return srgb / _SRGB_LINEAR_SLOPE
    return ((srgb + _SRGB_OFFSET) / _SRGB_SCALE) ** _SRGB_GAMMA


def _srgb_to_linear_rgb(red: float, green: float, blue: float) -> RGB:
    """Decode unit-range sRGB channels to a scene-linear color."""
    return (
        _srgb_channel_to_linear(red),
        _srgb_channel_to_linear(green),
        _srgb_channel_to_linear(blue),
    )


def _linear_channel_to_srgb8(channel: float) -> int:
    """Encode one scene-linear channel as a rounded 8-bit sRGB value."""
    return int(_linear_channel_to_srgb(channel) * _SRGB8_MAX + 0.5)


def saturated_hsl_to_linear_rgb(hue_degrees: float, lightness: float) -> RGB:
    """Create a scene-linear color from HSL with saturation fixed at 100%.

    Args:
        hue_degrees: Hue in degrees; wrapped into ``[0, 360)``.
        lightness: sRGB HSL lightness, clamped to ``[0, 1]``.

    Returns:
        The scene-linear RGB color.
    """
    hue = (hue_degrees % 360.0) / 360.0
    return _srgb_to_linear_rgb(*hls_to_rgb(hue, clamp_unit(lightness), 1.0))


def linear_rgb_to_hsl(color: RGB) -> HSL:
    """Return the conventional sRGB HSL of a scene-linear color."""
    red, green, blue = (_linear_channel_to_srgb(channel) for channel in color)
    hue, lightness, saturation = rgb_to_hls(red, green, blue)
    return HSL(hue_degrees=hue * 360.0, saturation=saturation, lightness=lightness)


def linear_rgb_to_srgb8(color: RGB) -> SRGB8:
    """Convert a scene-linear color to conventional 8-bit sRGB values."""
    red, green, blue = color
    return SRGB8(
        red=_linear_channel_to_srgb8(red),
        green=_linear_channel_to_srgb8(green),
        blue=_linear_channel_to_srgb8(blue),
    )


def format_hex_color(color: RGB) -> str:
    """Format a scene-linear color as a copy-ready sRGB ``#RRGGBB`` code."""
    red, green, blue = linear_rgb_to_srgb8(color)
    return f"#{red:02X}{green:02X}{blue:02X}"


def parse_hex_color(value: str) -> RGB:
    """Parse ``#RRGGBB`` sRGB text into a scene-linear color.

    Args:
        value: Six hex digits, optionally prefixed with ``#`` and surrounded
            by whitespace.

    Returns:
        The scene-linear RGB color.

    Raises:
        ValueError: If the text is not exactly six ASCII hex digits.
    """
    digits = value.strip().removeprefix("#")
    # int(..., 16) alone would also accept signs, spaces, and non-ASCII digits.
    if len(digits) != 6 or any(character not in hexdigits for character in digits):
        raise ValueError("Hex color must use the #RRGGBB format")
    red, green, blue = (
        int(digits[start : start + 2], 16) / _SRGB8_MAX for start in (0, 2, 4)
    )
    return _srgb_to_linear_rgb(red, green, blue)


def format_linear_rgb(color: RGB) -> str:
    """Format a scene-linear color as a stable copy-ready triplet."""
    return ", ".join(f"{clamp_unit(channel):.4f}" for channel in color)
