"""Draw closed surface strokes and turn their interpolated patch into a cut."""

from collections.abc import Sequence
from typing import cast, override

import bpy
from bpy_extras import view3d_utils
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from ..core import MIN_SURFACE_CUT_THICKNESS_MM, create_surface_cut, mm_to_units
from ..core.drawn_surface import interpolate_cutting_surface, simplify_closed_loop
from ._operator import OperatorReturn

_BOUNDARY_GROUP = "Cut Boundary"
_INTERIOR_GROUP = "Cut Interior"
_active_drawing: "SILCAST_OT_draw_surface_cut | None" = None


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
    _preview: bpy.types.Object
    _area: bpy.types.Area
    _region: bpy.types.Region
    _view: bpy.types.RegionView3D
    _bvh: BVHTree
    _selected: tuple[bpy.types.Object, ...]
    _loops: list[list[Vector]]
    _stroke: list[Vector]
    _drawing: bool
    _ready: bool
    _last_mouse: tuple[float, float] | None
    _size: float
    _thickness: float
    _minimum: float

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        return (
            _active_drawing is None
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
                if self._ready
                else f"{len(self._loops)} loops | Draw: LMB | Orbit: MMB | Close: C | Preview: Space | Undo: Backspace | Cancel: Esc"
            )
        self._area.header_text_set(message)
        self._area.tag_redraw()

    @override
    def invoke(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        del event
        global _active_drawing
        target = context.active_object
        area = context.area
        space = context.space_data
        if (
            target is None
            or area is None
            or not isinstance(space, bpy.types.SpaceView3D)
            or space.region_3d is None
        ):
            return {"CANCELLED"}
        if space.region_quadviews:
            self.report({"WARNING"}, "Use a single 3D view to draw the cut")
            return {"CANCELLED"}
        self._region = next(
            region for region in area.regions if region.type == "WINDOW"
        )
        self._view = space.region_3d
        self._area = area
        self._target = target
        self._selected = tuple(context.selected_objects or ())
        evaluated = target.evaluated_get(context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        try:
            points = [target.matrix_world @ vertex.co for vertex in mesh.vertices]
            if not mesh.polygons or not points:
                self.report({"WARNING"}, "Choose a mesh with faces to draw on")
                return {"CANCELLED"}
            self._bvh = BVHTree.FromPolygons(
                [(p.x, p.y, p.z) for p in points],
                [tuple(cast(Sequence[int], face.vertices)) for face in mesh.polygons],
            )
            low = Vector(tuple(min(p[i] for p in points) for i in range(3)))
            high = Vector(tuple(max(p[i] for p in points) for i in range(3)))
            self._size = (high - low).length
        finally:
            evaluated.to_mesh_clear()
        if self._size <= 0:
            return {"CANCELLED"}
        props = context.scene.silicone_casting
        self._thickness = mm_to_units(
            props.surface_cut_thickness_mm, context.scene.unit_settings.scale_length
        )
        self._minimum = mm_to_units(
            MIN_SURFACE_CUT_THICKNESS_MM, context.scene.unit_settings.scale_length
        )
        preview_mesh = bpy.data.meshes.new("Cut Strokes")
        self._preview = bpy.data.objects.new("Cut Strokes", preview_mesh)
        for collection in target.users_collection:
            collection.objects.link(self._preview)
        self._preview.display_type = "WIRE"
        self._preview.show_in_front = True
        self._preview.hide_render = True
        self._preview.select_set(True)
        self._loops = []
        self._stroke = []
        self._drawing = False
        self._ready = False
        self._last_mouse = None
        _active_drawing = self
        context.window_manager.modal_handler_add(self)
        self._header()
        return {"RUNNING_MODAL"}

    def _show_strokes(self) -> None:
        mesh = cast(bpy.types.Mesh, self._preview.data)
        points: list[Vector] = []
        edges: list[tuple[int, int]] = []
        for loop in self._loops:
            offset = len(points)
            points.extend(loop)
            edges.extend(
                (offset + i, offset + (i + 1) % len(loop)) for i in range(len(loop))
            )
        offset = len(points)
        points.extend(self._stroke)
        edges.extend((offset + i, offset + i + 1) for i in range(len(self._stroke) - 1))
        mesh.clear_geometry()
        mesh.from_pydata(points, edges, [])
        mesh.update()
        self._area.tag_redraw()

    def _point(self, mouse: Vector) -> Vector | None:
        if not (
            0 <= mouse.x < self._region.width and 0 <= mouse.y < self._region.height
        ):
            return None
        origin = view3d_utils.region_2d_to_origin_3d(
            self._region,
            self._view,
            (mouse.x, mouse.y),
            clamp=self._size * 4
            + (self._view.view_location - self._target.matrix_world.translation).length,
        )
        direction = view3d_utils.region_2d_to_vector_3d(
            self._region, self._view, (mouse.x, mouse.y)
        )
        point, _, _, _ = self._bvh.ray_cast(origin, direction)
        return point

    def _append_point(self, mouse: Vector) -> bool:
        point = self._point(mouse)
        if point is None:
            self._header(
                "Stroke paused off the mesh; resume near its end, or orbit with MMB"
            )
            return False
        if self._stroke:
            distance = (point - self._stroke[-1]).length
            if distance > self._size * 0.04:
                self._header(
                    "Resume near the last point; the stroke cannot jump across the mesh"
                )
                return False
            if distance < self._size * 0.0005:
                return True
        self._stroke.append(point)
        self._header()
        return True

    def _close_loop(self) -> None:
        if len(self._stroke) < 3:
            self._header("Draw a loop before closing it")
            return
        if (self._stroke[-1] - self._stroke[0]).length > self._size * 0.025:
            self._header("Continue drawing back to the start before closing the loop")
            return
        # The endpoint near the start is redundant and can create a tiny CDT
        # edge. Keep the first point as the exact closing point.
        if (
            len(self._stroke) > 3
            and (self._stroke[-1] - self._stroke[0]).length < self._size * 0.0005
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
                    simplify_closed_loop(loop, self._size * 0.0005)
                    for loop in self._loops
                ],
                margin=max(self._thickness * 2, self._size * 0.002),
            )
        except ValueError as error:
            self._header(str(error))
            self.report({"WARNING"}, str(error))
            return
        old_mesh = cast(bpy.types.Mesh, self._preview.data)
        self._preview.data = mesh
        bpy.data.meshes.remove(old_mesh)
        self._preview.vertex_groups.clear()
        self._preview.vertex_groups.new(name=_BOUNDARY_GROUP).add(
            boundary, 1.0, "REPLACE"
        )
        self._preview.vertex_groups.new(name=_INTERIOR_GROUP).add(
            interior, 1.0, "REPLACE"
        )
        self._ready = True
        self._header()

    def _cleanup(self, *, keep_surface: bool = False) -> None:
        global _active_drawing
        _active_drawing = None
        self._area.header_text_set(None)
        self._area.tag_redraw()
        if not keep_surface:
            mesh = self._preview.data
            bpy.data.objects.remove(self._preview, do_unlink=True)
            if isinstance(mesh, bpy.types.Mesh) and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        else:
            self._preview.select_set(False)
        for obj in self._selected:
            obj.select_set(True)

    @override
    def cancel(self, context: bpy.types.Context) -> None:
        del context
        if _active_drawing is self:
            self._cleanup()

    @override
    def modal(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        if _active_drawing is not self:
            return {"CANCELLED"}
        try:
            return self._modal(context, event)
        except Exception as error:
            self._cleanup()
            self.report({"ERROR"}, f"Could not draw the cut: {error}")
            return {"CANCELLED"}

    def _modal(
        self, context: bpy.types.Context, event: bpy.types.Event
    ) -> OperatorReturn:
        if event.type == "ESC" and event.value == "PRESS":
            self._cleanup()
            return {"CANCELLED"}
        if event.type in {
            "MIDDLEMOUSE",
            "WHEELUPMOUSE",
            "WHEELDOWNMOUSE",
            "TRACKPADPAN",
            "TRACKPADZOOM",
            "NDOF_MOTION",
        } or event.type.startswith("NUMPAD"):
            self._drawing = False
            self._last_mouse = None
            return {"PASS_THROUGH"}
        if event.type == "BACK_SPACE" and event.value == "PRESS":
            self._drawing = False
            if self._ready:
                self._ready = False
                self._preview.vertex_groups.clear()
            elif self._stroke:
                self._stroke = []
            elif self._loops:
                self._stroke = self._loops.pop()
            self._show_strokes()
            self._header()
        if self._ready:
            if event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS":
                create_surface_cut(
                    self._target,
                    self._preview,
                    self._thickness,
                    minimum_thickness=self._minimum,
                )
                self._preview.name = f"{self._target.name}.Cutting Surface"
                self._cleanup(keep_surface=True)
                context.view_layer.objects.active = self._target
                self.report(
                    {"INFO"},
                    "Surface Cut added. Use Edit Cutting Surface to shape its interior",
                )
                return {"FINISHED"}
            return {"RUNNING_MODAL"}
        if event.type == "SPACE" and event.value == "PRESS":
            self._drawing = False
            self._build_preview()
        elif event.type == "C" and event.value == "PRESS":
            self._drawing = False
            self._close_loop()
        elif event.type == "LEFTMOUSE":
            mouse = Vector(
                (event.mouse_x - self._region.x, event.mouse_y - self._region.y)
            )
            if event.value == "PRESS":
                self._drawing = self._append_point(mouse)
                self._last_mouse = (mouse.x, mouse.y) if self._drawing else None
                self._show_strokes()
            elif event.value == "RELEASE":
                self._drawing = False
                self._last_mouse = None
        elif event.type == "MOUSEMOVE" and self._drawing:
            mouse = Vector(
                (event.mouse_x - self._region.x, event.mouse_y - self._region.y)
            )
            previous = self._last_mouse
            if previous is not None:
                previous_point = Vector(previous)
                count = max(1, int((mouse - previous_point).length / 3))
                for i in range(1, count + 1):
                    if not self._append_point(previous_point.lerp(mouse, i / count)):
                        self._drawing = False
                        break
            self._last_mouse = (mouse.x, mouse.y)
            self._show_strokes()
        return {"RUNNING_MODAL"}


def cancel_surface_drawing() -> None:
    """Remove temporary geometry when the extension is disabled mid-stroke."""
    if _active_drawing is not None:
        _active_drawing.cancel(bpy.context)


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
            _active_drawing is None
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
