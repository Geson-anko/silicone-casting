"""Operator that measures the total volume of the selected meshes.

Measuring happens only on a button press: the result is written to
``Scene.silicone_casting`` and the panel formats what is stored, so
redrawing the sidebar never pays for a depsgraph evaluation. The stored
value is therefore a snapshot -- nothing invalidates it when the scene
changes afterwards, and the user refreshes it by pressing the button
again.
"""

from typing import Final, override

import bpy

from ..core import VolumeSummary, cubic_units_to_ml, format_ml
from ._operator import OperatorReturn, selected_meshes

#: How many object names the error message may list before it falls back to a
#: count. The status bar is a single line, so an unbounded list is unreadable.
_MAX_REPORTED_NAMES: Final = 3


class SILCAST_OT_measure_volume(bpy.types.Operator):
    """Measure the total volume of the selected meshes."""

    bl_idname = "silicone_casting.measure_volume"
    bl_label = "Measure Volume"
    # The tooltip is the only place the snapshot caveat reaches the user: the
    # result is shown as this operator's sibling button rather than through
    # `layout.prop()`, so the description on `volume_ml` never surfaces.
    bl_description = (
        "Measure the total volume of the selected meshes. "
        "The shown value stays as measured until you press this again"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    @override
    def poll(cls, context: bpy.types.Context) -> bool:
        # No mode check: measuring only reads geometry, and it returns the same
        # value in edit mode as in object mode.
        return bool(selected_meshes(context))

    @override
    def execute(self, context: bpy.types.Context) -> OperatorReturn:
        # `from_objects` picks the mesh objects out of the selection itself,
        # so the selection goes in as-is. See poll() for the `or ()`.
        summary = VolumeSummary.from_objects(
            context.selected_objects or (),
            context.evaluated_depsgraph_get(),
        )
        props = context.scene.silicone_casting

        names = summary.non_watertight_names
        if names:
            listed = ", ".join(names[:_MAX_REPORTED_NAMES])
            hidden = len(names) - _MAX_REPORTED_NAMES
            if hidden > 0:
                listed = f"{listed} and {hidden} more"
            # Resetting the flag on a cancelled run is deliberate. Blender
            # pushes no undo step for CANCELLED, so this reset cannot be undone
            # on its own; that asymmetry is still better than leaving the
            # previous number on screen, where it would read as the volume of
            # the selection that just failed to measure.
            props.volume_measured = False
            self.report({"ERROR"}, f"Not watertight: {listed}")
            return {"CANCELLED"}

        props.volume_ml = cubic_units_to_ml(
            summary.volume,
            context.scene.unit_settings.scale_length,
        )
        props.volume_measured = True
        # Formatted from the stored value, not the value just computed: the
        # scene property is single precision and the panel formats what is
        # stored, so reading it back keeps the reported, displayed, and copied
        # strings identical.
        shown = format_ml(props.volume_ml)
        self.report({"INFO"}, f"{shown} mL from {summary.measured_count} object(s)")
        return {"FINISHED"}
