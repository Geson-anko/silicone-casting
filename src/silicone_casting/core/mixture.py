"""Silicone mixture amounts derived from volume, density, and weight ratio."""

from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True)
class MixtureBreakdown:
    """Volumes and weights for a two-part silicone mixture."""

    volume_ml: float
    weight_g: float
    a_volume_ml: float
    b_volume_ml: float
    a_weight_g: float
    b_weight_g: float

    @classmethod
    def from_volume(
        cls,
        volume_ml: float,
        density_a_g_per_ml: float,
        density_b_g_per_ml: float,
        ratio_a: float,
        ratio_b: float,
    ) -> Self:
        """Split a target volume according to an A:B weight ratio.

        The scale converts the relative weight ratio into actual grams while
        satisfying ``a_volume_ml + b_volume_ml == volume_ml``. Densities and ratio
        terms are positive because the RNA properties that feed this method clamp
        them to positive values.

        Args:
            volume_ml: Total mixed silicone volume in millilitres.
            density_a_g_per_ml: Density of part A in grams per millilitre.
            density_b_g_per_ml: Density of part B in grams per millilitre.
            ratio_a: Relative weight of part A.
            ratio_b: Relative weight of part B.

        Returns:
            The total and per-part volumes and weights.
        """
        scale = volume_ml / (
            ratio_a / density_a_g_per_ml + ratio_b / density_b_g_per_ml
        )
        a_weight_g = scale * ratio_a
        b_weight_g = scale * ratio_b
        a_volume_ml = a_weight_g / density_a_g_per_ml
        b_volume_ml = b_weight_g / density_b_g_per_ml
        return cls(
            volume_ml=volume_ml,
            weight_g=a_weight_g + b_weight_g,
            a_volume_ml=a_volume_ml,
            b_volume_ml=b_volume_ml,
            a_weight_g=a_weight_g,
            b_weight_g=b_weight_g,
        )


def calculate_mixture(
    volume_ml: float,
    density_a_g_per_ml: float,
    density_b_g_per_ml: float,
    ratio_a: float,
    ratio_b: float,
) -> MixtureBreakdown:
    """Return a mixture breakdown using
    :meth:`MixtureBreakdown.from_volume`."""
    return MixtureBreakdown.from_volume(
        volume_ml, density_a_g_per_ml, density_b_g_per_ml, ratio_a, ratio_b
    )
