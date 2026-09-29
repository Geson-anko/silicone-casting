"""Draw closed surface strokes and turn their interpolated patch into a cut."""

from contextlib import suppress
from dataclasses import dataclass, field
from typing import Final, Self, TypeGuard, cast, override

import bpy
from mathutils import Vector

from ..core.cut_strokes import project_straight_segment, smooth_surface_stroke
from ..core.drawn_surface import interpolate_cutting_surface, simplify_closed_loop
from ..core.edge_paths import extend_edge_path
from ..core.surface_cut import MIN_SURFACE_CUT_THICKNESS_MM, create_surface_cut
from ..core.surface_picking import (
    SurfaceSnapshot,
    extend_stroke_along_edge,
    pick_surface_element,
)
from ..core.units import mm_to_units
from ..core.volume import is_watertight
from ..properties.settings import scene_settings
from . import _drawing_navigation
from ._drawing_session import DrawingSession
from ._operator import OperatorReturn
from ._stroke_history import StrokeHistory
from ._stroke_overlay import draw_snap_hint

_BOUNDARY_GROUP: Final = "Cut Boundary"
_INTERIOR_GROUP: Final = "Cut Interior"
_CUTTING_SURFACE_SOCKET: Final = "Cutting Surface"
_PREVIEW_NAME: Final = "Cut Strokes"
_HIDDEN_ENDPOINT: Final = "Orbit until the stroke endpoint is visible"

# Distances below are fractions of the mesh size, so drawing behaves the same
# on a ring and on a bust.
# Points closer than this are the same vertex.
_COINCIDENT_FRACTION: Final = 1e-6
# Samples closer than this only add noise, and tiny edges upset the CDT.
_MIN_SAMPLE_FRACTION: Final = 0.0005
# A longer jump means the cursor slid onto an unrelated part of the mesh.
_MAX_STEP_FRACTION: Final = 0.04
# How close the stroke must return to its start before C closes it.
_CLOSE_GAP_FRACTION: Final = 0.025
# Orthographic rays start this many mesh sizes behind the view target, so they
# begin in front of the whole mesh.
_RAY_CLAMP_SIZES: Final = 4
# Pixel distance at which a projected pixel is the endpoint itself.
_PIXEL_EPSILON: Final = 1e-5
# Screen distance between interpolated samples of a fast freehand drag.
_DRAG_STEP_PX: Final = 3


@dataclass(frozen=True)
class _Tolerances:
    """World-space drawing distances scaled to the target mesh."""

    coincident: float
    min_sample: float
    max_step: float
    close_gap: float

    @classmethod
    def for_size(cls, size: float) -> Self:
        return cls(
            coincident=size * _COINCIDENT_FRACTION,
            min_sample=size * _MIN_SAMPLE_FRACTION,
            max_step=size * _MAX_STEP_FRACTION,
            close_gap=size * _CLOSE_GAP_FRACTION,
        )


@dataclass
class _Strokes:
    """Closed loops plus the open stroke currently being drawn."""

    loops: list[list[Vector]] = field(default_factory=list[list[Vector]])
    current: list[Vector] = field(default_factory=list[Vector])

    def copy(self) -> Self:
        return type(self)([loop[:] for loop in self.loops], self.current[:])


@dataclass(frozen=True)
class _EdgeDisplay:
    """The target's own wireframe flags, restored when drawing ends."""

    show_wire: bool
    show_all_edges: bool

    @classmethod
    def from_object(cls, obj: bpy.types.Object) -> Self:
        return cls(obj.show_wire, obj.show_all_edges)

    def apply(self, obj: bpy.types.Object, *, force: bool = False) -> None:
        """Restore the flags, or turn the wireframe on while snapping."""
        obj.show_wire = self.show_wire or force
        obj.show_all_edges = self.show_all_edges or force


def _is_cutting_surface(obj: object) -> TypeGuard[bpy.types.Object]:
    return (
        isinstance(obj, bpy.types.Object)
        and obj.type == "MESH"
        and obj.vertex_groups.get(_INTERIOR_GROUP) is not None
    )


def _socket_value(
    modifier: bpy.types.NodesModifier, item: bpy.types.NodeTreeInterfaceSocketObject
) -> object:
    # Blender versions without ``properties`` store modifier inputs as ID
    # properties keyed by the socket identifier.
    properties = getattr(modifier, "properties", None)
    if properties is None:
        return modifier.get(item.identifier, item.default_value)
    return getattr(properties.inputs, item.identifier).value


