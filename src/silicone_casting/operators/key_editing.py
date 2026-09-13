"""Undoable creation and editing of persistent paired registration keys."""

from typing import TYPE_CHECKING, Protocol, cast, override

import bpy
from mathutils import Matrix, Vector

from ._operator import OperatorReturn
from .registration_keys import (
    KeySettings,
    add_key_modifier,
    create_key_operand,
    remove_key_operand,
    validate_key_modifier,
)

_SOCKET = "silcast_key_socket"
_NORMAL = "silcast_key_normal"


class _Settings(Protocol):
    key_active: bpy.types.Object | None
    key_mate: bpy.types.Object | None


def _settings(context: bpy.types.Context) -> _Settings:
    return cast(_Settings, context.scene.silicone_casting)


def is_registration_key(obj: bpy.types.Object | None) -> bool:
    """Recognize an editable pin by its persistent paired socket reference."""
    return obj is not None and obj.type == "MESH" and key_socket(obj) is not None


def key_socket(pin: bpy.types.Object) -> bpy.types.Object | None:
    """Resolve the socket even when either operand has been renamed."""
    socket = pin.get(_SOCKET)
    return socket if isinstance(socket, bpy.types.Object) else None


def load_key_settings(context: bpy.types.Context, pin: bpy.types.Object) -> None:
    """Select a persistent key and restore its editable settings to the
    sidebar."""
    if not is_registration_key(pin):
        raise ValueError("Select a registration key")
    props = _settings(context)
    KeySettings.from_pin(
        pin, scale_length=context.scene.unit_settings.scale_length
    ).restore(context)
    socket = key_socket(pin)
    assert socket is not None
    props.key_mate = socket.parent
    props.key_active = pin


def _record(
    pin: bpy.types.Object,
    socket: bpy.types.Object,
    normal: Vector,
    settings: KeySettings,
) -> None:
    assert pin.parent is not None
    pin[_SOCKET] = socket
    local_normal = pin.parent.matrix_world.to_3x3().transposed() @ normal
    pin[_NORMAL] = (local_normal.x, local_normal.y, local_normal.z)
    settings.store(pin)


def _modifier(
    target: bpy.types.Object, operand: bpy.types.Object
) -> bpy.types.BooleanModifier:
    for modifier in target.modifiers:
        if (
            isinstance(modifier, bpy.types.BooleanModifier)
            and modifier.object == operand
        ):
            return modifier
    raise ValueError("The registration key modifier has been removed")


def _pin(context: bpy.types.Context, name: str) -> bpy.types.Object:
    pin = bpy.data.objects.get(name) if name else _settings(context).key_active
    if not is_registration_key(pin):
        raise ValueError("Select a registration key")
    assert pin is not None
    return pin


def _update(
    context: bpy.types.Context,
    pin: bpy.types.Object,
    matrix: Matrix,
    normal: Vector,
    settings: KeySettings,
) -> None:
    socket = key_socket(pin)
    assert socket is not None
    operands = (pin, socket)
    if any(obj.parent is None for obj in operands):
        raise ValueError("Both mold halves must still exist")
    targets = [cast(bpy.types.Object, obj.parent) for obj in operands]
    modifiers = [_modifier(target, obj) for target, obj in zip(targets, operands)]
    dimensions = settings.dimensions()
    if normal.length_squared < 1e-20:
        raise ValueError("Surface normal must be nonzero")
    old_meshes = [cast(bpy.types.Mesh, obj.data) for obj in operands]
    old_matrices = [obj.matrix_world.copy() for obj in operands]
    new_meshes: list[bpy.types.Mesh] = []
    try:
        for obj, is_socket in zip(operands, (False, True)):
            mesh = dimensions.create_mesh(obj.name, socket=is_socket)
            new_meshes.append(mesh)
            obj.data = mesh
            obj.matrix_world = matrix
        context.view_layer.update()
        for target, obj, modifier in zip(targets, operands, modifiers):
            validate_key_modifier(context, target, obj, modifier)
    except (ValueError, RuntimeError):
        for obj, mesh, previous in zip(operands, old_meshes, old_matrices):
            obj.data = mesh
            obj.matrix_world = previous
        for mesh in new_meshes:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        context.view_layer.update()
        raise
    for mesh in old_meshes:
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    _record(pin, socket, normal, settings)
    _settings(context).key_active = pin


