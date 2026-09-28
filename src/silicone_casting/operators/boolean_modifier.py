"""Operators that add Boolean modifiers to the active mesh."""

from typing import TYPE_CHECKING, Final, Literal, NamedTuple, Self, cast, override

import bpy
from bpy.props import EnumProperty

from ..core.surface_cut import MIN_SURFACE_CUT_THICKNESS_MM, create_surface_cut
from ..core.units import mm_to_units
from ..properties.settings import BooleanSolver, scene_settings
from ._operator import OperatorReturn

type _BooleanOperation = Literal["DIFFERENCE", "UNION", "INTERSECT"]

#: Items of the ``operation`` enum, also used by the sidebar for its buttons.
OPERATION_ITEMS: Final = (
    ("DIFFERENCE", "Difference", "Subtract the operand from the active mesh"),
    ("UNION", "Union", "Combine the active mesh and operand"),
    ("INTERSECT", "Intersect", "Keep only the volume shared with the operand"),
)

_INVALID_INPUTS_MESSAGE: Final = (
    "Select an active mesh and choose a different mesh operand"
)


class _BooleanInputs(NamedTuple):
    """The mesh that receives the modifier and the mesh it operates with."""

    target: bpy.types.Object
    operand: bpy.types.Object

    @classmethod
    def from_context(cls, context: bpy.types.Context) -> Self | None:
        """Pair the active selected mesh with the scene's operand mesh.

        Returns:
            The pair, or ``None`` outside Object Mode, when the active object
            is not a selected mesh, or when the operand is missing, not a
            mesh, or the target itself.
        """
        target = context.active_object
        if (
            context.mode != "OBJECT"
            or target is None
            or target.type != "MESH"
            or not target.select_get()
        ):
            return None

        operand = scene_settings(context).boolean_operand
        if operand is None or operand.type != "MESH" or operand == target:
            return None
        return cls(target, operand)


def _add_boolean_modifier(
    inputs: _BooleanInputs,
    operation: _BooleanOperation,
    solver: BooleanSolver,
) -> bpy.types.BooleanModifier:
    """Add one Boolean modifier that uses the operand object."""
    modifier = cast(
        bpy.types.BooleanModifier,
        inputs.target.modifiers.new(name="Boolean", type="BOOLEAN"),
    )
    modifier.operand_type = "OBJECT"
    modifier.object = inputs.operand
    modifier.operation = operation
    modifier.solver = solver
    return modifier


class SILCAST_OT_add_boolean(bpy.types.Operator):
    """Add one Boolean modifier to the active selected mesh."""

    bl_idname = "silicone_casting.add_boolean"
    bl_label = "Add Boolean Modifier"
    bl_options = {"REGISTER", "UNDO"}

    if TYPE_CHECKING:
        operation: _BooleanOperation
    else:
        operation: EnumProperty(
            name="Operation",
            items=OPERATION_ITEMS,
            default="DIFFERENCE",
            options={"SKIP_SAVE"},
        )

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        return _BooleanInputs.from_context(context) is not None

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        inputs = _BooleanInputs.from_context(context)
        if inputs is None:
            self.report({"ERROR"}, _INVALID_INPUTS_MESSAGE)
            return {"CANCELLED"}

        solver = scene_settings(context).boolean_solver
        _add_boolean_modifier(inputs, self.operation, solver)

        self.report(
            {"INFO"}, f"Added {self.operation.title()} Boolean to {inputs.target.name}"
        )
        return {"FINISHED"}


class SILCAST_OT_add_surface_cut(bpy.types.Operator):
    """Add one modifier that solidifies and subtracts a cutting surface."""

    bl_idname = "silicone_casting.add_surface_cut"
    bl_label = "Add Surface Cut"
    bl_description = (
        "Add one Surface Cut modifier that solidifies the operand and subtracts "
        "it from the active mesh"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        return _BooleanInputs.from_context(context) is not None

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        inputs = _BooleanInputs.from_context(context)
        if inputs is None:
            self.report({"ERROR"}, _INVALID_INPUTS_MESSAGE)
            return {"CANCELLED"}

        target, surface = inputs
        scale_length = context.scene.unit_settings.scale_length
        create_surface_cut(
            target,
            surface,
            mm_to_units(scene_settings(context).surface_cut_thickness_mm, scale_length),
            minimum_thickness=mm_to_units(MIN_SURFACE_CUT_THICKNESS_MM, scale_length),
        )

        self.report(
            {"INFO"},
            f"Added surface cut from {surface.name} to {target.name}",
        )
        return {"FINISHED"}
