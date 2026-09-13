"""Adapt color simulator RNA values to the core mixing calculation."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Protocol, cast

import bpy

from ..core import (
    RGB,
    CalibratedColorant,
    SimulatedSiliconeAppearance,
)


class ColorantValues(Protocol):
    """RNA values needed to calculate one colorant contribution."""

    enabled: bool
    colorant_name: str
    calibration_color: Sequence[float]
    calibration_hex: str
    calibration_hue_degrees: float
    calibration_lightness_percent: float
    calibration_drops_per_ml: float
    drops: float


class ColorantCollection(Protocol):
    """Mutable RNA collection containing colorant rows."""

    def __len__(self) -> int: ...

    def __getitem__(self, index: int) -> ColorantValues: ...

    def __iter__(self) -> Iterator[ColorantValues]: ...

    def add(self) -> ColorantValues: ...

    def remove(self, index: int) -> None: ...


class ColorProfileValues(Protocol):
    """RNA values shared by the simulator UI and material updater."""

    profile_name: str
    base_volume_ml: float
    base_color: Sequence[float]
    transparency: float
    colorants: ColorantCollection
    colorant_active_index: int
    preview_material: bpy.types.Material | None


class ColorProfileCollection(Protocol):
    """Mutable RNA collection containing named profiles."""

    def __len__(self) -> int: ...

    def __getitem__(self, index: int) -> ColorProfileValues: ...

    def __iter__(self) -> Iterator[ColorProfileValues]: ...

    def add(self) -> ColorProfileValues: ...

    def remove(self, index: int) -> None: ...


class MixturePartValues(Protocol):
    enabled: bool
    volume_ml: float


class ColorSimulatorSettings(Protocol):
    """Scene-level container for named color profiles."""

    color_profiles: ColorProfileCollection
    color_profile_active_index: int
    mixture_parts: Sequence[MixturePartValues]


def active_color_profile(
    settings: ColorSimulatorSettings,
) -> ColorProfileValues | None:
    """Return the selected profile, or none when the collection is empty."""
    index = settings.color_profile_active_index
    if not 0 <= index < len(settings.color_profiles):
        return None
    return settings.color_profiles[index]


def calculate_profile_color(profile: ColorProfileValues) -> RGB:
    """Calculate the scene-linear preview color for one saved profile."""
    return calculate_profile_appearance(profile).color


def calculate_profile_appearance(
    profile: ColorProfileValues,
) -> SimulatedSiliconeAppearance:
    """Calculate color and optical appearance for one saved profile."""
    colorants = (
        CalibratedColorant(
            calibration_color=cast(RGB, tuple(colorant.calibration_color[:3])),
            calibration_drops_per_ml=colorant.calibration_drops_per_ml,
            drops=colorant.drops,
            enabled=colorant.enabled,
        )
        for colorant in profile.colorants
    )
    return SimulatedSiliconeAppearance.from_mixture(
        cast(RGB, tuple(profile.base_color[:3])),
        profile.base_volume_ml,
        profile.transparency,
        colorants,
    )
