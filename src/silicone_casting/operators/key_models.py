"""Settings and transactional ownership of paired registration key operands."""

from dataclasses import dataclass
from typing import Literal, Self, cast

import bpy
from mathutils import Matrix, Vector

from ..core.registration_keys import KeyDimensions, placement_matrix
from ..core.volume import world_volume
from ..properties.settings import scene_settings

_SOCKET = "silcast_key_socket"
_NORMAL = "silcast_key_normal"


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
        props = scene_settings(context)
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
        props = scene_settings(context)
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


@dataclass(frozen=True)
class KeyPair:
    """Own a pin, its socket, and changes to their paired Boolean modifiers."""

    _pin: bpy.types.Object
    _socket: bpy.types.Object

    @property
    def pin(self) -> bpy.types.Object:
        """The selectable pin used to identify this pair in the sidebar."""
        return self._pin

    @property
    def socket(self) -> bpy.types.Object:
        """The matching socket operand parented to the opposite mold half."""
        return self._socket

    @classmethod
    def from_pin(cls, pin: bpy.types.Object | None) -> Self | None:
        """Resolve a saved pair without relying on mutable object names."""
        if pin is None or pin.type != "MESH":
            return None
        socket = pin.get(_SOCKET)
        return cls(pin, socket) if isinstance(socket, bpy.types.Object) else None

    @classmethod
    def from_context(cls, context: bpy.types.Context, key_name: str = "") -> Self:
        """Require the named pair or the sidebar's selected key."""
        pin = (
            bpy.data.objects.get(key_name)
            if key_name
            else scene_settings(context).key_active
        )
        pair = cls.from_pin(pin)
        if pair is None:
            raise ValueError("Select a registration key")
        return pair

    @classmethod
    def can_create(cls, context: bpy.types.Context) -> bool:
        """Accept two distinct editable mesh halves in the current view
        layer."""
        target = context.active_object
        mate = scene_settings(context).key_mate
        return (
            context.mode == "OBJECT"
            and target is not None
            and target.type == "MESH"
            and mate is not None
            and mate.type == "MESH"
            and target != mate
            and cast(bpy.types.Library | None, target.library) is None
            and cast(bpy.types.Library | None, mate.library) is None
            and cls.from_pin(target) is None
            and target.name in context.view_layer.objects
            and mate.name in context.view_layer.objects
        )

    @classmethod
    def create(
        cls,
        context: bpy.types.Context,
        settings: KeySettings,
        location: Vector,
        normal: Vector,
    ) -> Self:
        """Create and validate both operands, removing partial work on
        failure."""
        if not cls.can_create(context):
            raise ValueError("Choose two different editable mesh halves")
        target = context.active_object
        mate = scene_settings(context).key_mate
        assert target is not None and mate is not None
        dimensions = settings.dimensions()
        if normal.length_squared < 1e-20:
            raise ValueError("Surface normal must be nonzero")
        matrix = settings.placement(location, normal)
        operands: list[bpy.types.Object] = []
        modifiers: list[tuple[bpy.types.Object, bpy.types.BooleanModifier]] = []
        try:
            for half, socket in ((target, False), (mate, True)):
                operand = cls._create_operand(context, dimensions, socket=socket)
                operands.append(operand)
                operand.parent = half
                operand.matrix_world = matrix
                modifier = cls._add_modifier(
                    half, operand, "DIFFERENCE" if socket else "UNION"
                )
                modifiers.append((half, modifier))
                context.view_layer.update()
                cls._validate_modifier(context, half, operand, modifier)
            pin, socket_obj = operands
            pair = cls(pin, socket_obj)
            pair._record(normal, settings)
            for operand in operands:
                operand.hide_set(True)
            scene_settings(context).key_active = pin
            return pair
        except (ValueError, RuntimeError):
            for half, modifier in reversed(modifiers):
                half.modifiers.remove(modifier)
            for operand in operands:
                cls._remove_operand(operand)
            raise

    def select(self, context: bpy.types.Context) -> None:
        """Restore this pair's saved inputs and select it for sidebar
        editing."""
        KeySettings.from_pin(
            self._pin, scale_length=context.scene.unit_settings.scale_length
        ).restore(context)
        props = scene_settings(context)
        props.key_mate = self._socket.parent
        props.key_active = self._pin

    def move(
        self, context: bpy.types.Context, location: Vector, normal: Vector
    ) -> None:
        """Move using saved dimensions, independently of uncommitted sidebar
        edits."""
        settings = KeySettings.from_pin(
            self._pin, scale_length=context.scene.unit_settings.scale_length
        )
        matrix = settings.placement(location, normal)
        self._replace(context, settings, matrix, normal)
        self.select(context)

    def edit(self, context: bpy.types.Context, settings: KeySettings) -> None:
        """Apply input changes at the existing contact, retaining its
        tangent."""
        parent = self._pin.parent
        if parent is None:
            raise ValueError("The pin half has been removed")
        normal = parent.matrix_world.to_3x3().inverted_safe().transposed() @ Vector(
            self._pin[_NORMAL]
        )
        matrix = settings.edited_placement(self._pin, normal)
        self._replace(context, settings, matrix, normal)

    def delete(self, context: bpy.types.Context) -> None:
        """Remove this pair's operands and every parent modifier using them."""
        scene_settings(context).key_active = None
        for operand in (self._pin, self._socket):
            parent = operand.parent
            if parent is not None:
                for modifier in list(parent.modifiers):
                    if (
                        isinstance(modifier, bpy.types.BooleanModifier)
                        and modifier.object == operand
                    ):
                        parent.modifiers.remove(modifier)
            self._remove_operand(operand)

    def _replace(
        self,
        context: bpy.types.Context,
        settings: KeySettings,
        matrix: Matrix,
        normal: Vector,
    ) -> None:
        operands = (self._pin, self._socket)
        if any(obj.parent is None for obj in operands):
            raise ValueError("Both mold halves must still exist")
        targets = [cast(bpy.types.Object, obj.parent) for obj in operands]
        modifiers = [
            self._modifier(target, obj) for target, obj in zip(targets, operands)
        ]
        dimensions = settings.dimensions()
        if normal.length_squared < 1e-20:
            raise ValueError("Surface normal must be nonzero")
        old_meshes = [cast(bpy.types.Mesh, obj.data) for obj in operands]
        old_matrices = [obj.matrix_world.copy() for obj in operands]
        new_meshes: list[bpy.types.Mesh] = []
        try:
            for obj, socket in zip(operands, (False, True)):
                mesh = dimensions.create_mesh(obj.name, socket=socket)
                new_meshes.append(mesh)
                obj.data = mesh
                obj.matrix_world = matrix
            context.view_layer.update()
            for target, obj, modifier in zip(targets, operands, modifiers):
                self._validate_modifier(context, target, obj, modifier)
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
        self._record(normal, settings)
        scene_settings(context).key_active = self._pin

    def _record(self, normal: Vector, settings: KeySettings) -> None:
        assert self._pin.parent is not None
        self._pin[_SOCKET] = self._socket
        local_normal = self._pin.parent.matrix_world.to_3x3().transposed() @ normal
        self._pin[_NORMAL] = (local_normal.x, local_normal.y, local_normal.z)
        settings.store(self._pin)

    @classmethod
    def _create_operand(
        cls, context: bpy.types.Context, dimensions: KeyDimensions, *, socket: bool
    ) -> bpy.types.Object:
        mesh = dimensions.create_mesh(
            "Registration Socket" if socket else "Registration Pin", socket=socket
        )
        try:
            obj = bpy.data.objects.new(mesh.name, mesh)
        except (ValueError, RuntimeError):
            bpy.data.meshes.remove(mesh)
            raise
        try:
            context.scene.collection.objects.link(obj)
            obj.hide_render = True
            obj.hide_select = True
        except (ValueError, RuntimeError):
            cls._remove_operand(obj)
            raise
        return obj

    @staticmethod
    def _remove_operand(obj: bpy.types.Object) -> None:
        mesh = cast(bpy.types.Mesh, obj.data)
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)

    @staticmethod
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

    @staticmethod
    def _add_modifier(
        target: bpy.types.Object,
        operand: bpy.types.Object,
        operation: Literal["UNION", "DIFFERENCE"],
    ) -> bpy.types.BooleanModifier:
        modifier = cast(
            bpy.types.BooleanModifier,
            target.modifiers.new("Registration Key", "BOOLEAN"),
        )
        try:
            modifier.operation = operation
            modifier.solver = "EXACT"
            modifier.object = operand
        except (ValueError, RuntimeError):
            target.modifiers.remove(modifier)
            raise
        return modifier

    @staticmethod
    def _validate_modifier(
        context: bpy.types.Context,
        target: bpy.types.Object,
        operand: bpy.types.Object,
        modifier: bpy.types.BooleanModifier,
    ) -> None:
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
