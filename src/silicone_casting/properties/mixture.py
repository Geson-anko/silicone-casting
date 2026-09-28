"""Saved silicone mixture settings, calculated amounts, and row selection."""

from typing import TYPE_CHECKING, Final, Literal

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

# Densities and ratios are divisors in MixtureBreakdown, so the RNA inputs stay
# strictly positive; 0.001 is the smallest value the three-digit fields show.
_MIN_DENSITY_G_PER_ML: Final = 0.001
_MIN_MIXTURE_RATIO: Final = 0.001
# Sentinel for "no active row" and "no range anchor".
_NO_ROW: Final = -1


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
        """Split a volume into A and B using the saved density mode and ratio.

        Args:
            volume_ml: Total mixed silicone volume in millilitres.

        Returns:
            The per-part volumes and weights. With a shared density, part A's
            density is used for both parts and the saved B density is ignored.
        """
        density_b = (
            self.density_a_g_per_ml
            if self.use_shared_density
            else self.density_b_g_per_ml
        )
        return MixtureBreakdown.from_volume(
            volume_ml, self.density_a_g_per_ml, density_b, self.ratio_a, self.ratio_b
        )

    def total_volume(self, *, selected_only: bool = False) -> float:
        """Sum the volumes of enabled parts.

        Args:
            selected_only: Count only rows that are also selected.

        Returns:
            The summed volume in millilitres.
        """
        return sum(
            part.volume_ml
            for part in self.parts
            if part.enabled and (not selected_only or part.selected)
        )

    def has_selected_parts(self) -> bool:
        """Return whether any row is selected."""
        return any(part.selected for part in self.parts)

    def add_part(self) -> SiliconeCastingMixturePart:
        """Append a default zero-volume part without selecting it."""
        part = self.parts.add()
        self.clear_selection_cursor()
        return part

    def remove_selected_parts(self) -> None:
        """Remove selected parts while keeping the order of the other rows."""
        # Walk backwards so removals do not shift the indices still to visit.
        for index in range(len(self.parts) - 1, -1, -1):
            if self.parts[index].selected:
                self.parts.remove(index)
        self.clear_selection_cursor()

    def move_selected_parts(self, direction: MoveDirection) -> bool:
        """Move every selected row one step, keeping their order.

        A selected row only swaps with an unselected neighbour, so a block of
        adjacent selected rows moves as one and a block at the edge stays put.

        Args:
            direction: Whether rows move towards the top or the bottom.

        Returns:
            True if at least one row moved.
        """
        step = -1 if direction == "UP" else 1
        # Visit rows from the side they move towards, so a moved row is not
        # visited again in its new position.
        indices = (
            range(1, len(self.parts))
            if direction == "UP"
            else range(len(self.parts) - 2, -1, -1)
        )
        moved = False
        for index in indices:
            neighbour = index + step
            if self.parts[index].selected and not self.parts[neighbour].selected:
                self.parts.move(index, neighbour)
                moved = True
        self.clear_selection_cursor()
        return moved

    def select_part(self, index: int, mode: SelectionMode) -> bool:
        """Select a row with replace, toggle, or anchored range semantics.

        ``RANGE`` and ``ADD_RANGE`` extend from the previous anchor and keep it;
        without a valid anchor they behave like ``REPLACE``. The other modes
        make the clicked row the new anchor.

        Args:
            index: Row to click.
            mode: How the click combines with the current selection.

        Returns:
            False if ``index`` is not a row, otherwise True.
        """
        if not self._is_row(index):
            return False
        anchor = self.selection_anchor
        self._activate_keeping_selection(index)

        if mode in {"RANGE", "ADD_RANGE"} and self._is_row(anchor):
            if mode == "RANGE":
                self._deselect_all()
            self._select_range(anchor, index)
            self.selection_anchor = anchor
            return True

        if mode == "TOGGLE":
            self.parts[index].selected = not self.parts[index].selected
        else:
            self._deselect_all()
            self.parts[index].selected = True
        self.selection_anchor = index
        return True

    def clear_selection_cursor(self) -> None:
        """Clear the active row and range anchor, keeping selection."""
        self.selection_anchor = _NO_ROW
        self.active_index = _NO_ROW

    def _is_row(self, index: int) -> bool:
        return 0 <= index < len(self.parts)

    def _deselect_all(self) -> None:
        for part in self.parts:
            part.selected = False

    def _select_range(self, first: int, last: int) -> None:
        """Select every row between two indices inclusive, in either order."""
        low, high = sorted((first, last))
        for index in range(low, high + 1):
            self.parts[index].selected = True

    def _activate_keeping_selection(self, index: int) -> None:
        """Highlight a row without the replace-selection side effect.

        Assigning ``active_index`` runs ``_select_active_part``, which models a
        plain click on the native list, so the prior selection is restored.
        """
        previous_selection = [part.selected for part in self.parts]
        self.active_index = index
        for part, was_selected in zip(self.parts, previous_selection, strict=True):
            part.selected = was_selected

    def _select_active_part(self, _context: bpy.types.Context) -> None:
        """Mirror native UI-list activation into the saved row selection."""
        index = self.active_index
        if not self._is_row(index):
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
