"""Native toolbar key placement with one undoable operation per gesture."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final, NamedTuple, cast, override

import bpy
import gpu
from bpy_extras import view3d_utils
from gpu_extras.batch import (
    batch_for_shader,  # pyright: ignore[reportUnknownVariableType]
)
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from ..core.surface_picking import SurfaceSnapshot
from ..properties.settings import scene_settings
from ._operator import OperatorReturn
from .key_models import KeyPair, KeySettings

type Color = tuple[float, float, float, float]

_TOOL_ID: Final = "silicone_casting.registration_keys"
_SELECT_TOOL_ID: Final = "builtin.select_box"
_PIN_COLOR: Final[Color] = (1.0, 0.5, 0.05, 1.0)
_SOCKET_COLOR: Final[Color] = (0.2, 0.7, 1.0, 1.0)
_HOVER_COLOR: Final[Color] = (0.3, 1.0, 0.35, 1.0)
# A collapsed (e.g. zero-scaled) object has no invertible matrix to cast into.
_MIN_PICK_DETERMINANT: Final = 1e-12
# Lets a key whose surface coincides with the half's face still win the pick.
_PICK_DEPTH_TOLERANCE: Final = 1e-5
# Pointer travel, in region pixels, that turns a click on a key into a drag.
_DRAG_THRESHOLD_PX: Final = 4

# The running gesture, so the cursor preview can yield to it and unloading
# the extension can remove its draw callback.
_gesture: SILCAST_OT_place_key | None = None


class _SurfaceHit(NamedTuple):
    position: Vector
    normal: Vector


class _Pick(NamedTuple):
    """The key under the cursor, if any, and the hit on the active half."""

    key: KeyPair | None
    hit: _SurfaceHit | None


def _ray(context: bpy.types.Context, xy: tuple[float, float]) -> tuple[Vector, Vector]:
    """Return the world-space view ray through region coordinates."""
    region = context.region
    view = context.region_data
    assert region is not None and isinstance(view, bpy.types.RegionView3D)
    return (
        view3d_utils.region_2d_to_origin_3d(region, view, xy),
        view3d_utils.region_2d_to_vector_3d(region, view, xy),
    )


def _object_hit(
    obj: bpy.types.Object, origin: Vector, direction: Vector
) -> _SurfaceHit | None:
    """Ray cast one object, returning the world-space hit and normal."""
    matrix = obj.matrix_world
    if abs(matrix.to_3x3().determinant()) < _MIN_PICK_DETERMINANT:
        return None
    inverse = matrix.inverted()
    hit, point, normal, _ = obj.ray_cast(inverse @ origin, inverse.to_3x3() @ direction)
    if not hit:
        return None
    return _SurfaceHit(
        matrix @ point, (inverse.transposed().to_3x3() @ normal).normalized()
    )


def _pick(context: bpy.types.Context, xy: tuple[float, float]) -> _Pick:
    """Find the key and the active-half face under region coordinates."""
    target = context.active_object
    if target is None or target.type != "MESH":
        return _Pick(None, None)
    origin, direction = _ray(context, xy)
    depsgraph = context.evaluated_depsgraph_get()
    hit = _object_hit(target.evaluated_get(depsgraph), origin, direction)
    max_distance = (
        (hit.position - origin).length + _PICK_DEPTH_TOLERANCE if hit else float("inf")
    )
    key = _nearest_key(context, target, origin, direction, max_distance)
    return _Pick(key, hit)


def _nearest_key(
    context: bpy.types.Context,
    target: bpy.types.Object,
    origin: Vector,
    direction: Vector,
    max_distance: float,
) -> KeyPair | None:
    """Return the closest pin of ``target`` hit within ``max_distance``."""
    nearest = None
    for obj in context.scene.objects:
        if obj.parent != target:
            continue
        pair = KeyPair.from_pin(obj)
        if pair is None:
            continue
        hit = _object_hit(obj, origin, direction)
        if hit is None:
            continue
        distance = (hit.position - origin).length
        if distance <= max_distance:
            nearest = pair
            max_distance = distance
    return nearest


def _surface_without_keys(
    context: bpy.types.Context, target: bpy.types.Object
) -> BVHTree:
    """Snapshot the half with its key modifiers disabled.

    Taken once at gesture start, so dragging never climbs an existing
    pin or follows the moving preview.
    """
    modifiers = [
        modifier
        for modifier in target.modifiers
        if isinstance(modifier, bpy.types.BooleanModifier)
        and modifier.object is not None
        and KeyPair.from_pin(modifier.object) is not None
    ]
    visibility = [modifier.show_viewport for modifier in modifiers]
    try:
        for modifier in modifiers:
            modifier.show_viewport = False
        return SurfaceSnapshot.from_objects(
            (target,), context.evaluated_depsgraph_get()
        ).bvh
    finally:
        for modifier, visible in zip(modifiers, visibility, strict=True):
            modifier.show_viewport = visible


def _draw_lines(
    context: bpy.types.Context,
    points: list[Vector],
    edges: Iterable[tuple[int, int]],
    color: Color,
    *,
    window_coordinates: bool = False,
) -> None:
    """Draw world-space edges projected into the current region."""
    region, view = context.region, context.region_data
    if region is None or not isinstance(view, bpy.types.RegionView3D):
        return
    offset = Vector((region.x, region.y)) if window_coordinates else Vector((0, 0))
    pixels = [view3d_utils.location_3d_to_region_2d(region, view, p) for p in points]
    lines: list[tuple[float, float]] = []
    for a, b in edges:
        start, end = pixels[a], pixels[b]
        # Points behind the view have no projection; skip their edges.
        if start is not None and end is not None:
            start, end = start + offset, end + offset
            lines.extend(((start.x, start.y), (end.x, end.y)))
    if not lines:
        return
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    batch = batch_for_shader(shader, "LINES", {"pos": lines})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def _draw_key_preview(
    context: bpy.types.Context,
    position: Vector,
    normal: Vector,
    *,
    window_coordinates: bool = False,
) -> None:
    """Draw the sidebar's pin and socket as wireframes at a surface point."""
    settings = KeySettings.from_context(context)
    dimensions = settings.dimensions()
    matrix = settings.placement(position, normal)
    for socket, color in ((False, _PIN_COLOR), (True, _SOCKET_COLOR)):
        geometry = dimensions.geometry(socket=socket)
        _draw_lines(
            context,
            [matrix @ Vector(vertex) for vertex in geometry.vertices],
            geometry.edges(),
            color,
            window_coordinates=window_coordinates,
        )


