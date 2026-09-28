"""JSON exchange for mixture tables and named color recipes."""

import json
import math
import os
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, cast, override

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from ..properties.settings import SiliconeCastingProperties, scene_settings
from ._operator import OperatorReturn

type RecipeKind = Literal["MIXTURE", "COLORS"]
type _Record = dict[str, object]
type _Collection = bpy.types.bpy_prop_collection_idprop[bpy.types.PropertyGroup]


class _Range(NamedTuple):
    """Inclusive bounds for a finite JSON number."""

    minimum: float
    maximum: float


# A schema rule describes one JSON value:
# - ``bool`` / ``str``: a value of exactly that type
# - ``_Range``: a finite int or float within the bounds
# - ``dict``: an object with exactly these keys, each checked by its own rule
# - one-element ``list``: a list of any length whose items follow that rule
# - longer ``list``: a fixed-length vector checked component by component
type _Rule = type[bool] | type[str] | _Range | dict[str, _Rule] | list[_Rule]

_FORMAT_NAME: Final = "silicone_casting"
# Version 1 files are rejected rather than migrated.
_FORMAT_VERSION: Final = 2
# Largest finite single-precision float, the ceiling of a Blender FloatProperty.
_FLOAT_MAX: Final = 3.4028234663852886e38
# The lower bound matches the ``min`` of the strictly positive RNA inputs.
_POSITIVE: Final = _Range(0.001, _FLOAT_MAX)
_NONNEGATIVE: Final = _Range(0.0, _FLOAT_MAX)
_UNIT: Final = _Range(0.0, 1.0)

# Only recipe inputs belong in exchange files; material pointers and derived
# display values are deliberately excluded. Numeric limits match the RNA inputs.
# Fields are restored in key order, so scalar inputs precede nested rows (a
# profile's base volume setter rescales any colorants already present).
_COLORANT: Final[dict[str, _Rule]] = {
    "enabled": bool,
    "colorant_name": str,
    "calibration_hue_degrees": _Range(0.0, 360.0),
    "calibration_lightness_percent": _Range(0.0, 100.0),
    "calibration_drops_per_ml": _POSITIVE,
    "drops": _NONNEGATIVE,
}
_PROFILE: Final[dict[str, _Rule]] = {
    "profile_name": str,
    "base_volume_ml": _POSITIVE,
    "base_color": [_UNIT, _UNIT, _UNIT],
    "transparency": _UNIT,
    "colorants": [_COLORANT],
}
_MIXTURE_PART: Final[dict[str, _Rule]] = {
    "enabled": bool,
    "selected": bool,
    "part_name": str,
    "volume_ml": _NONNEGATIVE,
}
_MIXTURE: Final[dict[str, _Rule]] = {
    "use_shared_density": bool,
    "density_a_g_per_ml": _POSITIVE,
    "density_b_g_per_ml": _POSITIVE,
    "ratio_a": _POSITIVE,
    "ratio_b": _POSITIVE,
    "parts": [_MIXTURE_PART],
}
_COLORS: Final[dict[str, _Rule]] = {"color_profiles": [_PROFILE]}
_SCHEMAS: Final[dict[RecipeKind, dict[str, _Rule]]] = {
    "MIXTURE": _MIXTURE,
    "COLORS": _COLORS,
}
_KINDS: Final = (
    ("MIXTURE", "Mixture", "Replace the mixture settings and all part rows on import"),
    ("COLORS", "Colors", "Append all imported color profiles to the existing profiles"),
)


def _validate(value: object, rule: _Rule, location: str) -> None:
    """Check a JSON value against its rule, naming the path of the first error.

    Raises:
        ValueError: If the value does not satisfy the rule.
    """
    if isinstance(rule, dict):
        _validate_object(value, rule, location)
    elif isinstance(rule, list):
        _validate_list(value, rule, location)
    elif isinstance(rule, _Range):
        _validate_number(value, rule, location)
    else:
        _validate_scalar(value, rule, location)


def _validate_object(value: object, rule: dict[str, _Rule], location: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{location}: expected an object")
    record = cast(_Record, value)
    if record.keys() != rule.keys():
        raise ValueError(f"{location}: missing or unknown fields")
    for key, child in rule.items():
        _validate(record[key], child, f"{location}.{key}")


def _validate_list(value: object, rule: list[_Rule], location: str) -> None:
    if not isinstance(value, list):
        raise ValueError(f"{location}: expected a list")
    items = cast(list[object], value)
    if len(rule) == 1:
        for item in items:
            _validate(item, rule[0], location)
        return
    if len(items) != len(rule):
        raise ValueError(f"{location}: expected {len(rule)} components")
    for item, component in zip(items, rule, strict=True):
        _validate(item, component, location)


def _validate_number(value: object, bounds: _Range, location: str) -> None:
    # ``type`` rather than ``isinstance`` so JSON booleans are not numbers.
    if type(value) not in (int, float):
        raise ValueError(f"{location}: expected a number")
    number = cast(float, value)
    if not bounds.minimum <= number <= bounds.maximum or not math.isfinite(number):
        raise ValueError(f"{location}: number out of range")


def _validate_scalar(
    value: object, expected: type[bool] | type[str], location: str
) -> None:
    if type(value) is not expected:
        raise ValueError(f"{location}: invalid value type")
    if expected is str:
        _validate_text(cast(str, value), location)


def _validate_text(text: str, location: str) -> None:
    """Reject text that Blender's C strings cannot hold."""
    if "\x00" in text:
        raise ValueError(f"{location}: embedded null character")
    # JSON may carry lone surrogates, which are not encodable as UTF-8.
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"{location}: invalid Unicode text") from error


def _is_row_list(rule: _Rule) -> bool:
    """Return whether a rule describes a collection of RNA records."""
    return isinstance(rule, list) and isinstance(rule[0], dict)