class SILCAST_OT_add_registration_key(bpy.types.Operator):
    """Create a paired key at a picked world-space surface point."""

    bl_idname = "silicone_casting.add_registration_key"
    bl_label = "Add Registration Key"
    bl_options = {"REGISTER", "UNDO"}

    if TYPE_CHECKING:
        location: tuple[float, float, float]
        normal: tuple[float, float, float]
    else:
        location: bpy.props.FloatVectorProperty(size=3, subtype="TRANSLATION")
        normal: bpy.props.FloatVectorProperty(
            size=3, default=(0, 0, 1), subtype="DIRECTION"
        )

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        target = context.active_object
        mate = _settings(context).key_mate
        return (
            context.mode == "OBJECT"
            and target is not None
            and target.type == "MESH"
            and mate is not None
            and mate.type == "MESH"
            and target != mate
            and cast(bpy.types.Library | None, target.library) is None
            and cast(bpy.types.Library | None, mate.library) is None
            and not is_registration_key(target)
            and target.name in context.view_layer.objects
            and mate.name in context.view_layer.objects
        )

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        if not self.poll(context):
            self.report({"ERROR"}, "Choose two different editable mesh halves")
            return {"CANCELLED"}
        target = context.active_object
        mate = _settings(context).key_mate
        assert target is not None and mate is not None
        created: list[bpy.types.Object] = []
        modifiers: list[tuple[bpy.types.Object, bpy.types.Modifier]] = []
        try:
            settings = KeySettings.from_context(context)
            dimensions = settings.dimensions()
            normal = Vector(self.normal)
            if normal.length_squared < 1e-20:
                raise ValueError("Surface normal must be nonzero")
            matrix = settings.placement(Vector(self.location), normal)
            for half, socket in ((target, False), (mate, True)):
                operand = create_key_operand(context, dimensions, socket=socket)
                created.append(operand)
                operand.parent = half
                operand.matrix_world = matrix
                modifier = add_key_modifier(
                    half, operand, "DIFFERENCE" if socket else "UNION"
                )
                modifiers.append((half, modifier))
                context.view_layer.update()
                validate_key_modifier(context, half, operand, modifier)
            pin, socket_obj = created
            _record(pin, socket_obj, normal, settings)
            for operand in created:
                operand.hide_set(True)
            _settings(context).key_active = pin
        except (ValueError, RuntimeError) as exc:
            for half, modifier in reversed(modifiers):
                half.modifiers.remove(modifier)
            for operand in created:
                remove_key_operand(operand)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class SILCAST_OT_move_registration_key(bpy.types.Operator):
    """Move an existing key, preserving its saved dimensions and orientation
    mode."""

    bl_idname = "silicone_casting.move_registration_key"
    bl_label = "Move Registration Key"
    bl_options = {"REGISTER", "UNDO"}

    if TYPE_CHECKING:
        key_name: str
    else:
        key_name: bpy.props.StringProperty()
    if TYPE_CHECKING:
        location: tuple[float, float, float]
        normal: tuple[float, float, float]
    else:
        location: bpy.props.FloatVectorProperty(size=3, subtype="TRANSLATION")
        normal: bpy.props.FloatVectorProperty(
            size=3, default=(0, 0, 1), subtype="DIRECTION"
        )

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        try:
            pin = _pin(context, self.key_name)
            settings = KeySettings.from_pin(
                pin, scale_length=context.scene.unit_settings.scale_length
            )
            normal = Vector(self.normal)
            matrix = settings.placement(Vector(self.location), normal)
            _update(context, pin, matrix, normal, settings)
            load_key_settings(context, pin)
        except (ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


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
            pin = _pin(context, self.key_name)
            if pin.parent is None:
                raise ValueError("The pin half has been removed")
            normal = (
                pin.parent.matrix_world.to_3x3().inverted_safe().transposed()
                @ Vector(pin[_NORMAL])
            )
            settings = KeySettings.from_context(context)
            matrix = settings.edited_placement(pin, normal)
            _update(context, pin, matrix, normal, settings)
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
            pin = _pin(context, self.key_name)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        socket = key_socket(pin)
        assert socket is not None
        _settings(context).key_active = None
        for operand in (pin, socket):
            parent = operand.parent
            if parent is not None:
                for modifier in list(parent.modifiers):
                    if (
                        isinstance(modifier, bpy.types.BooleanModifier)
                        and modifier.object == operand
                    ):
                        parent.modifiers.remove(modifier)
            remove_key_operand(operand)
        return {"FINISHED"}
