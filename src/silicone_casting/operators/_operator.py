"""Shared primitives for Blender operator boundaries."""

from typing import Literal

import bpy

#: Blender's ``OperatorReturnItems`` RNA enum, spelled out so operator modules
#: stay importable at runtime (the stub-only alias is not).
type OperatorReturn = set[
    Literal["RUNNING_MODAL", "CANCELLED", "FINISHED", "PASS_THROUGH", "INTERFACE"]
]


def selected_meshes(context: bpy.types.Context) -> list[bpy.types.Object]:
    """Return a stable snapshot of selected meshes in selection order."""
    selected = context.selected_objects or ()
    return [obj for obj in selected if obj.type == "MESH"]
