"""Preview and attach paired registration keys to separated mold halves."""

from collections.abc import Iterable
from dataclasses import dataclass
from math import pi
from typing import Literal, Protocol, Self, cast, override

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from ..core.registration_keys import KeyDimensions, placement_matrix
from ..core.volume import world_volume
from ._operator import OperatorReturn


@dataclass(frozen=True)
class KeySettings:
    """Snapshot sidebar or saved key values without changing their units."""

    _shape: str
    _width_mm: float
    _length_mm: float
    _height_mm: float
    _embed_mm: float
    _clearance_mm: float
    _depth_clearance_mm: float
    _taper: float
    _angle: float
    _align_normal: bool
    _flip: bool
    _axis: str
    _scale_length: float

    @classmethod
    def from_context(cls, context: bpy.types.Context) -> Self:
        """Read the sidebar once for one key operation."""
        props = _settings(context)
        return cls(
            _shape=props.key_shape,
            _width_mm=props.key_width_mm,
            _length_mm=props.key_length_mm,
            _height_mm=props.key_height_mm,
            _embed_mm=props.key_embed_mm,
            _clearance_mm=props.key_clearance_mm,
            _depth_clearance_mm=props.key_depth_clearance_mm,
            _taper=props.key_taper,
            _angle=props.key_angle,
            _align_normal=props.key_align_normal,
            _flip=props.key_flip,
            _axis=props.key_axis,
            _scale_length=context.scene.unit_settings.scale_length,
        )

    @classmethod
    def from_pin(cls, pin: bpy.types.Object, *, scale_length: float) -> Self:
        """Read persisted inputs using the scene's current unit scale."""
        return cls(
            _shape=cast(str, pin["key_shape"]),
            _width_mm=cast(float, pin["key_width_mm"]),
            _length_mm=cast(float, pin["key_length_mm"]),
            _height_mm=cast(float, pin["key_height_mm"]),
            _embed_mm=cast(float, pin["key_embed_mm"]),
            _clearance_mm=cast(float, pin["key_clearance_mm"]),
            _depth_clearance_mm=cast(float, pin["key_depth_clearance_mm"]),
            _taper=cast(float, pin["key_taper"]),
            _angle=cast(float, pin["key_angle"]),
            _align_normal=cast(bool, pin["key_align_normal"]),
            _flip=cast(bool, pin["key_flip"]),
            _axis=cast(str, pin["key_axis"]),
            _scale_length=scale_length,
        )

    def dimensions(self) -> KeyDimensions:
        """Convert saved millimetres into validated physical dimensions."""
        dimensions = KeyDimensions.from_mm(
            self._shape,
            self._width_mm,
            self._length_mm,
            self._height_mm,
            self._embed_mm,
            self._clearance_mm,
            self._depth_clearance_mm,
            scale_length=self._scale_length,
            taper=self._taper,
        )
        dimensions.validate()
        return dimensions

    def placement(self, location: Vector, normal: Vector) -> Matrix:
        """Orient the key along the face normal or the selected world axis."""
        direction = normal.copy()
        if not self._align_normal:
            direction = Vector(
                {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[self._axis]
            )
        if self._flip:
            direction.negate()
        return placement_matrix(location, direction, self._angle)

    def edited_placement(self, pin: bpy.types.Object, normal: Vector) -> Matrix:
        """Preserve a transformed key's tangent when its alignment is
        unchanged."""
        location = pin.matrix_world.translation.copy()
        matrix = self.placement(location, normal)
        if not (
            self._align_normal
            and cast(bool, pin["key_align_normal"])
            and self._flip == cast(bool, pin["key_flip"])
        ):
            return matrix
        # Rebuild a rigid frame so scaling the half does not scale key dimensions.
        z = matrix.to_3x3() @ Vector((0, 0, 1))
        x = pin.matrix_world.to_3x3() @ Vector((1, 0, 0))
        x = (x - z * x.dot(z)).normalized()
        y = cast(Vector, z.cross(x))
        rotation = (
            Matrix(((x.x, x.y, x.z), (y.x, y.y, y.z), (z.x, z.y, z.z)))
            .transposed()
            .to_4x4()
        )
        angle_change = self._angle - cast(float, pin["key_angle"])
        return (
            Matrix.Translation((location.x, location.y, location.z))
            @ rotation
            @ Matrix.Rotation(angle_change, 4, "Z")
        )

    def store(self, pin: bpy.types.Object) -> None:
        """Keep original millimetre inputs for later edits and scene
        rescaling."""
        for name, value in self._stored_values().items():
            pin[name] = value

    def restore(self, context: bpy.types.Context) -> None:
        """Copy saved inputs to the sidebar in their persisted field order."""
        props = context.scene.silicone_casting
        for name, value in self._stored_values().items():
            setattr(props, name, value)

    def _stored_values(self) -> dict[str, str | float | bool]:
        return {
            "key_shape": self._shape,
            "key_width_mm": self._width_mm,
            "key_length_mm": self._length_mm,
            "key_height_mm": self._height_mm,
            "key_embed_mm": self._embed_mm,
            "key_clearance_mm": self._clearance_mm,
            "key_depth_clearance_mm": self._depth_clearance_mm,
            "key_taper": self._taper,
            "key_angle": self._angle,
            "key_align_normal": self._align_normal,
            "key_flip": self._flip,
            "key_axis": self._axis,
        }


class _Settings(Protocol):
    key_mate: bpy.types.Object | None
    key_shape: str
    key_width_mm: float
    key_length_mm: float
    key_height_mm: float
    key_embed_mm: float
    key_clearance_mm: float
    key_depth_clearance_mm: float
    key_taper: float
    key_angle: float
    key_align_normal: bool
    key_flip: bool
    key_axis: str
    key_preview_pin: bpy.types.Object | None
    key_preview_socket: bpy.types.Object | None
    key_preview_target: bpy.types.Object | None
    key_preview_mate: bpy.types.Object | None


def _settings(context: bpy.types.Context) -> _Settings:
    return cast(_Settings, context.scene.silicone_casting)


def create_key_operand(
    context: bpy.types.Context, dimensions: KeyDimensions, *, socket: bool
) -> bpy.types.Object:
    """Link one hidden-from-render operand for preview or persistent
    placement."""
    mesh = dimensions.create_mesh(
        "Registration Socket" if socket else "Registration Pin", socket=socket
    )
    obj = bpy.data.objects.new(mesh.name, mesh)
    try:
        context.scene.collection.objects.link(obj)
        obj.hide_render = True
        obj.hide_select = True
    except (ValueError, RuntimeError):
        remove_key_operand(obj)
        raise
    return obj


def remove_key_operand(obj: bpy.types.Object) -> None:
    """Remove a key helper and release its mesh when no other object uses
    it."""
    mesh = cast(bpy.types.Mesh, obj.data)
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def add_key_modifier(
    target: bpy.types.Object,
    operand: bpy.types.Object,
    operation: Literal["UNION", "DIFFERENCE"],
) -> bpy.types.BooleanModifier:
    """Append the Exact Boolean shared by preview commits and direct
    placement."""
    modifier = cast(
        bpy.types.BooleanModifier, target.modifiers.new("Registration Key", "BOOLEAN")
    )
    try:
        modifier.operation = operation
        modifier.solver = "EXACT"
        modifier.object = operand
    except (ValueError, RuntimeError):
        target.modifiers.remove(modifier)
        raise
    return modifier


def _clear_preview(props: _Settings) -> None:
    for obj in (props.key_preview_pin, props.key_preview_socket):
        if obj is not None:
            remove_key_operand(obj)
    props.key_preview_pin = None
    props.key_preview_socket = None
    props.key_preview_target = None
    props.key_preview_mate = None


def _nearest_surface(
    context: bpy.types.Context, target: bpy.types.Object
) -> tuple[Vector, Vector]:
    evaluated = target.evaluated_get(context.evaluated_depsgraph_get())
    mesh = cast(bpy.types.Mesh | None, evaluated.to_mesh())
    try:
        if mesh is None or not mesh.polygons:
            raise ValueError("The active half has no surface")
        points = [evaluated.matrix_world @ v.co for v in mesh.vertices]
        surface = BVHTree.FromPolygons(
            [(v.x, v.y, v.z) for v in points],
            [tuple(cast(Iterable[int], p.vertices)) for p in mesh.polygons],
        )
        position, normal, _, _ = surface.find_nearest(context.scene.cursor.location)
        if position is None or normal is None:
            raise ValueError("No nearby surface found")
        if evaluated.matrix_world.to_3x3().determinant() < 0:
            normal.negate()
        return position, normal
    finally:
        evaluated.to_mesh_clear()


def _preview_matrix(context: bpy.types.Context, target: bpy.types.Object) -> Matrix:
    props = _settings(context)
    position, normal = _nearest_surface(context, target)
    if props.key_align_normal:
        if props.key_flip:
            normal.negate()
        return placement_matrix(position, normal, props.key_angle)
    matrix = context.scene.cursor.matrix.copy()
    matrix.translation = position
    if props.key_flip:
        matrix = matrix @ Matrix.Rotation(pi, 4, "X")
    return matrix @ Matrix.Rotation(props.key_angle, 4, "Z")


def _create_preview(
    context: bpy.types.Context, dimensions: KeyDimensions, matrix: Matrix
) -> None:
    props = _settings(context)
    _clear_preview(props)
    props.key_preview_target = context.active_object
    props.key_preview_mate = props.key_mate
    for socket in (False, True):
        obj = create_key_operand(context, dimensions, socket=socket)
        obj.matrix_world = matrix
        obj.display_type = "WIRE" if socket else "SOLID"
        obj.show_in_front = True
        obj.color = (0.1, 0.6, 1.0, 1.0) if socket else (1.0, 0.5, 0.05, 1.0)  # pyright: ignore[reportAttributeAccessIssue]
        if socket:
            props.key_preview_socket = obj
        else:
            props.key_preview_pin = obj


class SILCAST_OT_preview_registration_key(bpy.types.Operator):
    """Snap a paired preview to the face nearest the 3D cursor."""

    bl_idname = "silicone_casting.preview_registration_key"
    bl_label = "Preview / Update Key"
    bl_description = "Place a key on the active half, nearest the 3D cursor; choose the socket half below"
    bl_options = {"REGISTER", "UNDO"}

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
            and mate != target
            and target in list(context.scene.objects)
            and mate in list(context.scene.objects)
            and cast(bpy.types.Library | None, target.library) is None
            and cast(bpy.types.Library | None, mate.library) is None
        )

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        if not self.poll(context):
            self.report({"ERROR"}, "Choose two different editable mesh halves")
            return {"CANCELLED"}
        props = _settings(context)
        target = context.active_object
        assert target is not None
        if target in (props.key_preview_pin, props.key_preview_socket):
            self.report({"ERROR"}, "Select the mold half, not its preview")
            return {"CANCELLED"}
        try:
            matrix = _preview_matrix(context, target)
            dimensions = KeySettings.from_context(context).dimensions()
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        _create_preview(context, dimensions, matrix)
        self.report(
            {"INFO"},
            "Preview ready; move the cursor or change settings and update, then confirm",
        )
        return {"FINISHED"}


