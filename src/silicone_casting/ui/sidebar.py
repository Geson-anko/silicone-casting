"""Panels shown in the add-on's 3D View sidebar."""

from typing import Final, cast, override

import bpy

from ..core.units import format_ml
from ..operators.boolean_modifier import (
    OPERATION_ITEMS,
    SILCAST_OT_add_boolean,
    SILCAST_OT_add_surface_cut,
)
from ..operators.copy_value import SILCAST_OT_copy_value
from ..operators.draw_air_vents import SILCAST_OT_draw_air_vents
from ..operators.draw_surface_cut import (
    SILCAST_OT_draw_surface_cut,
    SILCAST_OT_edit_cutting_surface,
)
from ..operators.export_stl import SILCAST_OT_export_stl
from ..operators.inherit_shape import SILCAST_OT_inherit_shape
from ..operators.key_editing import (
    SILCAST_OT_delete_registration_key,
    SILCAST_OT_edit_registration_key,
)
from ..operators.key_placement import (
    SILCAST_OT_start_key_placement,
    SILCAST_OT_stop_key_placement,
)
from ..operators.measure_volume import SILCAST_OT_measure_volume
from ..operators.separate_loose_parts import SILCAST_OT_separate_loose_parts
from ..operators.solidify import SILCAST_OT_apply_solidify, SILCAST_OT_solidify
from ..properties.settings import SiliconeCastingProperties, scene_settings
from .color import SILCAST_PT_color_simulator
from .mixture import SILCAST_PT_mixture_calculator

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
        """Draw nothing: the sub-panels hold every control.

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
        settings = scene_settings(context)
        layout.operator(SILCAST_OT_measure_volume.bl_idname, icon="DRIVER_DISTANCE")

        row = layout.split(factor=0.5)
        row.label(text=_VOLUME_LABEL)
        if not settings.volume_measured:
            # Nothing to copy yet, so the value is a plain label.
            row.label(text=_NOT_MEASURED)
        else:
            # Formatted exactly once: the same string is what the user sees and
            # what the copy operator puts on the clipboard.
            text = format_ml(settings.volume_ml)
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
        settings = scene_settings(context)
        self._draw_solidify(settings)
        self._draw_boolean(settings)
        self._draw_surface_cut(settings)
        self._draw_air_vents(settings)
        self._draw_inherit_shape(context, settings)
        layout.separator()
        layout.operator(SILCAST_OT_separate_loose_parts.bl_idname, icon="MESH_DATA")
        layout.separator()
        self._draw_registration_keys(settings)
        layout.operator(SILCAST_OT_export_stl.bl_idname, icon="EXPORT")

    def _section(self, identifier: str, title: str) -> bpy.types.UILayout | None:
        """Add a collapsible section, closed by default.

        Returns:
            The section body, or ``None`` while the section is collapsed.
        """
        layout = self.layout
        assert layout is not None
        # Blender returns None for the body when collapsed; the stub omits it.
        header, body = cast(
            tuple[bpy.types.UILayout, bpy.types.UILayout | None],
            layout.panel(identifier, default_closed=True),
        )
        header.label(text=title)
        return body

    def _draw_solidify(self, settings: SiliconeCastingProperties) -> None:
        """Draw wall thickness settings and apply controls."""
        solidify = self._section("solidify", "Solidify")
        if solidify is None:
            return
        solidify.prop(settings, "solidify_thickness")
        row = solidify.row()
        row.prop(settings, "solidify_flip")
        row.prop(settings, "solidify_even_thickness")
        solidify.operator(SILCAST_OT_solidify.bl_idname, icon="MOD_SOLIDIFY")
        solidify.operator(SILCAST_OT_apply_solidify.bl_idname)

    def _draw_boolean(self, settings: SiliconeCastingProperties) -> None:
        """Draw the Boolean operand, solver, and one button per operation."""
        boolean = self._section("boolean", "Boolean")
        if boolean is None:
            return
        boolean.prop(settings, "boolean_operand")
        boolean.row().prop(settings, "boolean_solver", expand=True)
        operations = boolean.row(align=True)
        for operation, label, _description in OPERATION_ITEMS:
            button = operations.operator(SILCAST_OT_add_boolean.bl_idname, text=label)
            button.operation = operation

    def _draw_surface_cut(self, settings: SiliconeCastingProperties) -> None:
        """Draw surface cutting and freehand drawing controls."""
        cutting = self._section("surface_cut", "Surface Cut")
        if cutting is None:
            return
        cutting.prop(settings, "boolean_operand", text="")
        cutting.prop(settings, "surface_cut_thickness")
        cutting.operator(SILCAST_OT_add_surface_cut.bl_idname, icon="MOD_SOLIDIFY")
        cutting.separator()
        cutting.prop(settings, "surface_cut_margin")
        cutting.row().prop(settings, "surface_cut_input_mode", expand=True)
        cutting.operator(SILCAST_OT_draw_surface_cut.bl_idname, icon="GREASEPENCIL")
        cutting.operator(SILCAST_OT_edit_cutting_surface.bl_idname, icon="EDITMODE_HLT")

    def _draw_air_vents(self, settings: SiliconeCastingProperties) -> None:
        """Draw the air vent diameter and drawing control."""
        vents = self._section("air_vents", "Air Vents")
        if vents is None:
            return
        vents.prop(settings, "air_vent_diameter")
        vents.operator(SILCAST_OT_draw_air_vents.bl_idname, icon="GREASEPENCIL")
        vents.label(text="First face sets the plane")
        vents.label(text="Drag to draw / Enter to cut")

    def _draw_inherit_shape(
        self, context: bpy.types.Context, settings: SiliconeCastingProperties
    ) -> None:
        """Draw object and collection shape inheritance."""
        inherit = self._section("inherit_shape", "Inherit Shape")
        if inherit is None:
            return
        active = context.active_object
        object_row = inherit.row()
        object_row.enabled = active is not None and active.type == "MESH"
        object_row.operator(SILCAST_OT_inherit_shape.bl_idname, icon="MOD_BOOLEAN")
        inherit.prop(settings, "inherit_collection", text="")
        collection_row = inherit.row()
        collection_row.enabled = settings.inherit_collection is not None
        collection_button = collection_row.operator(
            SILCAST_OT_inherit_shape.bl_idname,
            text="Inherit Collection Shape",
            icon="OUTLINER_COLLECTION",
        )
        collection_button.use_collection = True

    def _draw_registration_keys(self, settings: SiliconeCastingProperties) -> None:
        """Draw pin dimensions, placement, and selected-key editing."""
        keys = self._section("registration_keys", "Registration Keys")
        if keys is None:
            return
        keys.label(text="Active half: pin")
        keys.prop(settings, "key_mate", text="Socket")
        keys.prop(settings, "key_shape")
        keys.prop(settings, "key_width")
        if settings.key_shape == "RECTANGLE":
            keys.prop(settings, "key_length")
        if settings.key_shape == "TAPERED":
            keys.prop(settings, "key_taper_angle")
            keys.prop(settings, "key_taper")
        keys.prop(settings, "key_height")
        keys.prop(settings, "key_embed")
        keys.prop(settings, "key_clearance")
        keys.prop(settings, "key_depth_clearance")
        keys.prop(settings, "key_align_normal")
        if not settings.key_align_normal:
            keys.prop(settings, "key_axis", expand=True)
        keys.prop(settings, "key_flip")
        keys.prop(settings, "key_angle")

        row = keys.row(align=True)
        row.operator(SILCAST_OT_start_key_placement.bl_idname, icon="ADD")
        row.operator(
            SILCAST_OT_stop_key_placement.bl_idname, text="Done", icon="CHECKMARK"
        )
        keys.label(text="Click: add / select")
        keys.label(text="Drag: move / Delete: remove")

        if settings.key_active is None:
            return
        keys.label(text=f"Selected: {settings.key_active.name}")
        keys.operator(
            SILCAST_OT_edit_registration_key.bl_idname, text="Update Selected Key"
        )
        keys.operator(
            SILCAST_OT_delete_registration_key.bl_idname,
            text="Delete Selected Key",
            icon="X",
        )
