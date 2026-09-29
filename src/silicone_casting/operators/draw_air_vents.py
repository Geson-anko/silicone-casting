"""Draw planar round air channels and subtract them from selected molds."""

from dataclasses import dataclass
from typing import Final, override

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
from ._operator import OperatorReturn, selected_meshes
from ._stroke_history import StrokeHistory

type _Paths = list[list[Vector]]

_PREVIEW_NAME: Final = "Air Vent Preview"
# Relative to the diameter: drawing jitter below 5% cannot be seen in the tube.
_SIMPLIFY_FRACTION: Final = 0.05
# Relative to the diameter: a release this close to the last point adds nothing.
_COINCIDENT_FRACTION: Final = 1e-6
# Below this ray/normal alignment the plane intersection is numerically unstable.
_EDGE_ON_ALIGNMENT: Final = 1e-5
# Screen distance a drag must travel before it samples another point.
_DRAG_STEP_PX: Final = 3


def _copy_paths(paths: _Paths) -> _Paths:
    return [[point.copy() for point in path] for path in paths]


@dataclass(frozen=True)
class _DrawingPlane:
    """The plane frozen by the first click, which every vent lies on."""

    origin: Vector
    normal: Vector

    def is_edge_on(self, direction: Vector) -> bool:
        return abs(direction.dot(self.normal)) < _EDGE_ON_ALIGNMENT

    def intersect(self, origin: Vector, direction: Vector) -> Vector | None:
        """Return where a view ray meets the plane, or None behind the view."""
        alignment = direction.dot(self.normal)
        distance = (self.origin - origin).dot(self.normal) / alignment
        if distance < 0:
            return None
        return origin + distance * direction


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
    _plane: _DrawingPlane | None
    _paths: _Paths
    _history: StrokeHistory[_Paths]
    # True only while the preview tube matches every drawn path.
    _can_cut: bool
    _diameter: float
    # Last sampled cursor position while LMB is held; None when not dragging.
    _drag_at: tuple[float, float] | None

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        targets = selected_meshes(context)
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
                if self._plane is None
                else self._drawing_help()
            )
        self._session.header(message)

    def _drawing_help(self) -> str:
        return " | ".join(
            (
                f"{len(self._paths)} vents / {len(self._targets)} targets",
                "Draw: drag LMB",
                "Extend: Ctrl-click",
                "Smooth: S",
                "Undo/Redo: Ctrl-Z/Shift-Z",
                "Remove: Backspace",
                "Cut: Enter",
                "Esc: cancel",
            )
        )

    @override
    def invoke(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        del event
        self._targets = tuple(selected_meshes(context))
        try:
            self._surface = SurfaceSnapshot.from_objects(
                self._targets, context.evaluated_depsgraph_get()
            )
        except ValueError as error:
            self.report({"WARNING"}, str(error))
            return {"CANCELLED"}
        self._plane = None
        self._paths = []
        self._history = StrokeHistory(_copy_paths)
        self._can_cut = False
        self._drag_at = None
        self._diameter = scene_settings(context).air_vent_diameter
        try:
            self._session = DrawingSession.from_context(
                context, self, _PREVIEW_NAME, tuple(self._targets[0].users_collection)
            )
        except ValueError as error:
            self.report({"WARNING"}, str(error))
            return {"CANCELLED"}
        except Exception as error:
            # Operator boundary: report any startup failure instead of a traceback.
            self.report({"ERROR"}, f"Could not start drawing air vents: {error}")
            return {"CANCELLED"}
        self._session.preview.hide_select = True
        self._header()
        return {"RUNNING_MODAL"}

    def _freeze_plane(self, mouse: Vector) -> Vector | None:
        """Fix the drawing plane on the clicked face; return the hit."""
        origin, direction = self._session.ray(mouse)
        point, normal, _, _ = self._surface.bvh.ray_cast(origin, direction)
        if point is None or normal is None:
            self._header("Click a face of a selected mesh to set the plane")
            return None
        self._plane = _DrawingPlane(point.copy(), normal.normalized())
        return point

    def _plane_point(self, mouse: Vector) -> Vector | None:
        """Project the cursor onto the frozen plane."""
        assert self._plane is not None
        origin, direction = self._session.ray(mouse)
        if self._plane.is_edge_on(direction):
            self._header("The drawing plane is edge-on; orbit the view to draw")
            return None
        return self._plane.intersect(origin, direction)

    def _remember(self) -> None:
        self._history.remember(self._paths)

    def _rebuild(self) -> None:
        """Rebuild the preview tube and whether Enter may commit it."""
        self._can_cut = False
        paths = [
            simplify_vent_path(path, self._diameter * _SIMPLIFY_FRACTION)
            for path in self._paths
        ]
        complete = [path for path in paths if len(path) >= 2]
        if self._plane is None or not complete:
            self._session.show_paths(paths)
            self._header()
            return
        try:
            mesh = create_air_vent_mesh(
                _PREVIEW_NAME, complete, self._plane.normal, self._diameter
            )
        except ValueError as error:
            # Show the line when a bend cannot support the chosen diameter.
            # _can_cut stays False so Enter never commits the stale tube.
            self._session.show_paths(paths)
            self._header(str(error))
            return
        self._can_cut = len(complete) == len(paths)
        self._session.replace_mesh(mesh)
        self._header()

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
            # Operator boundary: never leave the viewport locked by a failure.
            self._session.close()
            self.report({"ERROR"}, f"Could not draw air vents: {error}")
            return {"CANCELLED"}

    def _sync_diameter(self, context: bpy.types.Context) -> None:
        diameter = scene_settings(context).air_vent_diameter
        if diameter != self._diameter:
            self._diameter = diameter
            self._rebuild()

    def _modal(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        self._sync_diameter(context)
        if event.type.startswith("TIMER"):
            return {"PASS_THROUGH"}
        pressed = event.value == "PRESS"
        if event.type == "ESC" and pressed:
            self._session.close()
            return {"CANCELLED"}
        navigation = self._session.navigation(context, event)
        if navigation is not None:
            self._drag_at = None
            return navigation
        if pressed and (event.ctrl or event.oskey) and event.type in {"Z", "Y"}:
            self._step_history(redo=event.type == "Y" or event.shift)
        elif event.type == "BACK_SPACE" and pressed:
            self._remove_last_path()
        elif event.type == "S" and pressed and self._paths:
            self._smooth_last_path()
        elif event.type in {"RET", "NUMPAD_ENTER"} and pressed:
            return self._finish()
        elif event.type == "LEFTMOUSE":
            self._mouse_button(event)
        elif event.type == "MOUSEMOVE" and self._drag_at is not None:
            self._drag_mouse(event)
        return {"RUNNING_MODAL"}

    def _step_history(self, *, redo: bool) -> None:
        self._drag_at = None
        paths = self._history.step(self._paths, redo=redo)
        if paths is not None:
            self._paths = paths
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
            simplify_vent_path(self._paths[-1], self._diameter * _SIMPLIFY_FRACTION)
        )
        self._rebuild()

    def _finish(self) -> OperatorReturn:
        self._drag_at = None
        self._rebuild()
        if not self._can_cut:
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
            self._press(mouse, extend=event.ctrl)
        elif event.value == "RELEASE":
            self._release(mouse)

    def _press(self, mouse: Vector, *, extend: bool) -> None:
        """Start a new vent, or extend the last one with a straight segment."""
        point = (
            self._freeze_plane(mouse)
            if self._plane is None
            else self._plane_point(mouse)
        )
        if point is None:
            return
        self._remember()
        if extend and self._paths:
            self._paths[-1].append(point)
            self._drag_at = None
        else:
            self._paths.append([point])
            self._drag_at = (mouse.x, mouse.y)
        self._rebuild()

    def _release(self, mouse: Vector) -> None:
        if self._drag_at is not None:
            point = self._plane_point(mouse)
            if (
                point is not None
                and (point - self._paths[-1][-1]).length
                > self._diameter * _COINCIDENT_FRACTION
            ):
                self._paths[-1].append(point)
            self._rebuild()
        self._drag_at = None

    def _drag_mouse(self, event: bpy.types.Event) -> None:
        mouse = self._session.mouse(event)
        if (
            self._drag_at is None
            or (mouse - Vector(self._drag_at)).length < _DRAG_STEP_PX
        ):
            return
        point = self._plane_point(mouse)
        if point is not None:
            self._paths[-1].append(point)
            self._drag_at = (mouse.x, mouse.y)
            self._rebuild()


def cancel_air_vent_drawing() -> None:
    """Remove unfinished vents when the extension is disabled."""
    active = _drawing_navigation.active_drawing
    if isinstance(active, SILCAST_OT_draw_air_vents):
        active.cancel(bpy.context)
