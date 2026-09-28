"""Undoable sidebar actions for the selected registration key pair."""

from typing import TYPE_CHECKING, override

import bpy

from ._operator import OperatorReturn
from .key_models import KeyPair, KeySettings


class SILCAST_OT_edit_registration_key(bpy.types.Operator):
    """Apply sidebar settings at the key's existing surface contact."""

    bl_idname = "silicone_casting.edit_registration_key"
    bl_label = "Update Selected Key"
    bl_options = {"REGISTER", "UNDO"}

    if TYPE_CHECKING:
        key_name: str
    else:
        key_name: bpy.props.StringProperty()

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        try:
            pair = KeyPair.from_context(context, self.key_name)
            pair.edit(context, KeySettings.from_context(context))
        except (ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class SILCAST_OT_delete_registration_key(bpy.types.Operator):
    """Remove only the selected paired operands and their Boolean modifiers."""

    bl_idname = "silicone_casting.delete_registration_key"
    bl_label = "Delete Selected Key"
    bl_options = {"REGISTER", "UNDO"}

    if TYPE_CHECKING:
        key_name: str
    else:
        key_name: bpy.props.StringProperty()

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        try:
            KeyPair.from_context(context, self.key_name).delete(context)
        except (ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}