class SILCAST_OT_cancel_registration_key(bpy.types.Operator):
    """Remove the pending preview without changing either mold half."""

    bl_idname = "silicone_casting.cancel_registration_key"
    bl_label = "Cancel Preview"
    bl_options = {"REGISTER", "UNDO"}

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        _clear_preview(_settings(context))
        return {"FINISHED"}


def validate_key_modifier(
    context: bpy.types.Context,
    target: bpy.types.Object,
    operand: bpy.types.Object,
    modifier: bpy.types.BooleanModifier,
) -> None:
    """Validate overlap and closed output while preserving modifier order."""
    was_visible = modifier.show_viewport
    try:
        modifier.show_viewport = False
        before = world_volume(target, context.evaluated_depsgraph_get())
        tool_volume = world_volume(operand, context.evaluated_depsgraph_get())
        modifier.show_viewport = True
        if before is None or before <= 0 or tool_volume is None:
            raise ValueError("Mold halves must be closed solids")
        after = world_volume(target, context.evaluated_depsgraph_get())
        if after is None or after <= 0:
            raise ValueError("The key must leave a closed mold half")
        tolerance = tool_volume * 1e-5
        change = after - before if modifier.operation == "UNION" else before - after
        if change <= tolerance or (
            modifier.operation == "UNION" and change >= tool_volume - tolerance
        ):
            raise ValueError(
                "Key must overlap both halves and protrude from the pin half; "
                "adjust position or direction"
            )
    finally:
        modifier.show_viewport = was_visible


