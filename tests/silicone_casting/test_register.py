"""End-to-end path through registration, the scene properties and the
operators.

This is the tier-1 counterpart of ``tests/blender/run.py``: it exercises
the same code against the ``bpy`` wheel, while the tier-2 script
exercises it after a real ``extension install-file``.
"""

from collections.abc import Iterator

import bpy
import pytest

import silicone_casting


@pytest.fixture(scope="module")
def registered() -> Iterator[None]:
    silicone_casting.register()
    yield
    silicone_casting.unregister()


class TestRegistration:
    def test_scene_gains_the_settings_property_group(self, registered: None) -> None:
        assert bpy.context.scene.silicone_casting is not None

    def test_both_solidify_operators_become_callable(self, registered: None) -> None:
        # `dir` lists the operators Blender actually resolved; `hasattr` on
        # a `bpy.ops` namespace is always true, so it would prove nothing.
        operators = dir(bpy.ops.silicone_casting)
        assert "solidify" in operators
        assert "apply_solidify" in operators

    def test_both_measurement_operators_become_callable(self, registered: None) -> None:
        # AC-49 / AC-51 (volume_measurement spec). `dir` for the same reason
        # as above.
        operators = dir(bpy.ops.silicone_casting)
        assert "measure_volume" in operators
        assert "copy_value" in operators

    def test_the_stl_export_operator_becomes_callable(self, registered: None) -> None:
        operators = dir(bpy.ops.silicone_casting)
        assert "export_stl" in operators

    def test_the_boolean_operator_becomes_callable(self, registered: None) -> None:
        operators = dir(bpy.ops.silicone_casting)
        assert "add_boolean" in operators

    def test_both_split_workflow_operators_become_callable(
        self, registered: None
    ) -> None:
        operators = dir(bpy.ops.silicone_casting)
        assert "add_surface_cut" in operators
        assert "separate_loose_parts" in operators

    def test_the_inherit_shape_operator_becomes_callable(
        self, registered: None
    ) -> None:
        operators = dir(bpy.ops.silicone_casting)
        assert "inherit_shape" in operators

    def test_the_mixture_table_operators_become_callable(
        self, registered: None
    ) -> None:
        operators = dir(bpy.ops.silicone_casting)
        for name in (
            "add_mixture_part",
            "remove_mixture_parts",
            "move_mixture_parts",
            "select_mixture_part",
        ):
            assert name in operators

    def test_the_color_simulator_operators_become_callable(
        self, registered: None
    ) -> None:
        operators = dir(bpy.ops.silicone_casting)
        for name in (
            "add_color_profile",
            "remove_color_profile",
            "add_colorant",
            "remove_colorant",
            "copy_mixture_volume_to_coloring",
            "apply_color_material",
        ):
            assert name in operators

    def test_the_sidebar_registers_as_a_parent_with_three_sub_panels(
        self, registered: None
    ) -> None:
        # AC-56 / FR-8: Blender resolves `bl_parent_id` while registering, so
        # a sub-panel registered before SILCAST_PT_main raises RuntimeError
        # and takes the whole add-on down with it. The module fixture is what
        # actually detects that regression; this test names the guarantee and
        # confirms Blender resolved every child.
        types = dir(bpy.types)
        assert "SILCAST_PT_main" in types
        assert "SILCAST_PT_measurement" in types
        assert "SILCAST_PT_mixture_calculator" in types
        assert "SILCAST_PT_processing" in types
        assert "SILCAST_UL_mixture_parts" in types
        assert "SILCAST_PT_coloring" in types
        assert "SILCAST_PT_color_simulator" in types
        assert "SILCAST_UL_color_profiles" in types
        assert "SILCAST_UL_colorants" in types


class TestSolidifySettings:
    @pytest.mark.api_contract
    def test_scene_settings_carry_the_solidify_properties(
        self, registered: None
    ) -> None:
        # Contract pin, not a behaviour test: these names are written into
        # users' .blend files and read back from them (NFR-4).
        properties = bpy.context.scene.silicone_casting.bl_rna.properties
        assert "solidify_thickness_mm" in properties
        assert "solidify_flip" in properties
        assert "solidify_even_thickness" in properties

    def test_even_thickness_is_enabled_by_default(self, registered: None) -> None:
        properties = bpy.context.scene.silicone_casting.bl_rna.properties
        assert properties["solidify_even_thickness"].default

    def test_legacy_thickness_storage_remains_in_millimetres(
        self, registered: None
    ) -> None:
        # Saved values retain their original unit for existing .blend files.
        properties = bpy.context.scene.silicone_casting.bl_rna.properties
        assert properties["solidify_thickness_mm"].unit == "NONE"


