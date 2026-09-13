"""JSON exchange for mixture tables and named color recipes."""

import json
import math
import os
from pathlib import Path
from typing import Protocol, cast, override

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from ._color_adapter import ColorProfileValues
from ._color_material import ensure_color_preview_material
from ._operator import OperatorReturn

# Only recipe inputs belong in exchange files; material pointers and derived
# display values are deliberately excluded. Numeric limits match the RNA inputs.
type _Rule = (
    type[bool] | type[str] | tuple[float, float] | dict[str, _Rule] | list[_Rule]
)
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
    "mixture_use_shared_density": bool,
    "mixture_density_a_g_per_ml": _POSITIVE,
    "mixture_density_b_g_per_ml": _POSITIVE,
    "mixture_ratio_a": _POSITIVE,
    "mixture_ratio_b": _POSITIVE,
    "mixture_parts": [
        {
            "enabled": bool,
            "selected": bool,
            "part_name": str,
            "volume_ml": _NONNEGATIVE,
        }
    ],
}
_SCHEMAS: dict[str, dict[str, _Rule]] = {
    "MIXTURE": _MIXTURE,
    "COLORS": {"color_profiles": [_PROFILE]},
}
_KINDS = (
    ("MIXTURE", "Mixture", "Replace the mixture settings and all part rows on import"),
    ("COLORS", "Colors", "Append all imported color profiles to the existing profiles"),
)


class _Collection(Protocol):
    def clear(self) -> None: ...
    def add(self) -> bpy.types.PropertyGroup: ...


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


def _snapshot(source: object, schema: dict[str, _Rule]) -> dict[str, object]:
    data: dict[str, object] = {}
    for key, rule in schema.items():
        value = getattr(source, key)
        if isinstance(rule, list):
            if isinstance(rule[0], dict):
                value = [_snapshot(item, rule[0]) for item in value]
            else:
                value = list(value)
        data[key] = value
    return data


def _restore(target: object, data: dict[str, object], schema: dict[str, _Rule]) -> None:
    for key, rule in schema.items():
        value = data[key]
        if isinstance(rule, list) and isinstance(rule[0], dict):
            collection = cast(_Collection, getattr(target, key))
            # Color imports append; mixture rows replace the table.
            if key != "color_profiles":
                collection.clear()
            for item in cast(list[dict[str, object]], value):
                entry = collection.add()
                _restore(entry, item, rule[0])
                if key == "color_profiles":
                    ensure_color_preview_material(cast(ColorProfileValues, entry))
        else:
            setattr(target, key, value)


class _RecipeFileOperator:
    """Shared file selector properties for the two exchange operations."""

    filepath: StringProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="File Path",
        subtype="FILE_PATH",
        options={"SKIP_SAVE"},
    )
    filter_glob: StringProperty(  # pyright: ignore[reportInvalidTypeForm]
        default="*.json",
        options={"HIDDEN"},
    )
    kind: EnumProperty(  # pyright: ignore[reportInvalidTypeForm]
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
    check_existing: BoolProperty(  # pyright: ignore[reportInvalidTypeForm]
        default=True,
        options={"HIDDEN"},
    )

    @override
    def check(self, context: bpy.types.Context) -> bool:
        # Normalize before Blender asks whether to overwrite an existing file.
        filepath = cast(str, self.filepath)  # pyright: ignore[reportUnknownMemberType]
        normalized = bpy.path.ensure_ext(filepath, ".json")
        if os.path.basename(filepath) and normalized != filepath:
            self.filepath = normalized
            return True
        return False

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        kind = cast(str, self.kind)  # pyright: ignore[reportUnknownMemberType]
        filepath = cast(str, self.filepath)  # pyright: ignore[reportUnknownMemberType]
        try:
            if not filepath:
                raise ValueError("Choose a JSON file path")
            data = _snapshot(context.scene.silicone_casting, _SCHEMAS[kind])
            _validate(data, _SCHEMAS[kind], kind)
            document = {
                "format": "silicone_casting",
                "version": 1,
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
        kind = cast(str, self.kind)  # pyright: ignore[reportUnknownMemberType]
        filepath = cast(str, self.filepath)  # pyright: ignore[reportUnknownMemberType]
        try:
            document: object = json.loads(Path(filepath).read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                raise ValueError("Expected a recipe document")
            doc = cast(dict[str, object], document)
            if (
                doc.get("format") != "silicone_casting"
                or type(doc.get("version")) is not int
                or doc.get("version") != 1
                or doc.get("kind") != kind
            ):
                raise ValueError("Unsupported recipe format, version, or type")
            data = doc.get("data")
            _validate(data, _SCHEMAS[kind], kind)
        except (OSError, ValueError, RecursionError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        settings = context.scene.silicone_casting
        _restore(settings, cast(dict[str, object], data), _SCHEMAS[kind])
        if kind == "MIXTURE":
            settings.mixture_active_index = -1
            settings.mixture_selection_anchor = -1
        else:
            settings.color_profile_active_index = len(settings.color_profiles) - 1
        self.report({"INFO"}, "Recipes imported")
        return {"FINISHED"}
