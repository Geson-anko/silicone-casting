"""Settings and transactional ownership of paired registration key operands."""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Final, Literal, Self, cast

import bpy
from mathutils import Matrix, Vector

from ..core.registration_keys import KeyDimensions, placement_matrix, validate_normal
from ..core.volume import world_volume
from ..properties.settings import scene_settings

# Custom property keys on the pin; saved in .blend files.
_SOCKET_KEY: Final = "silcast_key_socket"
_NORMAL_KEY: Final = "silcast_key_normal"

_MODIFIER_NAME: Final = "Registration Key"
_PIN_NAME: Final = "Registration Pin"
_SOCKET_NAME: Final = "Registration Socket"
_AXIS_DIRECTIONS: Final = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}
# Relative to the key's own volume: Boolean volume noise below this is not a
# real overlap between the key and a mold half.
_VOLUME_TOLERANCE_RATIO: Final = 1e-5

type BooleanOperation = Literal["UNION", "DIFFERENCE"]


@dataclass(frozen=True)
class KeySettings:
    """Snapshot of sidebar or saved key inputs, still in their stored units."""

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
        sidebar = scene_settings(context)
        return cls(
            _shape=sidebar.key_shape,
            _width_mm=sidebar.key_width_mm,
            _length_mm=sidebar.key_length_mm,
            _height_mm=sidebar.key_height_mm,
            _embed_mm=sidebar.key_embed_mm,
            _clearance_mm=sidebar.key_clearance_mm,
            _depth_clearance_mm=sidebar.key_depth_clearance_mm,
            _taper=sidebar.key_taper,
            _angle=sidebar.key_angle,
            _align_normal=sidebar.key_align_normal,
            _flip=sidebar.key_flip,
            _axis=sidebar.key_axis,
            _scale_length=context.scene.unit_settings.scale_length,
        )

    @classmethod
    def from_pin(cls, pin: bpy.types.Object, *, scale_length: float) -> Self:
        """Read a pin's saved inputs with the scene's current unit scale."""
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
        """Convert the millimetre inputs into validated scene-unit dimensions.

        Raises:
            ValueError: If the inputs describe a degenerate key.
        """
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
        """Orient the key along the face normal or the selected world axis.

        Args:
            location: World-space contact point.
            normal: World-space face normal; unused when a fixed axis is set.

        Returns:
            The key's rigid world matrix.

        Raises:
            ValueError: If the resulting direction is zero.
        """
        if self._align_normal:
            direction = normal.copy()
        else:
            direction = Vector(_AXIS_DIRECTIONS[self._axis])
        if self._flip:
            direction.negate()
        return placement_matrix(location, direction, self._angle)

    def placement_after_edit(
        self, previous: Self, current: Matrix, normal: Vector
    ) -> Matrix:
        """Place an edited key at its current contact and tangent.

        While the key stays aligned to the same face side, its in-plane
        orientation is taken from ``current`` (which may have been transformed
        together with its half) and turned only by the change in angle.

        Args:
            previous: The inputs the key was last built with.
            current: The key's current world matrix.
            normal: World-space face normal at the contact.

        Returns:
            The key's new rigid world matrix.
        """
        location = current.translation.copy()
        matrix = self.placement(location, normal)
        keeps_alignment = (
            self._align_normal
            and previous._align_normal
            and self._flip == previous._flip
        )
        if not keeps_alignment:
            return matrix
        # Rebuild a rigid frame so a scaled half does not scale key dimensions.
        z = matrix.to_3x3() @ Vector((0, 0, 1))
        x = current.to_3x3() @ Vector((1, 0, 0))
        x = (x - z * x.dot(z)).normalized()
        y = cast(Vector, z.cross(x))
        rotation = (
            Matrix(((x.x, x.y, x.z), (y.x, y.y, y.z), (z.x, z.y, z.z)))
            .transposed()
            .to_4x4()
        )
        return (
            Matrix.Translation((location.x, location.y, location.z))
            @ rotation
            @ Matrix.Rotation(self._angle - previous._angle, 4, "Z")
        )

    def store(self, pin: bpy.types.Object) -> None:
        """Save the millimetre inputs on the pin for edits and rescaling."""
        for name, value in self._persisted_inputs().items():
            pin[name] = value

    def restore(self, context: bpy.types.Context) -> None:
        """Copy the inputs to the sidebar in their persisted field order."""
        sidebar = scene_settings(context)
        for name, value in self._persisted_inputs().items():
            setattr(sidebar, name, value)

    def _persisted_inputs(self) -> dict[str, str | float | bool]:
        """Map inputs by the name shared by sidebar and pin properties."""
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
    """A pin, its socket, and the Boolean modifiers joining them to halves.

    The pin is parented to the pin half and unioned into it; the socket
    is parented to the opposite half and subtracted from it. Every
    change either completes on both operands or is rolled back.
    """

    _pin: bpy.types.Object
    _socket: bpy.types.Object

    @property
    def pin(self) -> bpy.types.Object:
        """The pin operand, which identifies this pair in the sidebar."""
        return self._pin

    @property
    def socket(self) -> bpy.types.Object:
        """The matching socket operand parented to the opposite mold half."""
        return self._socket

    @classmethod
    def from_pin(cls, pin: bpy.types.Object | None) -> Self | None:
        """Resolve a saved pair through its custom property, not object names.

        Returns:
            The pair, or ``None`` if ``pin`` is not a registration key pin.
        """
        if pin is None or pin.type != "MESH":
            return None
        socket = pin.get(_SOCKET_KEY)
        return cls(pin, socket) if isinstance(socket, bpy.types.Object) else None

    @classmethod
    def from_context(cls, context: bpy.types.Context, key_name: str = "") -> Self:
        """Resolve the named pair, or the sidebar's selected key if unnamed.

        Raises:
            ValueError: If no registration key matches.
        """
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
        """Whether the active object and mate are two editable halves."""
        target = context.active_object
        mate = scene_settings(context).key_mate
        return (
            context.mode == "OBJECT"
            and target is not None
            and mate is not None
            and target != mate
            and _is_editable_mesh_in_view_layer(context, target)
            and _is_editable_mesh_in_view_layer(context, mate)
            and cls.from_pin(target) is None
        )

    @classmethod
    def create(
        cls,
        context: bpy.types.Context,
        settings: KeySettings,
        location: Vector,
        normal: Vector,
    ) -> Self:
        """Add a pin to the active half and a socket to the mate.

        Args:
            context: Context whose active object is the pin half.
            settings: Inputs for the new key.
            location: World-space contact point.
            normal: World-space face normal at the contact.

        Returns:
            The new pair, which also becomes the sidebar's selected key.

        Raises:
            ValueError: If the halves are unsuitable, the inputs are invalid,
                or the key would not overlap both halves. Partial work is
                removed before raising.
        """
        if not cls.can_create(context):
            raise ValueError("Choose two different editable mesh halves")
        target = context.active_object
        mate = scene_settings(context).key_mate
        assert target is not None and mate is not None
        dimensions = settings.dimensions()
        validate_normal(normal)
        matrix = settings.placement(location, normal)
        operands: list[bpy.types.Object] = []
        modifiers: list[tuple[bpy.types.Object, bpy.types.BooleanModifier]] = []
        try:
            for half, socket in ((target, False), (mate, True)):
                operand = _create_operand(context, dimensions, socket=socket)
                operands.append(operand)
                operand.parent = half
                operand.matrix_world = matrix
                modifier = _add_modifier(
                    half, operand, "DIFFERENCE" if socket else "UNION"
                )
                modifiers.append((half, modifier))
                context.view_layer.update()
                _check_boolean_effect(context, half, operand, modifier)
            pin, socket_operand = operands
            pair = cls(pin, socket_operand)
            pair._record(normal, settings)
            for operand in operands:
                operand.hide_set(True)
            scene_settings(context).key_active = pin
            return pair
        except (ValueError, RuntimeError):
            for half, modifier in reversed(modifiers):
                half.modifiers.remove(modifier)
            for operand in operands:
                _remove_operand(operand)
            raise

    def select(self, context: bpy.types.Context) -> None:
        """Load this pair's saved inputs into the sidebar and select it."""
        self._saved_settings(context).restore(context)
        sidebar = scene_settings(context)
        sidebar.key_mate = self._socket.parent
        sidebar.key_active = self._pin

    def move(
        self, context: bpy.types.Context, location: Vector, normal: Vector
    ) -> None:
        """Move the pair with its saved inputs, ignoring sidebar edits.

        Raises:
            ValueError: If the moved key would not overlap both halves; the
                pair is left unchanged.
        """
        settings = self._saved_settings(context)
        self._rebuild(context, settings, settings.placement(location, normal), normal)
        self.select(context)

    def edit(self, context: bpy.types.Context, settings: KeySettings) -> None:
        """Rebuild the pair from new inputs at its existing contact.

        Raises:
            ValueError: If a half is gone or the new key is invalid; the pair
                is left unchanged.
        """
        parent = self._pin.parent
        if parent is None:
            raise ValueError("The pin half has been removed")
        normal = self._saved_world_normal(parent)
        matrix = settings.placement_after_edit(
            self._saved_settings(context), self._pin.matrix_world, normal
        )
        self._rebuild(context, settings, matrix, normal)

    def delete(self, context: bpy.types.Context) -> None:
        """Remove both operands and every parent modifier that uses them."""
        scene_settings(context).key_active = None
        for operand in (self._pin, self._socket):
            parent = operand.parent
            if parent is not None:
                for modifier in list(_boolean_modifiers_using(parent, operand)):
                    parent.modifiers.remove(modifier)
            _remove_operand(operand)

    def _saved_settings(self, context: bpy.types.Context) -> KeySettings:
        return KeySettings.from_pin(
            self._pin, scale_length=context.scene.unit_settings.scale_length
        )

    def _saved_world_normal(self, parent: bpy.types.Object) -> Vector:
        """Map the stored parent-local normal back to world space."""
        rotation = parent.matrix_world.to_3x3()
        return rotation.inverted_safe().transposed() @ Vector(self._pin[_NORMAL_KEY])

    def _rebuild(
        self,
        context: bpy.types.Context,
        settings: KeySettings,
        matrix: Matrix,
        normal: Vector,
    ) -> None:
        """Swap in new meshes and placement for both operands, or roll back."""
        operands = (self._pin, self._socket)
        if any(operand.parent is None for operand in operands):
            raise ValueError("Both mold halves must still exist")
        halves = [cast(bpy.types.Object, operand.parent) for operand in operands]
        modifiers = [
            _modifier_using(half, operand) for half, operand in zip(halves, operands)
        ]
        dimensions = settings.dimensions()
        validate_normal(normal)
        old_meshes = [cast(bpy.types.Mesh, operand.data) for operand in operands]
        old_matrices = [operand.matrix_world.copy() for operand in operands]
        new_meshes: list[bpy.types.Mesh] = []
        try:
            for operand, socket in zip(operands, (False, True)):
                mesh = dimensions.create_mesh(operand.name, socket=socket)
                new_meshes.append(mesh)
                operand.data = mesh
                operand.matrix_world = matrix
            context.view_layer.update()
            for half, operand, modifier in zip(halves, operands, modifiers):
                _check_boolean_effect(context, half, operand, modifier)
        except (ValueError, RuntimeError):
            for operand, mesh, previous in zip(operands, old_meshes, old_matrices):
                operand.data = mesh
                operand.matrix_world = previous
            _remove_unused_meshes(new_meshes)
            context.view_layer.update()
            raise
        _remove_unused_meshes(old_meshes)
        self._record(normal, settings)
        scene_settings(context).key_active = self._pin

    def _record(self, normal: Vector, settings: KeySettings) -> None:
        """Save the socket link, local normal, and inputs on the pin."""
        parent = self._pin.parent
        assert parent is not None
        self._pin[_SOCKET_KEY] = self._socket
        # Normals map to local space by the transpose, so the pair survives
        # rigid motion of its half.
        local_normal = parent.matrix_world.to_3x3().transposed() @ normal
        self._pin[_NORMAL_KEY] = (local_normal.x, local_normal.y, local_normal.z)
        settings.store(self._pin)


