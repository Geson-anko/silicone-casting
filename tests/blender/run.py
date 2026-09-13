"""Tier-2 integration checks, run inside a real Blender.

Invoked by ``just blender-test`` as::

    blender --background --python tests/blender/run.py

This runs *after* ``extension install-file``, so it verifies the parts the
``bpy`` wheel cannot: that the built zip installs, that Blender resolves
the add-on under its extension module path, and that the operators behave
identically there. It deliberately has **no third-party dependencies** --
not even pytest -- so that it needs nothing installed into Blender's own
Python on any of the three CI platforms. It also imports nothing from
``tests/``, which is not on Blender's path.

Failures raise ``AssertionError``; the exit code is set explicitly at the
end because Blender swallows tracebacks from ``--python`` scripts.
"""

import struct
import sys
import tempfile
import traceback
from pathlib import Path

import addon_utils
import bpy

# Blender exposes user-repository extensions under this module path.
ADDON_MODULE = "bl_ext.user_default.silicone_casting"

# Mirrors silicone_casting.core.MODIFIER_NAME, which tier 1 pins as public
# API. Spelled out here because the add-on is imported by Blender, not by
# this script.
MODIFIER_NAME = "Silicone Casting Solidify"

CUBE_SIZE = 2.0
THICKNESS_MM = 3.0

# THICKNESS_MM in Blender units, with the default scene scale of 1 unit = 1 m.
THICKNESS = 0.003

# A 2x2x2 cube solidified outwards: the original 8 vertices plus 8 on the
# outer shell, still 12 quads. Half the extent grows by the wall thickness.
EXPECTED_VERTEX_COUNT = 16
EXPECTED_FACE_COUNT = 12
EXPECTED_EXTENT = CUBE_SIZE / 2 + THICKNESS
TOLERANCE = 1e-5
COLOR_TOLERANCE = 2e-4

# A 2 cm cube for the volume checks: 0.02 BU on a side with the default scene
# scale of 1 BU = 1 m, which is 8 mL.
MEASURED_CUBE_SIZE = 0.02
EXPECTED_VOLUME_ML = 8.0
# Mesh coordinates and the scene's FloatProperty are both float32, so the
# volume lands within about 1e-5 relative of the analytic value.
VOLUME_TOLERANCE = 1e-4

# A value in the shape the panel produces: two decimals, no unit, no commas.
DISPLAYED_VALUE = "8.00"

# STL export checks use a 2x2 plane, a one-unit Solidify modifier, and the
# operator's fixed 1000x scale. The exported bounds must therefore span 2000
# on X/Y and 1000 on Z.
STL_PLANE_HALF_SIZE = 1.0
STL_SOLIDIFY_THICKNESS = 1.0
STL_EXPORT_SCALE = 1000.0
STL_FAR_OBJECT_X = 10.0
STL_TOLERANCE = 1e-4

LOOSE_PART_VERTICES = [
    (0.0, 0.0, 0.0),
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (3.0, 0.0, 0.0),
    (4.0, 0.0, 0.0),
    (3.0, 1.0, 0.0),
]
LOOSE_PART_FACES = [(0, 1, 2), (3, 4, 5)]

_HALF = MEASURED_CUBE_SIZE / 2.0
# A cube with its top face left off: the four edges around the hole are
# boundary edges, so this mesh has no defined volume.
OPEN_CUBE_VERTICES = [
    (-_HALF, -_HALF, -_HALF),
    (_HALF, -_HALF, -_HALF),
    (_HALF, _HALF, -_HALF),
    (-_HALF, _HALF, -_HALF),
    (-_HALF, -_HALF, _HALF),
    (_HALF, -_HALF, _HALF),
    (_HALF, _HALF, _HALF),
    (-_HALF, _HALF, _HALF),
]
OPEN_CUBE_FACES = [
    (0, 1, 2, 3),
    (0, 4, 5, 1),
    (1, 5, 6, 2),
    (2, 6, 7, 3),
    (3, 7, 4, 0),
]


def check_addon_is_enabled() -> None:
    """The installed extension must be importable and enabled."""
    enabled = {module.__name__ for module in addon_utils.modules() if module}
    assert (
        ADDON_MODULE in sys.modules or ADDON_MODULE in enabled
    ), f"{ADDON_MODULE} was not enabled; installed add-ons: {sorted(enabled)}"
    # `dir` lists the operators Blender actually resolved; `hasattr` on a
    # `bpy.ops` namespace is always true, so it would prove nothing.
    operators = dir(bpy.ops.silicone_casting)
    for name in (
        "solidify",
        "apply_solidify",
        "measure_volume",
        "copy_value",
        "export_stl",
        "add_boolean",
        "add_surface_cut",
        "draw_surface_cut",
        "draw_air_vents",
        "edit_cutting_surface",
        "separate_loose_parts",
        "inherit_shape",
        "add_mixture_part",
        "remove_mixture_parts",
        "move_mixture_parts",
        "select_mixture_part",
        "add_color_profile",
        "remove_color_profile",
        "add_colorant",
        "remove_colorant",
        "copy_mixture_volume_to_coloring",
        "apply_color_material",
        "export_recipes",
        "import_recipes",
    ):
        assert (
            name in operators
        ), f"operator {name} is missing; silicone_casting has {sorted(operators)}"


