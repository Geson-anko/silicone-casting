"""Executable spec for the fixed-settings STL export operator.

The tests use Blender's real STL exporter and inspect the written binary file.
Nothing in ``bpy`` is mocked.
"""

import os
import struct
from collections.abc import Callable, Iterator
from pathlib import Path

import bpy
import pytest
from _helpers import make_cube_mesh

import silicone_casting
from silicone_casting.operators.export_stl import (
    _LAST_EXPORT_DIRECTORY_KEY,
    SILCAST_OT_export_stl,
    _default_filepath,
)

PLANE_HALF_SIZE = 1.0
SOLIDIFY_THICKNESS = 1.0
EXPORT_SCALE = 1000.0
FAR_CUBE_LOCATION_X = 10.0

type AddObject = Callable[..., bpy.types.Object]


def _leave_edit_mode() -> None:
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


@pytest.fixture(scope="module")
def registered() -> Iterator[None]:
    silicone_casting.register()
    yield
    silicone_casting.unregister()


@pytest.fixture(autouse=True)
def reset_export_directory(registered: None) -> Iterator[None]:
    """Keep the remembered runtime directory from leaking between tests."""
    window_manager = bpy.context.window_manager
    if _LAST_EXPORT_DIRECTORY_KEY in window_manager:
        del window_manager[_LAST_EXPORT_DIRECTORY_KEY]
    yield
    if _LAST_EXPORT_DIRECTORY_KEY in window_manager:
        del window_manager[_LAST_EXPORT_DIRECTORY_KEY]


@pytest.fixture
def scene_units() -> Iterator[bpy.types.UnitSettings]:
    units = bpy.context.scene.unit_settings
    original = units.system, units.scale_length
    yield units
    units.system, units.scale_length = original


@pytest.fixture
def add_object(registered: None) -> Iterator[AddObject]:
    """Add selected scene objects and clean up their datablocks afterwards."""
    for existing in bpy.context.scene.objects:
        existing.select_set(False)

    created: list[bpy.types.Object] = []

    def add(name: str, data: bpy.types.ID, *, select: bool = True) -> bpy.types.Object:
        obj = bpy.data.objects.new(name, data)
        bpy.context.scene.collection.objects.link(obj)
        obj.select_set(select)
        created.append(obj)
        return obj

    yield add

    _leave_edit_mode()
    datablocks = {(type(obj.data).__name__, obj.data.name): obj.data for obj in created}
    for obj in created:
        bpy.data.objects.remove(obj)
    bpy.data.batch_remove([data for data in datablocks.values() if data.users == 0])


def _read_binary_stl_vertices(path: Path) -> list[tuple[float, float, float]]:
    """Read all triangle vertices from a binary STL file."""
    payload = path.read_bytes()
    triangle_count = struct.unpack_from("<I", payload, 80)[0]
    assert len(payload) == 84 + triangle_count * 50

    vertices: list[tuple[float, float, float]] = []
    for index in range(triangle_count):
        offset = 84 + index * 50 + 12
        coordinates = struct.unpack_from("<9f", payload, offset)
        vertices.extend(
            [
                (coordinates[0], coordinates[1], coordinates[2]),
                (coordinates[3], coordinates[4], coordinates[5]),
                (coordinates[6], coordinates[7], coordinates[8]),
            ]
        )
    return vertices


class TestWhenTheExportButtonIsClickable:
    @pytest.mark.usefixtures("add_object")
    def test_the_button_is_not_clickable_with_an_empty_selection(self) -> None:
        assert not SILCAST_OT_export_stl.poll(bpy.context)

    def test_the_button_is_not_clickable_without_a_selected_mesh(
        self, add_object: AddObject
    ) -> None:
        add_object("Camera", bpy.data.cameras.new("CameraData"))

        assert not SILCAST_OT_export_stl.poll(bpy.context)

    def test_the_button_is_clickable_with_a_selected_mesh(
        self, add_object: AddObject
    ) -> None:
        add_object("Mold", make_cube_mesh(2.0, "MoldMesh"))

        assert SILCAST_OT_export_stl.poll(bpy.context)

    def test_the_button_is_not_clickable_outside_object_mode(
        self, add_object: AddObject
    ) -> None:
        obj = add_object("Mold", make_cube_mesh(2.0, "MoldMesh"))
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")

        assert not SILCAST_OT_export_stl.poll(bpy.context)


