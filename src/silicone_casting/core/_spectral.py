"""Representative spectral reflectance conversion and subtractive mixing."""

from collections.abc import Iterable
from math import exp, fsum, log

type RGB = tuple[float, float, float]
type Spectrum = tuple[float, ...]

# The 10-band conversion coefficients and epsilon handling are adapted from
# MyPaint's lib/blending.hpp (Copyright (C) 2012 Andrew Chadwick), licensed
# under GPL-2.0-or-later. MyPaint attributes the spectral WGM model to Scott
# Allen Burns, Meng, and others. A 2% floor represents display black as a
# positive reflectance, as required by the weighted geometric mean.
_EPSILON = 0.02
_OFFSET = 1.0 - _EPSILON

_RGB_FROM_SPECTRUM = (
    (
        0.026595621243689,
        0.049779426257903,
        0.022449850859496,
        -0.218453689278271,
        -0.256894883201278,
        0.445881722194840,
        0.772365886289756,
        0.194498761382537,
        0.014038157587820,
        0.007687264480513,
    ),
    (
        -0.032601672674412,
        -0.061021043498478,
        -0.052490001018404,
        0.206659098273522,
        0.572496335158169,
        0.317837248815438,
        -0.021216624031211,
        -0.019387668756117,
        -0.001521339050858,
        -0.000835181622534,
    ),
    (
        0.339475473216284,
        0.635401374177222,
        0.771520797089589,
        0.113222640692379,
        -0.055251113343776,
        -0.048222578468680,
        -0.012966666339586,
        -0.001523814504223,
        -0.000094718948810,
        -0.000051604594741,
    ),
)

_RED_SPECTRUM = (
    0.009281362787953,
    0.009732627042016,
    0.011254252737167,
    0.015105578649573,
    0.024797924177217,
    0.083622585502406,
    0.977865045723212,
    1.0,
    0.999961046144372,
    0.999999992756822,
)
_GREEN_SPECTRUM = (
    0.002854127435775,
    0.003917589679914,
    0.012132151699187,
    0.748259205918013,
    1.0,
    0.865695937531795,
    0.037477469241101,
    0.022816789725717,
    0.021747419446456,
    0.021384940572308,
)
_BLUE_SPECTRUM = (
    0.537052150373386,
    0.546646402401469,
    0.575501819073983,
    0.258778829633924,
    0.041709923751716,
    0.012662638828324,
    0.007485593127390,
    0.006766900622462,
    0.006699764779016,
    0.006676219883241,
)


def _clamp_unit(value: float) -> float:
    """Clamp one scalar to the inclusive zero-to-one range."""
    return min(max(value, 0.0), 1.0)


def _rgb_to_spectrum(color: RGB) -> Spectrum:
    """Upsample scene-linear RGB to a positive representative spectrum."""
    red, green, blue = (_clamp_unit(channel) * _OFFSET + _EPSILON for channel in color)
    return tuple(
        _RED_SPECTRUM[index] * red
        + _GREEN_SPECTRUM[index] * green
        + _BLUE_SPECTRUM[index] * blue
        for index in range(len(_RED_SPECTRUM))
    )


def _spectrum_to_rgb(spectrum: Spectrum) -> RGB:
    """Collapse a representative spectrum back to scene-linear RGB."""

    def channel(row: tuple[float, ...]) -> float:
        value = fsum(
            coefficient * sample
            for coefficient, sample in zip(row, spectrum, strict=True)
        )
        return _clamp_unit((value - _EPSILON) / _OFFSET)

    return (
        channel(_RGB_FROM_SPECTRUM[0]),
        channel(_RGB_FROM_SPECTRUM[1]),
        channel(_RGB_FROM_SPECTRUM[2]),
    )


def mix_spectral_reflectance(
    weighted_colors: Iterable[tuple[RGB, float]],
) -> RGB:
    """Mix representative reflectances by their weighted geometric mean."""
    values = tuple((color, weight) for color, weight in weighted_colors if weight > 0.0)
    total_weight = fsum(weight for _color, weight in values)
    if total_weight <= 0.0:
        raise ValueError("At least one positive color weight is required")

    spectra = tuple(
        (_rgb_to_spectrum(color), weight / total_weight) for color, weight in values
    )
    mixed = tuple(
        exp(fsum(weight * log(spectrum[index]) for spectrum, weight in spectra))
        for index in range(len(_RED_SPECTRUM))
    )
    return _spectrum_to_rgb(mixed)
