"""Preview and attach paired registration keys to separated mold halves."""

from collections.abc import Iterable
from math import pi
from typing import Literal, Protocol, cast, override

import bpy
from mathutils import Matrix
from mathutils.bvhtree import BVHTree

from ..core.registration_keys import KeyDimensions, create_key_mesh, placement_matrix
from ..core.units import mm_to_units
from ..core.volume import world_volume
from ._operator import OperatorReturn


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
    key_preview_pin: bpy.types.Object | None
    key_preview_socket: bpy.types.Object | None
    key_preview_target: bpy.types.Object | None
    key_preview_mate: bpy.types.Object | None


def _settings(context: bpy.types.Context) -> _Settings:
    return cast(_Settings, context.scene.silicone_casting)


def _clear_preview(props: _Settings) -> None:
    for obj in (props.key_preview_pin, props.key_preview_socket):
        if obj is not None:
            mesh = cast(bpy.types.Mesh, obj.data)
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
    props.key_preview_pin = None
    props.key_preview_socket = None
    props.key_preview_target = None
    props.key_preview_mate = None


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
        scale = context.scene.unit_settings.scale_length
        values = [
            mm_to_units(v, scale)
            for v in (
                props.key_width_mm,
                props.key_length_mm,
                props.key_height_mm,
                props.key_embed_mm,
                props.key_clearance_mm,
                props.key_depth_clearance_mm,
            )
        ]
        dimensions = KeyDimensions(props.key_shape, *values, taper=props.key_taper)
        evaluated = target.evaluated_get(context.evaluated_depsgraph_get())
        mesh = cast(bpy.types.Mesh | None, evaluated.to_mesh())
        try:
            if mesh is None or not mesh.polygons:
                raise ValueError("The active half has no surface")
            points = [evaluated.matrix_world @ v.co for v in mesh.vertices]
            vertices = [(v.x, v.y, v.z) for v in points]
            surface = BVHTree.FromPolygons(
                vertices,
                [tuple(cast(Iterable[int], p.vertices)) for p in mesh.polygons],
            )
            position, normal, _, _ = surface.find_nearest(context.scene.cursor.location)
            if position is None or normal is None:
                raise ValueError("No nearby surface found")
            if props.key_align_normal:
                if evaluated.matrix_world.to_3x3().determinant() < 0:
                    normal.negate()
                if props.key_flip:
                    normal.negate()
                matrix = placement_matrix(position, normal, props.key_angle)
            else:
                matrix = context.scene.cursor.matrix.copy()
                matrix.translation = position
                if props.key_flip:
                    matrix = matrix @ Matrix.Rotation(pi, 4, "X")
                matrix = matrix @ Matrix.Rotation(props.key_angle, 4, "Z")
            dimensions.validate()
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        finally:
            evaluated.to_mesh_clear()
        _clear_preview(props)
        props.key_preview_target = target
        props.key_preview_mate = props.key_mate
        for socket in (False, True):
            mesh = create_key_mesh(
                "Registration Socket" if socket else "Registration Pin",
                dimensions,
                socket=socket,
            )
            obj = bpy.data.objects.new(mesh.name, mesh)
            context.scene.collection.objects.link(obj)
            obj.matrix_world = matrix
            obj.display_type = "WIRE" if socket else "SOLID"
            obj.show_in_front = True
            obj.hide_render = True
            obj.hide_select = True
            obj.color = (0.1, 0.6, 1.0, 1.0) if socket else (1.0, 0.5, 0.05, 1.0)  # pyright: ignore[reportAttributeAccessIssue]
            if socket:
                props.key_preview_socket = obj
            else:
                props.key_preview_pin = obj
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
                depsgraph = context.evaluated_depsgraph_get()
                before = world_volume(target, depsgraph)
                tool_volume = world_volume(operand, depsgraph)
                if before is None or before <= 0 or tool_volume is None:
                    raise ValueError("Mold halves must be closed solids")
                modifier = cast(
                    bpy.types.BooleanModifier,
                    target.modifiers.new("Registration Key", "BOOLEAN"),
                )
                created.append((target, modifier))
                modifier.operation = cast(Literal["UNION", "DIFFERENCE"], operation)
                modifier.solver = "EXACT"
                modifier.object = operand
                after = world_volume(target, context.evaluated_depsgraph_get())
                if after is None or after <= 0:
                    raise ValueError("The key must leave a closed mold half")
                tolerance = tool_volume * 1e-5
                change = after - before if operation == "UNION" else before - after
                if change <= tolerance or (
                    operation == "UNION" and change >= tool_volume - tolerance
                ):
                    raise ValueError(
                        "Key must overlap both halves and protrude from the pin half; adjust position or direction"
                    )
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
