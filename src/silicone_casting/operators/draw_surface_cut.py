"""Draw closed surface strokes and turn their interpolated patch into a cut."""

from typing import cast, override

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
from ..properties.settings import scene_settings
from . import _drawing_navigation
from ._drawing_session import DrawingSession
from ._operator import OperatorReturn
from ._stroke_overlay import draw_snap_hint

_BOUNDARY_GROUP = "Cut Boundary"
_INTERIOR_GROUP = "Cut Interior"


def _cutting_surface(target: bpy.types.Object | None) -> bpy.types.Object | None:
    if target is None or target.type != "MESH":
        return None
    if target.vertex_groups.get(_INTERIOR_GROUP) is not None:
        return target
    for modifier in reversed(list(target.modifiers)):
        if (
            not isinstance(modifier, bpy.types.NodesModifier)
            or modifier.node_group is None
        ):
            continue
        interface = modifier.node_group.interface
        assert interface is not None
        for item in interface.items_tree:
            if (
                isinstance(item, bpy.types.NodeTreeInterfaceSocketObject)
                and item.in_out == "INPUT"
                and item.name == "Cutting Surface"
            ):
                properties = getattr(modifier, "properties", None)
                if properties is None:
                    surface = modifier.get(item.identifier, item.default_value)
                else:
                    surface = getattr(properties.inputs, item.identifier).value
                if (
                    isinstance(surface, bpy.types.Object)
                    and surface.type == "MESH"
                    and surface.vertex_groups.get(_INTERIOR_GROUP) is not None
                ):
                    return surface
    return None


