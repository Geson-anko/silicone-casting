"""Saved silicone mixture settings, calculated amounts, and row selection."""

from typing import TYPE_CHECKING, Literal

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)

from ..core.mixture import MixtureBreakdown

if TYPE_CHECKING:
    from bpy.types import bpy_prop_collection_idprop

type MoveDirection = Literal["UP", "DOWN"]
type SelectionMode = Literal["REPLACE", "TOGGLE", "RANGE", "ADD_RANGE"]

_MIN_DENSITY_G_PER_ML = 0.001
_MIN_MIXTURE_RATIO = 0.001


class SiliconeCastingMixturePart(bpy.types.PropertyGroup):
    """One manually entered part in the silicone mixture table."""

    if TYPE_CHECKING:
        enabled: bool
        selected: bool
        part_name: str
        volume_ml: float
    else:
        enabled: BoolProperty(
            name="Enabled",
            description="Include this part in mixture totals",
            default=True,
        )
        selected: BoolProperty(
            name="Selected",
            description="Include this part in the selected subtotal",
            default=False,
        )
        part_name: StringProperty(name="Name", default="Part")
        # Keep the calculation's physical unit independent of scene display units.
        volume_ml: FloatProperty(name="Volume (mL)", default=0.0, min=0.0, precision=2)


class SiliconeCastingMixture(bpy.types.PropertyGroup):
    """Density, ratio, and editable parts owned by one scene's mixture."""

    def breakdown(self, volume_ml: float) -> MixtureBreakdown:
        """Calculate weights and component volumes with the saved density
        mode."""
        density_b = (
            self.density_a_g_per_ml
            if self.use_shared_density
            else self.density_b_g_per_ml
        )
        return MixtureBreakdown.from_volume(
            volume_ml, self.density_a_g_per_ml, density_b, self.ratio_a, self.ratio_b
        )

    def total_volume(self, *, selected_only: bool = False) -> float:
        """Sum enabled parts, optionally limiting the total to selected
        rows."""
        return sum(
            part.volume_ml
            for part in self.parts
            if part.enabled and (not selected_only or part.selected)
        )

    def add_part(self) -> SiliconeCastingMixturePart:
        """Append a default zero-volume part without selecting it."""
        part = self.parts.add()
        self._clear_selection_cursor()
        return part

    def remove_selected_parts(self) -> None:
        """Remove selected parts while retaining the order of the other
        rows."""
        for index in range(len(self.parts) - 1, -1, -1):
            if self.parts[index].selected:
                self.parts.remove(index)
        self._clear_selection_cursor()

    def move_selected_parts(self, direction: MoveDirection) -> bool:
        """Move selected rows by one position without reordering selected
        rows."""
        moved = False
        if direction == "UP":
            for index in range(1, len(self.parts)):
                if self.parts[index].selected and not self.parts[index - 1].selected:
                    self.parts.move(index, index - 1)
                    moved = True
        else:
            for index in range(len(self.parts) - 2, -1, -1):
                if self.parts[index].selected and not self.parts[index + 1].selected:
                    self.parts.move(index, index + 1)
                    moved = True
        self._clear_selection_cursor()
        return moved

    def select_part(self, index: int, mode: SelectionMode) -> bool:
        """Select a row using replace, toggle, or anchored range semantics."""
        if not 0 <= index < len(self.parts):
            return False
        anchor = self.selection_anchor
        previous_selection = [part.selected for part in self.parts]
        self.active_index = index
        for part, was_selected in zip(self.parts, previous_selection, strict=True):
            part.selected = was_selected

        if mode in {"RANGE", "ADD_RANGE"} and 0 <= anchor < len(self.parts):
            if mode == "RANGE":
                for part in self.parts:
                    part.selected = False
            first, last = sorted((anchor, index))
            for selected_index in range(first, last + 1):
                self.parts[selected_index].selected = True
            self.selection_anchor = anchor
            return True

        if mode == "TOGGLE":
            self.parts[index].selected = not self.parts[index].selected
        else:
            for part in self.parts:
                part.selected = False
            self.parts[index].selected = True
        self.selection_anchor = index
        return True

    def _clear_selection_cursor(self) -> None:
        """Clear the active row and range anchor after changing the table."""
        self.selection_anchor = -1
        self.active_index = -1

    def _select_active_part(self, _context: bpy.types.Context) -> None:
        """Mirror native UI-list activation into the saved row selection."""
        index = self.active_index
        if not 0 <= index < len(self.parts):
            return
        for part_index, part in enumerate(self.parts):
            part.selected = part_index == index
        self.selection_anchor = index

    if TYPE_CHECKING:
        use_shared_density: bool
        density_a_g_per_ml: float
        density_b_g_per_ml: float
        ratio_a: float
        ratio_b: float
        parts: bpy_prop_collection_idprop[SiliconeCastingMixturePart]
        selection_anchor: int
        active_index: int
    else:
        use_shared_density: BoolProperty(
            name="Same Density for A and B",
            description="Use part A's density for both parts",
            default=True,
        )
        density_a_g_per_ml: FloatProperty(
            name="Density A (g/mL)",
            default=1.1,
            min=_MIN_DENSITY_G_PER_ML,
            soft_max=5.0,
            precision=3,
        )
        density_b_g_per_ml: FloatProperty(
            name="Density B (g/mL)",
            default=1.1,
            min=_MIN_DENSITY_G_PER_ML,
            soft_max=5.0,
            precision=3,
        )
        ratio_a: FloatProperty(
            name="Ratio A",
            description="Relative weight of part A",
            default=1.0,
            min=_MIN_MIXTURE_RATIO,
            soft_max=100.0,
            precision=3,
        )
        ratio_b: FloatProperty(
            name="Ratio B",
            description="Relative weight of part B",
            default=1.0,
            min=_MIN_MIXTURE_RATIO,
            soft_max=100.0,
            precision=3,
        )
        parts: CollectionProperty(type=SiliconeCastingMixturePart)
        selection_anchor: IntProperty(
            name="Mixture Selection Anchor",
            default=-1,
            min=-1,
            options={"HIDDEN", "SKIP_SAVE"},
        )
        active_index: IntProperty(
            name="Active Mixture Part",
            default=-1,
            min=-1,
            options={"HIDDEN", "SKIP_SAVE"},
            update=_select_active_part,
        )
