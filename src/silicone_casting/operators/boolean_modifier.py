"""Operators that add Boolean modifiers to the active mesh."""

from typing import TYPE_CHECKING, Literal, cast, override

import bpy
from bpy.props import EnumProperty

from ..core.surface_cut import MIN_SURFACE_CUT_THICKNESS_MM, create_surface_cut
from ..core.units import mm_to_units
from ..properties.settings import BooleanSolver, scene_settings
from ._operator import OperatorReturn

type _BooleanOperation = Literal["DIFFERENCE", "UNION", "INTERSECT"]

_OPERATIONS = (
    ("DIFFERENCE", "Difference", "Subtract the operand from the active mesh"),
    ("UNION", "Union", "Combine the active mesh and operand"),
    ("INTERSECT", "Intersect", "Keep only the volume shared with the operand"),
)


def _boolean_inputs(
    context: bpy.types.Context,
) -> tuple[bpy.types.Object, bpy.types.Object] | None:
    """Return a valid active target and distinct mesh operand."""
    target = context.active_object
    if (
        context.mode != "OBJECT"
        or target is None
        or target.type != "MESH"
        or not target.select_get()
    ):
        return None

    props = scene_settings(context)
    operand = props.boolean_operand
    if operand is None or operand.type != "MESH" or operand == target:
        return None
    return target, operand


def _add_boolean_modifier(
    target: bpy.types.Object,
    operand: bpy.types.Object,
    operation: _BooleanOperation,
    solver: BooleanSolver,
) -> bpy.types.BooleanModifier:
    """Add and configure one object-operand Boolean modifier."""
    modifier = cast(
        bpy.types.BooleanModifier,
        target.modifiers.new(name="Boolean", type="BOOLEAN"),
    )
    modifier.operand_type = "OBJECT"
    modifier.object = operand
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
            items=_OPERATIONS,
            default="DIFFERENCE",
            options={"SKIP_SAVE"},
        )

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        return _boolean_inputs(context) is not None

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        inputs = _boolean_inputs(context)
        if inputs is None:
            self.report(
                {"ERROR"},
                "Select an active mesh and choose a different mesh operand",
            )
            return {"CANCELLED"}

        target, operand = inputs
        props = scene_settings(context)
        _add_boolean_modifier(target, operand, self.operation, props.boolean_solver)

        self.report(
            {"INFO"}, f"Added {self.operation.title()} Boolean to {target.name}"
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
        return _boolean_inputs(context) is not None

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        inputs = _boolean_inputs(context)
        if inputs is None:
            self.report(
                {"ERROR"},
                "Select an active mesh and choose a different mesh operand",
            )
            return {"CANCELLED"}

        target, surface = inputs
        props = scene_settings(context)
        thickness = mm_to_units(
            props.surface_cut_thickness_mm,
            context.scene.unit_settings.scale_length,
        )
        minimum_thickness = mm_to_units(
            MIN_SURFACE_CUT_THICKNESS_MM,
            context.scene.unit_settings.scale_length,
        )
        create_surface_cut(
            target,
            surface,
            thickness,
            minimum_thickness=minimum_thickness,
        )

        self.report(
            {"INFO"},
            f"Added surface cut from {surface.name} to {target.name}",
        )
        return {"FINISHED"}