def check_scene_properties() -> None:
    """The scene must carry the add-on's settings after registration."""
    settings = bpy.context.scene.silicone_casting
    assert settings is not None, "scene settings are missing"
    names = set(settings.bl_rna.properties.keys())
    for name in (
        "solidify_thickness_mm",
        "solidify_flip",
        "solidify_even_thickness",
        "volume_ml",
        "volume_measured",
        "boolean_operand",
        "boolean_solver",
        "surface_cut_thickness_mm",
        "surface_cut_margin_mm",
        "surface_cut_input_mode",
        "mixture",
        "color_profiles",
        "color_profile_active_index",
    ):
        assert name in names, f"{name} is missing; scene settings have {sorted(names)}"
    mixture_names = set(settings.mixture.bl_rna.properties.keys())
    assert {
        "use_shared_density",
        "density_a_g_per_ml",
        "density_b_g_per_ml",
        "ratio_a",
        "ratio_b",
        "parts",
        "selection_anchor",
        "active_index",
    } <= mixture_names


def check_mixture_part_operations() -> None:
    """The installed add-on must add, select, move, and remove rows."""
    settings = bpy.context.scene.silicone_casting
    settings.mixture.parts.clear()
    for name in ("A", "B", "C", "D"):
        result = bpy.ops.silicone_casting.add_mixture_part()
        assert result == {"FINISHED"}, f"add_mixture_part returned {result}"
        settings.mixture.parts[-1].part_name = name

    bpy.ops.silicone_casting.select_mixture_part(index=1, mode="REPLACE")
    bpy.ops.silicone_casting.select_mixture_part(index=3, mode="TOGGLE")
    result = bpy.ops.silicone_casting.move_mixture_parts(direction="UP")
    assert result == {"FINISHED"}, f"move_mixture_parts returned {result}"
    assert [part.part_name for part in settings.mixture.parts] == [
        "B",
        "A",
        "D",
        "C",
    ]

    result = bpy.ops.silicone_casting.remove_mixture_parts()
    assert result == {"FINISHED"}, f"remove_mixture_parts returned {result}"
    assert [part.part_name for part in settings.mixture.parts] == ["A", "C"]
    assert settings.mixture.selection_anchor == -1


def check_named_color_profiles_update_and_apply_independently() -> None:
    """Each recipe must own one live material that can be assigned to
    meshes."""
    settings = bpy.context.scene.silicone_casting
    settings.color_profiles.clear()
    settings.color_profile_active_index = -1

    result = bpy.ops.silicone_casting.add_color_profile()
    assert result == {"FINISHED"}, f"add_color_profile returned {result}"
    warm = settings.color_profiles[0]
    warm.profile_name = "Warm"
    warm.base_volume_ml = 1.0
    warm.base_color = (1.0, 0.8, 0.5)
    result = bpy.ops.silicone_casting.add_colorant()
    assert result == {"FINISHED"}, f"add_colorant returned {result}"
    warm.colorants[0].calibration_hue_degrees = 30.0
    warm.colorants[0].calibration_lightness_percent = 25.0
    warm.colorants[0].calibration_hex = "#804000"
    assert warm.colorants[0].calibration_hex == "#804000"
    assert abs(warm.colorants[0].calibration_hue_degrees - 30.0) <= TOLERANCE
    warm.colorants[0].drops = 1.0

    result = bpy.ops.silicone_casting.add_color_profile()
    assert result == {"FINISHED"}, f"second add_color_profile returned {result}"
    cool = settings.color_profiles[1]
    cool.profile_name = "Cool"
    cool.base_color = (0.5, 0.7, 1.0)
    assert warm.preview_material != cool.preview_material
    assert all(
        abs(actual - expected) <= COLOR_TOLERANCE
        for actual, expected in zip(
            warm.preview_material.diffuse_color[:3],
            (0.215861, 0.051269, 0.0),
            strict=True,
        )
    )

    _deselect_everything()
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    cube = bpy.context.active_object
    assert cube is not None, "primitive_cube_add did not leave an active object"
    result = bpy.ops.silicone_casting.apply_color_material()
    assert result == {"FINISHED"}, f"apply_color_material returned {result}"
    assert cube.active_material == cool.preview_material


