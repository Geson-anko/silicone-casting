"""Shared layout primitives for the two recipe editors."""

import bpy


def table_cells(
    layout: bpy.types.UILayout, weights: tuple[float, ...]
) -> tuple[bpy.types.UILayout, ...]:
    """Split a responsive row into columns with the requested proportions."""
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


def draw_recipe_exchange(layout: bpy.types.UILayout, kind: str) -> None:
    """Draw the JSON exchange controls for one recipe editor."""
    exchange = layout.row(align=True)
    exchange.operator(
        "silicone_casting.export_recipes", text="Export JSON", icon="EXPORT"
    ).kind = kind
    exchange.operator(
        "silicone_casting.import_recipes", text="Import JSON", icon="IMPORT"
    ).kind = kind
