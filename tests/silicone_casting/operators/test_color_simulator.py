"""Named color profiles, live material previews, and material assignment."""

from collections.abc import Iterator

import bpy
import pytest

import silicone_casting
from silicone_casting.core import format_hex_color, linear_rgb_to_hsl, parse_hex_color
from silicone_casting.operators.color_simulator import (
    _MATERIAL_PREFIX,
    _SHADER_NODE_NAME,
)


@pytest.fixture(scope="module")
def registered() -> Iterator[None]:
    silicone_casting.register()
    yield
    silicone_casting.unregister()


@pytest.fixture
def settings(registered: None) -> Iterator[bpy.types.PropertyGroup]:
    props = bpy.context.scene.silicone_casting
    props.color_profiles.clear()
    props.color_profile_active_index = -1
    props.mixture_parts.clear()
    yield props
    props.color_profiles.clear()
    props.color_profile_active_index = -1
    props.mixture_parts.clear()
    for material in tuple(bpy.data.materials):
        if material.name.startswith(_MATERIAL_PREFIX) and material.users == 0:
            bpy.data.materials.remove(material)


def _add_profile(settings: bpy.types.PropertyGroup) -> bpy.types.PropertyGroup:
    result = bpy.ops.silicone_casting.add_color_profile()
    assert result == {"FINISHED"}
    return settings.color_profiles[settings.color_profile_active_index]


