"""Shared view controls for modal drawing in a single 3D viewport."""

from typing import Literal, cast

import bpy

from ._operator import OperatorReturn


def over_view_controls(
    context: bpy.types.Context,
    event: bpy.types.Event,
    area: bpy.types.Area,
    region: bpy.types.Region,
) -> bool:
    """Leave sidebars, headers and native navigation gizmos interactive."""
    x, y = event.mouse_x, event.mouse_y
    if not (
        region.x <= x < region.x + region.width
        and region.y <= y < region.y + region.height
    ):
        return True
    right, top = region.x + region.width, region.y + region.height
    for other in area.regions:
        if other.type == "WINDOW" or other.width <= 1 or other.height <= 1:
            continue
        if (
            other.x <= x < other.x + other.width
            and other.y <= y < other.y + other.height
        ):
            return True
        if other.type == "UI":
            right = min(right, other.x)
        elif other.type in {"HEADER", "TOOL_HEADER"} and other.y > region.y:
            top = min(top, other.y)
    space = area.spaces.active
    assert isinstance(space, bpy.types.SpaceView3D)
    if not (space.show_gizmo and space.show_gizmo_navigate):
        return False
    preferences = context.preferences
    assert preferences is not None
    scale = preferences.system.ui_scale
    view = preferences.view
    # Blender anchors navigation controls to the visible region's upper
    # right corner, outside the sidebar (view3d_gizmo_navigate.cc).
    size = view.gizmo_size_navigate_v3d
    if view.mini_axis_type == "GIZMO":
        if right - (size + 20) * scale <= x and top - (size + 20) * scale <= y:
            return True
        offset = (10 + size / 2) * 2.2
    else:
        offset = 22.5
    return bool(
        view.show_gizmo
        and right - 40 * scale <= x
        and top - (offset + 140) * scale <= y
    )


def navigate_drawing_view(
    context: bpy.types.Context,
    event: bpy.types.Event,
    area: bpy.types.Area,
    region: bpy.types.Region,
) -> OperatorReturn | None:
    """Handle axis and panel shortcuts; pass native orbit and zoom through."""
    if event.type in {"N", "T"} and event.value == "PRESS":
        space = area.spaces.active
        assert isinstance(space, bpy.types.SpaceView3D)
        if event.type == "N":
            space.show_region_ui = not space.show_region_ui
        else:
            space.show_region_toolbar = not space.show_region_toolbar
        return {"RUNNING_MODAL"}
    axis = {"NUMPAD_1": "FRONT", "NUMPAD_3": "RIGHT", "NUMPAD_7": "TOP"}.get(event.type)
    if axis is None:
        preferences = context.preferences
        if preferences is not None and preferences.inputs.use_emulate_numpad:
            axis = {"ONE": "FRONT", "THREE": "RIGHT", "SEVEN": "TOP"}.get(event.type)
    if axis is not None and event.value == "PRESS":
        if event.ctrl:
            axis = {"FRONT": "BACK", "RIGHT": "LEFT", "TOP": "BOTTOM"}[axis]
        with context.temp_override(  # pyright: ignore[reportUnknownMemberType]
            area=area, region=region
        ):
            bpy.ops.view3d.view_axis(
                type=cast(
                    Literal["LEFT", "RIGHT", "BOTTOM", "TOP", "FRONT", "BACK"], axis
                ),
                align_active=event.shift,
            )
        return {"RUNNING_MODAL"}
    if event.type in {
        "MIDDLEMOUSE",
        "WHEELUPMOUSE",
        "WHEELDOWNMOUSE",
        "TRACKPADPAN",
        "TRACKPADZOOM",
        "NDOF_MOTION",
        "ACCENT_GRAVE",
        "N",
        "T",
    } or (event.type.startswith("NUMPAD") and event.type != "NUMPAD_ENTER"):
        return {"PASS_THROUGH"}
    return None