class TestMeasurementSettings:
    """Where a measurement is stored (volume_measurement spec §5.7)."""

    @pytest.mark.api_contract
    def test_scene_settings_carry_the_measurement_properties(
        self, registered: None
    ) -> None:
        # Contract pin, not a behaviour test: AC-57 / NFR-4. These two names
        # are written into users' .blend files and read back from them, and
        # the panel addresses them by name.
        properties = bpy.context.scene.silicone_casting.bl_rna.properties
        assert "volume_ml" in properties
        assert "volume_measured" in properties

    def test_the_volume_is_not_declared_as_a_volume_property(
        self, registered: None
    ) -> None:
        # AC-58 / FR-29: unit="VOLUME" would re-display the value in the
        # scene's unit settings, breaking "always shown in mL" (FR-38). Same
        # reasoning as the millimetre thickness above.
        properties = bpy.context.scene.silicone_casting.bl_rna.properties
        assert properties["volume_ml"].unit == "NONE"


class TestBooleanSettings:
    @pytest.mark.api_contract
    def test_scene_settings_carry_the_boolean_properties(
        self, registered: None
    ) -> None:
        properties = bpy.context.scene.silicone_casting.bl_rna.properties
        assert "boolean_operand" in properties
        assert "boolean_solver" in properties

    def test_exact_is_the_default_boolean_solver(self, registered: None) -> None:
        properties = bpy.context.scene.silicone_casting.bl_rna.properties
        assert properties["boolean_solver"].default == "EXACT"

    def test_all_documented_boolean_solvers_are_available(
        self, registered: None
    ) -> None:
        properties = bpy.context.scene.silicone_casting.bl_rna.properties
        identifiers = {
            item.identifier for item in properties["boolean_solver"].enum_items
        }
        assert identifiers == {"MANIFOLD", "EXACT", "FLOAT"}


class TestSurfaceCutSettings:
    @pytest.mark.api_contract
    def test_scene_settings_carry_the_surface_cut_thickness(
        self, registered: None
    ) -> None:
        properties = bpy.context.scene.silicone_casting.bl_rna.properties
        assert "surface_cut_thickness_mm" in properties

    def test_thickness_defaults_to_its_one_micron_minimum(
        self, registered: None
    ) -> None:
        thickness = bpy.context.scene.silicone_casting.bl_rna.properties[
            "surface_cut_thickness_mm"
        ]
        assert thickness.default == pytest.approx(0.001)
        assert thickness.hard_min == pytest.approx(0.001)
        assert thickness.unit == "NONE"