class TestExportStlOperator:
    @pytest.mark.parametrize(
        ("system", "metres_per_unit", "side_in_units"),
        [
            ("METRIC", 1.0, 0.02),
            ("METRIC", 0.01, 2.0),
            ("METRIC", 0.001, 20.0),
            ("IMPERIAL", 0.0254, 0.02 / 0.0254),
            ("NONE", 0.001, 20.0),
        ],
    )
    def test_export_keeps_a_twenty_millimetre_cube_at_its_physical_size(
        self,
        add_object: AddObject,
        tmp_path: Path,
        scene_units: bpy.types.UnitSettings,
        system: str,
        metres_per_unit: float,
        side_in_units: float,
    ) -> None:
        scene_units.system = system
        scene_units.scale_length = metres_per_unit
        source = add_object("20 mm Mold", make_cube_mesh(side_in_units, "MoldMesh"))
        bpy.context.view_layer.objects.active = source
        path = tmp_path / "20mm.stl"

        assert bpy.ops.silicone_casting.export_stl(filepath=str(path)) == {"FINISHED"}

        vertices = _read_binary_stl_vertices(path)
        for axis in range(3):
            coordinates = [vertex[axis] for vertex in vertices]
            assert min(coordinates) == pytest.approx(-10.0, abs=1e-4)
            assert max(coordinates) == pytest.approx(10.0, abs=1e-4)
        assert scene_units.system == system
        assert scene_units.scale_length == pytest.approx(metres_per_unit)

    def test_selected_non_mesh_objects_are_ignored_during_export(
        self, add_object: AddObject, tmp_path: Path
    ) -> None:
        add_object("Mold", make_cube_mesh(2.0, "MoldMesh"))
        camera = add_object("Camera", bpy.data.cameras.new("CameraData"))
        bpy.context.view_layer.objects.active = camera

        requested_path = tmp_path / "MoldWithCameraSelected"
        result = bpy.ops.silicone_casting.export_stl(filepath=str(requested_path))

        output_path = requested_path.with_suffix(".stl")
        assert result == {"FINISHED"}
        assert output_path.is_file()
        assert _read_binary_stl_vertices(output_path)

    def test_the_default_filename_comes_from_the_active_object(
        self, add_object: AddObject
    ) -> None:
        add_object("Other", make_cube_mesh(2.0, "OtherMesh"))
        active = add_object("Upper Mold", make_cube_mesh(2.0, "UpperMoldMesh"))
        bpy.context.view_layer.objects.active = active

        filepath = _default_filepath(bpy.context)

        assert os.path.basename(filepath) == "Upper Mold.stl"

    def test_the_initial_directory_comes_from_the_blend_file(
        self, add_object: AddObject
    ) -> None:
        active = add_object("Mold", make_cube_mesh(2.0, "MoldMesh"))
        bpy.context.view_layer.objects.active = active

        filepath = _default_filepath(bpy.context)

        assert os.path.dirname(filepath) == bpy.path.abspath("//")

    def test_the_next_default_directory_is_where_the_previous_export_finished(
        self, add_object: AddObject, tmp_path: Path
    ) -> None:
        active = add_object("Mold", make_cube_mesh(2.0, "MoldMesh"))
        bpy.context.view_layer.objects.active = active
        export_directory = tmp_path / "exports"
        export_directory.mkdir()

        result = bpy.ops.silicone_casting.export_stl(
            filepath=str(export_directory / "First Mold")
        )
        filepath = _default_filepath(bpy.context)

        assert result == {"FINISHED"}
        assert os.path.dirname(filepath) == str(export_directory)
        assert os.path.basename(filepath) == "Mold.stl"

    def test_export_uses_selection_modifiers_and_scale_1000(
        self, add_object: AddObject, tmp_path: Path
    ) -> None:
        plane_mesh = bpy.data.meshes.new("SelectedPlaneMesh")
        plane_mesh.from_pydata(
            [
                (-PLANE_HALF_SIZE, -PLANE_HALF_SIZE, 0.0),
                (PLANE_HALF_SIZE, -PLANE_HALF_SIZE, 0.0),
                (PLANE_HALF_SIZE, PLANE_HALF_SIZE, 0.0),
                (-PLANE_HALF_SIZE, PLANE_HALF_SIZE, 0.0),
            ],
            [],
            [(0, 1, 2, 3)],
        )
        plane_mesh.update()
        selected = add_object("SelectedPlane", plane_mesh)
        modifier = selected.modifiers.new("Test Solidify", "SOLIDIFY")
        modifier.thickness = SOLIDIFY_THICKNESS
        modifier.offset = 1.0
        bpy.context.view_layer.objects.active = selected

        unselected = add_object(
            "UnselectedCube",
            make_cube_mesh(2.0, "UnselectedCubeMesh"),
            select=False,
        )
        unselected.location.x = FAR_CUBE_LOCATION_X

        requested_path = tmp_path / "SelectedPlane"
        result = bpy.ops.silicone_casting.export_stl(filepath=str(requested_path))

        output_path = requested_path.with_suffix(".stl")
        assert result == {"FINISHED"}
        assert output_path.is_file()
        assert modifier.name in selected.modifiers

        vertices = _read_binary_stl_vertices(output_path)
        x_coordinates = [vertex[0] for vertex in vertices]
        y_coordinates = [vertex[1] for vertex in vertices]
        z_coordinates = [vertex[2] for vertex in vertices]
        assert min(x_coordinates) == pytest.approx(-EXPORT_SCALE)
        assert max(x_coordinates) == pytest.approx(EXPORT_SCALE)
        assert min(y_coordinates) == pytest.approx(-EXPORT_SCALE)
        assert max(y_coordinates) == pytest.approx(EXPORT_SCALE)
        assert max(z_coordinates) - min(z_coordinates) == pytest.approx(EXPORT_SCALE)


@pytest.mark.api_contract
def test_export_operator_keeps_its_idname() -> None:
    assert SILCAST_OT_export_stl.bl_idname == "silicone_casting.export_stl"
