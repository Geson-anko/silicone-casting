"""Color simulator lists, drawing, and popover panel."""

from __future__ import annotations

from typing import cast, override

import bpy

from ..core import format_hex_color, format_linear_rgb, linear_rgb_to_srgb8
from ..operators import (
    SILCAST_OT_add_color_profile,
    SILCAST_OT_add_colorant,
    SILCAST_OT_apply_color_material,
    SILCAST_OT_copy_mixture_volume_to_coloring,
    SILCAST_OT_copy_value,
    SILCAST_OT_remove_color_profile,
    SILCAST_OT_remove_colorant,
)
from ..operators.color_simulator import (
    ColorantValues,
    ColorProfileValues,
    ColorSimulatorSettings,
    active_color_profile,
    calculate_profile_appearance,
)


def _colorant_table_cells(
    layout: bpy.types.UILayout,
) -> tuple[bpy.types.UILayout, ...]:
    """Keep dye headings and editable rows in the same responsive columns."""
    weights = (0.55, 1.2, 2.5, 2.0, 2.0, 2.8, 2.2)
    remaining = layout.row(align=True)
    remaining_weight = sum(weights)
    cells: list[bpy.types.UILayout] = []
    for weight in weights[:-1]:
        split = remaining.split(factor=weight / remaining_weight, align=True)
        cells.append(split.column(align=True))
        remaining = split.column(align=True)
        remaining_weight -= weight
    cells.append(remaining)
    return tuple(cells)


class SILCAST_UL_color_profiles(bpy.types.UIList):
    """Compact selector for named color recipes."""

    bl_idname = "SILCAST_UL_color_profiles"

    @override
    def draw_item(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        data: object | None,
        item: object | None,
        icon: int | None,
        active_data: object,
        active_property: str | None,
        index: int | None,
        flt_flag: int | None,
    ) -> None:
        del context, data, icon, active_data, active_property, index, flt_flag
        if item is not None:
            layout.prop(item, "profile_name", text="", emboss=False, icon="MATERIAL")


class SILCAST_UL_colorants(bpy.types.UIList):
    """Editable calibrated colorants for the active profile."""

    bl_idname = "SILCAST_UL_colorants"

    @override
    def draw_item(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        data: object | None,
        item: object | None,
        icon: int | None,
        active_data: object,
        active_property: str | None,
        index: int | None,
        flt_flag: int | None,
    ) -> None:
        del context, data, icon, active_data, active_property, index, flt_flag
        if item is None:
            return
        colorant = cast(ColorantValues, item)
        cells = _colorant_table_cells(layout)
        for cell, property_name in zip(
            cells,
            (
                "enabled",
                "calibration_color",
                "colorant_name",
                "calibration_hue_degrees",
                "calibration_lightness_percent",
                "calibration_drops_per_ml",
                "drops",
            ),
            strict=True,
        ):
            cell.prop(colorant, property_name, text="")


def _draw_profile_selector(
    layout: bpy.types.UILayout,
    scene_settings: bpy.types.PropertyGroup,
) -> None:
    exchange = layout.row(align=True)
    exchange.operator(
        "silicone_casting.export_recipes", text="Export JSON", icon="EXPORT"
    ).kind = "COLORS"
    exchange.operator(
        "silicone_casting.import_recipes", text="Import JSON", icon="IMPORT"
    ).kind = "COLORS"
    profiles = layout.box()
    profiles.label(text="1. Choose a Named Profile")
    profile_row = profiles.row()
    profile_row.template_list(
        SILCAST_UL_color_profiles.bl_idname,
        "color_profiles",
        scene_settings,
        "color_profiles",
        scene_settings,
        "color_profile_active_index",
        rows=1,
    )
    profile_controls = profile_row.column(align=True)
    profile_controls.operator(
        SILCAST_OT_add_color_profile.bl_idname,
        text="",
        icon="ADD",
    )
    profile_controls.operator(
        SILCAST_OT_remove_color_profile.bl_idname,
        text="",
        icon="REMOVE",
    )


def _draw_base_settings(
    layout: bpy.types.UILayout,
    profile: ColorProfileValues,
) -> None:
    base = layout.box()
    base.label(text="2. Set the Silicone Base Color, Volume, and Transparency")
    volume = base.row(align=True)
    volume.prop(profile, "base_volume_ml")
    volume.operator(
        SILCAST_OT_copy_mixture_volume_to_coloring.bl_idname,
        text="Use Mixture Total",
        icon="IMPORT",
    )
    base.prop(profile, "base_color", text="")
    base.prop(
        profile,
        "transparency",
        text="Base Transparency (1 clear / 0 opaque)",
        slider=True,
    )