class TestMixtureSettings:
    @pytest.mark.api_contract
    def test_scene_settings_carry_the_mixture_properties(
        self, registered: None
    ) -> None:
        properties = bpy.context.scene.silicone_casting.bl_rna.properties
        for name in (
            "mixture_use_shared_density",
            "mixture_density_a_g_per_ml",
            "mixture_density_b_g_per_ml",
            "mixture_ratio_a",
            "mixture_ratio_b",
            "mixture_parts",
            "mixture_selection_anchor",
            "mixture_active_index",
        ):
            assert name in properties

    @pytest.mark.api_contract
    def test_mixture_rows_carry_the_saved_input_properties(
        self, registered: None
    ) -> None:
        settings = bpy.context.scene.silicone_casting
        settings.mixture_parts.clear()
        part = settings.mixture_parts.add()

        properties = part.bl_rna.properties
        for name in ("enabled", "selected", "part_name", "volume_ml"):
            assert name in properties

        settings.mixture_parts.clear()

    def test_mixture_settings_have_the_documented_defaults(
        self, registered: None
    ) -> None:
        properties = bpy.context.scene.silicone_casting.bl_rna.properties
        assert properties["mixture_use_shared_density"].default is True
        assert properties["mixture_density_a_g_per_ml"].default == pytest.approx(1.1)
        assert properties["mixture_density_b_g_per_ml"].default == pytest.approx(1.1)
        assert properties["mixture_ratio_a"].default == pytest.approx(1.0)
        assert properties["mixture_ratio_b"].default == pytest.approx(1.0)

    def test_density_and_ratio_are_clamped_to_positive_values(
        self, registered: None
    ) -> None:
        settings = bpy.context.scene.silicone_casting
        settings.mixture_density_a_g_per_ml = 0.0
        settings.mixture_density_b_g_per_ml = 0.0
        settings.mixture_ratio_a = 0.0
        settings.mixture_ratio_b = 0.0

        assert settings.mixture_density_a_g_per_ml > 0.0
        assert settings.mixture_density_b_g_per_ml > 0.0
        assert settings.mixture_ratio_a > 0.0
        assert settings.mixture_ratio_b > 0.0

    @pytest.mark.api_contract
    def test_saved_row_inputs_and_transient_selection_state_keep_their_storage_roles(
        self, registered: None
    ) -> None:
        # Contract pin, not a behaviour test: table inputs belong in .blend
        # files, while UI-list navigation state must reset after file load.
        settings = bpy.context.scene.silicone_casting
        settings.mixture_parts.clear()
        part = settings.mixture_parts.add()

        for name in ("enabled", "selected", "part_name", "volume_ml"):
            assert not part.bl_rna.properties[name].is_skip_save

        properties = settings.bl_rna.properties
        assert not properties["mixture_parts"].is_skip_save
        assert properties["mixture_selection_anchor"].is_skip_save
        assert properties["mixture_active_index"].is_skip_save

        settings.mixture_parts.clear()


class TestColorProfileSettings:
    @pytest.mark.api_contract
    def test_scene_settings_carry_named_color_profiles(self, registered: None) -> None:
        properties = bpy.context.scene.silicone_casting.bl_rna.properties
        assert "color_profiles" in properties
        assert "color_profile_active_index" in properties

    @pytest.mark.api_contract
    def test_profiles_and_colorants_carry_the_saved_inputs(
        self, registered: None
    ) -> None:
        settings = bpy.context.scene.silicone_casting
        settings.color_profiles.clear()
        profile = settings.color_profiles.add()
        colorant = profile.colorants.add()

        for name in (
            "profile_name",
            "base_volume_ml",
            "base_color",
            "transparency",
            "cloudiness",
            "result_color",
            "colorants",
            "colorant_active_index",
            "preview_material",
        ):
            assert name in profile.bl_rna.properties
        for name in (
            "enabled",
            "is_opacifier",
            "colorant_name",
            "calibration_color",
            "calibration_hex",
            "calibration_hue_degrees",
            "calibration_lightness_percent",
            "calibration_drops_per_ml",
            "drops",
        ):
            assert name in colorant.bl_rna.properties

        settings.color_profiles.clear()

    def test_colorants_expose_an_editable_color_picker_and_hex_input(
        self, registered: None
    ) -> None:
        settings = bpy.context.scene.silicone_casting
        settings.color_profiles.clear()
        profile = settings.color_profiles.add()
        colorant = profile.colorants.add()

        color = colorant.bl_rna.properties["calibration_color"]
        hex_color = colorant.bl_rna.properties["calibration_hex"]
        assert color.subtype == "COLOR"
        assert not color.is_hidden
        assert hex_color.type == "STRING"

        settings.color_profiles.clear()

    @pytest.mark.api_contract
    def test_profile_and_colorant_numeric_inputs_keep_their_rna_ranges(
        self, registered: None
    ) -> None:
        # Contract pin, not a behaviour test: these RNA constraints protect
        # saved recipes from invalid physical quantities and color channels.
        settings = bpy.context.scene.silicone_casting
        settings.color_profiles.clear()
        profile = settings.color_profiles.add()
        colorant = profile.colorants.add()

        profile_properties = profile.bl_rna.properties
        base_volume = profile_properties["base_volume_ml"]
        transparency = profile_properties["transparency"]
        assert base_volume.type == "FLOAT"
        assert base_volume.default == pytest.approx(100.0)
        assert base_volume.hard_min == pytest.approx(0.001)
        assert transparency.type == "FLOAT"
        assert transparency.default == pytest.approx(1.0)
        assert transparency.hard_min == pytest.approx(0.0)
        assert transparency.hard_max == pytest.approx(1.0)

        colorant_properties = colorant.bl_rna.properties
        calibration_color = colorant_properties["calibration_color"]
        hue = colorant_properties["calibration_hue_degrees"]
        lightness = colorant_properties["calibration_lightness_percent"]
        concentration = colorant_properties["calibration_drops_per_ml"]
        drops = colorant_properties["drops"]
        assert calibration_color.type == "FLOAT"
        assert calibration_color.array_length == 3
        assert calibration_color.hard_min == pytest.approx(0.0)
        assert calibration_color.hard_max == pytest.approx(1.0)
        assert hue.hard_min == pytest.approx(0.0)
        assert hue.hard_max == pytest.approx(360.0)
        assert lightness.hard_min == pytest.approx(0.0)
        assert lightness.hard_max == pytest.approx(100.0)
        assert concentration.hard_min == pytest.approx(0.001)
        assert drops.hard_min == pytest.approx(0.0)

        settings.color_profiles.clear()

    @pytest.mark.api_contract
    def test_saved_color_inputs_and_derived_display_values_keep_their_storage_roles(
        self, registered: None
    ) -> None:
        # Contract pin, not a behaviour test: editable recipes and their
        # material survive .blend saves; derived swatches and list navigation
        # are rebuilt instead of becoming a second source of truth.
        settings = bpy.context.scene.silicone_casting
        settings.color_profiles.clear()
        profile = settings.color_profiles.add()
        colorant = profile.colorants.add()

        scene_properties = settings.bl_rna.properties
        assert not scene_properties["color_profiles"].is_skip_save
        assert not scene_properties["color_profile_active_index"].is_skip_save

        profile_properties = profile.bl_rna.properties
        for name in (
            "profile_name",
            "base_volume_ml",
            "base_color",
            "transparency",
            "colorants",
            "preview_material",
        ):
            assert not profile_properties[name].is_skip_save
        assert profile_properties["result_color"].is_skip_save
        assert profile_properties["colorant_active_index"].is_skip_save

        colorant_properties = colorant.bl_rna.properties
        for name in (
            "enabled",
            "colorant_name",
            "calibration_color",
            "calibration_hue_degrees",
            "calibration_lightness_percent",
            "calibration_drops_per_ml",
            "drops",
        ):
            assert not colorant_properties[name].is_skip_save
        assert colorant_properties["calibration_hex"].is_skip_save

        settings.color_profiles.clear()


