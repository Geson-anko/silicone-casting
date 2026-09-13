"""JSON exchange for mixture tables and named color recipes."""

import json
import math
import os
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast, override

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from ..properties.color import SiliconeCastingColorProfile
from ..properties.settings import scene_settings
from ._operator import OperatorReturn

# Only recipe inputs belong in exchange files; material pointers and derived
# display values are deliberately excluded. Numeric limits match the RNA inputs.
type RecipeKind = Literal["MIXTURE", "COLORS"]
type _Rule = (
    type[bool] | type[str] | tuple[float, float] | dict[str, _Rule] | list[_Rule]
)
_FORMAT_VERSION = 2
_POSITIVE = (0.001, 3.4028234663852886e38)
_NONNEGATIVE = (0.0, 3.4028234663852886e38)
_COLORANT: dict[str, _Rule] = {
    "enabled": bool,
    "colorant_name": str,
    "calibration_hue_degrees": (0.0, 360.0),
    "calibration_lightness_percent": (0.0, 100.0),
    "calibration_drops_per_ml": _POSITIVE,
    "drops": _NONNEGATIVE,
}
_PROFILE: dict[str, _Rule] = {
    "profile_name": str,
    "base_volume_ml": _POSITIVE,
    "base_color": [(0.0, 1.0), (0.0, 1.0), (0.0, 1.0)],
    "transparency": (0.0, 1.0),
    "colorants": [_COLORANT],
}
_MIXTURE: dict[str, _Rule] = {
    "use_shared_density": bool,
    "density_a_g_per_ml": _POSITIVE,
    "density_b_g_per_ml": _POSITIVE,
    "ratio_a": _POSITIVE,
    "ratio_b": _POSITIVE,
    "parts": [
        {
            "enabled": bool,
            "selected": bool,
            "part_name": str,
            "volume_ml": _NONNEGATIVE,
        }
    ],
}
_SCHEMAS: dict[RecipeKind, dict[str, _Rule]] = {
    "MIXTURE": _MIXTURE,
    "COLORS": {"color_profiles": [_PROFILE]},
}
_KINDS = (
    ("MIXTURE", "Mixture", "Replace the mixture settings and all part rows on import"),
    ("COLORS", "Colors", "Append all imported color profiles to the existing profiles"),
)


def _validate(value: object, rule: _Rule, location: str) -> None:
    """Validate the complete document before changing any scene inputs."""
    if isinstance(rule, dict):
        if not isinstance(value, dict):
            raise ValueError(f"{location}: expected an object")
        data = cast(dict[str, object], value)
        if data.keys() != rule.keys():
            raise ValueError(f"{location}: missing or unknown fields")
        for key, child in rule.items():
            _validate(data[key], child, f"{location}.{key}")
    elif isinstance(rule, list):
        if not isinstance(value, list):
            raise ValueError(f"{location}: expected a list")
        items = cast(list[object], value)
        if len(rule) > 1 and len(items) != len(rule):
            raise ValueError(f"{location}: expected {len(rule)} components")
        for index, item in enumerate(items):
            _validate(item, rule[0] if len(rule) == 1 else rule[index], location)
    elif isinstance(rule, tuple):
        if type(value) not in (int, float):
            raise ValueError(f"{location}: expected a number")
        number = cast(float, value)
        if not rule[0] <= number <= rule[1] or not math.isfinite(number):
            raise ValueError(f"{location}: number out of range")
    elif type(value) is not rule:
        raise ValueError(f"{location}: invalid value type")
    elif rule is str:
        text = cast(str, value)
        if "\x00" in text:
            raise ValueError(f"{location}: embedded null character")
        try:
            text.encode("utf-8")
        except UnicodeEncodeError as error:
            raise ValueError(f"{location}: invalid Unicode text") from error


def _snapshot(
    source: bpy.types.PropertyGroup, schema: dict[str, _Rule]
) -> dict[str, object]:
    """Read the schema's named RNA fields at the JSON serialization
    boundary."""
    data: dict[str, object] = {}
    for key, rule in schema.items():
        value: object = getattr(source, key)
        if isinstance(rule, list):
            if isinstance(rule[0], dict):
                collection = cast(
                    "bpy.types.bpy_prop_collection_idprop[bpy.types.PropertyGroup]",
                    value,
                )
                value = [_snapshot(item, rule[0]) for item in collection]
            else:
                value = list(cast(Sequence[float], value))
        data[key] = value
    return data


def _restore(
    target: bpy.types.PropertyGroup,
    data: dict[str, object],
    schema: dict[str, _Rule],
) -> None:
    """Assign only fields that passed the complete document validation."""
    for key, rule in schema.items():
        value = data[key]
        if isinstance(rule, list) and isinstance(rule[0], dict):
            collection = cast(
                "bpy.types.bpy_prop_collection_idprop[bpy.types.PropertyGroup]",
                getattr(target, key),
            )
            # Color imports append; mixture rows replace the table.
            if key != "color_profiles":
                collection.clear()
            for item in cast(list[dict[str, object]], value):
                entry = collection.add()
                _restore(entry, item, rule[0])
                if key == "color_profiles":
                    cast(SiliconeCastingColorProfile, entry).ensure_preview_material()
        else:
            setattr(target, key, value)


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
        filepath = self.filepath
        try:
            if not filepath:
                raise ValueError("Choose a JSON file path")
            settings = scene_settings(context)
            source = settings.mixture if kind == "MIXTURE" else settings
            data = _snapshot(source, _SCHEMAS[kind])
            _validate(data, _SCHEMAS[kind], kind)
            document = {
                "format": "silicone_casting",
                "version": _FORMAT_VERSION,
                "kind": kind,
                "data": data,
            }
            Path(bpy.path.ensure_ext(filepath, ".json")).write_text(
                json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False)
                + "\n",
                encoding="utf-8",
            )
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
        kind = self.kind
        filepath = self.filepath
        try:
            document: object = json.loads(Path(filepath).read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                raise ValueError("Expected a recipe document")
            doc = cast(dict[str, object], document)
            if (
                doc.get("format") != "silicone_casting"
                or type(doc.get("version")) is not int
                or doc.get("version") != _FORMAT_VERSION
                or doc.get("kind") != kind
            ):
                raise ValueError("Unsupported recipe format, version, or type")
            data = doc.get("data")
            _validate(data, _SCHEMAS[kind], kind)
        except (OSError, ValueError, RecursionError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        settings = scene_settings(context)
        target = settings.mixture if kind == "MIXTURE" else settings
        _restore(target, cast(dict[str, object], data), _SCHEMAS[kind])
        if kind == "MIXTURE":
            settings.mixture.active_index = -1
            settings.mixture.selection_anchor = -1
        else:
            settings.color_profile_active_index = len(settings.color_profiles) - 1
        self.report({"INFO"}, "Recipes imported")
        return {"FINISHED"}
