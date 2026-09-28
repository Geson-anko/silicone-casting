"""Executable spec for the clipboard operator behind the result row.

Source of truth: ``memory/specs/volume_measurement.md`` §5.5, acceptance
criteria AC-50 -- AC-55.

The operator copies whatever string it is handed; it knows nothing about
volumes, which is why it is named ``copy_value`` and why it takes a single
``StringProperty`` (§5.5).

**The clipboard contents must not be asserted here** (MUST NOT, §9.5 note /
L-8): in a background run ``window_manager.clipboard`` accepts the
assignment but always reads back as an empty string, so such a test would
verify nothing. That the pasted text is exactly the displayed number is
covered by the manual check AC-76; that it is the *same* string as the one
on screen is a structural property of ``draw`` (FR-48, review item §10.4).
"""

from collections.abc import Iterator

import bpy
import pytest

import silicone_casting
from silicone_casting.operators.copy_value import SILCAST_OT_copy_value

#: A value in the shape the panel produces: two decimals, no unit, no commas.
DISPLAYED_VALUE = "8.00"


@pytest.fixture(scope="module")
def registered() -> Iterator[None]:
    """The add-on registered, so ``bpy.ops`` and the operator's RNA exist."""
    silicone_casting.register()
    yield
    silicone_casting.unregister()


@pytest.fixture
def nothing_selected(registered: None) -> None:
    """Deselect the startup scene, which ships a selected ``Cube`` (§5.11)."""
    for existing in bpy.context.scene.objects:
        existing.select_set(False)


class TestCopyingAValue:
    def test_copying_a_displayed_value_finishes(self, registered: None) -> None:
        # AC-50
        result = bpy.ops.silicone_casting.copy_value(value=DISPLAYED_VALUE)

        assert result == {"FINISHED"}

    def test_copying_does_not_depend_on_the_selection(
        self, nothing_selected: None
    ) -> None:
        # §5.5: writing to the clipboard depends on neither the selection nor
        # the mode, so the operator defines no `poll`. With nothing selected
        # at all, a `poll` would make this call raise instead of finishing.
        result = bpy.ops.silicone_casting.copy_value(value=DISPLAYED_VALUE)

        assert result == {"FINISHED"}


class TestPublicSurface:
    def test_the_operator_takes_the_value_to_copy_as_a_property(
        self, registered: None
    ) -> None:
        # AC-55 / FR-47: the panel hands the string over by assigning to the
        # `OperatorProperties` that `layout.operator()` returns, so the
        # property has to exist on the registered operator.
        #
        # Read through `bpy.ops`, not through the class: `SILCAST_OT_*.bl_rna`
        # resolves to Blender's own `Operator` struct (bl_idname, bl_options,
        # ...) and never lists the operator's declared properties, so
        # asserting on it would fail no matter what the operator declares.
        properties = bpy.ops.silicone_casting.copy_value.get_rna_type().properties

        assert "value" in properties

    def test_copying_pushes_no_undo_step(self) -> None:
        # AC-53 / FR-49: the operator changes nothing in the scene, so an
        # undo step here would swallow the user's previous modelling action
        # (AC-81). Semantic invariant, not a pin of the literal set.
        assert "UNDO" not in SILCAST_OT_copy_value.bl_options

    def test_the_operator_carries_a_tooltip(self) -> None:
        # AC-54 / FR-52: the button's text is a bare number, so the tooltip
        # is the only thing that tells the user clicking it copies the value.
        assert SILCAST_OT_copy_value.bl_description != ""

    @pytest.mark.api_contract
    def test_the_operator_keeps_its_idname(self) -> None:
        # Contract pin, not a behaviour test: AC-52 fixes the name the panel
        # and any future result row address this operator by (NFR-4).
        assert SILCAST_OT_copy_value.bl_idname == "silicone_casting.copy_value"