def _snapshot(source: bpy.types.PropertyGroup, schema: dict[str, _Rule]) -> _Record:
    """Read the schema's RNA fields into plain JSON-serializable values."""
    record: _Record = {}
    for key, rule in schema.items():
        value: object = getattr(source, key)
        if isinstance(rule, list):
            if _is_row_list(rule):
                row_schema = cast(dict[str, _Rule], rule[0])
                value = [_snapshot(row, row_schema) for row in cast(_Collection, value)]
            else:
                value = list(cast(Sequence[float], value))
        record[key] = value
    return record


def _assign(
    target: bpy.types.PropertyGroup, record: _Record, schema: dict[str, _Rule]
) -> None:
    """Assign validated fields in schema order, replacing nested row lists."""
    for key, rule in schema.items():
        value = record[key]
        if not _is_row_list(rule):
            setattr(target, key, value)
            continue
        row_schema = cast(dict[str, _Rule], cast(list[_Rule], rule)[0])
        rows = cast(_Collection, getattr(target, key))
        rows.clear()
        for row_record in cast(list[_Record], value):
            _assign(rows.add(), row_record, row_schema)


def _snapshot_recipe(settings: SiliconeCastingProperties, kind: RecipeKind) -> _Record:
    source = settings.mixture if kind == "MIXTURE" else settings
    return _snapshot(source, _SCHEMAS[kind])


def _replace_mixture(settings: SiliconeCastingProperties, record: _Record) -> None:
    """Overwrite the mixture inputs and rows with an imported table."""
    _assign(settings.mixture, record, _MIXTURE)
    settings.mixture.clear_selection_cursor()


def _append_color_profiles(
    settings: SiliconeCastingProperties, record: _Record
) -> None:
    """Append imported profiles, each with its own preview material."""
    for profile_record in cast(list[_Record], record["color_profiles"]):
        profile = settings.color_profiles.add()
        _assign(profile, profile_record, _PROFILE)
        profile.ensure_preview_material()
    settings.color_profile_active_index = len(settings.color_profiles) - 1


def _write_document(filepath: str, kind: RecipeKind, data: _Record) -> None:
    document = {
        "format": _FORMAT_NAME,
        "version": _FORMAT_VERSION,
        "kind": kind,
        "data": data,
    }
    text = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False)
    Path(filepath).write_text(text + "\n", encoding="utf-8")


def _read_recipe(filepath: str, kind: RecipeKind) -> _Record:
    """Load and fully validate a document before any scene input changes.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If the file is not a valid recipe of ``kind``.
        RecursionError: If the JSON nests deeper than Python can parse.
    """
    document: object = json.loads(Path(filepath).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("Expected a recipe document")
    header = cast(_Record, document)
    version = header.get("version")
    if (
        header.get("format") != _FORMAT_NAME
        # ``type`` check so ``2.0`` is not accepted as version 2.
        or type(version) is not int
        or version != _FORMAT_VERSION
        or header.get("kind") != kind
    ):
        raise ValueError("Unsupported recipe format, version, or type")
    data = header.get("data")
    _validate(data, _SCHEMAS[kind], kind)
    return cast(_Record, data)


class _RecipeFileOperator:
    """Shared file selector properties for the two exchange operations."""

    if TYPE_CHECKING:
        filepath: str
        filter_glob: str
        kind: RecipeKind
    else:
        filepath: StringProperty(
            name="File Path",
            subtype="FILE_PATH",
            options={"SKIP_SAVE"},
        )
        filter_glob: StringProperty(
            default="*.json",
            options={"HIDDEN"},
        )
        kind: EnumProperty(
            name="Recipe Type",
            items=_KINDS,
            default="MIXTURE",
        )

    def invoke(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        context.window_manager.fileselect_add(cast(bpy.types.Operator, self))
        return {"RUNNING_MODAL"}


class SILCAST_OT_export_recipes(_RecipeFileOperator, bpy.types.Operator):
    """Save the mixture table or all color profiles to a JSON file."""

    bl_idname = "silicone_casting.export_recipes"
    bl_label = "Export Recipes"
    if TYPE_CHECKING:
        check_existing: bool
    else:
        check_existing: BoolProperty(
            default=True,
            options={"HIDDEN"},
        )

    @override
    def check(self, context: bpy.types.Context) -> bool:
        # Normalize before Blender asks whether to overwrite an existing file.
        filepath = self.filepath
        normalized = bpy.path.ensure_ext(filepath, ".json")
        if os.path.basename(filepath) and normalized != filepath:
            self.filepath = normalized
            return True
        return False

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        kind = self.kind
        try:
            if not self.filepath:
                raise ValueError("Choose a JSON file path")
            data = _snapshot_recipe(scene_settings(context), kind)
            # Validate our own output too, so a file we write can be read back.
            _validate(data, _SCHEMAS[kind], kind)
            _write_document(bpy.path.ensure_ext(self.filepath, ".json"), kind, data)
        except (OSError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report({"INFO"}, "Recipes exported")
        return {"FINISHED"}


class SILCAST_OT_import_recipes(_RecipeFileOperator, bpy.types.Operator):
    """Load a mixture table or append color profiles from a JSON file."""

    bl_idname = "silicone_casting.import_recipes"
    bl_label = "Import Recipes"
    bl_options = {"REGISTER", "UNDO"}

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        try:
            data = _read_recipe(self.filepath, self.kind)
        except (OSError, ValueError, RecursionError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        settings = scene_settings(context)
        if self.kind == "MIXTURE":
            _replace_mixture(settings, data)
        else:
            _append_color_profiles(settings, data)
        self.report({"INFO"}, "Recipes imported")
        return {"FINISHED"}
