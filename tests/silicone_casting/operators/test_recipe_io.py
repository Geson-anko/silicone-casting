"""Recipe exchange preserves usable mixtures and rejects invalid documents."""

import json
from collections.abc import Iterator

import bpy
import pytest

import silicone_casting


@pytest.fixture
def settings() -> Iterator[bpy.types.PropertyGroup]:
    silicone_casting.register()
    scene = bpy.data.scenes.new("Recipe exchange")
    with bpy.context.temp_override(scene=scene):
        yield scene.silicone_casting
    bpy.data.scenes.remove(scene)
    silicone_casting.unregister()


def test_mixture_round_trip_replaces_rows_and_preserves_inputs(settings, tmp_path):
    settings.mixture_use_shared_density = False
    settings.mixture_density_a_g_per_ml = 1.2
    settings.mixture_density_b_g_per_ml = 0.9
    settings.mixture_ratio_a = 10
    settings.mixture_ratio_b = 1
    first = settings.mixture_parts.add()
    first.part_name = "右の型"
    first.volume_ml = 12.5
    first.selected = True
    second = settings.mixture_parts.add()
    second.part_name = "Unused"
    second.enabled = False
    second.volume_ml = 30
    path = str(tmp_path / "mixture.json")
    assert bpy.ops.silicone_casting.export_recipes(filepath=path) == {"FINISHED"}
    settings.mixture_parts.clear()
    settings.mixture_parts.add().part_name = "Replace me"
    settings.mixture_ratio_a = 1
    assert bpy.ops.silicone_casting.import_recipes(filepath=path) == {"FINISHED"}
    assert [p.part_name for p in settings.mixture_parts] == ["右の型", "Unused"]
    assert [p.volume_ml for p in settings.mixture_parts] == [12.5, 30]
    assert settings.mixture_parts[0].selected
    assert not settings.mixture_parts[1].enabled
    assert settings.mixture_ratio_a == 10
    assert settings.mixture_density_b_g_per_ml == pytest.approx(0.9)
    assert not settings.mixture_use_shared_density


def test_colors_append_with_independent_materials_and_exact_doses(settings, tmp_path):
    bpy.ops.silicone_casting.add_color_profile()
    profile = settings.color_profiles[0]
    profile.profile_name = "白と青"
    profile.base_volume_ml = 25
    profile.base_color = (0.8, 0.9, 1)
    profile.transparency = 0.7
    dye = profile.colorants.add()
    dye.calibration_hue_degrees = 210
    dye.calibration_lightness_percent = 100
    dye.calibration_drops_per_ml = 2.5
    dye.drops = 0.75
    dye.enabled = False
    blue = profile.colorants.add()
    blue.calibration_hue_degrees = 240
    blue.calibration_lightness_percent = 40
    blue.drops = 3.5
    before = tuple(profile.result_color)
    original_material = profile.preview_material
    path = str(tmp_path / "colors.json")
    bpy.ops.silicone_casting.export_recipes(filepath=path, kind="COLORS")
    bpy.ops.silicone_casting.import_recipes(filepath=path, kind="COLORS")
    assert len(settings.color_profiles) == 2
    imported = settings.color_profiles[1]
    assert imported.profile_name == "白と青"
    assert imported.base_volume_ml == 25
    assert [c.drops for c in imported.colorants] == [0.75, 3.5]
    assert imported.colorants[0].calibration_hue_degrees == pytest.approx(210)
    assert not imported.colorants[0].enabled
    assert imported.colorants[0].calibration_drops_per_ml == 2.5
    assert tuple(imported.result_color) == pytest.approx(before)
    assert imported.preview_material != original_material
    assert tuple(imported.preview_material.diffuse_color[:3]) == pytest.approx(before)


@pytest.mark.parametrize("invalid", [None, True, -1, "12", float("nan"), float("inf")])
def test_invalid_late_row_does_not_change_existing_mixture(settings, tmp_path, invalid):
    settings.mixture_parts.add().part_name = "Keep me"
    path = tmp_path / "mixture.json"
    bpy.ops.silicone_casting.export_recipes(filepath=str(path))
    doc = json.loads(path.read_text())
    doc["data"]["mixture_ratio_a"] = 4
    doc["data"]["mixture_parts"].append(
        {
            "enabled": True,
            "selected": False,
            "part_name": "Bad",
            "volume_ml": invalid,
        }
    )
    path.write_text(json.dumps(doc))
    with pytest.raises(RuntimeError):
        bpy.ops.silicone_casting.import_recipes(filepath=str(path))
    assert settings.mixture_ratio_a == 1
    assert [p.part_name for p in settings.mixture_parts] == ["Keep me"]


@pytest.mark.parametrize("contents", ["{", "[]", '{"format": "other"}'])
def test_malformed_or_unsupported_document_preserves_profiles(
    settings, tmp_path, contents
):
    settings.color_profiles.add().profile_name = "Keep"
    path = tmp_path / "bad.json"
    path.write_text(contents)
    with pytest.raises(RuntimeError):
        bpy.ops.silicone_casting.import_recipes(filepath=str(path), kind="COLORS")
    assert [p.profile_name for p in settings.color_profiles] == ["Keep"]


def test_export_adds_json_extension_and_reports_io_errors(settings, tmp_path):
    path = tmp_path / "recipe"
    bpy.ops.silicone_casting.export_recipes(filepath=str(path))
    assert path.with_suffix(".json").is_file()
    with pytest.raises(RuntimeError):
        bpy.ops.silicone_casting.export_recipes(
            filepath=str(tmp_path / "missing" / "x")
        )
