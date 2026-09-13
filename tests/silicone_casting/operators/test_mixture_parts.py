"""Row editing and selection for the manually entered mixture table."""

from collections.abc import Iterator

import bpy
import pytest

import silicone_casting
from silicone_casting.ui.mixture import _filter_mixture_parts_by_name


@pytest.fixture(scope="module")
def registered() -> Iterator[None]:
    silicone_casting.register()
    yield
    silicone_casting.unregister()


@pytest.fixture
def settings(registered: None) -> Iterator[bpy.types.PropertyGroup]:
    props = bpy.context.scene.silicone_casting
    props.mixture.parts.clear()
    props.mixture.selection_anchor = -1
    props.mixture.active_index = -1
    props.mixture.use_shared_density = True
    props.mixture.density_a_g_per_ml = 1.1
    props.mixture.density_b_g_per_ml = 1.1
    props.mixture.ratio_a = 1.0
    props.mixture.ratio_b = 1.0
    yield props
    props.mixture.parts.clear()
    props.mixture.selection_anchor = -1
    props.mixture.active_index = -1
    props.mixture.use_shared_density = True
    props.mixture.density_a_g_per_ml = 1.1
    props.mixture.density_b_g_per_ml = 1.1
    props.mixture.ratio_a = 1.0
    props.mixture.ratio_b = 1.0


def _add_parts(props: bpy.types.PropertyGroup, *names: str) -> None:
    for name in names:
        part = props.mixture.parts.add()
        part.part_name = name


def _selected_indices(props: bpy.types.PropertyGroup) -> list[int]:
    return [index for index, part in enumerate(props.mixture.parts) if part.selected]


