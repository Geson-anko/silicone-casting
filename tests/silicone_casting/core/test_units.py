"""Unit conversion and display formatting, both ways.

Lengths go in as millimetres (``mm / 1000 / scale_length``) and volumes
come out as cubic centimetres (``volume * (scale_length * 100) ** 3``),
which is also the millilitre the user reads off a measuring cup. Every
expected value below is derived from those definitions in the spec, not
read off a run: 3 mm is 0.003 m, and a cubic metre is a million cubic
centimetres.
"""

import ast
import inspect
from types import ModuleType

import pytest

import silicone_casting.core.units as units_module
from silicone_casting.core.units import (
    cubic_units_to_ml,
    format_grams,
    format_ml,
    mm_to_units,
)


def _imported_module_names(module: ModuleType) -> set[str]:
    """Top-level names of every module imported anywhere in *module*."""
    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return {name.split(".")[0] for name in names}


class TestMmToUnits:
    def test_three_millimetres_is_three_thousandths_of_a_unit_by_default(self) -> None:
        # scale_length 1.0 is Blender's default: 1 unit is 1 metre.
        assert mm_to_units(3.0, 1.0) == pytest.approx(0.003, rel=1e-12)

    def test_three_millimetres_is_three_units_when_a_unit_is_a_millimetre(self) -> None:
        # Spec S-7: with scale_length 0.001 a unit *is* a millimetre, so
        # the same physical wall must come out as 3.0 units. The value the
        # user typed never changes; only its unit expression does.
        assert mm_to_units(3.0, 0.001) == pytest.approx(3.0, rel=1e-12)

    def test_zero_millimetres_is_zero_units(self) -> None:
        assert mm_to_units(0.0, 1.0) == 0.0


#: A cubic metre is (100 cm) ** 3, so this is what one cubic Blender unit
#: is worth in a scene left at the default scale_length of 1.0.
ML_PER_CUBIC_UNIT = 100.0**3

#: The 2 cm cube of the spec (6.3), 0.02 BU a side in a default scene.
TWO_CM_CUBE_IN_UNITS = 0.02**3

#: The same physical cube in a scene where one unit is a millimetre.
TWO_CM_CUBE_IN_MILLIMETRE_UNITS = 20.0**3


class TestCubicUnitsToCm3:
    def test_one_cubic_unit_is_a_million_cubic_centimetres_by_default(self) -> None:
        # AC-1. scale_length 1.0 makes a unit a metre, and a cubic metre
        # is a million cubic centimetres.
        assert cubic_units_to_ml(1.0, 1.0) == pytest.approx(
            ML_PER_CUBIC_UNIT, rel=1e-12
        )

    def test_a_two_centimetre_cube_measures_eight_millilitres(self) -> None:
        # AC-2 / G-1: 8 mL is the number the user pours.
        assert cubic_units_to_ml(TWO_CM_CUBE_IN_UNITS, 1.0) == pytest.approx(
            8.0, rel=1e-9
        )

    def test_the_same_cube_measures_the_same_in_a_millimetre_scene(self) -> None:
        # AC-3 / S-7: with scale_length 0.001 a unit *is* a millimetre, so
        # a 20-unit cube is the same physical object as the 0.02-unit one
        # above and must yield the same millilitres. Only the scene's unit
        # expression changed, never the material in the mould.
        assert cubic_units_to_ml(
            TWO_CM_CUBE_IN_MILLIMETRE_UNITS, 0.001
        ) == pytest.approx(8.0, rel=1e-6)

    def test_no_volume_converts_to_no_volume(self) -> None:
        # AC-4.
        assert cubic_units_to_ml(0.0, 1.0) == 0.0

    def test_doubling_the_scene_scale_multiplies_the_volume_by_eight(self) -> None:
        # AC-5: volume is a third-degree quantity in a length, so the
        # conversion has to cube scale_length rather than scale by it.
        # 8 * 1e6 is the AC-1 value with each axis twice as long.
        assert cubic_units_to_ml(1.0, 2.0) == pytest.approx(
            8.0 * ML_PER_CUBIC_UNIT, rel=1e-12
        )


class TestFormatCm3:
    def test_a_whole_number_of_millilitres_still_shows_two_decimals(self) -> None:
        # AC-7 / FR-42: the column stays readable because the width of the
        # number never changes with the value.
        assert format_ml(8.0) == "8.00"

    def test_zero_is_written_out_rather_than_left_blank(self) -> None:
        # AC-8: "--" means not measured (FR-45); a measured zero is 0.00.
        assert format_ml(0.0) == "0.00"

    def test_a_five_figure_volume_carries_no_thousands_separator(self) -> None:
        # AC-9 / FR-42: a comma would stop a spreadsheet from reading the
        # pasted text as a number, which is the point of the copy button.
        assert format_ml(72216.7225) == "72216.72"

    def test_a_very_large_volume_does_not_collapse_into_exponent_notation(
        self,
    ) -> None:
        # AC-10 / FR-42: "1.2e+09" would paste as text, not as a number.
        formatted = format_ml(1.2e9)

        assert "e" not in formatted
        assert formatted == "1200000000.00"

    def test_a_volume_far_below_the_resolution_reads_as_zero(self) -> None:
        # AC-11 / L-4: two decimals is the deliberate floor. Reading
        # silicone to a hundredth of a millilitre has no bench meaning, so
        # a speck of a part showing 0.00 is the accepted cost.
        assert format_ml(1e-7) == "0.00"


class TestFormatGrams:
    def test_grams_always_have_two_decimal_places(self) -> None:
        assert format_grams(55.0) == "55.00"

    def test_grams_have_no_unit_or_thousands_separator(self) -> None:
        assert format_grams(12345.678) == "12345.68"


class TestUnitsModuleStandsAloneFromBlender:
    def test_the_conversion_module_does_not_import_bpy(self) -> None:
        # NFR-1 / FR-40 / AC-6: the conversions are pure arithmetic over a
        # scale_length the caller passes in. Importing bpy here would let
        # the scene leak back into functions that must not read it.
        assert "bpy" not in _imported_module_names(units_module)