@pytest.mark.parametrize(
    "name", ["solidify_thickness", "surface_cut_thickness", "surface_cut_margin"]
)
@pytest.mark.parametrize("scale", [1.0, 0.1, 0.001])
def test_distance_preserves_saved_millimetres_across_scene_scales(
    registered: None, scale: float, name: str
) -> None:
    scene = bpy.data.scenes.new("Distance Units")
    try:
        scene.unit_settings.scale_length = scale
        props = scene.silicone_casting
        setattr(props, name + "_mm", 0.2)
        assert getattr(props, name) == pytest.approx(0.0002 / scale)
        setattr(props, name, 0.0005 / scale)
        assert getattr(props, name + "_mm") == pytest.approx(0.5)
        scene.unit_settings.scale_length = scale * 2
        assert getattr(props, name) == pytest.approx(0.0005 / (scale * 2))
        assert getattr(props, name + "_mm") == pytest.approx(0.5)
    finally:
        bpy.data.scenes.remove(scene)


@pytest.mark.api_contract
@pytest.mark.parametrize(
    "name", ["solidify_thickness", "surface_cut_thickness", "surface_cut_margin"]
)
def test_distance_inputs_declare_native_length_units(
    registered: None, name: str
) -> None:
    # Contract pin: Blender uses this metadata for unit-aware input and display.
    prop = bpy.context.scene.silicone_casting.bl_rna.properties[name]
    assert prop.subtype == "DISTANCE"
    assert prop.unit == "LENGTH"


@pytest.mark.parametrize(
    "name,minimum", [("solidify_thickness", 0.001), ("surface_cut_thickness", 0.001)]
)
def test_distance_input_keeps_the_physical_minimum(
    registered: None, name: str, minimum: float
) -> None:
    scene = bpy.data.scenes.new("Distance Minimum")
    try:
        scene.unit_settings.scale_length = 0.001
        props = scene.silicone_casting
        setattr(props, name, 0.0)
        assert getattr(props, name + "_mm") == pytest.approx(minimum)
    finally:
        bpy.data.scenes.remove(scene)
