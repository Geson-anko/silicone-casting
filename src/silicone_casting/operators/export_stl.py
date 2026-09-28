"""Operator that exports the selected meshes with fixed STL settings."""

import os
from typing import TYPE_CHECKING, Final, cast, override

import bpy
from bpy.props import BoolProperty, StringProperty

from ._operator import OperatorReturn, selected_meshes

_STL_EXTENSION: Final = ".stl"

# STL has no unit field; slicers read its numbers as millimetres, so one metre
# is written as 1000.
_MM_PER_METRE: Final = 1000.0

# Window-manager key remembering the folder of the last successful export.
_LAST_EXPORT_DIRECTORY_KEY: Final = "_silicone_casting_last_stl_export_directory"


def _default_filepath(context: bpy.types.Context) -> str:
    """Build the initial path from the last export folder and the mesh name.

    The file is named after the active object when it is one of the
    selected meshes, otherwise after the first selected mesh. Without an
    earlier export the folder is the one holding the .blend file.
    """
    meshes = selected_meshes(context)
    active = context.active_object
    source = active if active in meshes else meshes[0]
    directory = cast(str, context.window_manager.get(_LAST_EXPORT_DIRECTORY_KEY, ""))
    return os.path.join(
        directory or bpy.path.abspath("//"), f"{source.name}{_STL_EXTENSION}"
    )


class SILCAST_OT_export_stl(bpy.types.Operator):
    """Export the selected meshes as a millimetre-scaled STL file."""

    bl_idname = "silicone_casting.export_stl"
    bl_label = "Export STL"
    bl_description = (
        "Export only the selected meshes with modifiers applied, in millimetres"
    )

    if TYPE_CHECKING:
        filepath: str
        filter_glob: str
        check_existing: bool
    else:
        filepath: StringProperty(
            name="File Path",
            subtype="FILE_PATH",
            options={"SKIP_SAVE"},
        )
        filter_glob: StringProperty(
            default="*.stl",
            options={"HIDDEN"},
        )
        check_existing: BoolProperty(
            default=True,
            options={"HIDDEN"},
        )

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT" and bool(selected_meshes(context))

    @override
    def invoke(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        self.filepath = _default_filepath(context)
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    @override
    def check(self, context: bpy.types.Context) -> bool:
        # The file browser's overwrite warning must check the path that
        # execute() will actually write, so the extension is added here too.
        # A bare folder path is left alone until the user types a name.
        filepath = self.filepath
        normalized = bpy.path.ensure_ext(filepath, _STL_EXTENSION)
        if not os.path.basename(filepath) or normalized == filepath:
            return False
        self.filepath = normalized
        return True

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        # The user can change the selection or mode while the file browser is
        # open, so validate the context again when they confirm the path.
        if not self.poll(context):
            self.report({"ERROR"}, "Select at least one mesh in Object Mode")
            return {"CANCELLED"}

        filepath = self.filepath
        if not filepath:
            self.report({"ERROR"}, "Choose an STL file path")
            return {"CANCELLED"}

        filepath = bpy.path.ensure_ext(filepath, _STL_EXTENSION)
        result = bpy.ops.wm.stl_export(
            filepath=filepath,
            export_selected_objects=True,
            apply_modifiers=True,
            # Use the same metres-per-unit conversion as thickness and volume.
            # Blender ignores scale_length when its unit system is NONE, so
            # perform the conversion here and disable the exporter's own one.
            global_scale=_MM_PER_METRE * context.scene.unit_settings.scale_length,
            use_scene_unit=False,
        )
        if "FINISHED" not in result:
            return result

        context.window_manager[_LAST_EXPORT_DIRECTORY_KEY] = os.path.dirname(filepath)
        self.report({"INFO"}, f"Exported STL: {os.path.basename(filepath)}")
        return result