class TestAddAndRemove:
    def test_add_creates_the_documented_default_row(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        result = bpy.ops.silicone_casting.add_mixture_part()

        assert result == {"FINISHED"}
        assert len(settings.mixture.parts) == 1
        part = settings.mixture.parts[0]
        assert part.enabled
        assert not part.selected
        assert part.part_name == "Part"
        assert part.volume_ml == 0.0

    def test_remove_deletes_every_selected_row(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        _add_parts(settings, "A", "B", "C", "D")
        settings.mixture.parts[1].selected = True
        settings.mixture.parts[3].selected = True
        settings.mixture.selection_anchor = 3

        result = bpy.ops.silicone_casting.remove_mixture_parts()

        assert result == {"FINISHED"}
        assert [part.part_name for part in settings.mixture.parts] == ["A", "C"]
        assert settings.mixture.selection_anchor == -1
        assert settings.mixture.active_index == -1


class TestMove:
    def test_up_moves_each_selected_block_one_position(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        _add_parts(settings, "A", "B", "C", "D", "E")
        settings.mixture.parts[1].selected = True
        settings.mixture.parts[3].selected = True

        result = bpy.ops.silicone_casting.move_mixture_parts(direction="UP")

        assert result == {"FINISHED"}
        assert [part.part_name for part in settings.mixture.parts] == [
            "B",
            "A",
            "D",
            "C",
            "E",
        ]
        assert _selected_indices(settings) == [0, 2]
        assert settings.mixture.selection_anchor == -1
        assert settings.mixture.active_index == -1

    def test_down_moves_each_selected_block_one_position(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        _add_parts(settings, "A", "B", "C", "D", "E")
        settings.mixture.parts[1].selected = True
        settings.mixture.parts[3].selected = True

        result = bpy.ops.silicone_casting.move_mixture_parts(direction="DOWN")

        assert result == {"FINISHED"}
        assert [part.part_name for part in settings.mixture.parts] == [
            "A",
            "C",
            "B",
            "E",
            "D",
        ]
        assert _selected_indices(settings) == [2, 4]
        assert settings.mixture.active_index == -1


class TestSelection:
    def test_plain_selection_replaces_the_selection_and_sets_the_anchor(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        _add_parts(settings, "A", "B", "C")
        settings.mixture.parts[0].selected = True

        result = bpy.ops.silicone_casting.select_mixture_part(index=1, mode="REPLACE")

        assert result == {"FINISHED"}
        assert _selected_indices(settings) == [1]
        assert settings.mixture.selection_anchor == 1
        assert settings.mixture.active_index == 1

    def test_ctrl_mode_toggles_only_the_clicked_row(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        _add_parts(settings, "A", "B", "C")
        settings.mixture.parts[0].selected = True

        bpy.ops.silicone_casting.select_mixture_part(index=2, mode="TOGGLE")
        bpy.ops.silicone_casting.select_mixture_part(index=0, mode="TOGGLE")

        assert _selected_indices(settings) == [2]
        assert settings.mixture.selection_anchor == 0
        assert settings.mixture.active_index == 0

    def test_shift_mode_replaces_with_the_anchor_to_click_range(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        _add_parts(settings, "A", "B", "C", "D", "E")
        bpy.ops.silicone_casting.select_mixture_part(index=1, mode="REPLACE")
        settings.mixture.parts[4].selected = True

        result = bpy.ops.silicone_casting.select_mixture_part(index=3, mode="RANGE")

        assert result == {"FINISHED"}
        assert _selected_indices(settings) == [1, 2, 3]
        assert settings.mixture.selection_anchor == 1
        assert settings.mixture.active_index == 3

    def test_ctrl_shift_mode_adds_the_range_to_the_existing_selection(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        _add_parts(settings, "A", "B", "C", "D", "E")
        bpy.ops.silicone_casting.select_mixture_part(index=1, mode="REPLACE")
        settings.mixture.parts[4].selected = True

        result = bpy.ops.silicone_casting.select_mixture_part(index=3, mode="ADD_RANGE")

        assert result == {"FINISHED"}
        assert _selected_indices(settings) == [1, 2, 3, 4]
        assert settings.mixture.selection_anchor == 1
        assert settings.mixture.active_index == 3

    def test_shift_without_an_anchor_falls_back_to_single_selection(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        _add_parts(settings, "A", "B", "C")
        settings.mixture.parts[0].selected = True

        bpy.ops.silicone_casting.select_mixture_part(index=2, mode="RANGE")

        assert _selected_indices(settings) == [2]
        assert settings.mixture.selection_anchor == 2

    def test_native_list_activation_replaces_the_saved_selection(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        _add_parts(settings, "A", "B", "C")
        settings.mixture.parts[0].selected = True
        settings.mixture.parts[2].selected = True

        settings.mixture.active_index = 1

        assert _selected_indices(settings) == [1]
        assert settings.mixture.selection_anchor == 1


class TestTotals:
    def test_shared_density_uses_a_while_retaining_the_b_value(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        settings.mixture.density_a_g_per_ml = 2.0
        settings.mixture.density_b_g_per_ml = 1.0
        settings.mixture.ratio_a = 1.0
        settings.mixture.ratio_b = 1.0
        settings.mixture.use_shared_density = True

        shared = settings.mixture.breakdown(100.0)
        settings.mixture.use_shared_density = False
        individual = settings.mixture.breakdown(100.0)

        assert shared.a_volume_ml == pytest.approx(50.0)
        assert shared.b_volume_ml == pytest.approx(50.0)
        assert individual.a_volume_ml == pytest.approx(100.0 / 3.0)
        assert individual.b_volume_ml == pytest.approx(200.0 / 3.0)
        assert settings.mixture.density_b_g_per_ml == pytest.approx(1.0)

    def test_disabled_rows_are_excluded_from_total_and_selected_subtotal(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        _add_parts(settings, "Enabled", "Disabled", "Unselected")
        volumes = (10.0, 20.0, 30.0)
        for part, volume in zip(settings.mixture.parts, volumes, strict=True):
            part.volume_ml = volume
        settings.mixture.parts[0].selected = True
        settings.mixture.parts[1].selected = True
        settings.mixture.parts[1].enabled = False

        assert settings.mixture.total_volume() == pytest.approx(40.0)
        assert settings.mixture.total_volume(selected_only=True) == pytest.approx(10.0)


class TestNameFilter:
    def test_part_names_are_matched_case_insensitively_by_substring(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        _add_parts(settings, "Main Body", "LID", "Body Support")

        flags = _filter_mixture_parts_by_name(
            "body",
            1,
            settings.mixture.parts,
        )

        assert flags == [1, 0, 1]
