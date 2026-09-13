"""Calibrated spectral-reflectance mixing for silicone colorants."""

from collections.abc import Callable, Iterable

import pytest

from silicone_casting.core import (
    CalibratedColorant,
    SimulatedSiliconeAppearance,
    format_hex_color,
    format_linear_rgb,
    linear_rgb_to_hsl,
    linear_rgb_to_srgb8,
    parse_hex_color,
    saturated_hsl_to_linear_rgb,
    simulate_silicone_appearance,
    simulate_silicone_color,
)

WHITE = (1.0, 1.0, 1.0)


def test_no_colorant_preserves_the_base_color() -> None:
    base = (1.0, 0.9, 0.7)

    result = simulate_silicone_color(base, 100.0, [])

    assert result == pytest.approx(base)


def test_dye_specific_calibration_concentration_reproduces_its_color() -> None:
    calibration = (0.8, 0.2, 0.1)
    colorant = CalibratedColorant(calibration, 2.0, 200.0)

    result = simulate_silicone_color(WHITE, 100.0, [colorant])

    assert result == pytest.approx(calibration, abs=1e-4)


def test_doubling_base_volume_mixes_equal_parts_base_and_calibration_color() -> None:
    colorant = CalibratedColorant((0.25, 0.64, 0.81), 1.0, 100.0)

    result = simulate_silicone_color(WHITE, 200.0, [colorant])

    assert result == pytest.approx(
        (0.509796, 0.802891, 0.901514),
        abs=1e-6,
    )


def test_multiple_colorants_are_independent_of_row_order() -> None:
    red = CalibratedColorant((0.9, 0.3, 0.3), 0.75, 60.0)
    blue = CalibratedColorant((0.3, 0.4, 0.9), 2.0, 100.0)

    forward = simulate_silicone_color(WHITE, 80.0, [red, blue])
    reverse = simulate_silicone_color(WHITE, 80.0, [blue, red])

    assert forward == pytest.approx(reverse)


def test_disabled_and_zero_drop_rows_do_not_contribute() -> None:
    ignored = [
        CalibratedColorant((0.1, 0.2, 0.3), 1.0, 5.0, enabled=False),
        CalibratedColorant((0.2, 0.3, 0.4), 1.0, 0.0),
    ]

    result = simulate_silicone_color(WHITE, 100.0, ignored)

    assert result == pytest.approx(WHITE)


def test_calibration_color_can_be_brighter_than_the_base() -> None:
    base = (0.8, 0.7, 0.6)
    colorant = CalibratedColorant((0.9, 0.5, 0.3), 1.0, 100.0)

    result = simulate_silicone_color(base, 100.0, [colorant])

    assert result == pytest.approx((0.9, 0.5, 0.3), abs=2e-4)


@pytest.mark.parametrize("volume", [0.0, -1.0])
def test_non_positive_base_volume_is_rejected(volume: float) -> None:
    with pytest.raises(ValueError, match="volume"):
        simulate_silicone_color(WHITE, volume, [])


def test_non_positive_calibration_drops_are_rejected_when_used() -> None:
    colorant = CalibratedColorant((0.5, 0.5, 0.5), 0.0, 1.0)

    with pytest.raises(ValueError, match="Calibration"):
        simulate_silicone_color(WHITE, 100.0, [colorant])


def test_white_uses_the_shared_spectral_rule_and_reaches_opaque_at_calibration() -> (
    None
):
    white = CalibratedColorant(WHITE, 1.0, 100.0)

    result = simulate_silicone_appearance(
        (1.0, 0.9, 0.7),
        100.0,
        0.8,
        [white],
    )

    assert result.color == pytest.approx(WHITE, abs=1e-4)
    assert result.transparency == pytest.approx(0.0)


@pytest.mark.parametrize("colorants", [list, iter], ids=["list", "single-pass"])
def test_white_makes_another_dye_paler_below_its_calibration_concentration(
    colorants: Callable[[list[CalibratedColorant]], Iterable[CalibratedColorant]],
) -> None:
    blue = CalibratedColorant((0.2, 0.4, 0.8), 1.0, 100.0)
    half_strength_white = CalibratedColorant(WHITE, 1.0, 50.0)

    result = SimulatedSiliconeAppearance.from_mixture(
        WHITE,
        100.0,
        0.8,
        colorants([blue, half_strength_white]),
    )

    assert result.color == pytest.approx(
        (0.347639, 0.547790, 0.864344),
        abs=1e-6,
    )
    assert result.transparency == pytest.approx(0.0)


