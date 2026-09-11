"""Panels shown in the add-on's 3D View sidebar."""

from __future__ import annotations

from typing import Final, override

import bpy

from ..core import format_ml
from ..operators import (
    SILCAST_OT_add_boolean,
    SILCAST_OT_add_surface_cut,
    SILCAST_OT_apply_solidify,
    SILCAST_OT_copy_value,
    SILCAST_OT_draw_surface_cut,
    SILCAST_OT_edit_cutting_surface,
    SILCAST_OT_export_stl,
    SILCAST_OT_inherit_shape,
    SILCAST_OT_measure_volume,
    SILCAST_OT_separate_loose_parts,
    SILCAST_OT_solidify,
)
from ._color_panel import SILCAST_PT_color_simulator
from ._mixture_panel import SILCAST_PT_mixture_calculator

#: Left column of the volume row. The unit lives in the label so that the
#: value stays a bare number, ready to be pasted into a spreadsheet.
_VOLUME_LABEL: Final = "Volume (mL)"

#: Stands in for the value before the first measurement. Keeping it to two
#: characters keeps the row's shape identical before and after measuring.
_NOT_MEASURED: Final = "--"


class SILCAST_PT_main(bpy.types.Panel):
    """Entry point for the add-on in the 3D View sidebar."""

    bl_label = "Silicone Casting"
    bl_idname = "SILCAST_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Silicone Casting"

    @override
    def draw(self, context: bpy.types.Context) -> None:
        """Add nothing: this panel is a header, its sub-panels hold every
        control.

        The method stays because Blender refuses to register a panel
        without a ``draw``.
        """


class SILCAST_PT_measurement(bpy.types.Panel):
    """Measured quantities of the current selection."""

    bl_label = "Measurement"
    bl_idname = "SILCAST_PT_measurement"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    # No bl_category: a child panel follows its parent's tab, so naming one
    # here would give the tab two sources of truth.
    bl_parent_id = SILCAST_PT_main.bl_idname
    bl_order = 0

    @override
    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        # `Panel.layout` is typed optional because it is unset outside a draw
        # call; Blender always populates it before invoking draw().
        assert layout is not None
        props = context.scene.silicone_casting
        layout.operator(SILCAST_OT_measure_volume.bl_idname, icon="DRIVER_DISTANCE")

        row = layout.split(factor=0.5)
        row.label(text=_VOLUME_LABEL)
        if not props.volume_measured:
            # Nothing to copy yet, so the value is a plain label.
            row.label(text=_NOT_MEASURED)
        else:
            # Formatted exactly once: the same string is what the user sees and
            # what the copy operator puts on the clipboard.
            text = format_ml(props.volume_ml)
            # `layout.label` cannot be clicked, so the value is drawn as the text
            # of an un-embossed operator button instead.
            copy = row.operator(
                SILCAST_OT_copy_value.bl_idname, text=text, emboss=False
            )
            copy.value = text

        layout.separator()
        layout.popover(
            panel=SILCAST_PT_mixture_calculator.bl_idname,
            text="Mixture Calculator",
            icon="SPREADSHEET",
            direction="HORIZONTAL",
        )


class SILCAST_PT_coloring(bpy.types.Panel):
    """Entry point for named silicone color recipes."""

    bl_label = "Coloring"
    bl_idname = "SILCAST_PT_coloring"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_parent_id = SILCAST_PT_main.bl_idname
    bl_order = 1

    @override
    def draw(self, context: bpy.types.Context) -> None:
        del context
        layout = self.layout
        assert layout is not None
        layout.popover(
            panel=SILCAST_PT_color_simulator.bl_idname,
            text="Color Mixing Simulator",
            icon="COLOR",
            direction="HORIZONTAL",
        )


class SILCAST_PT_processing(bpy.types.Panel):
    """Operations that reshape the selected meshes."""

    bl_label = "Processing"
    bl_idname = "SILCAST_PT_processing"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_parent_id = SILCAST_PT_main.bl_idname
    bl_order = 2

    @override
    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        # `Panel.layout` is typed optional because it is unset outside a draw
        # call; Blender always populates it before invoking draw().
        assert layout is not None
        props = context.scene.silicone_casting
        layout.prop(props, "solidify_thickness_mm")
        row = layout.row()
        row.prop(props, "solidify_flip")
        row.prop(props, "solidify_even_thickness")
        layout.operator(SILCAST_OT_solidify.bl_idname, icon="MOD_SOLIDIFY")
        layout.operator(SILCAST_OT_apply_solidify.bl_idname)
        layout.separator()
        boolean = layout.box()
        boolean.label(text="Boolean", icon="MOD_BOOLEAN")
        boolean.prop(props, "boolean_operand")
        boolean.prop(props, "boolean_solver", expand=True)
        operations = boolean.row(align=True)
        for operation, label in (
            ("DIFFERENCE", "Difference"),
            ("UNION", "Union"),
            ("INTERSECT", "Intersect"),
        ):
            button = operations.operator(
                SILCAST_OT_add_boolean.bl_idname,
                text=label,
            )
            button.operation = operation
        boolean.prop(props, "surface_cut_thickness_mm")
        boolean.operator(
            SILCAST_OT_add_surface_cut.bl_idname,
            icon="MOD_SOLIDIFY",
        )
        boolean.separator()
        boolean.prop(props, "surface_cut_margin")
        boolean.prop(props, "surface_cut_input_mode", expand=True)
        boolean.operator(SILCAST_OT_draw_surface_cut.bl_idname, icon="GREASEPENCIL")
        boolean.operator(SILCAST_OT_edit_cutting_surface.bl_idname, icon="EDITMODE_HLT")
        object_row = layout.row()
        object_row.enabled = (
            context.active_object is not None and context.active_object.type == "MESH"
        )
        object_row.operator(SILCAST_OT_inherit_shape.bl_idname, icon="MOD_BOOLEAN")
        layout.prop(props, "inherit_collection")
        collection_row = layout.row()
        collection_row.enabled = props.inherit_collection is not None
        collection_row.operator(
            SILCAST_OT_inherit_shape.bl_idname,
            text="Inherit Collection Shape",
            icon="OUTLINER_COLLECTION",
        ).use_collection = True
        layout.operator(
            SILCAST_OT_separate_loose_parts.bl_idname,
            icon="MESH_DATA",
        )
        layout.separator()
        keys = layout.box()
        keys.label(text="Registration Keys")
        keys.label(text="Active half: pin / Cursor: placement")
        keys.prop(props, "key_mate")
        keys.prop(props, "key_shape")
        keys.prop(props, "key_width_mm")
        if props.key_shape == "RECTANGLE":
            keys.prop(props, "key_length_mm")
        if props.key_shape == "TAPERED":
            keys.prop(props, "key_taper")
        for name in ("height", "embed", "clearance", "depth_clearance"):
            keys.prop(props, f"key_{name}_mm")
        keys.prop(props, "key_align_normal")
        keys.prop(props, "key_flip")
        keys.prop(props, "key_angle")
        keys.operator("silicone_casting.preview_registration_key", icon="HIDE_OFF")
        row = keys.row(align=True)
        row.operator("silicone_casting.commit_registration_key", icon="CHECKMARK")
        row.operator("silicone_casting.cancel_registration_key", icon="X")
        layout.operator(SILCAST_OT_export_stl.bl_idname, icon="EXPORT")
