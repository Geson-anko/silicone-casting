"""Native toolbar key placement with one undoable operation per gesture."""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast, override

import bpy
import gpu
from bpy_extras import view3d_utils
from gpu_extras.batch import (
    batch_for_shader,  # pyright: ignore[reportUnknownVariableType]
)
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from ..core.registration_keys import KeyDimensions, key_geometry, placement_matrix
from ..core.units import mm_to_units
from ._operator import OperatorReturn
from .key_editing import is_registration_key, load_key_settings

_TOOL_ID = "silicone_casting.registration_keys"
_gesture: SILCAST_OT_place_key | None = None


def _dimensions(context: bpy.types.Context) -> KeyDimensions:
    p = context.scene.silicone_casting
    scale = context.scene.unit_settings.scale_length
    return KeyDimensions(
        p.key_shape,
        *(
            mm_to_units(getattr(p, f"key_{name}_mm"), scale)
            for name in (
                "width",
                "length",
                "height",
                "embed",
                "clearance",
                "depth_clearance",
            )
        ),
        taper=p.key_taper,
    )


def _matrix(context: bpy.types.Context, position: Vector, normal: Vector) -> Matrix:
    p = context.scene.silicone_casting
    if not p.key_align_normal:
        normal = Vector({"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[p.key_axis])
    if p.key_flip:
        normal = -normal
    return placement_matrix(position, normal, p.key_angle)


def _ray(context: bpy.types.Context, xy: tuple[float, float]) -> tuple[Vector, Vector]:
    region = context.region
    view = context.region_data
    assert region is not None and isinstance(view, bpy.types.RegionView3D)
    return (
        view3d_utils.region_2d_to_origin_3d(region, view, xy),
        view3d_utils.region_2d_to_vector_3d(region, view, xy),
    )


def _object_hit(
    obj: bpy.types.Object, origin: Vector, direction: Vector
) -> tuple[Vector, Vector] | None:
    matrix = obj.matrix_world
    if abs(matrix.to_3x3().determinant()) < 1e-12:
        return None
    inverse = matrix.inverted()
    local_origin = inverse @ origin
    local_direction = inverse.to_3x3() @ direction
    hit, point, normal, _ = obj.ray_cast(local_origin, local_direction)
    if not hit:
        return None
    return matrix @ point, (inverse.transposed().to_3x3() @ normal).normalized()


def _pick(
    context: bpy.types.Context, xy: tuple[float, float]
) -> tuple[bpy.types.Object | None, tuple[Vector, Vector] | None]:
    target = context.active_object
    if target is None or target.type != "MESH":
        return None, None
    origin, direction = _ray(context, xy)
    depsgraph = context.evaluated_depsgraph_get()
    hit = _object_hit(target.evaluated_get(depsgraph), origin, direction)
    limit = (hit[0] - origin).length + 1e-5 if hit else float("inf")
    nearest = None
    for obj in context.scene.objects:
        if obj.parent != target or not is_registration_key(obj):
            continue
        candidate = _object_hit(obj, origin, direction)
        if candidate is not None:
            distance = (candidate[0] - origin).length
            if distance <= limit:
                nearest = obj
                limit = distance
    return nearest, hit


def _surface(context: bpy.types.Context, target: bpy.types.Object) -> BVHTree:
    # Snapshot the underlying half once at gesture start, so dragging never
    # climbs an existing pin or follows the moving preview.
    modifiers = [
        m
        for m in target.modifiers
        if isinstance(m, bpy.types.BooleanModifier)
        and m.object is not None
        and is_registration_key(m.object)
    ]
    states = [m.show_viewport for m in modifiers]
    evaluated = None
    try:
        for m in modifiers:
            m.show_viewport = False
        evaluated = target.evaluated_get(context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        points = [evaluated.matrix_world @ v.co for v in mesh.vertices]
        return BVHTree.FromPolygons(
            [(v.x, v.y, v.z) for v in points],
            [tuple(cast(Iterable[int], face.vertices)) for face in mesh.polygons],
        )
    finally:
        if evaluated is not None:
            evaluated.to_mesh_clear()
        for m, state in zip(modifiers, states, strict=True):
            m.show_viewport = state


def _lines(
    context: bpy.types.Context,
    points: list[Vector],
    edges: Iterable[tuple[int, int]],
    color: tuple[float, float, float, float],
    *,
    window_coordinates: bool = False,
) -> None:
    region, view = context.region, context.region_data
    if region is None or not isinstance(view, bpy.types.RegionView3D):
        return
    offset = Vector((region.x, region.y)) if window_coordinates else Vector((0, 0))
    pixels = [view3d_utils.location_3d_to_region_2d(region, view, p) for p in points]
    lines: list[tuple[float, float]] = []
    for a, b in edges:
        start, end = pixels[a], pixels[b]
        if start is not None and end is not None:
            start, end = start + offset, end + offset
            lines.extend(((start.x, start.y), (end.x, end.y)))
    if lines:
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        batch = batch_for_shader(shader, "LINES", {"pos": lines})
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)


def _ghost(
    context: bpy.types.Context, matrix: Matrix, *, window_coordinates: bool = False
) -> None:
    for socket, color in ((False, (1.0, 0.5, 0.05, 1.0)), (True, (0.2, 0.7, 1.0, 1.0))):
        vertices, faces = key_geometry(_dimensions(context), socket=socket)
        edges = {
            (min(a, b), max(a, b))
            for face in faces
            for a, b in zip(face, face[1:] + face[:1])
        }
        _lines(
            context,
            [matrix @ Vector(v) for v in vertices],
            edges,
            color,
            window_coordinates=window_coordinates,
        )


class SILCAST_WST_registration_keys(bpy.types.WorkSpaceTool):
    """Click to add/select a key; drag to move it along the mold surface."""

    bl_idname = _TOOL_ID
    bl_label = "Registration Keys"
    bl_description = "Click a face to add; click a key to edit; drag to move; Delete removes the selected key"
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_icon = "ops.mesh.primitive_cylinder_add_gizmo"
    bl_cursor = "CROSSHAIR"
    bl_keymap = (
        ("silicone_casting.place_key", {"type": "LEFTMOUSE", "value": "PRESS"}, None),
        (
            "silicone_casting.delete_registration_key",
            {"type": "DEL", "value": "PRESS"},
            None,
        ),
        (
            "silicone_casting.delete_registration_key",
            {"type": "X", "value": "PRESS"},
            None,
        ),
        (
            "silicone_casting.stop_key_placement",
            {"type": "ESC", "value": "PRESS"},
            None,
        ),
    )

    @staticmethod
    def draw_cursor(
        context: bpy.types.Context, _tool: bpy.types.WorkSpaceTool, xy: tuple[int, int]
    ) -> None:
        if (
            _gesture is not None
            or context.region is None
            or not isinstance(context.region_data, bpy.types.RegionView3D)
        ):
            return
        # Native cursor callbacks use window coordinates; POST_PIXEL gestures
        # use region coordinates. Convert picking and drawing in opposite directions.
        mouse = (float(xy[0] - context.region.x), float(xy[1] - context.region.y))
        try:
            key, hit = _pick(context, mouse)
            selected = context.scene.silicone_casting.key_active
            if (
                selected is not None
                and selected != key
                and selected.parent == context.active_object
                and is_registration_key(selected)
            ):
                mesh = cast(bpy.types.Mesh, selected.data)
                _lines(
                    context,
                    [selected.matrix_world @ v.co for v in mesh.vertices],
                    (cast(tuple[int, int], e.vertices) for e in mesh.edges),
                    (1.0, 0.5, 0.05, 1.0),
                    window_coordinates=True,
                )
            if key is not None:
                mesh = cast(bpy.types.Mesh, key.data)
                edges = [
                    tuple(cast(Iterable[int], edge.vertices)) for edge in mesh.edges
                ]
                _lines(
                    context,
                    [key.matrix_world @ v.co for v in mesh.vertices],
                    ((e[0], e[1]) for e in edges),
                    (0.3, 1.0, 0.35, 1.0),
                    window_coordinates=True,
                )
            elif hit is not None:
                _ghost(context, _matrix(context, *hit), window_coordinates=True)
        except (ValueError, RuntimeError, ReferenceError):
            # No geometry or invalid dimensions: the click operator reports it.
            return


class SILCAST_OT_start_key_placement(bpy.types.Operator):
    """Activate the native tool without capturing global Undo/Redo events."""

    bl_idname = "silicone_casting.start_key_placement"
    bl_label = "Place Keys"

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        p = context.scene.silicone_casting
        obj = context.active_object
        return (
            context.mode == "OBJECT"
            and obj is not None
            and obj.type == "MESH"
            and p.key_mate is not None
            and p.key_mate != obj
        )

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        bpy.ops.wm.tool_set_by_id(name=_TOOL_ID)
        self.report(
            {"INFO"},
            "Click to add/select; drag to move; update selected in panel; Delete removes; Esc exits",
        )
        return {"FINISHED"}


class SILCAST_OT_stop_key_placement(bpy.types.Operator):
    """Return to Blender's selection tool."""

    bl_idname = "silicone_casting.stop_key_placement"
    bl_label = "Finish Placing"

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
        return {"FINISHED"}


class SILCAST_OT_place_key(bpy.types.Operator):
    """Preview one click/drag gesture, then commit exactly one action."""

    bl_idname = "silicone_casting.place_key"
    bl_label = "Place / Move Key"
    bl_options = {"UNDO", "BLOCKING"}

    _key_name: str
    _press: Vector
    _bvh: BVHTree
    _position: Vector
    _normal: Vector
    _valid: bool
    _moved: bool
    _handle: object | None = None
    _area: bpy.types.Area | None = None

    @override
    def invoke(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        global _gesture
        if (
            not SILCAST_OT_start_key_placement.poll(context)
            or context.region is None
            or context.region.type != "WINDOW"
        ):
            return {"CANCELLED"}
        target = context.active_object
        assert target is not None
        self._press = Vector((event.mouse_region_x, event.mouse_region_y))
        key, hit = _pick(context, (self._press.x, self._press.y))
        if hit is None and key is None:
            return {"CANCELLED"}
        self._key_name = key.name if key is not None else ""
        if key is not None:
            load_key_settings(context, key)
        self._bvh = _surface(context, target)
        self._position = Vector((0, 0, 0))
        self._normal = Vector((0, 0, 1))
        self._valid = False
        self._moved = False
        self._area = context.area
        self._update(context, event)
        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            self._draw, (), "WINDOW", "POST_PIXEL"
        )
        _gesture = self
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _update(self, context: bpy.types.Context, event: bpy.types.Event) -> None:
        origin, direction = _ray(
            context, (float(event.mouse_region_x), float(event.mouse_region_y))
        )
        point, normal, _, _ = self._bvh.ray_cast(origin, direction)
        self._valid = point is not None and normal is not None
        if point is not None and normal is not None:
            self._position, self._normal = point, normal
        if (
            normal is not None
            and context.active_object is not None
            and context.active_object.matrix_world.to_3x3().determinant() < 0
        ):
            normal.negate()
        if self._area is not None:
            self._area.tag_redraw()

    def _draw(self) -> None:
        context = bpy.context
        if context.area == self._area and self._valid:
            try:
                _ghost(context, _matrix(context, self._position, self._normal))
            except ValueError:
                return

    def _finish(self) -> None:
        global _gesture
        if self._handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, "WINDOW")
            self._handle = None
        _gesture = None
        if self._area is not None:
            self._area.tag_redraw()

    @override
    def cancel(self, context: bpy.types.Context) -> None:
        self._finish()

    @override
    def modal(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._finish()
            return {"CANCELLED"}
        if event.type == "MOUSEMOVE":
            self._moved |= (
                Vector((event.mouse_region_x, event.mouse_region_y)) - self._press
            ).length > 4
            self._update(context, event)
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            self._finish()
            if self._key_name and not self._moved:
                return {"FINISHED"}
            if not self._valid:
                return {"CANCELLED"}
            position = (self._position.x, self._position.y, self._position.z)
            normal = (self._normal.x, self._normal.y, self._normal.z)
            try:
                if self._key_name:
                    return cast(
                        OperatorReturn,
                        getattr(bpy.ops, "silicone_casting").move_registration_key(
                            key_name=self._key_name, location=position, normal=normal
                        ),
                    )
                return cast(
                    OperatorReturn,
                    getattr(bpy.ops, "silicone_casting").add_registration_key(
                        location=position, normal=normal
                    ),
                )
            except RuntimeError as exc:
                self.report({"WARNING"}, str(exc))
                return {"CANCELLED"}
        return {"RUNNING_MODAL"}


def cancel_key_gesture() -> None:
    """Remove a transient drawing callback when the extension unloads."""
    if _gesture is not None:
        _gesture.cancel(bpy.context)
