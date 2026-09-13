"""Pure arithmetic for splitting a target silicone volume into A and B."""

from dataclasses import fields

import pytest

from silicone_casting.core.mixture import MixtureBreakdown


def _assert_breakdown(actual: MixtureBreakdown, expected: MixtureBreakdown) -> None:
    for field in fields(MixtureBreakdown):
        assert getattr(actual, field.name) == pytest.approx(
            getattr(expected, field.name), rel=1e-12
        )


class TestCalculateMixture:
    def test_equal_density_and_ratio_split_one_hundred_ml_evenly(self) -> None:
        actual = MixtureBreakdown.from_volume(100.0, 1.1, 1.1, 1.0, 1.0)

        _assert_breakdown(
            actual,
            MixtureBreakdown(
                volume_ml=100.0,
                weight_g=110.0,
                a_volume_ml=50.0,
                b_volume_ml=50.0,
                a_weight_g=55.0,
                b_weight_g=55.0,
            ),
        )

    def test_different_densities_follow_a_three_to_one_weight_ratio(self) -> None:
        actual = MixtureBreakdown.from_volume(90.0, 1.5, 1.0, 3.0, 1.0)

        _assert_breakdown(
            actual,
            MixtureBreakdown(
                volume_ml=90.0,
                weight_g=120.0,
                a_volume_ml=60.0,
                b_volume_ml=30.0,
                a_weight_g=90.0,
                b_weight_g=30.0,
            ),
        )

    def test_zero_volume_makes_every_output_zero(self) -> None:
        actual = MixtureBreakdown.from_volume(0.0, 1.5, 0.9, 10.0, 1.0)

        _assert_breakdown(actual, MixtureBreakdown(0.0, 0.0, 0.0, 0.0, 0.0, 0.0))

    def test_breakdowns_are_additive_across_part_volumes(self) -> None:
        first = MixtureBreakdown.from_volume(20.0, 1.4, 0.95, 2.0, 1.0)
        second = MixtureBreakdown.from_volume(30.0, 1.4, 0.95, 2.0, 1.0)
        combined = MixtureBreakdown.from_volume(50.0, 1.4, 0.95, 2.0, 1.0)

        for field in fields(MixtureBreakdown):
            assert getattr(first, field.name) + getattr(
                second, field.name
            ) == pytest.approx(getattr(combined, field.name), rel=1e-12)