def _is_editable_mesh_in_view_layer(
    context: bpy.types.Context, obj: bpy.types.Object
) -> bool:
    return (
        obj.type == "MESH"
        and cast(bpy.types.Library | None, obj.library) is None
        and obj.name in context.view_layer.objects
    )


def _create_operand(
    context: bpy.types.Context, dimensions: KeyDimensions, *, socket: bool
) -> bpy.types.Object:
    """Link a new render- and select-hidden operand object to the scene."""
    mesh = dimensions.create_mesh(_SOCKET_NAME if socket else _PIN_NAME, socket=socket)
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
        _remove_operand(obj)
        raise
    return obj


def _remove_operand(obj: bpy.types.Object) -> None:
    mesh = cast(bpy.types.Mesh, obj.data)
    bpy.data.objects.remove(obj, do_unlink=True)
    _remove_unused_meshes((mesh,))


def _remove_unused_meshes(meshes: Iterable[bpy.types.Mesh]) -> None:
    for mesh in meshes:
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def _boolean_modifiers_using(
    half: bpy.types.Object, operand: bpy.types.Object
) -> Iterator[bpy.types.BooleanModifier]:
    for modifier in half.modifiers:
        if (
            isinstance(modifier, bpy.types.BooleanModifier)
            and modifier.object == operand
        ):
            yield modifier


