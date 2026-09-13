"""Mixture calculator table, list, and popover panel."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Final, cast, override

import bpy

if TYPE_CHECKING:
    from bpy.types import bpy_prop_array

from ..core.mixture import MixtureBreakdown
from ..core.units import format_grams, format_ml
from ..operators.mixture_parts import (
    SILCAST_OT_add_mixture_part,
    SILCAST_OT_move_mixture_parts,
    SILCAST_OT_remove_mixture_parts,
    SILCAST_OT_select_mixture_part,
)
from ..properties.mixture import SiliconeCastingMixture, SiliconeCastingMixturePart
from ..properties.settings import scene_settings
from ._layout import draw_recipe_exchange, table_cells

# Relative widths keep the whole table responsive while reserving most of the
# flexible space for the editable part name. Selection and Enabled stay compact.
_MIXTURE_COLUMN_WEIGHTS: Final = (
    0.65,
    1.2,
    4.4,
    1.55,
    1.55,
    1.55,
    1.55,
    1.55,
    1.55,
)


def _draw_mixture_header(layout: bpy.types.UILayout) -> None:
    """Draw headings for the editable and calculated table columns."""
    cells = table_cells(layout, _MIXTURE_COLUMN_WEIGHTS)
    for cell, label in zip(
        cells,
        ("#", "Enabled", "Name", "Vol", "W (g)", "A Vol", "B Vol", "A W", "B W"),
        strict=True,
    ):
        cell.label(text=label)


def _draw_breakdown(
    cells: Sequence[bpy.types.UILayout],
    breakdown: MixtureBreakdown,
    *,
    enabled: bool = True,
) -> None:
    """Render derived quantities in the shared row and subtotal columns."""
    values = (
        format_grams(breakdown.weight_g),
        format_ml(breakdown.a_volume_ml),
        format_ml(breakdown.b_volume_ml),
        format_grams(breakdown.a_weight_g),
        format_grams(breakdown.b_weight_g),
    )
    for cell, text in zip(cells, values, strict=True):
        output = cell.row(align=True)
        output.enabled = enabled
        output.label(text=text)


def _draw_mixture_part(
    layout: bpy.types.UILayout,
    props: SiliconeCastingMixture,
    part: SiliconeCastingMixturePart,
    index: int,
) -> None:
    """Draw one part across the full width of the calculator popover."""
    cells = table_cells(layout, _MIXTURE_COLUMN_WEIGHTS)
    select = cells[0].operator(
        SILCAST_OT_select_mixture_part.bl_idname,
        text=str(index + 1),
        depress=part.selected,
    )
    select.index = index
    cells[1].prop(part, "enabled", text="")
    cells[2].prop(part, "part_name", text="")
    cells[3].prop(part, "volume_ml", text="")

    _draw_breakdown(cells[4:], props.breakdown(part.volume_ml), enabled=part.enabled)


def _draw_mixture_summary(
    layout: bpy.types.UILayout,
    props: SiliconeCastingMixture,
    label: str,
    volume_ml: float,
) -> None:
    """Draw one subtotal using the same columns as a part row."""
    cells = table_cells(layout, _MIXTURE_COLUMN_WEIGHTS)
    cells[0].label(text="")
    cells[1].label(text="")
    cells[2].label(text=label)
    cells[3].label(text=format_ml(volume_ml))

    _draw_breakdown(cells[4:], props.breakdown(volume_ml))


def _filter_mixture_parts_by_name(
    pattern: str,
    bitflag: int,
    parts: Sequence[SiliconeCastingMixturePart],
    *,
    reverse: bool = False,
) -> list[int]:
    """Return Blender UI-list flags matching the saved part name."""
    return cast(
        list[int],
        bpy.types.UI_UL_list.filter_items_by_name(  # pyright: ignore[reportUnknownMemberType]
            pattern,
            bitflag,
            parts,
            "part_name",
            reverse=reverse,
        ),
    )


def _draw_mixture_settings(
    layout: bpy.types.UILayout, props: SiliconeCastingMixture
) -> None:
    """Draw the density mode and the A:B weight ratio."""
    settings = layout.box()
    density = settings.row(align=True)
    density.prop(props, "use_shared_density")
    if props.use_shared_density:
        density.prop(
            props,
            "density_a_g_per_ml",
            text="Density (g/mL)",
        )
    else:
        density.prop(props, "density_a_g_per_ml", text="Density A")
        density.prop(props, "density_b_g_per_ml", text="Density B")

    ratio = settings.row(align=True)
    ratio.prop(props, "ratio_a", text="Ratio A")
    ratio.prop(props, "ratio_b", text="Ratio B")


def _draw_mixture_controls(layout: bpy.types.UILayout, any_selected: bool) -> None:
    """Add rows and enable removal or movement for the selected rows."""
    controls = layout.row(align=True)
    controls.operator(SILCAST_OT_add_mixture_part.bl_idname, text="", icon="ADD")
    selected_controls = controls.row(align=True)
    selected_controls.enabled = any_selected
    selected_controls.operator(
        SILCAST_OT_remove_mixture_parts.bl_idname,
        text="",
        icon="REMOVE",
    )
    move_up = selected_controls.operator(
        SILCAST_OT_move_mixture_parts.bl_idname,
        text="",
        icon="TRIA_UP",
    )
    move_up.direction = "UP"
    move_down = selected_controls.operator(
        SILCAST_OT_move_mixture_parts.bl_idname,
        text="",
        icon="TRIA_DOWN",
    )
    move_down.direction = "DOWN"


class SILCAST_UL_mixture_parts(bpy.types.UIList):
    """Editable mixture rows with Blender's native active-row highlight."""

    bl_idname = "SILCAST_UL_mixture_parts"

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
        """Draw one editable table row inside the native UI list."""
        del context, data, icon, active_property, flt_flag
        if item is None or index is None:
            return
        props = cast(SiliconeCastingMixture, active_data)
        part = cast(SiliconeCastingMixturePart, item)
        _draw_mixture_part(layout, props, part, index)

    @override
    def filter_items(
        self,
        context: bpy.types.Context,
        data: object | None,
        property: str,
    ) -> tuple[bpy_prop_array, bpy_prop_array]:
        """Filter displayed rows by their editable Name value."""
        del context
        if data is None:
            return cast("bpy_prop_array", []), cast("bpy_prop_array", [])
        parts = cast(Sequence[SiliconeCastingMixturePart], getattr(data, property))
        flags = _filter_mixture_parts_by_name(
            self.filter_name,
            self.bitflag_filter_item,
            parts,
            reverse=self.use_filter_invert,
        )
        # Blender consumes ordinary Python lists here, while the 5.1 stub
        # declares the callback result as bpy_prop_array.
        return (
            cast("bpy_prop_array", flags),
            cast("bpy_prop_array", []),
        )


