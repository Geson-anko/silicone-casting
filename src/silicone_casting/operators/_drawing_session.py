"""Own viewport resources for one cancellable modal drawing session."""

from collections.abc import Callable, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Self, cast

import bpy
from bpy_extras import view3d_utils
from mathutils import Vector

from . import _drawing_navigation
from ._operator import OperatorReturn


@dataclass
class DrawingSession:
    """Keep temporary geometry and viewport handles under one lifetime."""

    _area: bpy.types.Area
    region: bpy.types.Region
    view: bpy.types.RegionView3D
    preview: bpy.types.Object
    _mesh: bpy.types.Mesh
    _manager: bpy.types.WindowManager
    _operator: bpy.types.Operator | None
    _timer: bpy.types.Timer | None
    _handle: object | None

    @classmethod
    def from_context(
        cls,
        context: bpy.types.Context,
        operator: bpy.types.Operator,
        name: str,
        collections: Sequence[bpy.types.Collection],
        *,
        draw: Callable[[], None] | None = None,
    ) -> Self:
        """Acquire a complete drawing session, rolling back a failed
        startup."""
        area, space = context.area, context.space_data
        if (
            area is None
            or not isinstance(space, bpy.types.SpaceView3D)
            or space.region_3d is None
            or space.region_quadviews
        ):
            raise ValueError("Use a single 3D view to draw")
        region = next(r for r in area.regions if r.type == "WINDOW")
        manager = context.window_manager
        with ExitStack() as resources:
            mesh = bpy.data.meshes.new(name)
            resources.callback(bpy.data.meshes.remove, mesh)
            preview = bpy.data.objects.new(name, mesh)
            resources.callback(bpy.data.objects.remove, preview, do_unlink=True)
            for collection in collections:
                collection.objects.link(preview)
            preview.display_type = "WIRE"
            preview.show_in_front = True
            preview.hide_render = True
            handle = None
            if draw is not None:
                handle = bpy.types.SpaceView3D.draw_handler_add(
                    draw, (), "WINDOW", "POST_PIXEL"
                )
                resources.callback(
                    bpy.types.SpaceView3D.draw_handler_remove, handle, "WINDOW"
                )
            timer = manager.event_timer_add(0.1, window=context.window)
            resources.callback(manager.event_timer_remove, timer)
            session = cls(
                area,
                region,
                space.region_3d,
                preview,
                mesh,
                manager,
                operator,
                timer,
                handle,
            )
            manager.modal_handler_add(operator)
            _drawing_navigation.active_drawing = operator
            resources.pop_all()
            return session

    @property
    def running(self) -> bool:
        return self._operator is not None

    def mouse(self, event: bpy.types.Event) -> Vector:
        return Vector((event.mouse_x - self.region.x, event.mouse_y - self.region.y))

    def contains(self, mouse: Vector) -> bool:
        return 0 <= mouse.x < self.region.width and 0 <= mouse.y < self.region.height

    def ray(
        self, mouse: Vector, *, clamp: float | None = None
    ) -> tuple[Vector, Vector]:
        xy = (mouse.x, mouse.y)
        return (
            view3d_utils.region_2d_to_origin_3d(
                self.region, self.view, xy, clamp=clamp
            ),
            view3d_utils.region_2d_to_vector_3d(self.region, self.view, xy),
        )

    def project(self, point: Vector) -> Vector | None:
        return view3d_utils.location_3d_to_region_2d(self.region, self.view, point)

    def navigation(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn | None:
        if _drawing_navigation.over_view_controls(
            context, event, self._area, self.region
        ):
            return {"PASS_THROUGH"}
        return _drawing_navigation.navigate_drawing_view(
            context, event, self._area, self.region
        )

    def header(self, message: str) -> None:
        self._area.header_text_set(message)
        self.redraw()

    def redraw(self) -> None:
        self._area.tag_redraw()

    def replace_mesh(self, mesh: bpy.types.Mesh) -> None:
        old = self._mesh
        try:
            self.preview.data = mesh
        except ReferenceError:
            self._remove_unused_mesh(mesh)
            raise
        self._mesh = mesh
        self._remove_unused_mesh(old)

    def show_paths(
        self,
        paths: Sequence[Sequence[Vector]],
        *,
        loops: Sequence[Sequence[Vector]] = (),
    ) -> None:
        """Display closed rims first, followed by open drawing strokes."""
        points: list[Vector] = []
        edges: list[tuple[int, int]] = []
        for closed, strokes in ((True, loops), (False, paths)):
            for path in strokes:
                offset = len(points)
                points.extend(path)
                edges.extend(
                    (offset + i, offset + (i + 1) % len(path))
                    for i in range(len(path) if closed else len(path) - 1)
                )
        self.preview.display_type = "WIRE"
        mesh = cast(bpy.types.Mesh, self.preview.data)
        mesh.clear_geometry()
        mesh.from_pydata(points, edges, [])
        mesh.update()
        self.redraw()

    def close(self, *, keep_preview: bool = False) -> None:
        """Release handles once and either discard or hand off the preview."""
        operator = self._operator
        if operator is None:
            return
        self._operator = None
        if _drawing_navigation.active_drawing is operator:
            _drawing_navigation.active_drawing = None
        handle, self._handle = self._handle, None
        timer, self._timer = self._timer, None
        with ExitStack() as resources:
            resources.callback(self._clear_header)
            if not keep_preview:
                resources.callback(self._discard_preview)
            if timer is not None:
                resources.callback(self._manager.event_timer_remove, timer)
            if handle is not None:
                resources.callback(
                    bpy.types.SpaceView3D.draw_handler_remove, handle, "WINDOW"
                )

    def _discard_preview(self) -> None:
        try:
            bpy.data.objects.remove(self.preview, do_unlink=True)
        except ReferenceError:
            # The Outliner can remove the preview while drawing owns the viewport.
            pass
        self._remove_unused_mesh(self._mesh)

    @staticmethod
    def _remove_unused_mesh(mesh: bpy.types.Mesh) -> None:
        try:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        except ReferenceError:
            # Deleting the object and its data can invalidate both saved references.
            pass

    def _clear_header(self) -> None:
        try:
            self._area.header_text_set(None)
            self.redraw()
        except ReferenceError:
            # Closing the editor also ends the lifetime of its header.
            pass
