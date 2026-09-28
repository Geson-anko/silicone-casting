"""Unit conversion and display formatting for the addon's numbers.

The addon fixes the units it speaks to the user regardless of the
scene's unit settings: wall thickness is authored in millimetres and
volume is reported in millilitres, because those are the languages of 3D
printing and of casting silicone. Blender stores
both in its own unit system, so the conversions between the two live
here, together with the fixed-decimal formats used for volume and weight.

Nothing in this module may import ``bpy``: the scene's unit scale is
passed in as a plain number by the caller, which keeps every function
here a pure function that tier-1 tests can call without a scene.
"""


def mm_to_units(mm: float, scale_length: float) -> float:
    """Convert a length in millimetres to Blender units.

    Args:
        mm: Length to convert, in millimetres.
        scale_length: Metres represented by one Blender unit, taken from
            ``scene.unit_settings.scale_length``. Blender only accepts
            positive values, so no zero guard is needed here.

    Returns:
        The same length expressed in Blender units.
    """
    return mm / 1000 / scale_length


def units_to_mm(units: float, scale_length: float) -> float:
    """Convert a length in Blender units to millimetres.

    The inverse of :func:`mm_to_units`.

    Args:
        units: Length to convert, in Blender units.
        scale_length: Metres represented by one Blender unit, taken from
            ``scene.unit_settings.scale_length``.

    Returns:
        The same length expressed in millimetres.
    """
    return units * scale_length * 1000


def cubic_units_to_ml(volume: float, scale_length: float) -> float:
    """Convert a volume in cubic Blender units to millilitres.

    A millilitre is one cubic centimetre, and it is the unit written on
    measuring cups and on tins of casting silicone. The factor is cubed
    because a volume scales with the third power of a length: one Blender
    unit is ``scale_length`` metres, hence ``scale_length * 100``
    centimetres.

    Args:
        volume: Volume to convert, in cubic Blender units.
        scale_length: Metres represented by one Blender unit, taken from
            ``scene.unit_settings.scale_length``. Blender clamps that
            property to a positive value, and this is a multiplication
            either way, so no zero guard is needed here.

    Returns:
        The same volume expressed in millilitres.
    """
    return volume * (scale_length * 100.0) ** 3


def format_ml(volume_ml: float) -> str:
    """Format a volume in millilitres for display and for copying.

    This is the one place that decides what a measured volume looks like:
    the panel shows this string and the clipboard receives the very same
    string, so "what was copied" cannot drift from "what was shown".
    Fixed-point with two decimals is deliberate -- exponent notation and
    thousands separators would both stop the text from pasting into a
    spreadsheet as a number.

    Args:
        volume_ml: Volume in millilitres.

    Returns:
        The volume as a plain decimal with exactly two fractional
        digits, without a unit suffix.
    """
    return f"{volume_ml:.2f}"


def format_grams(weight_g: float) -> str:
    """Format a weight in grams for the mixture table.

    Args:
        weight_g: Weight in grams.

    Returns:
        A fixed two-decimal number without a unit or thousands separator.
    """
    return f"{weight_g:.2f}"
