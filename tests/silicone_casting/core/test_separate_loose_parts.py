"""Geometry behaviour when one mesh object is separated by loose parts."""

from collections.abc import Iterator

import bpy
import pytest
from _helpers import MeshInvariants, make_cube_mesh

from silicone_casting.core.separate_loose_parts import separate_loose_parts

TETRAHEDRA_VERTICES = [
    (0.0, 0.0, 0.0),
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
    (3.0, 0.0, 0.0),
    (4.0, 0.0, 0.0),
    (3.0, 1.0, 0.0),
    (3.0, 0.0, 1.0),
]
TETRAHEDRA_FACES = [
    (0, 2, 1),
    (0, 1, 3),
    (1, 2, 3),
    (2, 0, 3),
    (4, 6, 5),
    (4, 5, 7),
    (5, 6, 7),
    (6, 4, 7),
]


@pytest.fixture
def clean_scene_data() -> Iterator[None]:
    existing_objects = set(bpy.data.objects.keys())
    existing_meshes = set(bpy.data.meshes.keys())
    yield
    for obj in tuple(bpy.data.objects):
        if obj.name not in existing_objects:
            bpy.data.objects.remove(obj)
    for mesh in tuple(bpy.data.meshes):
        if mesh.name not in existing_meshes and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def _object_with_two_tetrahedra() -> bpy.types.Object:
    mesh = bpy.data.meshes.new("TwoTetrahedra")
    mesh.from_pydata(TETRAHEDRA_VERTICES, [], TETRAHEDRA_FACES)
    mesh.update()
    obj = bpy.data.objects.new("LooseParts", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def test_each_disconnected_component_becomes_one_mesh_object(
    clean_scene_data: None,
) -> None:
    source = _object_with_two_tetrahedra()

    parts = separate_loose_parts(source)

    assert len(parts) == 2
    assert parts[0] == source
    invariants = [MeshInvariants.from_mesh(part.data) for part in parts]
    assert all(item.vertex_count == 4 for item in invariants)
    assert all(item.edge_count == 6 for item in invariants)
    assert all(item.face_count == 4 for item in invariants)
    assert all(item.loose_part_count == 1 for item in invariants)
    assert all(item.is_watertight for item in invariants)
    assert {(item.bbox_min, item.bbox_max) for item in invariants} == {
        ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)),
        ((3.0, 0.0, 0.0), (4.0, 1.0, 1.0)),
    }


def test_new_parts_keep_the_objects_transform_and_collections(
    clean_scene_data: None,
) -> None:
    source = _object_with_two_tetrahedra()
    source.location = (2.0, 3.0, 4.0)
    extra_collection = bpy.data.collections.new("ExtraCollection")
    bpy.context.scene.collection.children.link(extra_collection)
    extra_collection.objects.link(source)

    parts = separate_loose_parts(source)

    expected_matrix = tuple(value for row in source.matrix_world for value in row)
    assert all(
        tuple(value for row in part.matrix_world for value in row) == expected_matrix
        for part in parts
    )
    assert all(
        set(part.users_collection) == {bpy.context.scene.collection, extra_collection}
        for part in parts
    )

    bpy.context.scene.collection.children.unlink(extra_collection)
    bpy.data.collections.remove(extra_collection)


def test_a_mesh_with_one_component_is_left_untouched(
    clean_scene_data: None,
) -> None:
    mesh = make_cube_mesh(2.0, "SingleCube")
    source = bpy.data.objects.new("SinglePart", mesh)
    bpy.context.scene.collection.objects.link(source)

    parts = separate_loose_parts(source)

    assert parts == (source,)
    assert source.data == mesh