class SILCAST_OT_draw_surface_cut(bpy.types.Operator):
    """Draw on the evaluated active mesh, preview, then add one live
    modifier."""

    bl_idname = "silicone_casting.draw_surface_cut"
    bl_label = "Draw Surface Cut"
    bl_description = (
        "Draw closed loops on the mesh, then preview an editable curved cutting surface"
    )
    bl_options = {"REGISTER", "UNDO"}

    _target: bpy.types.Object
    _session: DrawingSession
    _surface: SurfaceSnapshot
    _selected: tuple[bpy.types.Object, ...]
    _loops: list[list[Vector]]
    _stroke: list[Vector]
    _history: list[tuple[list[list[Vector]], list[Vector]]]
    _future: list[tuple[list[list[Vector]], list[Vector]]]
    _ready: bool
    _drag_at: tuple[float, float] | None
    _thickness: float
    _margin: float
    _minimum: float
    _input_mode: str
    _hover: tuple[int, ...] | None
    _wire: bool
    _all_edges: bool

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
            shortcuts = (
                "Loop: Alt-click | Path: Ctrl-click"
                if self._input_mode == "EDGE"
                else "Line: Ctrl-click"
            )
            message = (
                "Preview: Enter = cut | Backspace = return to drawing | Esc = cancel"
                if self._ready
                else f"{len(self._loops)} loops | {self._input_mode.title()}: LMB | {shortcuts} | Smooth: S | Undo/Redo: Ctrl-Z/Shift-Z | Close: C | Preview: Space | Esc: cancel"
            )
        self._session.header(message)

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
            self.report({"ERROR"}, f"Could not start drawing the cut: {error}")
            return {"CANCELLED"}
        return {"RUNNING_MODAL"}

    def _start_drawing(self, context: bpy.types.Context) -> None:
        props = scene_settings(context)
        self._thickness = mm_to_units(
            props.surface_cut_thickness_mm, context.scene.unit_settings.scale_length
        )
        self._margin = mm_to_units(
            props.surface_cut_margin_mm, context.scene.unit_settings.scale_length
        )
        self._minimum = mm_to_units(
            MIN_SURFACE_CUT_THICKNESS_MM, context.scene.unit_settings.scale_length
        )
        self._history = []
        self._future = []
        self._loops = []
        self._stroke = []
        self._ready = False
        self._drag_at = None
        self._wire = self._target.show_wire
        self._all_edges = self._target.show_all_edges
        self._input_mode = ""
        self._hover = None
        self._session = DrawingSession.from_context(
            context,
            self,
            "Cut Strokes",
            tuple(self._target.users_collection),
            draw=self._draw_snap_hint,
        )
        try:
            self._session.preview.select_set(True)
            self._set_input_mode(props.surface_cut_input_mode)
        except Exception:
            self._cleanup()
            raise

    def _show_strokes(self) -> None:
        self._session.show_paths((self._stroke,), loops=self._loops)

    def _ray(self, mouse: Vector) -> tuple[Vector, Vector]:
        return self._session.ray(
            mouse,
            clamp=self._surface.size * 4
            + (
                self._session.view.view_location - self._target.matrix_world.translation
            ).length,
        )

    def _point(self, mouse: Vector) -> Vector | None:
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
        self._target.show_wire = self._wire or mode != "FREEHAND"
        self._target.show_all_edges = self._all_edges or mode != "FREEHAND"
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
            tolerance=self._surface.size * 1e-6,
        )

    def _draw_snap_hint(self) -> None:
        if (
            bpy.context.region != self._session.region
            or self._ready
            or self._hover is None
        ):
            return
        pixels = [self._session.project(self._surface.vertices[i]) for i in self._hover]
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
        if stroke == self._stroke:
            return
        self._remember()
        self._stroke = stroke
        self._show_strokes()
        self._header()

    def _extend_to_edge(
        self, edge: tuple[int, int], *, loop: bool, shortest: bool
    ) -> list[Vector]:
        if loop or shortest:
            return extend_edge_path(
                self._stroke,
                self._surface.vertices,
                self._surface.edges,
                self._surface.faces,
                edge,
                loop=loop,
                tolerance=self._surface.size * 1e-6,
            )
        a, b = (self._surface.vertices[i] for i in edge)
        return extend_stroke_along_edge(self._stroke, a, b, self._surface.size * 1e-6)

    def _extend_to_vertex(self, index: int) -> list[Vector]:
        point = self._surface.vertices[index]
        if not self._stroke:
            return [point.copy()]
        start, end = (
            self._session.project(self._stroke[-1]),
            self._session.project(point),
        )
        if start is None or end is None:
            raise ValueError("Orbit until the stroke endpoint is visible")
        if (point - self._stroke[-1]).length < self._surface.size * 1e-6:
            return self._stroke
        origin, direction = self._ray(start)
        distance = (self._stroke[-1] - origin).dot(direction)
        if (
            self._surface.bvh.ray_cast(
                origin, direction, max(0.0, distance - self._surface.size * 1e-6)
            )[0]
            is not None
        ):
            raise ValueError("Orbit until the stroke endpoint is visible")
        connected = any(
            index in edge
            and any(
                (self._surface.vertices[i] - self._stroke[-1]).length
                < self._surface.size * 1e-6
                for i in edge
            )
            for edge in self._surface.edges
        )
        segment = (
            [self._stroke[-1], point.copy()]
            if connected
            else self._project_vertex_segment(start, end, point)
        )
        return [*self._stroke, *segment[1:]]

    def _project_vertex_segment(
        self, start: Vector, end: Vector, point: Vector
    ) -> list[Vector]:
        def project(pixel: Vector) -> Vector | None:
            if (pixel - start).length < 1e-5:
                return self._stroke[-1].copy()
            if (pixel - end).length < 1e-5:
                return point.copy()
            return self._point(pixel)

        return project_straight_segment(start, end, project, self._surface.size * 0.04)

    def _append_point(self, mouse: Vector) -> bool:
        point = self._point(mouse)
        if point is None:
            self._header(
                "Stroke paused off the mesh; resume near its end, or orbit with MMB"
            )
            return False
        if self._stroke:
            distance = (point - self._stroke[-1]).length
            if distance > self._surface.size * 0.04:
                self._header(
                    "Resume near the last point; the stroke cannot jump across the mesh"
                )
                return False
            if distance < self._surface.size * 0.0005:
                return True
        self._stroke.append(point)
        self._header()
        return True

    def _remember(self) -> None:
        self._future.clear()
        self._history.append(([loop[:] for loop in self._loops], self._stroke[:]))

    def _restore_history(self, *, redo: bool) -> None:
        source = self._future if redo else self._history
        destination = self._history if redo else self._future
        if not source:
            return
        destination.append(([loop[:] for loop in self._loops], self._stroke[:]))
        self._loops, self._stroke = source.pop()
        self._drag_at = None
        self._hover = None
        self._ready = False
        self._session.preview.vertex_groups.clear()
        self._show_strokes()
        self._header()

    def _straight_line(self, mouse: Vector) -> None:
        if not self._stroke:
            self._remember()
            self._append_point(mouse)
            return
        start = self._session.project(self._stroke[-1])
        if start is None:
            self._header("Orbit until the stroke endpoint is visible")
            return
        try:
            points = project_straight_segment(
                start, mouse, self._point, self._surface.size * 0.04
            )
            if (points[0] - self._stroke[-1]).length > self._surface.size * 0.0005:
                raise ValueError("Orbit until the stroke endpoint is visible")
        except ValueError as error:
            self._header(str(error))
            return
        self._remember()
        for point in points[1:]:
            if (point - self._stroke[-1]).length >= self._surface.size * 0.0005:
                self._stroke.append(point)
        self._header()

    def _smooth(self) -> None:
        stroke = self._stroke or (self._loops[-1] if self._loops else [])
        if len(stroke) < 3:
            self._header("Draw a line before smoothing it")
            return
        smoothed = smooth_surface_stroke(
            stroke, self._surface.bvh, closed=not self._stroke
        )
        self._remember()
        if self._stroke:
            self._stroke = smoothed
        else:
            self._loops[-1] = smoothed
        self._show_strokes()
        self._header()

    def _close_loop(self) -> None:
        if len(self._stroke) < 3:
            self._header("Draw a loop before closing it")
            return
        if (self._stroke[-1] - self._stroke[0]).length > self._surface.size * 0.025:
            self._header("Continue drawing back to the start before closing the loop")
            return
        self._remember()
        # The endpoint near the start is redundant and can create a tiny CDT
        # edge. Keep the first point as the exact closing point.
        if (
            len(self._stroke) > 3
            and (self._stroke[-1] - self._stroke[0]).length
            < self._surface.size * 0.0005
        ):
            self._stroke.pop()
        self._loops.append(self._stroke)
        self._stroke = []
        self._show_strokes()
        self._header()

    def _build_preview(self) -> None:
        if self._stroke:
            self._header("Close the current stroke with C before previewing")
            return
        try:
            mesh, boundary, interior = interpolate_cutting_surface(
                [
                    simplify_closed_loop(loop, self._surface.size * 0.0005)
                    for loop in self._loops
                ],
                margin=self._margin,
            )
        except ValueError as error:
            self._header(str(error))
            self.report({"WARNING"}, str(error))
            return
        self._session.replace_mesh(mesh)
        self._session.preview.display_type = "SOLID"
        self._session.preview.vertex_groups.clear()
        self._session.preview.vertex_groups.new(name=_BOUNDARY_GROUP).add(
            boundary, 1.0, "REPLACE"
        )
        self._session.preview.vertex_groups.new(name=_INTERIOR_GROUP).add(
            interior, 1.0, "REPLACE"
        )
        self._ready = True
        self._header()

    def _cleanup(self, *, keep_surface: bool = False) -> None:
        if not self._session.running:
            return
        try:
            self._session.close(keep_preview=keep_surface)
        finally:
            try:
                self._target.show_wire = self._wire
                self._target.show_all_edges = self._all_edges
            except ReferenceError:
                pass
            if keep_surface:
                try:
                    self._session.preview.select_set(False)
                except ReferenceError:
                    pass
            for obj in self._selected:
                try:
                    obj.select_set(True)
                except ReferenceError:
                    pass

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
        if self._ready:
            # Drop a stale preview if the new extension cannot be generated.
            self._ready = False
            self._session.preview.vertex_groups.clear()
            self._show_strokes()
            self._build_preview()

    def _modal(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        self._set_input_mode(scene_settings(context).surface_cut_input_mode)
        self._sync_margin(context)
        if event.type.startswith("TIMER"):
            return {"PASS_THROUGH"}
        if (
            event.value == "PRESS"
            and (event.ctrl or event.oskey)
            and event.type in {"Z", "Y"}
        ):
            self._restore_history(redo=event.type == "Y" or event.shift)
            return {"RUNNING_MODAL"}
        navigation = self._session.navigation(context, event)
        if navigation is not None:
            self._drag_at = None
            return navigation
        if event.type == "ESC" and event.value == "PRESS":
            self._cleanup()
            return {"CANCELLED"}
        if event.type == "BACK_SPACE" and event.value == "PRESS":
            self._remove_last_stroke()
        if self._ready:
            if event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS":
                return self._finish(context)
            return {"RUNNING_MODAL"}
        self._draw_event(event)
        return {"RUNNING_MODAL"}

    def _remove_last_stroke(self) -> None:
        self._drag_at = None
        if self._ready:
            self._ready = False
            self._session.preview.vertex_groups.clear()
        elif self._stroke:
            self._remember()
            self._stroke = []
        elif self._loops:
            self._remember()
            self._stroke = self._loops.pop()
        self._show_strokes()
        self._header()

    def _finish(self, context: bpy.types.Context) -> OperatorReturn:
        create_surface_cut(
            self._target,
            self._session.preview,
            self._thickness,
            minimum_thickness=self._minimum,
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
        if event.type == "S" and event.value == "PRESS":
            self._drag_at = None
            self._smooth()
        elif event.type == "SPACE" and event.value == "PRESS":
            self._drag_at = None
            self._build_preview()
        elif event.type == "C" and event.value == "PRESS":
            self._drag_at = None
            self._close_loop()
        elif event.type == "LEFTMOUSE":
            self._mouse_button(event)
        elif event.type == "MOUSEMOVE":
            self._move_mouse(event)

    def _mouse_button(self, event: bpy.types.Event) -> None:
        mouse = self._session.mouse(event)
        if event.value == "PRESS":
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
        elif event.value == "RELEASE":
            self._drag_at = None

    def _move_mouse(self, event: bpy.types.Event) -> None:
        mouse = self._session.mouse(event)
        if self._input_mode != "FREEHAND":
            self._hover = self._pick(mouse)
            self._session.redraw()
        elif self._drag_at is not None:
            previous = Vector(self._drag_at)
            count = max(1, int((mouse - previous).length / 3))
            self._drag_at = (mouse.x, mouse.y)
            for i in range(1, count + 1):
                if not self._append_point(previous.lerp(mouse, i / count)):
                    self._drag_at = None
                    break
            self._show_strokes()


def cancel_surface_drawing() -> None:
    """Remove temporary geometry when the extension is disabled mid-stroke."""
    active = _drawing_navigation.active_drawing
    if isinstance(active, SILCAST_OT_draw_surface_cut):
        active.cancel(bpy.context)


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
        surface.select_set(True)
        context.view_layer.objects.active = surface
        group = surface.vertex_groups[_INTERIOR_GROUP]
        surface.vertex_groups.active_index = group.index
        mesh = cast(bpy.types.Mesh, surface.data)
        for edge in mesh.edges:
            edge.select = False
        for face in mesh.polygons:
            face.select = False
        for vertex in mesh.vertices:
            vertex.select = any(item.group == group.index for item in vertex.groups)
        context.tool_settings.mesh_select_mode = (True, False, False)
        bpy.ops.object.mode_set(mode="EDIT")
        return {"FINISHED"}
