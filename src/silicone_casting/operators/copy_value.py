"""Operator that copies a value shown in the sidebar to the clipboard."""

from typing import TYPE_CHECKING, override

import bpy
from bpy.props import StringProperty

from ._operator import OperatorReturn


class SILCAST_OT_copy_value(bpy.types.Operator):
    """Copy this value to the clipboard."""

    bl_idname = "silicone_casting.copy_value"
    bl_label = "Copy Value"
    # The button's text is the value itself, so the tooltip is the only place
    # that can tell the user a click copies it.
    bl_description = "Copy this value to the clipboard"
    # No "UNDO": nothing in the scene changes, so pushing an undo step would
    # make the next Ctrl+Z swallow the user's last real edit instead.
    # "INTERNAL" hides it from the F3 search, where it would be called
    # without a value to copy.
    bl_options = {"REGISTER", "INTERNAL"}

    if TYPE_CHECKING:
        value: str
    else:
        value: StringProperty(
            name="Value",
            default="",
        )

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        context.window_manager.clipboard = self.value
        self.report({"INFO"}, f"Copied {self.value}")
        return {"FINISHED"}