class SILCAST_OT_commit_registration_key(bpy.types.Operator):
    """Attach the displayed pair as editable Boolean modifiers."""

    bl_idname = "silicone_casting.commit_registration_key"
    bl_label = "Confirm Key"
    bl_description = (
        "Add the displayed pin and socket as Boolean modifiers; repeat for more keys"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        p = _settings(context)
        return context.mode == "OBJECT" and all(
            obj is not None
            for obj in (
                p.key_preview_pin,
                p.key_preview_socket,
                p.key_preview_target,
                p.key_preview_mate,
            )
        )

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        if not self.poll(context):
            self.report({"ERROR"}, "Create a preview first")
            return {"CANCELLED"}
        p = _settings(context)
        pairs = (
            (p.key_preview_target, p.key_preview_pin, "UNION"),
            (p.key_preview_mate, p.key_preview_socket, "DIFFERENCE"),
        )
        created: list[tuple[bpy.types.Object, bpy.types.Modifier]] = []
        try:
            for target, operand, operation in pairs:
                assert target is not None and operand is not None
                if target.name not in context.view_layer.objects:
                    raise ValueError(
                        "Both mold halves must be in the current view layer"
                    )
                modifier = add_key_modifier(
                    target, operand, cast(Literal["UNION", "DIFFERENCE"], operation)
                )
                created.append((target, modifier))
                validate_key_modifier(context, target, operand, modifier)
        except (ValueError, RuntimeError) as exc:
            for target, modifier in reversed(created):
                target.modifiers.remove(modifier)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        for target, operand, _ in pairs:
            assert target is not None and operand is not None
            matrix = operand.matrix_world.copy()
            operand.parent = target
            operand.matrix_world = matrix
            operand.hide_set(True)
            operand.show_in_front = False
        p.key_preview_pin = None
        p.key_preview_socket = None
        p.key_preview_target = None
        p.key_preview_mate = None
        self.report({"INFO"}, "Added pin and socket modifiers")
        return {"FINISHED"}
