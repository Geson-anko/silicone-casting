"""Operators that edit and select the silicone mixture table."""

from typing import Literal, cast, override

import bpy
from bpy.props import EnumProperty, IntProperty

from ._operator import OperatorReturn

type _MoveDirection = Literal["UP", "DOWN"]
type _SelectionMode = Literal["REPLACE", "TOGGLE", "RANGE", "ADD_RANGE"]

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
        part = context.scene.silicone_casting.mixture_parts.add()
        part.enabled = True
        part.selected = False
        part.part_name = "Part"
        part.volume_ml = 0.0
        context.scene.silicone_casting.mixture_selection_anchor = -1
        context.scene.silicone_casting.mixture_active_index = -1
        return {"FINISHED"}


class SILCAST_OT_remove_mixture_parts(bpy.types.Operator):
    """Remove every selected part from the mixture table."""

    bl_idname = "silicone_casting.remove_mixture_parts"
    bl_label = "Remove Selected Mixture Parts"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        return any(
            part.selected for part in context.scene.silicone_casting.mixture_parts
        )

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        props = context.scene.silicone_casting
        parts = props.mixture_parts
        for index in range(len(parts) - 1, -1, -1):
            if parts[index].selected:
                parts.remove(index)
        props.mixture_selection_anchor = -1
        props.mixture_active_index = -1
        return {"FINISHED"}


class SILCAST_OT_move_mixture_parts(bpy.types.Operator):
    """Move selected mixture rows one position without reordering them."""

    bl_idname = "silicone_casting.move_mixture_parts"
    bl_label = "Move Selected Mixture Parts"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(  # pyright: ignore[reportInvalidTypeForm]
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
        return any(
            part.selected for part in context.scene.silicone_casting.mixture_parts
        )

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        props = context.scene.silicone_casting
        parts = props.mixture_parts
        direction = cast(
            _MoveDirection,
            self.direction,  # pyright: ignore[reportUnknownMemberType]
        )
        moved = False
        if direction == "UP":
            for index in range(1, len(parts)):
                if parts[index].selected and not parts[index - 1].selected:
                    parts.move(index, index - 1)
                    moved = True
        else:
            for index in range(len(parts) - 2, -1, -1):
                if parts[index].selected and not parts[index + 1].selected:
                    parts.move(index, index + 1)
                    moved = True
        props.mixture_selection_anchor = -1
        props.mixture_active_index = -1
        return {"FINISHED"} if moved else {"CANCELLED"}


class SILCAST_OT_select_mixture_part(bpy.types.Operator):
    """Select one mixture row using standard modifier-key semantics."""

    bl_idname = "silicone_casting.select_mixture_part"
    bl_label = "Select Mixture Part"
    bl_options = {"INTERNAL"}

    index: IntProperty(  # pyright: ignore[reportInvalidTypeForm]
        name="Index",
        default=0,
        min=0,
        options={"HIDDEN", "SKIP_SAVE"},
    )

    mode: EnumProperty(  # pyright: ignore[reportInvalidTypeForm]
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
            self.mode = "ADD_RANGE"  # pyright: ignore[reportUnknownMemberType]
        elif event.shift:
            self.mode = "RANGE"  # pyright: ignore[reportUnknownMemberType]
        elif event.ctrl:
            self.mode = "TOGGLE"  # pyright: ignore[reportUnknownMemberType]
        else:
            self.mode = "REPLACE"  # pyright: ignore[reportUnknownMemberType]
        return self.execute(context)

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        props = context.scene.silicone_casting
        parts = props.mixture_parts
        index = cast(int, self.index)  # pyright: ignore[reportUnknownMemberType]
        if index >= len(parts):
            return {"CANCELLED"}

        mode = cast(
            _SelectionMode,
            self.mode,  # pyright: ignore[reportUnknownMemberType]
        )
        anchor = props.mixture_selection_anchor
        previous_selection = [part.selected for part in parts]
        props.mixture_active_index = index
        for part, was_selected in zip(parts, previous_selection, strict=True):
            part.selected = was_selected

        if mode in {"RANGE", "ADD_RANGE"} and 0 <= anchor < len(parts):
            if mode == "RANGE":
                for part in parts:
                    part.selected = False
            first, last = sorted((anchor, index))
            for selected_index in range(first, last + 1):
                parts[selected_index].selected = True
            props.mixture_selection_anchor = anchor
            return {"FINISHED"}

        if mode != "TOGGLE":
            for part in parts:
                part.selected = False
            parts[index].selected = True
        else:
            parts[index].selected = not parts[index].selected
        props.mixture_selection_anchor = index
        return {"FINISHED"}