class SILCAST_PT_mixture_calculator(bpy.types.Panel):
    """Wide calculator opened as a popover beside the sidebar."""

    bl_label = "Mixture Calculator"
    bl_idname = "SILCAST_PT_mixture_calculator"
    bl_space_type = "VIEW_3D"
    bl_region_type = "HEADER"
    bl_ui_units_x = 48

    @override
    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        assert layout is not None
        props = scene_settings(context).mixture
        draw_recipe_exchange(layout, "MIXTURE")
        _draw_mixture_settings(layout, props)
        guidance = layout.row(align=True)
        guidance.label(text="Select row numbers with Click / Ctrl / Shift")
        guidance.label(text="Volumes: mL / Weights: g")
        _draw_mixture_header(layout)
        layout.template_list(
            SILCAST_UL_mixture_parts.bl_idname,
            "parts",
            props,
            "parts",
            props,
            "active_index",
            rows=6,
            maxrows=10,
        )

        any_selected = any(part.selected for part in props.parts)
        _draw_mixture_controls(layout, any_selected)

        if any_selected:
            selected_volume = props.total_volume(selected_only=True)
            layout.separator(factor=0.35)
            _draw_mixture_summary(layout, props, "Selected", selected_volume)

        total_volume = props.total_volume()
        _draw_mixture_summary(layout, props, "Total", total_volume)
