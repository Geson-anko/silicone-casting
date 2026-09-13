"""Panels shown in the add-on's 3D View sidebar."""

from __future__ import annotations

from typing import Final, Protocol, cast, override

import bpy

from ..core import format_ml
from ..operators import (
    SILCAST_OT_add_boolean,
    SILCAST_OT_add_surface_cut,
    SILCAST_OT_apply_solidify,
    SILCAST_OT_copy_value,
    SILCAST_OT_draw_air_vents,
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
from ._scene_properties import SiliconeCastingProperties

#: Left column of the volume row. The unit lives in the label so that the
#: value stays a bare number, ready to be pasted into a spreadsheet.
_VOLUME_LABEL: Final = "Volume (mL)"

#: Stands in for the value before the first measurement. Keeping it to two
#: characters keeps the row's shape identical before and after measuring.
_NOT_MEASURED: Final = "--"


class _RegistrationKeySettings(Protocol):
    """RNA fields that determine which key controls are visible."""

    key_shape: str
    key_align_normal: bool
    key_active: bpy.types.Object | None


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
        assert layout is not None
        props = context.scene.silicone_casting
        self._draw_solidify(props)
        self._draw_boolean(props)
        self._draw_surface_cut(props)
        self._draw_air_vents(props)
        self._draw_inherit_shape(context)
        layout.separator()
        layout.operator(SILCAST_OT_separate_loose_parts.bl_idname, icon="MESH_DATA")
        layout.separator()
        self._draw_registration_keys(cast(_RegistrationKeySettings, props))
        layout.operator(SILCAST_OT_export_stl.bl_idname, icon="EXPORT")

    def _section(self, identifier: str, title: str) -> bpy.types.UILayout | None:
        """Keep each processing task one click away without a long sidebar."""
        layout = self.layout
        assert layout is not None
        # Blender returns None for the body when collapsed; the stub omits it.
        header, body = cast(
            tuple[bpy.types.UILayout, bpy.types.UILayout | None],
            layout.panel(identifier, default_closed=True),
        )
        header.label(text=title)
        return body

    def _draw_solidify(self, props: SiliconeCastingProperties) -> None:
        """Draw wall thickness settings and apply controls."""
        solidify = self._section("solidify", "Solidify")
        if solidify is not None:
            solidify.prop(props, "solidify_thickness")
            row = solidify.row()
            row.prop(props, "solidify_flip")
            row.prop(props, "solidify_even_thickness")
            solidify.operator(SILCAST_OT_solidify.bl_idname, icon="MOD_SOLIDIFY")
            solidify.operator(SILCAST_OT_apply_solidify.bl_idname)

    def _draw_boolean(self, props: SiliconeCastingProperties) -> None:
        """Draw Boolean operands, solver, and operations."""
        boolean = self._section("boolean", "Boolean")
        if boolean is not None:
            boolean.prop(props, "boolean_operand")
            boolean.row().prop(props, "boolean_solver", expand=True)
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

    def _draw_surface_cut(self, props: SiliconeCastingProperties) -> None:
        """Draw surface cutting and freehand drawing controls."""
        cutting = self._section("surface_cut", "Surface Cut")
        if cutting is not None:
            cutting.prop(props, "boolean_operand", text="")
            cutting.prop(props, "surface_cut_thickness")
            cutting.operator(SILCAST_OT_add_surface_cut.bl_idname, icon="MOD_SOLIDIFY")
            cutting.separator()
            cutting.prop(props, "surface_cut_margin")
            cutting.row().prop(props, "surface_cut_input_mode", expand=True)
            cutting.operator(SILCAST_OT_draw_surface_cut.bl_idname, icon="GREASEPENCIL")
            cutting.operator(
                SILCAST_OT_edit_cutting_surface.bl_idname, icon="EDITMODE_HLT"
            )

    def _draw_air_vents(self, props: SiliconeCastingProperties) -> None:
        """Draw the air vent diameter and drawing control."""
        vents = self._section("air_vents", "Air Vents")
        if vents is not None:
            vents.prop(props, "air_vent_diameter")
            vents.operator(SILCAST_OT_draw_air_vents.bl_idname, icon="GREASEPENCIL")
            vents.label(text="First face sets the plane")
            vents.label(text="Drag to draw / Enter to cut")

    def _draw_inherit_shape(self, context: bpy.types.Context) -> None:
        """Draw object and collection shape inheritance."""
        props = context.scene.silicone_casting
        inherit = self._section("inherit_shape", "Inherit Shape")
        if inherit is not None:
            object_row = inherit.row()
            object_row.enabled = (
                context.active_object is not None
                and context.active_object.type == "MESH"
            )
            object_row.operator(SILCAST_OT_inherit_shape.bl_idname, icon="MOD_BOOLEAN")
            inherit.prop(props, "inherit_collection", text="")
            collection_row = inherit.row()
            collection_row.enabled = props.inherit_collection is not None
            collection_row.operator(
                SILCAST_OT_inherit_shape.bl_idname,
                text="Inherit Collection Shape",
                icon="OUTLINER_COLLECTION",
            ).use_collection = True

    def _draw_registration_keys(self, props: _RegistrationKeySettings) -> None:
        """Draw pin dimensions, placement, and selected-key editing."""
        keys = self._section("registration_keys", "Registration Keys")
        if keys is not None:
            keys.label(text="Active half: pin")
            keys.prop(props, "key_mate", text="Socket")
            keys.prop(props, "key_shape")
            keys.prop(props, "key_width")
            if props.key_shape == "RECTANGLE":
                keys.prop(props, "key_length")
            if props.key_shape == "TAPERED":
                keys.prop(props, "key_taper_angle")
                keys.prop(props, "key_taper")
            for name in ("height", "embed", "clearance", "depth_clearance"):
                keys.prop(props, f"key_{name}")
            keys.prop(props, "key_align_normal")
            if not props.key_align_normal:
                keys.prop(props, "key_axis", expand=True)
            keys.prop(props, "key_flip")
            keys.prop(props, "key_angle")
            row = keys.row(align=True)
            row.operator("silicone_casting.start_key_placement", icon="ADD")
            row.operator(
                "silicone_casting.stop_key_placement", text="Done", icon="CHECKMARK"
            )
            keys.label(text="Click: add / select")
            keys.label(text="Drag: move / Delete: remove")
            if props.key_active is not None:
                keys.label(text=f"Selected: {props.key_active.name}")
                keys.operator(
                    "silicone_casting.edit_registration_key", text="Update Selected Key"
                )
                keys.operator(
                    "silicone_casting.delete_registration_key",
                    text="Delete Selected Key",
                    icon="X",
                )
