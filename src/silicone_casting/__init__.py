"""Blender extension for producing resin molds for silicone casting."""

from typing import Final, cast

import bpy
from bpy.app.handlers import persistent

from . import operators, properties, ui
from .operators.key_placement import SILCAST_WST_registration_keys
from .properties.settings import SiliconeCastingProperties

# Models precede their operators and views; each package owns its registration list.
_CLASSES = (*properties.CLASSES, *operators.CLASSES, *ui.CLASSES)
_SCENE_ATTR: Final = "silicone_casting"


@persistent
def _reset_transient_selection_state(_unused: object) -> None:
    """Reset transient list-row selections when a saved file is opened."""
    for scene in bpy.data.scenes:
        settings = cast(
            SiliconeCastingProperties | None, getattr(scene, _SCENE_ATTR, None)
        )
        if settings is None:
            continue
        settings.mixture.clear_selection_cursor()
        for profile in settings.color_profiles:
            profile.colorant_active_index = -1


def register() -> None:
    """Register classes, attach the scene settings and add the tool."""
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    setattr(
        bpy.types.Scene,
        _SCENE_ATTR,
        bpy.props.PointerProperty(type=SiliconeCastingProperties),
    )
    bpy.utils.register_tool(
        SILCAST_WST_registration_keys, after={"builtin.transform"}, separator=True
    )
    if _reset_transient_selection_state not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_reset_transient_selection_state)


def unregister() -> None:
    """Close active tools and unregister views, operations and models."""
    operators.cancel_active_tools()
    bpy.utils.unregister_tool(SILCAST_WST_registration_keys)
    if _reset_transient_selection_state in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_reset_transient_selection_state)
    delattr(bpy.types.Scene, _SCENE_ATTR)
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
