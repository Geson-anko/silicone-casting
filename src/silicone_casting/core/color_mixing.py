"""Spectral subtractive mixing for calibrated silicone colorants."""

from collections.abc import Iterable
from colorsys import hls_to_rgb, rgb_to_hls
from dataclasses import dataclass
from math import fsum
from string import hexdigits

from ._spectral import mix_spectral_reflectance

RGB = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class CalibratedColorant:
    """One colorant dose calibrated against the current silicone base."""

    calibration_color: RGB
    calibration_drops_per_ml: float
    drops: float
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class SimulatedSiliconeAppearance:
    """Calculated color and optical appearance of one silicone mixture."""

    color: RGB
    transparency: float


def _clamp_unit(value: float) -> float:
    """Clamp one scalar to the inclusive zero-to-one range."""
    return min(max(value, 0.0), 1.0)


def _concentration_factor(
    colorant: CalibratedColorant,
    base_volume_ml: float,
) -> float:
    """Return actual concentration relative to one colorant's calibration."""
    if colorant.calibration_drops_per_ml <= 0.0:
        raise ValueError("Calibration drops per mL must be greater than zero")
    return colorant.drops / (base_volume_ml * colorant.calibration_drops_per_ml)


def simulate_silicone_color(
    base_color: RGB,
    base_volume_ml: float,
    colorants: Iterable[CalibratedColorant],
) -> RGB:
    """Return a scene-linear RGB estimate from representative spectra.

    Each calibration color is treated as the result at its dye-specific
    calibration concentration. Colors are upsampled to representative
    reflectance spectra, then mixed by a concentration-weighted
    geometric mean. This gives white, black, and chromatic colorants the
    same mixing rule and keeps the result independent of row order.
    """
    if base_volume_ml <= 0.0:
        raise ValueError("Base volume must be greater than zero")

    active_colorants: list[tuple[CalibratedColorant, float]] = []
    for colorant in colorants:
        if not colorant.enabled or colorant.drops <= 0.0:
            continue
        active_colorants.append(
            (colorant, _concentration_factor(colorant, base_volume_ml))
        )

    if not active_colorants:
        return base_color

    total_concentration = fsum(
        concentration for _colorant, concentration in active_colorants
    )
    weighted_colors = [
        (base_color, max(1.0 - total_concentration, 0.0)),
        *(
            (colorant.calibration_color, concentration)
            for colorant, concentration in active_colorants
        ),
    ]
    return mix_spectral_reflectance(weighted_colors)


def simulate_silicone_appearance(
    base_color: RGB,
    base_volume_ml: float,
    base_transparency: float,
    colorants: Iterable[CalibratedColorant],
) -> SimulatedSiliconeAppearance:
    """Return color and transparency for a calibrated mixture.

    All colorants share the spectral mixing rule and reduce transmission
    at their calibration concentration. The opacity rule remains an
    empirical calibration separate from the representative color
    calculation.
    """
    colorant_values = tuple(colorants)
    color = simulate_silicone_color(base_color, base_volume_ml, colorant_values)
    active_colorants = tuple(
        (colorant, _concentration_factor(colorant, base_volume_ml))
        for colorant in colorant_values
        if colorant.enabled and colorant.drops > 0.0
    )
    opacity_factor = _clamp_unit(
        fsum(concentration for _colorant, concentration in active_colorants)
    )
    transparency = _clamp_unit(base_transparency) * (1.0 - opacity_factor)
    return SimulatedSiliconeAppearance(color, transparency)


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