def _draw_colorants(
    layout: bpy.types.UILayout,
    profile: ColorProfileValues,
) -> None:
    colorants = layout.box()
    colorants.label(text="3. Add Colorants and Enter the Actual Drops")
    colorants.label(
        text="Picker / Hex input is normalized to Saturation 100%",
        icon="INFO",
    )
    colorants.label(
        text="Calibration Drops / mL: measured color/opacity point (1.0 estimate)",
        icon="INFO",
    )
    header = colorants.row()
    for cell, text in zip(
        _colorant_table_cells(header),
        (
            "On",
            "Color",
            "Dye",
            "Hue (degrees)",
            "Lightness (%)",
            "Calibration Drops / mL",
            "Actual Drops",
        ),
        strict=True,
    ):
        cell.label(text=text)
    header.column().label(text="", icon="BLANK1")
    colorant_row = colorants.row()
    profile_properties = cast(bpy.types.PropertyGroup, profile)
    colorant_row.template_list(
        SILCAST_UL_colorants.bl_idname,
        "colorants",
        profile_properties,
        "colorants",
        profile_properties,
        "colorant_active_index",
        rows=2,
    )
    colorant_controls = colorant_row.column(align=True)
    colorant_controls.operator(
        SILCAST_OT_add_colorant.bl_idname,
        text="",
        icon="ADD",
    )
    colorant_controls.operator(
        SILCAST_OT_remove_colorant.bl_idname,
        text="",
        icon="REMOVE",
    )

    if 0 <= profile.colorant_active_index < len(profile.colorants):
        selected = profile.colorants[profile.colorant_active_index]
        editor = colorants.box()
        editor.label(text=f"Edit Selected Dye Color: {selected.colorant_name}")
        edit_row = editor.row()
        picker = edit_row.column(align=True)
        picker.template_color_picker(
            selected,
            "calibration_color",
            value_slider=True,
        )
        values = edit_row.column(align=True)
        preview = values.row()
        preview.scale_y = 1.4
        preview.prop(selected, "calibration_color", text="Color")
        values.prop(selected, "calibration_hex", text="Hex (sRGB)")
        values.prop(selected, "calibration_hue_degrees", text="Hue (degrees)")
        values.prop(
            selected,
            "calibration_lightness_percent",
            text="Lightness (%)",
        )


def _draw_color_result(
    layout: bpy.types.UILayout,
    profile: ColorProfileValues,
) -> None:
    result = layout.box()
    result.label(text="4. Check the Mixed Color (click values to copy)")
    swatch = result.row()
    swatch.scale_y = 1.6
    swatch.prop(profile, "result_color", text="Result Color")

    calculated = calculate_profile_appearance(profile)
    srgb = linear_rgb_to_srgb8(calculated.color)
    color_values = (
        ("Hex (sRGB)", format_hex_color(calculated.color)),
        ("sRGB 8-bit", f"rgb({srgb[0]}, {srgb[1]}, {srgb[2]})"),
        ("Linear RGB", format_linear_rgb(calculated.color)),
    )
    value_row = result.row(align=True)
    for label, value in color_values:
        value_column = value_row.column(align=True)
        value_column.label(text=label)
        copy = value_column.operator(
            SILCAST_OT_copy_value.bl_idname,
            text=value,
            icon="COPYDOWN",
        )
        copy.value = value

    final_appearance = result.row(align=True)
    final_appearance.label(text=f"Result Transparency: {calculated.transparency:.2f}")
    final_appearance.operator(
        SILCAST_OT_apply_color_material.bl_idname,
        text="Apply to Selected",
        icon="MATERIAL",
    )


def draw_color_simulator(
    layout: bpy.types.UILayout,
    scene_settings: bpy.types.PropertyGroup,
) -> None:
    """Draw the simulator as a numbered profile-to-result workflow."""
    settings = cast(ColorSimulatorSettings, scene_settings)
    _draw_profile_selector(layout, scene_settings)

    profile = active_color_profile(settings)
    if profile is None:
        layout.label(text="Press + to add the first profile", icon="INFO")
        return

    _draw_base_settings(layout, profile)
    _draw_colorants(layout, profile)
    _draw_color_result(layout, profile)


class SILCAST_PT_color_simulator(bpy.types.Panel):
    """Wide color simulator opened horizontally beside the sidebar."""

    bl_label = "Color Mixing Simulator"
    bl_idname = "SILCAST_PT_color_simulator"
    bl_space_type = "VIEW_3D"
    bl_region_type = "HEADER"
    bl_ui_units_x = 48

    @override
    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        assert layout is not None
        draw_color_simulator(layout, context.scene.silicone_casting)