def _prepare_saved_mixture_settings() -> None:
    """Populate independent mixture rows and color profiles before saving."""
    settings = bpy.context.scene.silicone_casting
    settings.mixture.parts.clear()
    settings.mixture.use_shared_density = False
    settings.mixture.density_a_g_per_ml = 1.5
    settings.mixture.density_b_g_per_ml = 1.0
    settings.mixture.ratio_a = 3.0
    settings.mixture.ratio_b = 1.0
    settings.color_profiles.clear()
    settings.color_profile_active_index = -1

    bpy.ops.silicone_casting.add_color_profile()
    clear = settings.color_profiles[0]
    clear.profile_name = "Clear Yellow"
    clear.base_volume_ml = 125.0
    clear.base_color = (1.0, 0.9, 0.7)
    clear.transparency = 0.9
    bpy.ops.silicone_casting.add_colorant()
    amber = clear.colorants[0]
    amber.colorant_name = "Amber"
    amber.calibration_hue_degrees = 30.0
    amber.calibration_lightness_percent = 25.0
    amber.calibration_drops_per_ml = 2.0
    amber.drops = 0.5

    bpy.ops.silicone_casting.add_color_profile()
    opaque = settings.color_profiles[1]
    opaque.profile_name = "Opaque White"
    opaque.transparency = 0.8
    bpy.ops.silicone_casting.add_colorant()
    blue = opaque.colorants[0]
    blue.colorant_name = "Blue"
    blue.calibration_hue_degrees = 240.0
    blue.calibration_lightness_percent = 50.0
    blue.drops = 100.0
    bpy.ops.silicone_casting.add_colorant()
    white = opaque.colorants[1]
    white.colorant_name = "White"
    white.calibration_hue_degrees = 30.0
    white.calibration_lightness_percent = 100.0
    white.drops = 50.0

    body = settings.mixture.parts.add()
    body.enabled = True
    body.selected = False
    body.part_name = "Body"
    body.volume_ml = 60.0

    lid = settings.mixture.parts.add()
    lid.enabled = False
    lid.selected = True
    lid.part_name = "Lid"
    lid.volume_ml = 30.0
    settings.mixture.selection_anchor = 1
    settings.mixture.active_index = 1


def _assert_loaded_mixture_inputs(loaded: bpy.types.PropertyGroup) -> None:
    """Verify saved values and the reset of transient row selection after
    loading."""
    assert not loaded.mixture.use_shared_density
    assert abs(loaded.mixture.density_a_g_per_ml - 1.5) <= TOLERANCE
    assert abs(loaded.mixture.density_b_g_per_ml - 1.0) <= TOLERANCE
    assert abs(loaded.mixture.ratio_a - 3.0) <= TOLERANCE
    assert abs(loaded.mixture.ratio_b - 1.0) <= TOLERANCE
    assert [part.part_name for part in loaded.mixture.parts] == ["Body", "Lid"]
    assert [part.enabled for part in loaded.mixture.parts] == [True, False]
    assert [part.selected for part in loaded.mixture.parts] == [False, True]
    assert [part.volume_ml for part in loaded.mixture.parts] == [60.0, 30.0]
    assert loaded.mixture.selection_anchor == -1
    assert loaded.mixture.active_index == -1


def _assert_loaded_color_profiles(loaded: bpy.types.PropertyGroup) -> None:
    """Verify saved colorants, independent materials, and rebuilt preview
    colors."""
    assert [profile.profile_name for profile in loaded.color_profiles] == [
        "Clear Yellow",
        "Opaque White",
    ]
    loaded_clear = loaded.color_profiles[0]
    loaded_opaque = loaded.color_profiles[1]
    assert abs(loaded_clear.base_volume_ml - 125.0) <= TOLERANCE
    assert all(
        abs(actual - expected) <= TOLERANCE
        for actual, expected in zip(
            loaded_clear.base_color,
            (1.0, 0.9, 0.7),
            strict=True,
        )
    )
    assert abs(loaded_clear.transparency - 0.9) <= TOLERANCE
    assert len(loaded_clear.colorants) == 1
    loaded_amber = loaded_clear.colorants[0]
    assert loaded_amber.colorant_name == "Amber"
    assert abs(loaded_amber.calibration_hue_degrees - 30.0) <= TOLERANCE
    assert abs(loaded_amber.calibration_lightness_percent - 25.0) <= TOLERANCE
    assert abs(loaded_amber.calibration_drops_per_ml - 2.0) <= TOLERANCE
    assert abs(loaded_amber.drops - 0.5) <= TOLERANCE
    assert abs(loaded_opaque.transparency - 0.8) <= TOLERANCE
    assert len(loaded_opaque.colorants) == 2
    loaded_blue = loaded_opaque.colorants[0]
    loaded_white = loaded_opaque.colorants[1]
    assert loaded_blue.colorant_name == "Blue"
    assert abs(loaded_blue.calibration_hue_degrees - 240.0) <= TOLERANCE
    assert abs(loaded_blue.calibration_lightness_percent - 50.0) <= TOLERANCE
    assert loaded_white.colorant_name == "White"
    assert abs(loaded_white.calibration_hue_degrees - 30.0) <= TOLERANCE
    assert abs(loaded_white.calibration_lightness_percent - 100.0) <= TOLERANCE
    shader = loaded_opaque.preview_material.node_tree.nodes["Silicone Casting Shader"]
    assert abs(shader.inputs["Transmission Weight"].default_value) <= TOLERANCE
    assert abs(shader.inputs["Subsurface Weight"].default_value) <= TOLERANCE
    assert all(
        abs(actual - expected) <= TOLERANCE
        for actual, expected in zip(
            loaded_opaque.preview_material.diffuse_color,
            (0.036822, 0.107334, 1.0, 1.0),
            strict=True,
        )
    )
    assert loaded_clear.preview_material != loaded_opaque.preview_material
    assert loaded.color_profile_active_index == 1
    assert loaded_clear.colorant_active_index == -1