def _draw_outline(
    context: bpy.types.Context, obj: bpy.types.Object, color: Color
) -> None:
    """Draw an existing operand's edges in window coordinates."""
    mesh = cast(bpy.types.Mesh, obj.data)
    _draw_lines(
        context,
        [obj.matrix_world @ vertex.co for vertex in mesh.vertices],
        (cast(tuple[int, int], edge.vertices) for edge in mesh.edges),
        color,
        window_coordinates=True,
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
        """Highlight the key under the cursor or preview a new one."""
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
            hovered, hit = _pick(context, mouse)
            selected = KeyPair.from_pin(scene_settings(context).key_active)
            if (
                selected is not None
                and selected != hovered
                and selected.pin.parent == context.active_object
            ):
                _draw_outline(context, selected.pin, _PIN_COLOR)
            if hovered is not None:
                _draw_outline(context, hovered.pin, _HOVER_COLOR)
            elif hit is not None:
                _draw_key_preview(
                    context, hit.position, hit.normal, window_coordinates=True
                )
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
        return KeyPair.can_create(context)

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
        bpy.ops.wm.tool_set_by_id(name=_SELECT_TOOL_ID)
        return {"FINISHED"}


class SILCAST_OT_place_key(bpy.types.Operator):
    """Preview one click/drag gesture, then commit exactly one action."""

    # The docstring doubles as the tooltip (there is no bl_description), so
    # the gesture details live here: pressing on a key selects it and dragging
    # moves it; pressing on the face adds a key where the button is released.

    bl_idname = "silicone_casting.place_key"
    bl_label = "Place / Move Key"
    bl_options = {"UNDO", "BLOCKING"}

    _picked_key_name: str
    _press_xy: Vector
    _surface: BVHTree
    _position: Vector
    _normal: Vector
    _on_surface: bool
    _dragged: bool
    _draw_handle: object | None = None
    _area: bpy.types.Area | None = None

    @override
    def invoke(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        global _gesture
        if (
            not KeyPair.can_create(context)
            or context.region is None
            or context.region.type != "WINDOW"
        ):
            return {"CANCELLED"}
        target = context.active_object
        assert target is not None
        self._press_xy = Vector((event.mouse_region_x, event.mouse_region_y))
        picked, hit = _pick(context, (self._press_xy.x, self._press_xy.y))
        if hit is None and picked is None:
            return {"CANCELLED"}
        self._picked_key_name = picked.pin.name if picked is not None else ""
        if picked is not None:
            picked.select(context)
        self._surface = _surface_without_keys(context, target)
        self._position = Vector((0, 0, 0))
        self._normal = Vector((0, 0, 1))
        self._on_surface = False
        self._dragged = False
        self._area = context.area
        self._track_cursor(context, event)
        self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            self._draw, (), "WINDOW", "POST_PIXEL"
        )
        _gesture = self
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    @override
    def modal(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._finish()
            return {"CANCELLED"}
        if event.type == "MOUSEMOVE":
            travel = (
                Vector((event.mouse_region_x, event.mouse_region_y)) - self._press_xy
            )
            self._dragged |= travel.length > _DRAG_THRESHOLD_PX
            self._track_cursor(context, event)
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            self._finish()
            return self._commit(context)
        return {"RUNNING_MODAL"}

    @override
    def cancel(self, context: bpy.types.Context) -> None:
        self._finish()

    def _track_cursor(self, context: bpy.types.Context, event: bpy.types.Event) -> None:
        """Follow the cursor on the snapshot, keeping the last hit."""
        origin, direction = _ray(
            context, (float(event.mouse_region_x), float(event.mouse_region_y))
        )
        point, normal, _, _ = self._surface.ray_cast(origin, direction)
        self._on_surface = point is not None and normal is not None
        if point is not None and normal is not None:
            # Mirrored halves reverse face winding, so snapshot normals point inward.
            target = context.active_object
            if target is not None and target.matrix_world.to_3x3().determinant() < 0:
                normal.negate()
            self._position, self._normal = point, normal
        if self._area is not None:
            self._area.tag_redraw()

    def _draw(self) -> None:
        context = bpy.context
        if context.area != self._area or not self._on_surface:
            return
        try:
            _draw_key_preview(context, self._position, self._normal)
        except ValueError:
            # Invalid sidebar dimensions: the commit reports them.
            return

    def _finish(self) -> None:
        global _gesture
        if self._draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, "WINDOW")
            self._draw_handle = None
        _gesture = None
        if self._area is not None:
            self._area.tag_redraw()

    def _commit(self, context: bpy.types.Context) -> OperatorReturn:
        """Move the picked key, add a new one, or just keep the selection."""
        if self._picked_key_name and not self._dragged:
            return {"FINISHED"}
        if not self._on_surface:
            return {"CANCELLED"}
        try:
            if self._picked_key_name:
                KeyPair.from_context(context, self._picked_key_name).move(
                    context, self._position, self._normal
                )
            else:
                KeyPair.create(
                    context,
                    KeySettings.from_context(context),
                    self._position,
                    self._normal,
                )
        except (ValueError, RuntimeError) as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


def cancel_key_gesture() -> None:
    """Remove a transient drawing callback when the extension unloads."""
    if _gesture is not None:
        _gesture.cancel(bpy.context)
