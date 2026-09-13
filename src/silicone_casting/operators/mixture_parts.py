"""Blender entry points for the scene's mixture table operations."""

from typing import TYPE_CHECKING, override

import bpy
from bpy.props import EnumProperty, IntProperty

from ..properties.mixture import MoveDirection, SelectionMode
from ..properties.settings import scene_settings
from ._operator import OperatorReturn

_SELECTION_MODES = (
    ("REPLACE", "Replace", "Select only this row"),
    ("TOGGLE", "Toggle", "Toggle this row while preserving the others"),
    ("RANGE", "Range", "Select a continuous range from the anchor"),
    ("ADD_RANGE", "Add Range", "Add a continuous range from the anchor"),
)


class SILCAST_OT_add_mixture_part(bpy.types.Operator):
    """Add a manually entered part to the mixture table."""

    bl_idname = "silicone_casting.add_mixture_part"
    bl_label = "Add Mixture Part"
    bl_options = {"REGISTER", "UNDO"}

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        scene_settings(context).mixture.add_part()
        return {"FINISHED"}


class SILCAST_OT_remove_mixture_parts(bpy.types.Operator):
    """Remove every selected part from the mixture table."""

    bl_idname = "silicone_casting.remove_mixture_parts"
    bl_label = "Remove Selected Mixture Parts"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        return any(part.selected for part in scene_settings(context).mixture.parts)

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        scene_settings(context).mixture.remove_selected_parts()
        return {"FINISHED"}


class SILCAST_OT_move_mixture_parts(bpy.types.Operator):
    """Move selected mixture rows one position without reordering them."""

    bl_idname = "silicone_casting.move_mixture_parts"
    bl_label = "Move Selected Mixture Parts"
    bl_options = {"REGISTER", "UNDO"}

    if TYPE_CHECKING:
        direction: MoveDirection
    else:
        direction: EnumProperty(
            name="Direction",
            items=(
                ("UP", "Up", "Move selected rows up"),
                ("DOWN", "Down", "Move selected rows down"),
            ),
            default="UP",
            options={"HIDDEN", "SKIP_SAVE"},
        )

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        return any(part.selected for part in scene_settings(context).mixture.parts)

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        moved = scene_settings(context).mixture.move_selected_parts(self.direction)
        return {"FINISHED"} if moved else {"CANCELLED"}


class SILCAST_OT_select_mixture_part(bpy.types.Operator):
    """Select one mixture row using standard modifier-key semantics."""

    bl_idname = "silicone_casting.select_mixture_part"
    bl_label = "Select Mixture Part"
    bl_options = {"INTERNAL"}

    if TYPE_CHECKING:
        index: int
        mode: SelectionMode
    else:
        index: IntProperty(
            name="Index",
            default=0,
            min=0,
            options={"HIDDEN", "SKIP_SAVE"},
        )
        mode: EnumProperty(
            name="Mode",
            items=_SELECTION_MODES,
            default="REPLACE",
            options={"HIDDEN", "SKIP_SAVE"},
        )

    @override
    def invoke(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        if event.shift and event.ctrl:
            self.mode = "ADD_RANGE"
        elif event.shift:
            self.mode = "RANGE"
        elif event.ctrl:
            self.mode = "TOGGLE"
        else:
            self.mode = "REPLACE"
        return self.execute(context)

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        selected = scene_settings(context).mixture.select_part(self.index, self.mode)
        return {"FINISHED"} if selected else {"CANCELLED"}