def _check_reloaded_recipe_round_trip(
    loaded: bpy.types.PropertyGroup, path: Path
) -> None:
    """Scale a restored dye dose and round-trip it through recipe JSON."""
    loaded_clear = loaded.color_profiles[0]
    loaded_amber = loaded_clear.colorants[0]
    # The first volume edit after reloading must scale saved dye doses.
    loaded_clear.base_volume_ml *= 2
    assert abs(loaded_amber.drops - 1.0) <= TOLERANCE
    recipe_path = str(path.with_suffix(".json"))
    result = bpy.ops.silicone_casting.export_recipes(
        filepath=recipe_path, kind="COLORS"
    )
    assert result == {"FINISHED"}
    result = bpy.ops.silicone_casting.import_recipes(
        filepath=recipe_path, kind="COLORS"
    )
    assert result == {"FINISHED"}
    assert len(loaded.color_profiles) == 4
    loaded_clear = loaded.color_profiles[0]
    imported = loaded.color_profiles[2]
    assert abs(imported.base_volume_ml - loaded_clear.base_volume_ml) <= TOLERANCE
    assert abs(imported.colorants[0].drops - 1.0) <= TOLERANCE
    assert imported.preview_material != loaded_clear.preview_material


def check_mixture_settings_survive_save_and_reload() -> None:
    """Saved calculator and color-profile inputs must survive a .blend round-
    trip."""
    _prepare_saved_mixture_settings()

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "mixture-round-trip.blend"
        result = bpy.ops.wm.save_as_mainfile(filepath=str(path))
        assert result == {"FINISHED"}, f"save_as_mainfile returned {result}"
        result = bpy.ops.wm.open_mainfile(filepath=str(path))
        assert result == {"FINISHED"}, f"open_mainfile returned {result}"

        loaded = bpy.context.scene.silicone_casting
        _assert_loaded_mixture_inputs(loaded)
        _assert_loaded_color_profiles(loaded)
        _check_reloaded_recipe_round_trip(loaded, path)


def check_solidify_then_apply_gives_a_double_walled_cube() -> None:
    """Both operators must produce the geometry tier 1 asserts.

    A 2x2x2 cube walled 3 mm outwards becomes two shells: 16 vertices, 12
    faces, reaching 1.003 on every axis. The extent depends on Even
    Thickness being on -- without it the corners would only reach
    1 + 0.003/sqrt(3).
    """
    for existing in bpy.context.scene.objects:
        existing.select_set(False)

    bpy.ops.mesh.primitive_cube_add(size=CUBE_SIZE, location=(0.0, 0.0, 0.0))
    cube = bpy.context.active_object
    assert cube is not None, "primitive_cube_add did not leave an active object"
    cube.select_set(True)

    bpy.context.scene.unit_settings.scale_length = 1.0
    settings = bpy.context.scene.silicone_casting
    settings.solidify_thickness_mm = THICKNESS_MM
    settings.solidify_flip = False
    settings.solidify_even_thickness = True

    result = bpy.ops.silicone_casting.solidify()
    assert result == {"FINISHED"}, f"solidify returned {result}"
    stack = [modifier.name for modifier in cube.modifiers]
    assert MODIFIER_NAME in stack, f"{MODIFIER_NAME!r} not added; stack is {stack}"

    result = bpy.ops.silicone_casting.apply_solidify()
    assert result == {"FINISHED"}, f"apply_solidify returned {result}"
    stack = [modifier.name for modifier in cube.modifiers]
    assert MODIFIER_NAME not in stack, f"{MODIFIER_NAME!r} survived apply; got {stack}"

    mesh = cube.data
    assert (
        len(mesh.vertices) == EXPECTED_VERTEX_COUNT
    ), f"{len(mesh.vertices)} vertices, expected {EXPECTED_VERTEX_COUNT}"
    assert (
        len(mesh.polygons) == EXPECTED_FACE_COUNT
    ), f"{len(mesh.polygons)} faces, expected {EXPECTED_FACE_COUNT}"

    for axis, label in enumerate("xyz"):
        coordinates = [vertex.co[axis] for vertex in mesh.vertices]
        low, high = min(coordinates), max(coordinates)
        assert (
            abs(low + EXPECTED_EXTENT) <= TOLERANCE
        ), f"{label} min is {low}, expected {-EXPECTED_EXTENT} (tol {TOLERANCE})"
        assert (
            abs(high - EXPECTED_EXTENT) <= TOLERANCE
        ), f"{label} max is {high}, expected {EXPECTED_EXTENT} (tol {TOLERANCE})"


