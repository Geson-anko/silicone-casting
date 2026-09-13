"""Draw planar round air channels and subtract them from selected molds."""

from typing import override

import bpy
from mathutils import Vector

from ..core.air_vents import (
    add_air_vent_cutters,
    create_air_vent_mesh,
    simplify_vent_path,
    smooth_vent_path,
)
from ..core.surface_picking import SurfaceSnapshot
from ..properties.settings import scene_settings
from . import _drawing_navigation
from ._drawing_session import DrawingSession
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
    _session: DrawingSession
    _surface: SurfaceSnapshot
    _origin: tuple[float, float, float] | None
    _normal: Vector
    _paths: list[list[Vector]]
    _history: list[list[list[Vector]]]
    _future: list[list[list[Vector]]]
    _valid: bool
    _diameter: float
    _drag_at: tuple[float, float] | None

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
        self._session.header(message)

    @override
    def invoke(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        del event
        self._targets = tuple(
            obj for obj in context.selected_objects or () if obj.type == "MESH"
        )
        try:
            self._surface = SurfaceSnapshot.from_objects(
                self._targets, context.evaluated_depsgraph_get()
            )
        except ValueError as error:
            self.report({"WARNING"}, str(error))
            return {"CANCELLED"}
        self._origin = None
        self._normal = Vector((0, 0, 1))
        self._paths, self._history, self._future = [], [], []
        self._valid = False
        self._drag_at = None
        self._diameter = scene_settings(context).air_vent_diameter
        try:
            self._session = DrawingSession.from_context(
                context, self, "Air Vent Preview", (context.scene.collection,)
            )
        except ValueError as error:
            self.report({"WARNING"}, str(error))
            return {"CANCELLED"}
        except Exception as error:
            self.report({"ERROR"}, f"Could not start drawing air vents: {error}")
            return {"CANCELLED"}
        self._session.preview.hide_select = True
        self._header()
        return {"RUNNING_MODAL"}

    def _point(self, mouse: Vector) -> Vector | None:
        origin, direction = self._session.ray(mouse)
        if self._origin is None:
            point, normal, _, _ = self._surface.bvh.ray_cast(origin, direction)
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
            self._session.show_paths(paths)
        else:
            self._session.replace_mesh(mesh)
        self._header(message)

    @override
    def cancel(self, context: bpy.types.Context) -> None:
        del context
        self._session.close()

    @override
    def modal(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        if not self._session.running:
            return {"CANCELLED"}
        try:
            return self._modal(context, event)
        except Exception as error:
            self._session.close()
            self.report({"ERROR"}, f"Could not draw air vents: {error}")
            return {"CANCELLED"}

    def _modal(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        diameter = scene_settings(context).air_vent_diameter
        if diameter != self._diameter:
            self._diameter = diameter
            self._rebuild()
        if event.type.startswith("TIMER"):
            return {"PASS_THROUGH"}
        if event.type == "ESC" and event.value == "PRESS":
            self._session.close()
            return {"CANCELLED"}
        navigation = self._session.navigation(context, event)
        if navigation is not None:
            self._drag_at = None
            return navigation
        if (
            event.value == "PRESS"
            and (event.ctrl or event.oskey)
            and event.type in {"Z", "Y"}
        ):
            self._restore_history(redo=event.type == "Y" or event.shift)
        elif event.type == "BACK_SPACE" and event.value == "PRESS":
            self._remove_last_path()
        elif event.type == "S" and event.value == "PRESS" and self._paths:
            self._smooth_last_path()
        elif event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS":
            return self._finish()
        elif event.type == "LEFTMOUSE":
            self._mouse_button(event)
        elif event.type == "MOUSEMOVE" and self._drag_at is not None:
            self._drag_mouse(event)
        return {"RUNNING_MODAL"}

    def _restore_history(self, *, redo: bool) -> None:
        self._drag_at = None
        source, destination = (
            (self._future, self._history) if redo else (self._history, self._future)
        )
        if source:
            destination.append(self._paths)
            self._paths = source.pop()
            self._rebuild()

    def _remove_last_path(self) -> None:
        self._drag_at = None
        if self._paths:
            self._remember()
            self._paths.pop()
            self._rebuild()

    def _smooth_last_path(self) -> None:
        self._drag_at = None
        self._remember()
        self._paths[-1] = smooth_vent_path(
            simplify_vent_path(self._paths[-1], self._diameter * 0.05)
        )
        self._rebuild()

    def _finish(self) -> OperatorReturn:
        self._drag_at = None
        self._rebuild()
        if not self._valid:
            return {"RUNNING_MODAL"}
        preview = self._session.preview
        add_air_vent_cutters(self._targets, preview)
        preview.name = f"{self._targets[0].name}.Air Vents"
        preview.hide_select = False
        preview.show_in_front = False
        self._session.close(keep_preview=True)
        self.report({"INFO"}, f"Added air vents to {len(self._targets)} meshes")
        return {"FINISHED"}

    def _mouse_button(self, event: bpy.types.Event) -> None:
        mouse = self._session.mouse(event)
        if event.value == "PRESS":
            point = self._point(mouse)
            if point is not None:
                self._remember()
                if event.ctrl and self._paths:
                    self._paths[-1].append(point)
                    self._drag_at = None
                else:
                    self._paths.append([point])
                    self._drag_at = (mouse.x, mouse.y)
                self._rebuild()
        elif event.value == "RELEASE":
            if self._drag_at is not None:
                point = self._point(mouse)
                if (
                    point is not None
                    and (point - self._paths[-1][-1]).length > self._diameter * 1e-6
                ):
                    self._paths[-1].append(point)
                self._rebuild()
            self._drag_at = None

    def _drag_mouse(self, event: bpy.types.Event) -> None:
        mouse = self._session.mouse(event)
        if self._drag_at is not None and (mouse - Vector(self._drag_at)).length >= 3:
            point = self._point(mouse)
            if point is not None:
                self._paths[-1].append(point)
                self._drag_at = (mouse.x, mouse.y)
                self._rebuild()


def cancel_air_vent_drawing() -> None:
    """Remove unfinished vents when the extension is disabled."""
    active = _drawing_navigation.active_drawing
    if isinstance(active, SILCAST_OT_draw_air_vents):
        active.cancel(bpy.context)