def _modifier_cutting_surface(
    modifier: bpy.types.Modifier,
) -> bpy.types.Object | None:
    """Return the drawn patch wired into a Surface Cut node modifier."""
    if not isinstance(modifier, bpy.types.NodesModifier) or modifier.node_group is None:
        return None
    interface = modifier.node_group.interface
    assert interface is not None
    for item in interface.items_tree:
        if not (
            isinstance(item, bpy.types.NodeTreeInterfaceSocketObject)
            and item.in_out == "INPUT"
            and item.name == _CUTTING_SURFACE_SOCKET
        ):
            continue
        surface = _socket_value(modifier, item)
        if _is_cutting_surface(surface):
            return surface
    return None


def _cutting_surface(target: bpy.types.Object | None) -> bpy.types.Object | None:
    """Find the editable patch: the target itself, or its latest Surface Cut."""
    if target is None or target.type != "MESH":
        return None
    if _is_cutting_surface(target):
        return target
    for modifier in reversed(list(target.modifiers)):
        surface = _modifier_cutting_surface(modifier)
        if surface is not None:
            return surface
    return None


class SILCAST_OT_draw_surface_cut(bpy.types.Operator):
    """Draw on the active mesh, preview, then add one live modifier."""

    bl_idname = "silicone_casting.draw_surface_cut"
    bl_label = "Draw Surface Cut"
    bl_description = (
        "Draw closed loops on the mesh, then preview an editable curved cutting surface"
    )
    bl_options = {"REGISTER", "UNDO"}

    _target: bpy.types.Object
    _session: DrawingSession
    _surface: SurfaceSnapshot
    _tolerances: _Tolerances
    _selected: tuple[bpy.types.Object, ...]
    _strokes: _Strokes
    _history: StrokeHistory[_Strokes]
    # True while the interpolated patch, not the strokes, is shown.
    _previewing: bool
    # Last sampled cursor position while LMB is held; None when not dragging.
    _drag_at: tuple[float, float] | None
    _thickness: float
    _margin: float
    _minimum_thickness: float
    _input_mode: str
    # Vertex indices of the snapping candidate under the cursor.
    _hover: tuple[int, ...] | None
    _edge_display: _EdgeDisplay

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        return (
            _drawing_navigation.active_drawing is None
            and context.mode == "OBJECT"
            and context.area is not None
            and context.area.type == "VIEW_3D"
            and context.active_object is not None
            and context.active_object.type == "MESH"
        )

    def _header(self, message: str = "") -> None:
        if not message:
            message = (
                "Preview: Enter = cut | Backspace = return to drawing | Esc = cancel"
                if self._previewing
                else self._drawing_help()
            )
        self._session.header(message)

    def _drawing_help(self) -> str:
        snapping = (
            "Loop: Alt-click | Path: Ctrl-click"
            if self._input_mode == "EDGE"
            else "Line: Ctrl-click"
        )
        return " | ".join(
            (
                f"{len(self._strokes.loops)} loops",
                f"{self._input_mode.title()}: LMB",
                snapping,
                "Smooth: S",
                "Undo/Redo: Ctrl-Z/Shift-Z",
                "Close: C",
                "Preview: Space",
                "Esc: cancel",
            )
        )

    @override
    def invoke(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        del event
        target = context.active_object
        if target is None:
            return {"CANCELLED"}
        try:
            self._surface = SurfaceSnapshot.from_objects(
                (target,), context.evaluated_depsgraph_get()
            )
        except ValueError as error:
            self.report({"WARNING"}, str(error))
            return {"CANCELLED"}
        if self._surface.size <= 0:
            return {"CANCELLED"}
        self._target = target
        self._selected = tuple(context.selected_objects or ())
        try:
            self._start_drawing(context)
        except ValueError as error:
            self.report({"WARNING"}, str(error))
            return {"CANCELLED"}
        except Exception as error:
            # Operator boundary: report any startup failure instead of a traceback.
            self.report({"ERROR"}, f"Could not start drawing the cut: {error}")
            return {"CANCELLED"}
        return {"RUNNING_MODAL"}

    def _start_drawing(self, context: bpy.types.Context) -> None:
        settings = scene_settings(context)
        scale = context.scene.unit_settings.scale_length
        self._thickness = mm_to_units(settings.surface_cut_thickness_mm, scale)
        self._margin = mm_to_units(settings.surface_cut_margin_mm, scale)
        self._minimum_thickness = mm_to_units(MIN_SURFACE_CUT_THICKNESS_MM, scale)
        self._tolerances = _Tolerances.for_size(self._surface.size)
        self._strokes = _Strokes()
        self._history = StrokeHistory(_Strokes.copy)
        self._previewing = False
        self._drag_at = None
        self._edge_display = _EdgeDisplay.from_object(self._target)
        self._input_mode = ""
        self._hover = None
        self._session = DrawingSession.from_context(
            context,
            self,
            _PREVIEW_NAME,
            tuple(self._target.users_collection),
            draw=self._draw_snap_hint,
        )
        try:
            self._session.preview.select_set(True)
            self._set_input_mode(settings.surface_cut_input_mode)
        except Exception:
            # Release the session whatever went wrong, then let invoke report.
            self._cleanup()
            raise

    def _show_strokes(self) -> None:
        self._session.show_paths((self._strokes.current,), loops=self._strokes.loops)

    def _remember(self) -> None:
        self._history.remember(self._strokes)

    def _leave_preview(self) -> None:
        self._previewing = False
        self._session.preview.vertex_groups.clear()

    def _ray(self, mouse: Vector) -> tuple[Vector, Vector]:
        view_distance = (
            self._session.view.view_location - self._target.matrix_world.translation
        ).length
        return self._session.ray(
            mouse, clamp=self._surface.size * _RAY_CLAMP_SIZES + view_distance
        )

    def _point(self, mouse: Vector) -> Vector | None:
        """Return the surface point under a viewport pixel, if any."""
        if not self._session.contains(mouse):
            return None
        origin, direction = self._ray(mouse)
        point, _, _, _ = self._surface.bvh.ray_cast(origin, direction)
        return point

    def _set_input_mode(self, mode: str) -> None:
        if mode == self._input_mode:
            return
        self._input_mode = mode
        self._drag_at = None
        self._hover = None
        self._edge_display.apply(self._target, force=mode != "FREEHAND")
        self._header()

    def _pick(self, mouse: Vector) -> tuple[int, ...] | None:
        return pick_surface_element(
            mouse,
            self._surface.vertices,
            self._surface.edges,
            self._session.project,
            self._ray,
            self._surface.snap_bvh,
            vertex_mode=self._input_mode == "VERTEX",
            tolerance=self._tolerances.coincident,
        )

    def _draw_snap_hint(self) -> None:
        if (
            bpy.context.region != self._session.region
            or self._previewing
            or self._hover is None
        ):
            return
        pixels = [
            self._session.project(self._surface.vertices[index])
            for index in self._hover
        ]
        draw_snap_hint([pixel for pixel in pixels if pixel is not None])

    def _snap_click(
        self, mouse: Vector, *, loop: bool = False, shortest: bool = False
    ) -> None:
        self._hover = self._pick(mouse)
        if self._hover is None:
            self._header("Click near a visible vertex or edge")
            return
        try:
            if len(self._hover) == 2:
                stroke = self._extend_to_edge(
                    (self._hover[0], self._hover[1]), loop=loop, shortest=shortest
                )
            else:
                stroke = self._extend_to_vertex(self._hover[0])
        except ValueError as error:
            self._header(str(error))
            return
        if stroke == self._strokes.current:
            return
        self._remember()
        self._strokes.current = stroke
        self._show_strokes()
        self._header()

    def _extend_to_edge(
        self, edge: tuple[int, int], *, loop: bool, shortest: bool
    ) -> list[Vector]:
        if loop or shortest:
            return extend_edge_path(
                self._strokes.current,
                self._surface.vertices,
                self._surface.edges,
                self._surface.faces,
                edge,
                loop=loop,
                tolerance=self._tolerances.coincident,
            )
        a, b = (self._surface.vertices[index] for index in edge)
        return extend_stroke_along_edge(
            self._strokes.current, a, b, self._tolerances.coincident
        )

    def _extend_to_vertex(self, index: int) -> list[Vector]:
        """Continue the stroke to a vertex, along its edge when one connects.

        Raises:
            ValueError: If the stroke end is hidden, so a straight segment
                from it could not be projected onto the visible surface.
        """
        stroke = self._strokes.current
        point = self._surface.vertices[index]
        if not stroke:
            return [point.copy()]
        start = self._session.project(stroke[-1])
        end = self._session.project(point)
        if start is None or end is None:
            raise ValueError(_HIDDEN_ENDPOINT)
        if (point - stroke[-1]).length < self._tolerances.coincident:
            return stroke
        if self._is_occluded(stroke[-1], start):
            raise ValueError(_HIDDEN_ENDPOINT)
        if self._shares_edge_with_stroke_end(index):
            return [*stroke, point.copy()]
        return [*stroke, *self._project_vertex_segment(start, end, point)[1:]]

    def _is_occluded(self, point: Vector, pixel: Vector) -> bool:
        """Tell whether geometry hides ``point`` as seen at ``pixel``."""
        origin, direction = self._ray(pixel)
        distance = (point - origin).dot(direction)
        hit, _, _, _ = self._surface.bvh.ray_cast(
            origin, direction, max(0.0, distance - self._tolerances.coincident)
        )
        return hit is not None

    def _shares_edge_with_stroke_end(self, index: int) -> bool:
        end = self._strokes.current[-1]
        return any(
            index in edge
            and any(
                (self._surface.vertices[other] - end).length
                < self._tolerances.coincident
                for other in edge
            )
            for edge in self._surface.edges
        )

    def _project_vertex_segment(
        self, start: Vector, end: Vector, point: Vector
    ) -> list[Vector]:
        """Project a screen-space line onto the surface, pinning both ends."""
        stroke_end = self._strokes.current[-1]

        def project(pixel: Vector) -> Vector | None:
            if (pixel - start).length < _PIXEL_EPSILON:
                return stroke_end.copy()
            if (pixel - end).length < _PIXEL_EPSILON:
                return point.copy()
            return self._point(pixel)

        return project_straight_segment(start, end, project, self._tolerances.max_step)

    def _append_point(self, mouse: Vector) -> bool:
        """Add the surface point under the cursor to the open stroke.

        Returns:
            False when the stroke cannot continue there, which ends a drag.
        """
        point = self._point(mouse)
        if point is None:
            self._header(
                "Stroke paused off the mesh; resume near its end, or orbit with MMB"
            )
            return False
        stroke = self._strokes.current
        if stroke:
            distance = (point - stroke[-1]).length
            if distance > self._tolerances.max_step:
                self._header(
                    "Resume near the last point; the stroke cannot jump across the mesh"
                )
                return False
            if distance < self._tolerances.min_sample:
                return True
        stroke.append(point)
        self._header()
        return True

    def _step_history(self, *, redo: bool) -> None:
        strokes = self._history.step(self._strokes, redo=redo)
        if strokes is None:
            return
        self._strokes = strokes
        self._drag_at = None
        self._hover = None
        self._leave_preview()
        self._show_strokes()
        self._header()

    def _straight_line(self, mouse: Vector) -> None:
        stroke = self._strokes.current
        if not stroke:
            self._remember()
            self._append_point(mouse)
            return
        start = self._session.project(stroke[-1])
        if start is None:
            self._header(_HIDDEN_ENDPOINT)
            return
        try:
            points = project_straight_segment(
                start, mouse, self._point, self._tolerances.max_step
            )
            if (points[0] - stroke[-1]).length > self._tolerances.min_sample:
                raise ValueError(_HIDDEN_ENDPOINT)
        except ValueError as error:
            self._header(str(error))
            return
        self._remember()
        for point in points[1:]:
            if (point - stroke[-1]).length >= self._tolerances.min_sample:
                stroke.append(point)
        self._header()

    def _smooth(self) -> None:
        """Smooth the open stroke, else the last closed loop."""
        strokes = self._strokes
        closed = not strokes.current
        stroke = strokes.loops[-1] if closed and strokes.loops else strokes.current
        if len(stroke) < 3:
            self._header("Draw a line before smoothing it")
            return
        smoothed = smooth_surface_stroke(stroke, self._surface.bvh, closed=closed)
        self._remember()
        if closed:
            strokes.loops[-1] = smoothed
        else:
            strokes.current = smoothed
        self._show_strokes()
        self._header()

    def _close_loop(self) -> None:
        stroke = self._strokes.current
        if len(stroke) < 3:
            self._header("Draw a loop before closing it")
            return
        gap = (stroke[-1] - stroke[0]).length
        if gap > self._tolerances.close_gap:
            self._header("Continue drawing back to the start before closing the loop")
            return
        self._remember()
        # The endpoint near the start is redundant and can create a tiny CDT
        # edge. Keep the first point as the exact closing point.
        if len(stroke) > 3 and gap < self._tolerances.min_sample:
            stroke.pop()
        self._strokes.loops.append(stroke)
        self._strokes.current = []
        self._show_strokes()
        self._header()

    def _build_preview(self) -> None:
        if self._strokes.current:
            self._header("Close the current stroke with C before previewing")
            return
        try:
            mesh, boundary, interior = interpolate_cutting_surface(
                [
                    simplify_closed_loop(loop, self._tolerances.min_sample)
                    for loop in self._strokes.loops
                ],
                margin=self._margin,
            )
        except ValueError as error:
            self._header(str(error))
            self.report({"WARNING"}, str(error))
            return
        preview = self._session.preview
        self._session.replace_mesh(mesh)
        preview.display_type = "SOLID"
        preview.show_in_front = False
        preview.vertex_groups.clear()
        preview.vertex_groups.new(name=_BOUNDARY_GROUP).add(boundary, 1.0, "REPLACE")
        preview.vertex_groups.new(name=_INTERIOR_GROUP).add(interior, 1.0, "REPLACE")
        self._previewing = True
        self._header()

    def _cleanup(self, *, keep_surface: bool = False) -> None:
        """Close the session and give the user their scene state back."""
        if not self._session.running:
            return
        try:
            self._session.close(keep_preview=keep_surface)
        finally:
            # Objects may have been deleted while drawing owned the viewport.
            with suppress(ReferenceError):
                self._edge_display.apply(self._target)
            if keep_surface:
                with suppress(ReferenceError):
                    self._session.preview.select_set(False)
            for obj in self._selected:
                with suppress(ReferenceError):
                    obj.select_set(True)

    @override
    def cancel(self, context: bpy.types.Context) -> None:
        del context
        self._cleanup()

    @override
    def modal(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        if not self._session.running:
            return {"CANCELLED"}
        try:
            return self._modal(context, event)
        except Exception as error:
            # Operator boundary: never leave the viewport locked by a failure.
            self._cleanup()
            self.report({"ERROR"}, f"Could not draw the cut: {error}")
            return {"CANCELLED"}

    def _sync_margin(self, context: bpy.types.Context) -> None:
        margin = mm_to_units(
            scene_settings(context).surface_cut_margin_mm,
            context.scene.unit_settings.scale_length,
        )
        if margin == self._margin:
            return
        self._margin = margin
        if self._previewing:
            # Drop a stale preview if the new extension cannot be generated.
            self._leave_preview()
            self._show_strokes()
            self._build_preview()

    def _modal(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        self._set_input_mode(scene_settings(context).surface_cut_input_mode)
        self._sync_margin(context)
        if event.type.startswith("TIMER"):
            return {"PASS_THROUGH"}
        pressed = event.value == "PRESS"
        if pressed and (event.ctrl or event.oskey) and event.type in {"Z", "Y"}:
            self._step_history(redo=event.type == "Y" or event.shift)
            return {"RUNNING_MODAL"}
        navigation = self._session.navigation(context, event)
        if navigation is not None:
            self._drag_at = None
            return navigation
        if event.type == "ESC" and pressed:
            self._cleanup()
            return {"CANCELLED"}
        if event.type == "BACK_SPACE" and pressed:
            self._remove_last_stroke()
        if self._previewing:
            if event.type in {"RET", "NUMPAD_ENTER"} and pressed:
                return self._finish(context)
            return {"RUNNING_MODAL"}
        self._draw_event(event)
        return {"RUNNING_MODAL"}

    def _remove_last_stroke(self) -> None:
        """Leave the preview, or discard the open stroke, or reopen a loop."""
        self._drag_at = None
        strokes = self._strokes
        if self._previewing:
            self._leave_preview()
        elif strokes.current:
            self._remember()
            strokes.current = []
        elif strokes.loops:
            self._remember()
            strokes.current = strokes.loops.pop()
        self._show_strokes()
        self._header()

    def _finish(self, context: bpy.types.Context) -> OperatorReturn:
        manifold = is_watertight(self._target, context.evaluated_depsgraph_get())
        create_surface_cut(
            self._target,
            self._session.preview,
            self._thickness,
            minimum_thickness=self._minimum_thickness,
            solver="Manifold" if manifold else "Exact",
        )
        self._session.preview.name = f"{self._target.name}.Cutting Surface"
        self._cleanup(keep_surface=True)
        context.view_layer.objects.active = self._target
        self.report(
            {"INFO"},
            "Surface Cut added. Use Edit Cutting Surface to shape its interior",
        )
        return {"FINISHED"}

    def _draw_event(self, event: bpy.types.Event) -> None:
        pressed = event.value == "PRESS"
        if event.type == "S" and pressed:
            self._drag_at = None
            self._smooth()
        elif event.type == "SPACE" and pressed:
            self._drag_at = None
            self._build_preview()
        elif event.type == "C" and pressed:
            self._drag_at = None
            self._close_loop()
        elif event.type == "LEFTMOUSE":
            self._mouse_button(event)
        elif event.type == "MOUSEMOVE":
            self._move_mouse(event)

    def _mouse_button(self, event: bpy.types.Event) -> None:
        mouse = self._session.mouse(event)
        if event.value == "RELEASE":
            self._drag_at = None
            return
        if event.value != "PRESS":
            return
        if self._input_mode != "FREEHAND":
            self._snap_click(mouse, loop=event.alt, shortest=event.ctrl)
            return
        if event.ctrl:
            self._drag_at = None
            self._straight_line(mouse)
            self._show_strokes()
            return
        self._remember()
        self._drag_at = (mouse.x, mouse.y) if self._append_point(mouse) else None
        self._show_strokes()

    def _move_mouse(self, event: bpy.types.Event) -> None:
        mouse = self._session.mouse(event)
        if self._input_mode != "FREEHAND":
            self._hover = self._pick(mouse)
            self._session.redraw()
        elif self._drag_at is not None:
            self._drag_to(mouse)

    def _drag_to(self, mouse: Vector) -> None:
        """Sample a dragged segment evenly so fast strokes stay whole."""
        assert self._drag_at is not None
        previous = Vector(self._drag_at)
        count = max(1, int((mouse - previous).length / _DRAG_STEP_PX))
        self._drag_at = (mouse.x, mouse.y)
        for step in range(1, count + 1):
            if not self._append_point(previous.lerp(mouse, step / count)):
                self._drag_at = None
                break
        self._show_strokes()


def cancel_surface_drawing() -> None:
    """Remove temporary geometry when the extension is disabled mid-stroke."""
    active = _drawing_navigation.active_drawing
    if isinstance(active, SILCAST_OT_draw_surface_cut):
        active.cancel(bpy.context)


def _select_interior(surface: bpy.types.Object) -> None:
    """Select exactly the interior vertices, leaving the pinned rim alone."""
    group = surface.vertex_groups[_INTERIOR_GROUP]
    surface.vertex_groups.active_index = group.index
    mesh = cast(bpy.types.Mesh, surface.data)
    for edge in mesh.edges:
        edge.select = False
    for face in mesh.polygons:
        face.select = False
    for vertex in mesh.vertices:
        vertex.select = any(item.group == group.index for item in vertex.groups)


class SILCAST_OT_edit_cutting_surface(bpy.types.Operator):
    """Enter mesh editing with only the generated patch's interior selected."""

    bl_idname = "silicone_casting.edit_cutting_surface"
    bl_label = "Edit Cutting Surface"
    bl_description = "Edit the latest drawn cutting surface with its interior selected; the cut updates live"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        return (
            _drawing_navigation.active_drawing is None
            and context.mode == "OBJECT"
            and _cutting_surface(context.active_object) is not None
        )

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        surface = _cutting_surface(context.active_object)
        if surface is None:
            return {"CANCELLED"}
        for obj in context.selected_objects or ():
            obj.select_set(False)
        surface.hide_set(False)
        surface.display_type = "SOLID"
        surface.show_in_front = False
        surface.select_set(True)
        context.view_layer.objects.active = surface
        _select_interior(surface)
        context.tool_settings.mesh_select_mode = (True, False, False)
        bpy.ops.object.mode_set(mode="EDIT")
        return {"FINISHED"}
