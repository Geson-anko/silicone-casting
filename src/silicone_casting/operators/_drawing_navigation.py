"""Shared view controls for modal drawing in a single 3D viewport."""

from typing import Final, Literal

import bpy

from ._operator import OperatorReturn

type _ViewAxis = Literal["LEFT", "RIGHT", "BOTTOM", "TOP", "FRONT", "BACK"]

# Shared by both drawing operators so only one can own viewport input.
active_drawing: bpy.types.Operator | None = None

_NUMPAD_AXES: Final[dict[str, _ViewAxis]] = {
    "NUMPAD_1": "FRONT",
    "NUMPAD_3": "RIGHT",
    "NUMPAD_7": "TOP",
}
_EMULATED_NUMPAD_AXES: Final[dict[str, _ViewAxis]] = {
    "ONE": "FRONT",
    "THREE": "RIGHT",
    "SEVEN": "TOP",
}
# Ctrl flips a numpad view to the opposite side, as in Blender's keymap.
_OPPOSITE_AXES: Final[dict[_ViewAxis, _ViewAxis]] = {
    "FRONT": "BACK",
    "RIGHT": "LEFT",
    "TOP": "BOTTOM",
}
_PASS_THROUGH_EVENTS: Final = frozenset(
    {
        "MIDDLEMOUSE",
        "WHEELUPMOUSE",
        "WHEELDOWNMOUSE",
        "TRACKPADPAN",
        "TRACKPADZOOM",
        "NDOF_MOTION",
        "ACCENT_GRAVE",
        "N",
        "T",
    }
)

# Navigation gizmo layout in unscaled pixels, mirrored from Blender's
# view3d_gizmo_navigate.cc so clicks on those buttons reach Blender.
_GIZMO_MARGIN_PX: Final = 20
_GIZMO_BUTTON_OFFSET_PX: Final = 10
_GIZMO_BUTTON_OFFSET_SCALE: Final = 2.2
_MINI_AXIS_BUTTON_OFFSET_PX: Final = 22.5
_BUTTON_COLUMN_WIDTH_PX: Final = 40
_BUTTON_COLUMN_HEIGHT_PX: Final = 140


def _contains(region: bpy.types.Region, x: int, y: int) -> bool:
    return (
        region.x <= x < region.x + region.width
        and region.y <= y < region.y + region.height
    )


def _overlapping_regions(area: bpy.types.Area) -> list[bpy.types.Region]:
    """Visible sidebars and headers drawn over the main viewport region."""
    return [
        other
        for other in area.regions
        if other.type != "WINDOW" and other.width > 1 and other.height > 1
    ]


def _visible_corner(
    region: bpy.types.Region, overlapping: list[bpy.types.Region]
) -> tuple[int, int]:
    """Return the upper right corner of the viewport left uncovered."""
    right, top = region.x + region.width, region.y + region.height
    for other in overlapping:
        if other.type == "UI":
            right = min(right, other.x)
        elif other.type in {"HEADER", "TOOL_HEADER"} and other.y > region.y:
            top = min(top, other.y)
    return right, top


def _over_navigation_gizmo(
    context: bpy.types.Context,
    space: bpy.types.SpaceView3D,
    corner: tuple[int, int],
    x: int,
    y: int,
) -> bool:
    if not (space.show_gizmo and space.show_gizmo_navigate):
        return False
    preferences = context.preferences
    assert preferences is not None
    scale = preferences.system.ui_scale
    view = preferences.view
    right, top = corner
    # Blender anchors navigation controls to the visible region's upper
    # right corner, outside the sidebar.
    size = view.gizmo_size_navigate_v3d
    if view.mini_axis_type == "GIZMO":
        reach = (size + _GIZMO_MARGIN_PX) * scale
        if right - reach <= x and top - reach <= y:
            return True
        offset = (_GIZMO_BUTTON_OFFSET_PX + size / 2) * _GIZMO_BUTTON_OFFSET_SCALE
    else:
        offset = _MINI_AXIS_BUTTON_OFFSET_PX
    return bool(
        view.show_gizmo
        and right - _BUTTON_COLUMN_WIDTH_PX * scale <= x
        and top - (offset + _BUTTON_COLUMN_HEIGHT_PX) * scale <= y
    )


def over_view_controls(
    context: bpy.types.Context,
    event: bpy.types.Event,
    area: bpy.types.Area,
    region: bpy.types.Region,
) -> bool:
    """Tell whether the cursor is over UI that must stay interactive.

    Args:
        context: The modal operator's context.
        event: The event whose window coordinates are tested.
        area: The 3D view that owns the drawing.
        region: The main viewport region of ``area``.

    Returns:
        True outside the viewport, over sidebars and headers, and over
        Blender's navigation gizmo.
    """
    x, y = event.mouse_x, event.mouse_y
    if not _contains(region, x, y):
        return True
    overlapping = _overlapping_regions(area)
    if any(_contains(other, x, y) for other in overlapping):
        return True
    space = area.spaces.active
    assert isinstance(space, bpy.types.SpaceView3D)
    corner = _visible_corner(region, overlapping)
    return _over_navigation_gizmo(context, space, corner, x, y)


def _toggle_panel(area: bpy.types.Area, key: str) -> None:
    space = area.spaces.active
    assert isinstance(space, bpy.types.SpaceView3D)
    if key == "N":
        space.show_region_ui = not space.show_region_ui
    else:
        space.show_region_toolbar = not space.show_region_toolbar


def _view_axis(context: bpy.types.Context, event: bpy.types.Event) -> _ViewAxis | None:
    axis = _NUMPAD_AXES.get(event.type)
    if axis is None:
        preferences = context.preferences
        if preferences is not None and preferences.inputs.use_emulate_numpad:
            axis = _EMULATED_NUMPAD_AXES.get(event.type)
    if axis is not None and event.ctrl:
        axis = _OPPOSITE_AXES[axis]
    return axis


def _passes_through(event: bpy.types.Event) -> bool:
    """Leave orbit, zoom and the remaining numpad views to Blender."""
    return event.type in _PASS_THROUGH_EVENTS or (
        event.type.startswith("NUMPAD") and event.type != "NUMPAD_ENTER"
    )


def navigate_drawing_view(
    context: bpy.types.Context,
    event: bpy.types.Event,
    area: bpy.types.Area,
    region: bpy.types.Region,
) -> OperatorReturn | None:
    """Handle axis and panel shortcuts; pass native orbit and zoom through.

    Args:
        context: The modal operator's context.
        event: The event to handle.
        area: The 3D view that owns the drawing.
        region: The main viewport region of ``area``.

    Returns:
        The modal result when the event is a navigation event, or None when
        the drawing operator should handle it.
    """
    if event.type in {"N", "T"} and event.value == "PRESS":
        _toggle_panel(area, event.type)
        return {"RUNNING_MODAL"}
    axis = _view_axis(context, event)
    if axis is not None and event.value == "PRESS":
        with context.temp_override(  # pyright: ignore[reportUnknownMemberType]
            area=area, region=region
        ):
            bpy.ops.view3d.view_axis(type=axis, align_active=event.shift)
        return {"RUNNING_MODAL"}
    if _passes_through(event):
        return {"PASS_THROUGH"}
    return None