def check_boolean_modifier_uses_the_requested_inputs() -> None:
    """The installed operator must configure one modifier on the active
    mesh."""
    _deselect_everything()
    bpy.ops.mesh.primitive_cube_add(size=CUBE_SIZE, location=(0.0, 0.0, 0.0))
    target = bpy.context.active_object
    assert target is not None, "primitive_cube_add did not create the target"

    bpy.ops.mesh.primitive_cube_add(size=CUBE_SIZE, location=(1.0, 0.0, 0.0))
    operand = bpy.context.active_object
    assert operand is not None, "primitive_cube_add did not create the operand"
    operand.select_set(False)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target

    settings = bpy.context.scene.silicone_casting
    settings.boolean_operand = operand
    settings.boolean_solver = "MANIFOLD"
    result = bpy.ops.silicone_casting.add_boolean(operation="UNION")

    assert result == {"FINISHED"}, f"add_boolean returned {result}"
    boolean_modifiers = [
        modifier for modifier in target.modifiers if modifier.type == "BOOLEAN"
    ]
    assert (
        len(boolean_modifiers) == 1
    ), f"expected one Boolean modifier, got {[m.type for m in target.modifiers]}"
    modifier = boolean_modifiers[0]
    assert modifier.operand_type == "OBJECT"
    assert modifier.object == operand
    assert modifier.operation == "UNION"
    assert modifier.solver == "MANIFOLD"


def check_registration_keys_create_edit_and_delete() -> None:
    """Installed key operators produce paired evaluated solids."""
    import importlib

    from mathutils import Vector

    world_volume = importlib.import_module(f"{ADDON_MODULE}.core.volume").world_volume
    key_models = importlib.import_module(f"{ADDON_MODULE}.operators.key_models")
    scene = bpy.context.scene
    settings = scene.silicone_casting
    old_scale = scene.unit_settings.scale_length
    old_cursor = scene.cursor.location.copy()
    created = []
    try:
        scene.unit_settings.scale_length = 0.001
        _deselect_everything()
        bpy.ops.mesh.primitive_cube_add(size=20, location=(0, 0, -10))
        pin_half = bpy.context.active_object
        created.append(pin_half)
        bpy.ops.mesh.primitive_cube_add(size=20, location=(0, 0, 10))
        socket_half = bpy.context.active_object
        created.append(socket_half)
        socket_half.select_set(False)
        pin_half.select_set(True)
        bpy.context.view_layer.objects.active = pin_half
        settings.key_mate = socket_half
        settings.key_shape = "TAPERED"
        scene.cursor.location = (0, 0, 0)
        first = key_models.KeyPair.create(
            bpy.context,
            key_models.KeySettings.from_context(bpy.context),
            Vector((0, 0, 0)),
            Vector((0, 0, 1)),
        )
        created.extend((first.pin, first.socket))
        depsgraph = bpy.context.evaluated_depsgraph_get()
        assert world_volume(pin_half, depsgraph) > 8000
        assert 0 < world_volume(socket_half, depsgraph) < 8000
        second = key_models.KeyPair.create(
            bpy.context,
            key_models.KeySettings.from_context(bpy.context),
            Vector((5, 0, 0)),
            Vector((0, 0, 1)),
        )
        settings.key_width = 3
        assert bpy.ops.silicone_casting.edit_registration_key() == {"FINISHED"}
        second.move(bpy.context, Vector((5, 3, 0)), Vector((0, 0, 1)))
        assert bpy.ops.silicone_casting.delete_registration_key() == {"FINISHED"}
        assert len(pin_half.modifiers) == len(socket_half.modifiers) == 1
    finally:
        settings.key_mate = None
        for obj in created:
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        scene.unit_settings.scale_length = old_scale
        scene.cursor.location = old_cursor