def _modifier_using(
    half: bpy.types.Object, operand: bpy.types.Object
) -> bpy.types.BooleanModifier:
    modifier = next(_boolean_modifiers_using(half, operand), None)
    if modifier is None:
        raise ValueError("The registration key modifier has been removed")
    return modifier


def _add_modifier(
    half: bpy.types.Object, operand: bpy.types.Object, operation: BooleanOperation
) -> bpy.types.BooleanModifier:
    modifier = cast(
        bpy.types.BooleanModifier, half.modifiers.new(_MODIFIER_NAME, "BOOLEAN")
    )
    try:
        modifier.operation = operation
        modifier.solver = "EXACT"
        modifier.object = operand
    except (ValueError, RuntimeError):
        half.modifiers.remove(modifier)
        raise
    return modifier


def _check_boolean_effect(
    context: bpy.types.Context,
    half: bpy.types.Object,
    operand: bpy.types.Object,
    modifier: bpy.types.BooleanModifier,
) -> None:
    """Require the modifier to change a closed half by a real amount.

    A union must add some but not all of the key (it protrudes from the
    pin half); a difference must remove some of it (it reaches the
    socket half).
    """
    was_visible = modifier.show_viewport
    try:
        modifier.show_viewport = False
        before = world_volume(half, context.evaluated_depsgraph_get())
        key_volume = world_volume(operand, context.evaluated_depsgraph_get())
        modifier.show_viewport = True
        if before is None or before <= 0 or key_volume is None:
            raise ValueError("Mold halves must be closed solids")
        after = world_volume(half, context.evaluated_depsgraph_get())
        if after is None or after <= 0:
            raise ValueError("The key must leave a closed mold half")
        tolerance = key_volume * _VOLUME_TOLERANCE_RATIO
        is_union = modifier.operation == "UNION"
        change = after - before if is_union else before - after
        buried_in_pin_half = is_union and change >= key_volume - tolerance
        if change <= tolerance or buried_in_pin_half:
            raise ValueError(
                "Key must overlap both halves and protrude from the pin half; "
                "adjust position or direction"
            )
    finally:
        modifier.show_viewport = was_visible