class TestNamedProfiles:
    def test_profiles_have_independent_names_inputs_and_materials(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        warm = _add_profile(settings)
        warm.profile_name = "Warm Clear"
        warm.base_color = (1.0, 0.8, 0.5)

        cool = _add_profile(settings)
        cool.profile_name = "Cool"
        cool.base_color = (0.5, 0.7, 1.0)

        assert [profile.profile_name for profile in settings.color_profiles] == [
            "Warm Clear",
            "Cool",
        ]
        assert warm.preview_material != cool.preview_material
        assert tuple(warm.preview_material.diffuse_color[:3]) == pytest.approx(
            (1.0, 0.8, 0.5)
        )
        assert tuple(cool.preview_material.diffuse_color[:3]) == pytest.approx(
            (0.5, 0.7, 1.0)
        )

    def test_removing_a_profile_keeps_its_material_assigned_to_a_mesh(
        self,
        settings: bpy.types.PropertyGroup,
        cube_object: bpy.types.Object,
    ) -> None:
        profile = _add_profile(settings)
        material = profile.preview_material
        for obj in bpy.context.selected_objects or ():
            obj.select_set(False)
        cube_object.select_set(True)
        bpy.context.view_layer.objects.active = cube_object
        bpy.ops.silicone_casting.apply_color_material()

        result = bpy.ops.silicone_casting.remove_color_profile()

        assert result == {"FINISHED"}
        assert len(settings.color_profiles) == 0
        assert cube_object.active_material == material
        assert material.name in bpy.data.materials


class TestColorants:
    def test_add_creates_a_zero_dose_float_colorant(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        profile = _add_profile(settings)

        result = bpy.ops.silicone_casting.add_colorant()

        assert result == {"FINISHED"}
        colorant = profile.colorants[0]
        assert colorant.enabled
        assert colorant.colorant_name == "Colorant"
        assert colorant.calibration_hue_degrees == pytest.approx(0.0)
        assert colorant.calibration_lightness_percent == pytest.approx(50.0)
        assert tuple(colorant.calibration_color) == pytest.approx((1.0, 0.0, 0.0))
        assert colorant.calibration_drops_per_ml == pytest.approx(1.0)
        assert colorant.drops == pytest.approx(0.0)
        drops = colorant.bl_rna.properties["drops"]
        assert drops.type == "FLOAT"
        assert drops.step == 100

    def test_picker_color_is_previewed_and_normalized_to_maximum_saturation(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        profile = _add_profile(settings)
        bpy.ops.silicone_casting.add_colorant()
        colorant = profile.colorants[0]
        picked = parse_hex_color("#804060")
        _picked_hue, _picked_saturation, picked_lightness = linear_rgb_to_hsl(picked)

        colorant.calibration_color = picked

        hue, saturation, lightness = linear_rgb_to_hsl(
            tuple(colorant.calibration_color)
        )
        assert hue == pytest.approx(colorant.calibration_hue_degrees)
        assert saturation == pytest.approx(1.0)
        assert lightness == pytest.approx(picked_lightness)
        assert colorant.calibration_lightness_percent == pytest.approx(
            picked_lightness * 100.0
        )

    def test_hex_input_updates_hsl_and_the_color_preview(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        profile = _add_profile(settings)
        bpy.ops.silicone_casting.add_colorant()
        colorant = profile.colorants[0]

        colorant.calibration_hex = "#804000"

        assert colorant.calibration_hex == "#804000"
        assert format_hex_color(tuple(colorant.calibration_color)) == "#804000"
        assert colorant.calibration_hue_degrees == pytest.approx(30.0)
        assert colorant.calibration_lightness_percent == pytest.approx(
            25.098039,
            abs=1e-6,
        )

    def test_invalid_hex_input_keeps_the_previous_color(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        profile = _add_profile(settings)
        bpy.ops.silicone_casting.add_colorant()
        colorant = profile.colorants[0]
        before = tuple(colorant.calibration_color)

        colorant.calibration_hex = "not-a-color"

        assert tuple(colorant.calibration_color) == pytest.approx(before)
        assert colorant.calibration_hex == "#FF0000"

    def test_changing_drops_updates_only_the_owning_profile_material(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        first = _add_profile(settings)
        first.base_volume_ml = 1.0
        bpy.ops.silicone_casting.add_colorant()
        first_colorant = first.colorants[0]
        first_colorant.calibration_hue_degrees = 240.0
        first_colorant.calibration_lightness_percent = 50.0

        second = _add_profile(settings)
        second_before = tuple(second.preview_material.diffuse_color[:3])

        first_colorant.drops = 1.0

        assert tuple(first.preview_material.diffuse_color[:3]) == pytest.approx(
            (0.0, 0.0, 1.0),
            abs=1e-4,
        )
        assert tuple(second.preview_material.diffuse_color[:3]) == pytest.approx(
            second_before
        )

    def test_removing_the_active_colorant_restores_the_base_appearance(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        profile = _add_profile(settings)
        profile.base_volume_ml = 1.0
        profile.transparency = 0.8
        bpy.ops.silicone_casting.add_colorant()
        colorant = profile.colorants[0]
        colorant.calibration_hue_degrees = 240.0
        colorant.calibration_lightness_percent = 50.0
        colorant.drops = 1.0

        result = bpy.ops.silicone_casting.remove_colorant()

        shader = profile.preview_material.node_tree.nodes[_SHADER_NODE_NAME]
        assert result == {"FINISHED"}
        assert len(profile.colorants) == 0
        assert profile.colorant_active_index == -1
        assert tuple(profile.result_color) == pytest.approx((1.0, 1.0, 1.0))
        assert tuple(profile.preview_material.diffuse_color[:3]) == pytest.approx(
            (1.0, 1.0, 1.0)
        )
        assert shader.inputs["Transmission Weight"].default_value == pytest.approx(0.8)

    def test_all_dyes_reduce_transmission_and_white_also_lightens_the_color(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        profile = _add_profile(settings)
        profile.base_volume_ml = 1.0
        profile.transparency = 0.8
        bpy.ops.silicone_casting.add_colorant()
        blue = profile.colorants[0]
        blue.calibration_hue_degrees = 240.0
        blue.calibration_lightness_percent = 50.0
        blue.drops = 1.0

        shader = profile.preview_material.node_tree.nodes[_SHADER_NODE_NAME]

        assert tuple(profile.result_color) == pytest.approx(
            (0.0, 0.0, 1.0),
            abs=1e-4,
        )
        assert shader.inputs["Transmission Weight"].default_value == pytest.approx(0.0)

        bpy.ops.silicone_casting.add_colorant()
        white = profile.colorants[1]
        white.calibration_hue_degrees = 30.0
        white.calibration_lightness_percent = 100.0
        white.drops = 0.5

        shader = profile.preview_material.node_tree.nodes[_SHADER_NODE_NAME]

        assert shader.inputs["Transmission Weight"].default_value == pytest.approx(0.0)
        assert shader.inputs["Subsurface Weight"].default_value == pytest.approx(0.0)
        assert tuple(profile.result_color) == pytest.approx(
            (0.036822, 0.107334, 1.0),
            abs=1e-6,
        )


class TestMixtureVolumeCopy:
    def test_only_enabled_mixture_rows_are_copied(
        self, settings: bpy.types.PropertyGroup
    ) -> None:
        profile = _add_profile(settings)
        included = settings.mixture_parts.add()
        included.volume_ml = 40.0
        excluded = settings.mixture_parts.add()
        excluded.volume_ml = 60.0
        excluded.enabled = False

        result = bpy.ops.silicone_casting.copy_mixture_volume_to_coloring()

        assert result == {"FINISHED"}
        assert profile.base_volume_ml == pytest.approx(40.0)


class TestMaterialApplication:
    def test_active_material_slots_are_replaced_on_all_selected_meshes(
        self,
        settings: bpy.types.PropertyGroup,
        cube_object: bpy.types.Object,
        make_object,
    ) -> None:
        profile = _add_profile(settings)
        other_mesh = bpy.data.meshes.new("OtherColorMesh")
        other = make_object(other_mesh, "OtherColorObject")
        previous = bpy.data.materials.new("PreviousMaterial")
        other_mesh.materials.append(previous)
        for obj in bpy.context.selected_objects or ():
            obj.select_set(False)
        cube_object.select_set(True)
        other.select_set(True)
        bpy.context.view_layer.objects.active = cube_object

        result = bpy.ops.silicone_casting.apply_color_material()

        assert result == {"FINISHED"}
        assert cube_object.active_material == profile.preview_material
        assert other.active_material == profile.preview_material
        bpy.data.materials.remove(previous)


class TestVolumeScaling:
    def test_volume_scales_enabled_and_disabled_drops_without_changing_appearance(
        self, settings
    ):
        profile = _add_profile(settings)
        dye = profile.colorants.add()
        dye.drops = 12.5
        disabled = profile.colorants.add()
        disabled.enabled = False
        disabled.drops = 0.25
        before = tuple(profile.result_color)
        profile.base_volume_ml = 250
        assert [c.drops for c in profile.colorants] == pytest.approx([31.25, 0.625])
        assert tuple(profile.result_color) == pytest.approx(before)
        assert tuple(profile.preview_material.diffuse_color[:3]) == pytest.approx(
            before
        )
        profile.base_volume_ml = 50
        assert [c.drops for c in profile.colorants] == pytest.approx([6.25, 0.125])

    def test_mixture_total_scales_drops_from_existing_saved_volume(self, settings):
        profile = _add_profile(settings)
        profile["base_volume_ml"] = 40.0
        profile.colorants.add().drops = 2.5
        settings.mixture_parts.add().volume_ml = 10
        bpy.ops.silicone_casting.copy_mixture_volume_to_coloring()
        assert profile.colorants[0].drops == pytest.approx(0.625)
