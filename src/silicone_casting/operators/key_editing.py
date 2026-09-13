"""Undoable creation and editing of persistent paired registration keys."""

from typing import TYPE_CHECKING, Protocol, cast, override

import bpy
from mathutils import Matrix, Vector

from ..core.registration_keys import KeyDimensions, create_key_mesh, placement_matrix
from ..core.units import mm_to_units
from ._operator import OperatorReturn
from .registration_keys import validate_key_modifier

_FIELDS = (
    "key_shape",
    "key_width_mm",
    "key_length_mm",
    "key_height_mm",
    "key_embed_mm",
    "key_clearance_mm",
    "key_depth_clearance_mm",
    "key_taper",
    "key_angle",
    "key_align_normal",
    "key_flip",
    "key_axis",
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
    for name in _FIELDS:
        setattr(props, name, pin[name])
    socket = key_socket(pin)
    assert socket is not None
    props.key_mate = socket.parent
    props.key_active = pin


def _values(context: bpy.types.Context) -> dict[str, str | float | bool]:
    props = _settings(context)
    return {name: getattr(props, name) for name in _FIELDS}


def _dimensions(
    context: bpy.types.Context, values: dict[str, str | float | bool]
) -> KeyDimensions:
    lengths = [
        mm_to_units(float(values[name]), context.scene.unit_settings.scale_length)
        for name in _FIELDS[1:7]
    ]
    dimensions = KeyDimensions(
        str(values["key_shape"]), *lengths, taper=float(values["key_taper"])
    )
    dimensions.validate()
    return dimensions


def _frame(
    location: Vector, normal: Vector, values: dict[str, str | float | bool]
) -> Matrix:
    direction = normal.copy()
    if not values["key_align_normal"]:
        direction = Vector(
            {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[str(values["key_axis"])]
        )
    if values["key_flip"]:
        direction.negate()
    return placement_matrix(location, direction, float(values["key_angle"]))


def _record(
    pin: bpy.types.Object,
    socket: bpy.types.Object,
    normal: Vector,
    values: dict[str, str | float | bool],
) -> None:
    assert pin.parent is not None
    pin[_SOCKET] = socket
    local_normal = pin.parent.matrix_world.to_3x3().transposed() @ normal
    pin[_NORMAL] = (local_normal.x, local_normal.y, local_normal.z)
    for name, value in values.items():
        pin[name] = value


def _remove_operand(obj: bpy.types.Object) -> None:
    mesh = cast(bpy.types.Mesh, obj.data)
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh.users == 0:
        bpy.data.meshes.remove(mesh)


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
    values: dict[str, str | float | bool],
) -> None:
    socket = key_socket(pin)
    assert socket is not None
    operands = (pin, socket)
    if any(obj.parent is None for obj in operands):
        raise ValueError("Both mold halves must still exist")
    targets = [cast(bpy.types.Object, obj.parent) for obj in operands]
    modifiers = [_modifier(target, obj) for target, obj in zip(targets, operands)]
    dimensions = _dimensions(context, values)
    if normal.length_squared < 1e-20:
        raise ValueError("Surface normal must be nonzero")
    old_meshes = [cast(bpy.types.Mesh, obj.data) for obj in operands]
    old_matrices = [obj.matrix_world.copy() for obj in operands]
    new_meshes: list[bpy.types.Mesh] = []
    try:
        for obj, is_socket in zip(operands, (False, True)):
            mesh = create_key_mesh(obj.name, dimensions, socket=is_socket)
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
    _record(pin, socket, normal, values)
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
            values = _values(context)
            dimensions = _dimensions(context, values)
            normal = Vector(self.normal)
            if normal.length_squared < 1e-20:
                raise ValueError("Surface normal must be nonzero")
            matrix = _frame(Vector(self.location), normal, values)
            for half, socket in ((target, False), (mate, True)):
                mesh = create_key_mesh(
                    "Registration Socket" if socket else "Registration Pin",
                    dimensions,
                    socket=socket,
                )
                operand = bpy.data.objects.new(mesh.name, mesh)
                created.append(operand)
                context.scene.collection.objects.link(operand)
                operand.parent = half
                operand.matrix_world = matrix
                operand.hide_render = True
                operand.hide_select = True
                modifier = cast(
                    bpy.types.BooleanModifier,
                    half.modifiers.new("Registration Key", "BOOLEAN"),
                )
                modifiers.append((half, modifier))
                modifier.operation = "DIFFERENCE" if socket else "UNION"
                modifier.solver = "EXACT"
                modifier.object = operand
                context.view_layer.update()
                validate_key_modifier(context, half, operand, modifier)
            pin, socket_obj = created
            _record(pin, socket_obj, normal, values)
            for operand in created:
                operand.hide_set(True)
            _settings(context).key_active = pin
        except (ValueError, RuntimeError) as exc:
            for half, modifier in reversed(modifiers):
                half.modifiers.remove(modifier)
            for operand in created:
                _remove_operand(operand)
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
            values = {name: pin[name] for name in _FIELDS}
            normal = Vector(self.normal)
            matrix = _frame(Vector(self.location), normal, values)
            _update(context, pin, matrix, normal, values)
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
            values = _values(context)
            location = pin.matrix_world.translation.copy()
            matrix = _frame(location, normal, values)
            if (
                values["key_align_normal"]
                and pin["key_align_normal"]
                and values["key_flip"] == pin["key_flip"]
            ):
                # Preserve the tangent carried by the half's transform. Rebuild
                # a rigid frame so dimensions remain physical lengths even if
                # the parent was scaled, then apply only the angle change.
                z = matrix.to_3x3() @ Vector((0, 0, 1))
                x = pin.matrix_world.to_3x3() @ Vector((1, 0, 0))
                x = (x - z * x.dot(z)).normalized()
                y = cast(Vector, z.cross(x))
                rotation = (
                    Matrix(((x.x, x.y, x.z), (y.x, y.y, y.z), (z.x, z.y, z.z)))
                    .transposed()
                    .to_4x4()
                )
                angle_change = float(values["key_angle"]) - float(pin["key_angle"])
                matrix = (
                    Matrix.Translation((location.x, location.y, location.z))
                    @ rotation
                    @ Matrix.Rotation(angle_change, 4, "Z")
                )
            _update(context, pin, matrix, normal, values)
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
            _remove_operand(operand)
        return {"FINISHED"}