def check_surface_cut_is_one_integrated_modifier() -> None:
    """One installed modifier must solidify and subtract the surface."""
    _deselect_everything()
    bpy.ops.mesh.primitive_cube_add(size=CUBE_SIZE)
    target = bpy.context.active_object
    assert target is not None, "primitive_cube_add did not create the target"

    mesh = bpy.data.meshes.new("SurfaceCutMesh")
    mesh.from_pydata(
        [
            (-2.0, -2.0, 0.0),
            (2.0, -2.0, 0.0),
            (2.0, 2.0, 0.0),
            (-2.0, 2.0, 0.0),
        ],
        [],
        [(0, 1, 2, 3)],
    )
    surface = bpy.data.objects.new("SurfaceCut", mesh)
    bpy.context.scene.collection.objects.link(surface)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target

    settings = bpy.context.scene.silicone_casting
    settings.boolean_operand = surface
    settings.boolean_solver = "FLOAT"
    settings.surface_cut_thickness_mm = 0.25
    result = bpy.ops.silicone_casting.add_surface_cut()

    assert result == {"FINISHED"}, f"add_surface_cut returned {result}"
    assert len(surface.modifiers) == 0
    assert len(target.modifiers) == 1
    modifier = target.modifiers[0]
    assert modifier.name == "Surface Cut"
    assert modifier.type == "NODES"
    assert modifier.node_group is not None
    interface = modifier.node_group.interface
    assert interface is not None
    cutting_surface = next(
        item for item in interface.items_tree if item.name == "Cutting Surface"
    )
    thickness = next(item for item in interface.items_tree if item.name == "Thickness")
    even_thickness = next(
        item for item in interface.items_tree if item.name == "Even Thickness"
    )
    solver = next(item for item in interface.items_tree if item.name == "Solver")
    assert cutting_surface.default_value == surface
    assert abs(thickness.default_value - 0.00025) <= 1e-9
    assert abs(thickness.min_value - 0.000001) <= 1e-12
    assert not even_thickness.default_value
    assert solver.default_value == "Manifold"
    booleans = [
        node
        for node in modifier.node_group.nodes
        if node.bl_idname == "GeometryNodeMeshBoolean"
    ]
    assert len(booleans) == 2
    assert all(node.operation == "DIFFERENCE" for node in booleans)
    assert {node.solver for node in booleans} == {"MANIFOLD", "EXACT"}

    properties = getattr(modifier, "properties", None)
    if properties is None:
        modifier[even_thickness.identifier] = True
        modifier[solver.identifier] = 1
    else:
        getattr(properties.inputs, even_thickness.identifier).value = True
        getattr(properties.inputs, solver.identifier).value = "Exact"
    target.update_tag(refresh={"DATA"})
    bpy.context.view_layer.update()

    evaluated = target.evaluated_get(bpy.context.evaluated_depsgraph_get())
    evaluated_mesh = bpy.data.meshes.new_from_object(evaluated)
    try:
        assert _loose_part_count(evaluated_mesh) == 2
    finally:
        bpy.data.meshes.remove(evaluated_mesh)


def check_loose_parts_become_separate_objects() -> None:
    """The installed operator must bake parts and preserve its source."""
    _deselect_everything()
    mesh = bpy.data.meshes.new("LoosePartsMesh")
    mesh.from_pydata(LOOSE_PART_VERTICES, [], LOOSE_PART_FACES)
    source = bpy.data.objects.new("LooseParts", mesh)
    bpy.context.scene.collection.objects.link(source)
    source.select_set(True)
    bpy.context.view_layer.objects.active = source
    source_collections = set(source.users_collection)
    collection_names = set(bpy.data.collections.keys())
    solidify = source.modifiers.new("Hidden Solidify", "SOLIDIFY")
    solidify.thickness = 0.25
    solidify.show_viewport = False

    result = bpy.ops.silicone_casting.separate_loose_parts()

    assert result == {"FINISHED"}, f"separate_loose_parts returned {result}"
    assert source.hide_get()
    assert len(source.data.vertices) == 6
    assert len(source.data.polygons) == 2
    assert len(source.modifiers) == 1
    assert not solidify.show_viewport

    assert set(bpy.data.collections.keys()) == collection_names
    parts = list(bpy.context.selected_objects)
    assert len(parts) == 2, f"expected 2 parts, got {[obj.name for obj in parts]}"
    assert all(set(obj.users_collection) == source_collections for obj in parts)
    assert all(len(obj.modifiers) == 0 for obj in parts)
    assert all(len(obj.data.vertices) == 6 for obj in parts)
    assert all(len(obj.data.polygons) == 5 for obj in parts)


def _loose_part_count(mesh: bpy.types.Mesh) -> int:
    """Count vertex-connected components without third-party imports."""
    if len(mesh.vertices) == 0:
        return 0
    neighbors = [set() for _vertex in mesh.vertices]
    for edge in mesh.edges:
        first, second = edge.vertices
        neighbors[first].add(second)
        neighbors[second].add(first)

    seen: set[int] = set()
    parts = 0
    for start in range(len(mesh.vertices)):
        if start in seen:
            continue
        parts += 1
        stack = [start]
        while stack:
            vertex = stack.pop()
            if vertex in seen:
                continue
            seen.add(vertex)
            stack.extend(neighbors[vertex] - seen)
    return parts


def _deselect_everything() -> None:
    """Clear the selection, which the startup file leaves on its cube."""
    for existing in bpy.context.scene.objects:
        existing.select_set(False)