@pytest.mark.parametrize(
    "calibration",
    [
        (0.8, 0.2, 0.1),
        (0.1, 0.3, 0.8),
        (0.2, 0.2, 0.2),
    ],
)
def test_every_dye_reaches_opaque_at_its_calibration_concentration(
    calibration: tuple[float, float, float],
) -> None:
    dye = CalibratedColorant(calibration, 1.0, 100.0)

    result = SimulatedSiliconeAppearance.from_mixture(WHITE, 100.0, 0.7, [dye])

    assert result.color == pytest.approx(calibration, abs=1e-4)
    assert result.transparency == pytest.approx(0.0)


def test_half_strength_dye_halves_transparency() -> None:
    dye = CalibratedColorant((0.25, 0.64, 0.81), 1.0, 50.0)

    result = SimulatedSiliconeAppearance.from_mixture(WHITE, 100.0, 0.8, [dye])

    assert result.color == pytest.approx(
        (0.509796, 0.802891, 0.901514),
        abs=1e-6,
    )
    assert result.transparency == pytest.approx(0.4)


@pytest.mark.parametrize(
    ("hue_degrees", "lightness", "expected"),
    [
        (0.0, 0.5, (1.0, 0.0, 0.0)),
        (120.0, 0.5, (0.0, 1.0, 0.0)),
        (240.0, 0.5, (0.0, 0.0, 1.0)),
        (37.0, 1.0, WHITE),
        (212.0, 0.0, (0.0, 0.0, 0.0)),
    ],
)
def test_saturated_hsl_accepts_variable_lightness_but_always_maximum_saturation(
    hue_degrees: float,
    lightness: float,
    expected: tuple[float, float, float],
) -> None:
    color = saturated_hsl_to_linear_rgb(hue_degrees, lightness)

    assert color == pytest.approx(expected)
    if 0.0 < lightness < 1.0:
        _hue, saturation, actual_lightness = linear_rgb_to_hsl(color)
        assert saturation == pytest.approx(1.0)
        assert actual_lightness == pytest.approx(lightness)


def test_low_lightness_orange_represents_brown_without_losing_saturation() -> None:
    brown = saturated_hsl_to_linear_rgb(30.0, 0.25)

    assert brown == pytest.approx((0.214041, 0.050876, 0.0), abs=1e-6)
    hue, saturation, lightness = linear_rgb_to_hsl(brown)
    assert hue == pytest.approx(30.0)
    assert saturation == pytest.approx(1.0)
    assert lightness == pytest.approx(0.25)


def test_black_and_non_white_saturated_dyes_use_subtractive_darkening() -> None:
    black = CalibratedColorant(saturated_hsl_to_linear_rgb(0.0, 0.0), 1.0, 100.0)
    brown = CalibratedColorant(
        saturated_hsl_to_linear_rgb(30.0, 0.25),
        1.0,
        100.0,
    )

    black_result = SimulatedSiliconeAppearance.from_mixture(WHITE, 100.0, 0.8, [black])
    brown_result = SimulatedSiliconeAppearance.from_mixture(WHITE, 100.0, 0.8, [brown])

    assert max(black_result.color) < 1e-5
    assert brown_result.color == pytest.approx(brown.calibration_color, abs=1e-4)


def test_scene_linear_color_formats_are_copy_ready_srgb_values() -> None:
    color = (1.0, 0.0, 0.25)

    assert linear_rgb_to_srgb8(color) == (255, 0, 137)
    assert format_hex_color(color) == "#FF0089"
    assert format_linear_rgb(color) == "1.0000, 0.0000, 0.2500"


@pytest.mark.parametrize("hex_color", ["#804000", "804000", "#ffffff"])
def test_hex_color_input_round_trips_through_scene_linear_rgb(hex_color: str) -> None:
    parsed = parse_hex_color(hex_color)

    assert format_hex_color(parsed) == f"#{hex_color.removeprefix('#').upper()}"


def test_hex_color_input_accepts_surrounding_whitespace() -> None:
    assert format_hex_color(parse_hex_color(" \t#804000\n")) == "#804000"


@pytest.mark.parametrize(
    "invalid",
    [
        "",
        "#12345",
        "#GG0000",
        "#11223344",
        "#-10000",
        "#+10000",
        "#0 0 00",
        "#１２３４５６",
    ],
)
def test_invalid_hex_color_input_is_rejected(invalid: str) -> None:
    with pytest.raises(ValueError, match="RRGGBB"):
        parse_hex_color(invalid)
