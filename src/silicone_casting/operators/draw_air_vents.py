"""Draw planar round air channels and subtract them from selected molds."""

from collections.abc import Sequence
from typing import cast, override

import bpy
from bpy_extras import view3d_utils
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from ..core.air_vents import (
    add_air_vent_cutters,
    create_air_vent_mesh,
    simplify_vent_path,
    smooth_vent_path,
)
from . import _drawing_navigation
from ._drawing_navigation import navigate_drawing_view, over_view_controls
from ._operator import OperatorReturn


class SILCAST_OT_draw_air_vents(bpy.types.Operator):
    """Freeze a face plane, draw tubes, then cut the original selection."""

    bl_idname = "silicone_casting.draw_air_vents"
    bl_label = "Draw Air Vents"
    bl_description = (
        "Draw round air channels on the plane of the first clicked face, "
        "then subtract them from all selected meshes"
    )
    bl_options = {"REGISTER", "UNDO"}

    _targets: tuple[bpy.types.Object, ...]
    _preview: bpy.types.Object
    _area: bpy.types.Area
    _region: bpy.types.Region
    _view: bpy.types.RegionView3D
    _bvh: BVHTree
    _origin: tuple[float, float, float] | None
    _normal: Vector
    _paths: list[list[Vector]]
    _history: list[list[list[Vector]]]
    _future: list[list[list[Vector]]]
    _drawing: bool
    _valid: bool
    _diameter: float
    _last_mouse: tuple[float, float] | None
    _timer: bpy.types.Timer
    _running: bool = False

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        targets = [obj for obj in context.selected_objects or () if obj.type == "MESH"]
        return (
            _drawing_navigation.active_drawing is None
            and context.mode == "OBJECT"
            and context.area is not None
            and context.area.type == "VIEW_3D"
            and bool(targets)
            and all(obj.is_editable for obj in targets)
        )

    def _header(self, message: str = "") -> None:
        if not message:
            message = (
                "Click a selected mesh face to set the drawing plane | Esc: cancel"
                if self._origin is None
                else f"{len(self._paths)} vents / {len(self._targets)} targets | Draw: drag LMB | Extend: Ctrl-click | Smooth: S | Undo/Redo: Ctrl-Z/Shift-Z | Remove: Backspace | Cut: Enter | Esc: cancel"
            )
        self._area.header_text_set(message)
        self._area.tag_redraw()

    @override
    def invoke(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        del event
        area, space = context.area, context.space_data
        if (
            area is None
            or not isinstance(space, bpy.types.SpaceView3D)
            or space.region_3d is None
        ):
            return {"CANCELLED"}
        if space.region_quadviews:
            self.report({"WARNING"}, "Use a single 3D view to draw air vents")
            return {"CANCELLED"}
        self._area = area
        self._region = next(r for r in area.regions if r.type == "WINDOW")
        self._view = space.region_3d
        self._targets = tuple(
            obj for obj in context.selected_objects or () if obj.type == "MESH"
        )
        vertices: list[tuple[float, float, float]] = []
        faces: list[tuple[int, ...]] = []
        depsgraph = context.evaluated_depsgraph_get()
        for target in self._targets:
            evaluated = target.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            try:
                offset = len(vertices)
                for vertex in mesh.vertices:
                    point = evaluated.matrix_world @ vertex.co
                    vertices.append((point.x, point.y, point.z))
                faces.extend(
                    tuple(offset + i for i in cast(Sequence[int], face.vertices))
                    for face in mesh.polygons
                )
            finally:
                evaluated.to_mesh_clear()
        if not faces:
            self.report({"WARNING"}, "Choose meshes with faces to draw on")
            return {"CANCELLED"}
        self._bvh = BVHTree.FromPolygons(vertices, faces)
        self._origin = None
        self._normal = Vector((0, 0, 1))
        self._paths, self._history, self._future = [], [], []
        self._drawing = self._valid = False
        self._last_mouse = None
        self._diameter = context.scene.silicone_casting.air_vent_diameter
        mesh = bpy.data.meshes.new("Air Vent Preview")
        self._preview = bpy.data.objects.new("Air Vent Preview", mesh)
        context.scene.collection.objects.link(self._preview)
        self._preview.display_type = "WIRE"
        self._preview.show_in_front = True
        self._preview.hide_render = True
        self._preview.hide_select = True
        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        self._running = True
        _drawing_navigation.active_drawing = self
        context.window_manager.modal_handler_add(self)
        self._header()
        return {"RUNNING_MODAL"}

    def _point(self, mouse: Vector) -> Vector | None:
        xy = (mouse.x, mouse.y)
        origin = view3d_utils.region_2d_to_origin_3d(self._region, self._view, xy)
        direction = view3d_utils.region_2d_to_vector_3d(self._region, self._view, xy)
        if self._origin is None:
            point, normal, _, _ = self._bvh.ray_cast(origin, direction)
            if point is None or normal is None:
                self._header("Click a face of a selected mesh to set the plane")
                return None
            self._origin = (point.x, point.y, point.z)
            self._normal = normal.normalized()
            return point
        alignment = direction.dot(self._normal)
        if abs(alignment) < 1e-5:
            self._header("The drawing plane is edge-on; orbit the view to draw")
            return None
        distance = (Vector(self._origin) - origin).dot(self._normal) / alignment
        if distance < 0:
            return None
        return origin + distance * direction

    def _remember(self) -> None:
        self._history.append([[p.copy() for p in path] for path in self._paths])
        self._future.clear()

    def _rebuild(self) -> None:
        self._valid = False
        message = ""
        paths = [
            simplify_vent_path(path, self._diameter * 0.05) for path in self._paths
        ]
        complete = [path for path in paths if len(path) >= 2]
        try:
            mesh = create_air_vent_mesh(
                "Air Vent Preview", complete, self._normal, self._diameter
            )
            self._valid = len(complete) == len(paths)
        except ValueError as error:
            # Show the line when a bend cannot support the chosen diameter.
            # Never allow Enter to commit the previous, now stale tube.
            message = str(error) if complete else ""
            mesh = bpy.data.meshes.new("Air Vent Strokes")
            points: list[Vector] = []
            edges: list[tuple[int, int]] = []
            for path in paths:
                offset = len(points)
                points.extend(path)
                edges.extend((offset + i, offset + i + 1) for i in range(len(path) - 1))
            mesh.from_pydata([(p.x, p.y, p.z) for p in points], edges, [])
            mesh.update()
        old = cast(bpy.types.Mesh, self._preview.data)
        self._preview.data = mesh
        bpy.data.meshes.remove(old)
        self._header(message)

    def _cleanup(self, *, keep_cutter: bool = False) -> None:
        if not self._running:
            return
        self._running = False
        _drawing_navigation.active_drawing = None
        bpy.context.window_manager.event_timer_remove(self._timer)
        self._area.header_text_set(None)
        if not keep_cutter:
            mesh = self._preview.data
            bpy.data.objects.remove(self._preview, do_unlink=True)
            bpy.data.meshes.remove(cast(bpy.types.Mesh, mesh))
        self._area.tag_redraw()

    @override
    def cancel(self, context: bpy.types.Context) -> None:
        del context
        self._cleanup()

    @override
    def modal(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        if not self._running:
            return {"CANCELLED"}
        try:
            return self._modal(context, event)
        except Exception as error:
            self._cleanup()
            self.report({"ERROR"}, f"Could not draw air vents: {error}")
            return {"CANCELLED"}

    def _modal(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        diameter = context.scene.silicone_casting.air_vent_diameter
        if diameter != self._diameter:
            self._diameter = diameter
            self._rebuild()
        if event.type.startswith("TIMER"):
            return {"PASS_THROUGH"}
        if event.type == "ESC" and event.value == "PRESS":
            self._cleanup()
            return {"CANCELLED"}
        if over_view_controls(context, event, self._area, self._region):
            self._drawing = False
            return {"PASS_THROUGH"}
        navigation = navigate_drawing_view(context, event, self._area, self._region)
        if navigation is not None:
            self._drawing = False
            return navigation
        if (
            event.value == "PRESS"
            and (event.ctrl or event.oskey)
            and event.type in {"Z", "Y"}
        ):
            self._drawing = False
            redo = event.type == "Y" or event.shift
            source, destination = (
                (self._future, self._history) if redo else (self._history, self._future)
            )
            if source:
                destination.append(self._paths)
                self._paths = source.pop()
                self._rebuild()
        elif event.type == "BACK_SPACE" and event.value == "PRESS":
            self._drawing = False
            if self._paths:
                self._remember()
                self._paths.pop()
                self._rebuild()
        elif event.type == "S" and event.value == "PRESS" and self._paths:
            self._drawing = False
            self._remember()
            self._paths[-1] = smooth_vent_path(
                simplify_vent_path(self._paths[-1], self._diameter * 0.05)
            )
            self._rebuild()
        elif event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS":
            self._drawing = False
            self._rebuild()
            if self._valid:
                add_air_vent_cutters(self._targets, self._preview)
                self._preview.name = f"{self._targets[0].name}.Air Vents"
                self._preview.hide_select = False
                self._preview.show_in_front = False
                self._cleanup(keep_cutter=True)
                self.report({"INFO"}, f"Added air vents to {len(self._targets)} meshes")
                return {"FINISHED"}
        elif event.type == "LEFTMOUSE":
            mouse = Vector(
                (event.mouse_x - self._region.x, event.mouse_y - self._region.y)
            )
            if event.value == "PRESS":
                point = self._point(mouse)
                if point is not None:
                    self._remember()
                    if event.ctrl and self._paths:
                        self._paths[-1].append(point)
                        self._drawing = False
                    else:
                        self._paths.append([point])
                        self._drawing = True
                    self._last_mouse = (mouse.x, mouse.y)
                    self._rebuild()
            elif event.value == "RELEASE":
                if self._drawing:
                    point = self._point(mouse)
                    if (
                        point is not None
                        and (point - self._paths[-1][-1]).length > self._diameter * 1e-6
                    ):
                        self._paths[-1].append(point)
                    self._rebuild()
                self._drawing = False
        elif event.type == "MOUSEMOVE" and self._drawing:
            mouse = Vector(
                (event.mouse_x - self._region.x, event.mouse_y - self._region.y)
            )
            if (
                self._last_mouse is None
                or (mouse - Vector(self._last_mouse)).length >= 3
            ):
                point = self._point(mouse)
                if point is not None:
                    self._paths[-1].append(point)
                    self._last_mouse = (mouse.x, mouse.y)
                    self._rebuild()
        return {"RUNNING_MODAL"}


def cancel_air_vent_drawing() -> None:
    """Remove unfinished vents when the extension is disabled."""
    active = _drawing_navigation.active_drawing
    if isinstance(active, SILCAST_OT_draw_air_vents):
        active.cancel(bpy.context)