def check_measuring_a_closed_cube_stores_its_millilitres() -> None:
    """Measuring a 2 cm cube must store the 8 ml that tier 1 asserts.

    This is the value the sidebar shows as "8.00", produced by a real
    Blender's own depsgraph and mesh evaluation rather than by the
    wheel.
    """
    _deselect_everything()
    bpy.ops.mesh.primitive_cube_add(size=MEASURED_CUBE_SIZE, location=(0.0, 0.0, 0.0))
    cube = bpy.context.active_object
    assert cube is not None, "primitive_cube_add did not leave an active object"
    cube.select_set(True)
    bpy.context.scene.unit_settings.scale_length = 1.0

    result = bpy.ops.silicone_casting.measure_volume()
    assert result == {"FINISHED"}, f"measure_volume returned {result}"

    settings = bpy.context.scene.silicone_casting
    assert settings.volume_measured, "volume_measured stayed false after a good run"
    difference = abs(settings.volume_ml - EXPECTED_VOLUME_ML)
    assert difference <= VOLUME_TOLERANCE, (
        f"volume_ml is {settings.volume_ml}, expected {EXPECTED_VOLUME_ML} "
        f"(tol {VOLUME_TOLERANCE})"
    )


def check_an_open_mesh_clears_the_stored_measurement() -> None:
    """A selection whose volume is undefined must cancel and store nothing.

    The operator reports an ERROR, which Blender turns into a RuntimeError at
    the ``bpy.ops`` boundary, so the spec's ``{"CANCELLED"}`` surfaces here as
    that exception. ``volume_measured`` is seeded true first: a ``poll``
    failure never reaches ``execute``, so without the seed it could pass this
    check by accident.
    """
    _deselect_everything()
    mesh = bpy.data.meshes.new("OpenCube")
    mesh.from_pydata(OPEN_CUBE_VERTICES, [], OPEN_CUBE_FACES)
    mesh.update()
    open_cube = bpy.data.objects.new("OpenCube", mesh)
    bpy.context.scene.collection.objects.link(open_cube)
    open_cube.select_set(True)

    settings = bpy.context.scene.silicone_casting
    settings.volume_measured = True

    try:
        result = bpy.ops.silicone_casting.measure_volume()
    except RuntimeError as exc:
        cancelled, outcome = True, f"raised {exc}"
    else:
        cancelled, outcome = result == {"CANCELLED"}, f"returned {result}"

    assert cancelled, f"measure_volume {outcome} for a mesh with a hole"
    assert not settings.volume_measured, "the stale result was not cleared"


def check_copying_a_value_finishes() -> None:
    """The clipboard operator must run inside a real Blender too.

    Only the return value is checked. A background Blender's clipboard
    accepts the write but reads back empty, so what actually got copied
    cannot be verified from a script here either -- that is the manual
    check.
    """
    result = bpy.ops.silicone_casting.copy_value(value=DISPLAYED_VALUE)
    assert result == {"FINISHED"}, f"copy_value returned {result}"


def _binary_stl_vertices(path: Path) -> list[tuple[float, float, float]]:
    """Read triangle vertices from Blender's default binary STL output."""
    payload = path.read_bytes()
    triangle_count = struct.unpack_from("<I", payload, 80)[0]
    assert len(payload) == 84 + triangle_count * 50, "malformed binary STL"

    vertices: list[tuple[float, float, float]] = []
    for index in range(triangle_count):
        coordinates = struct.unpack_from("<9f", payload, 84 + index * 50 + 12)
        vertices.extend(
            [
                (coordinates[0], coordinates[1], coordinates[2]),
                (coordinates[3], coordinates[4], coordinates[5]),
                (coordinates[6], coordinates[7], coordinates[8]),
            ]
        )
    return vertices


def check_export_stl_uses_the_fixed_settings() -> None:
    """The installed operator must export selection, modifiers, and 1000x."""
    _deselect_everything()
    vertices = [
        (-STL_PLANE_HALF_SIZE, -STL_PLANE_HALF_SIZE, 0.0),
        (STL_PLANE_HALF_SIZE, -STL_PLANE_HALF_SIZE, 0.0),
        (STL_PLANE_HALF_SIZE, STL_PLANE_HALF_SIZE, 0.0),
        (-STL_PLANE_HALF_SIZE, STL_PLANE_HALF_SIZE, 0.0),
    ]
    faces = [(0, 1, 2, 3)]

    selected_mesh = bpy.data.meshes.new("ExportSelectedMesh")
    selected_mesh.from_pydata(vertices, [], faces)
    selected_mesh.update()
    selected = bpy.data.objects.new("ExportSelected", selected_mesh)
    bpy.context.scene.collection.objects.link(selected)
    selected.select_set(True)
    bpy.context.view_layer.objects.active = selected
    modifier = selected.modifiers.new("Export Solidify", "SOLIDIFY")
    modifier.thickness = STL_SOLIDIFY_THICKNESS
    modifier.offset = 1.0

    unselected_mesh = bpy.data.meshes.new("ExportUnselectedMesh")
    unselected_mesh.from_pydata(vertices, [], faces)
    unselected_mesh.update()
    unselected = bpy.data.objects.new("ExportUnselected", unselected_mesh)
    bpy.context.scene.collection.objects.link(unselected)
    unselected.location.x = STL_FAR_OBJECT_X
    unselected.select_set(False)

    with tempfile.TemporaryDirectory() as directory:
        requested_path = Path(directory) / "ExportSelected"
        result = bpy.ops.silicone_casting.export_stl(filepath=str(requested_path))
        output_path = requested_path.with_suffix(".stl")
        assert result == {"FINISHED"}, f"export_stl returned {result}"
        assert output_path.is_file(), f"STL was not written to {output_path}"

        exported = _binary_stl_vertices(output_path)

    x_coordinates = [vertex[0] for vertex in exported]
    y_coordinates = [vertex[1] for vertex in exported]
    z_coordinates = [vertex[2] for vertex in exported]
    expected_min = -STL_EXPORT_SCALE
    expected_max = STL_EXPORT_SCALE
    assert abs(min(x_coordinates) - expected_min) <= STL_TOLERANCE
    assert abs(max(x_coordinates) - expected_max) <= STL_TOLERANCE
    assert abs(min(y_coordinates) - expected_min) <= STL_TOLERANCE
    assert abs(max(y_coordinates) - expected_max) <= STL_TOLERANCE
    z_extent = max(z_coordinates) - min(z_coordinates)
    assert abs(z_extent - STL_EXPORT_SCALE) <= STL_TOLERANCE
    assert modifier.name in selected.modifiers, "export applied the source modifier"


def check_export_stl_preserves_physical_size_with_custom_scene_units() -> None:
    """A 20 mm cube must stay 20 mm even when distance labels are disabled."""
    _deselect_everything()
    bpy.ops.mesh.primitive_cube_add(size=20.0)
    units = bpy.context.scene.unit_settings
    previous = units.system, units.scale_length
    try:
        units.system = "NONE"
        units.scale_length = 0.001
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "20mm.stl"
            result = bpy.ops.silicone_casting.export_stl(filepath=str(path))
            assert result == {"FINISHED"}, f"export_stl returned {result}"
            vertices = _binary_stl_vertices(path)
        for axis in range(3):
            coordinates = [vertex[axis] for vertex in vertices]
            assert abs(min(coordinates) + 10.0) <= STL_TOLERANCE
            assert abs(max(coordinates) - 10.0) <= STL_TOLERANCE
    finally:
        units.system, units.scale_length = previous


def check_air_vents_cut_both_mold_halves() -> None:
    """The installed extension produces one live shared cutter for two
    halves."""
    from bl_ext.user_default.silicone_casting.core.air_vents import (
        add_air_vent_cutters,
        create_air_vent_mesh,
    )
    from bl_ext.user_default.silicone_casting.core.volume import world_volume
    from mathutils import Vector

    targets = []
    for x in (-1.0, 1.0):
        bpy.ops.mesh.primitive_cube_add(size=2, location=(x, 0, 0))
        targets.append(bpy.context.active_object)
    cutter_mesh = create_air_vent_mesh(
        "Air Vents",
        [[Vector((-3, 0, 0)), Vector((3, 0, 0))]],
        Vector((0, 0, 1)),
        0.4,
    )
    cutter = bpy.data.objects.new("Air Vents", cutter_mesh)
    bpy.context.scene.collection.objects.link(cutter)
    try:
        add_air_vent_cutters(targets, cutter)
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for target in targets:
            assert target.modifiers[-1].object == cutter
            volume = world_volume(target, depsgraph)
            assert volume is not None and 7.7 < volume < 7.8
    finally:
        for obj in [*targets, cutter]:
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.meshes.remove(mesh)


CHECKS = (
    check_addon_is_enabled,
    check_scene_properties,
    check_mixture_part_operations,
    check_named_color_profiles_update_and_apply_independently,
    check_solidify_then_apply_gives_a_double_walled_cube,
    check_boolean_modifier_uses_the_requested_inputs,
    check_registration_keys_create_edit_and_delete,
    check_surface_cut_is_one_integrated_modifier,
    check_air_vents_cut_both_mold_halves,
    check_loose_parts_become_separate_objects,
    check_measuring_a_closed_cube_stores_its_millilitres,
    check_an_open_mesh_clears_the_stored_measurement,
    check_copying_a_value_finishes,
    check_export_stl_uses_the_fixed_settings,
    check_export_stl_preserves_physical_size_with_custom_scene_units,
    # This opens a saved .blend, so it must stay last.
    check_mixture_settings_survive_save_and_reload,
)


def main() -> int:
    """Run every check, printing one line per result.

    Returns an exit code.
    """
    print(f"blender {bpy.app.version_string} -- tier-2 integration checks")
    failures = 0
    for check in CHECKS:
        try:
            check()
        except Exception:
            failures += 1
            print(f"FAIL {check.__name__}")
            traceback.print_exc()
        else:
            print(f"ok   {check.__name__}")
    print(f"{len(CHECKS) - failures}/{len(CHECKS)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
