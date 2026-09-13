"""Operator behaviour for separating selected mesh objects by loose parts."""

from collections.abc import Iterator

import bpy
import pytest

import silicone_casting
from silicone_casting.operators import SILCAST_OT_separate_loose_parts

PART_VERTICES = [
    (0.0, 0.0, 0.0),
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (3.0, 0.0, 0.0),
    (4.0, 0.0, 0.0),
    (3.0, 1.0, 0.0),
]
PART_FACES = [(0, 1, 2), (3, 4, 5)]
SECOND_SOURCE_VERTICES = [
    (0.0, 0.0, 0.0),
    (1.0, 0.0, 0.0),
    (1.0, 1.0, 0.0),
    (0.0, 1.0, 0.0),
]
SECOND_SOURCE_FACES = [(0, 1, 2, 3)]


@pytest.fixture(scope="module")
def registered() -> Iterator[None]:
    silicone_casting.register()
    yield
    silicone_casting.unregister()


@pytest.fixture
def loose_object(registered: None) -> Iterator[bpy.types.Object]:
    for existing in bpy.context.scene.objects:
        existing.select_set(False)
    bpy.context.view_layer.objects.active = None
    existing_objects = set(bpy.data.objects.keys())
    existing_meshes = set(bpy.data.meshes.keys())
    existing_collections = set(bpy.data.collections.keys())

    mesh = bpy.data.meshes.new("LooseTrianglesMesh")
    mesh.from_pydata(PART_VERTICES, [], PART_FACES)
    mesh.update()
    obj = bpy.data.objects.new("LooseTriangles", mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    yield obj

    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for created in tuple(bpy.data.objects):
        if created.name not in existing_objects:
            bpy.data.objects.remove(created)
    for created in tuple(bpy.data.meshes):
        if created.name not in existing_meshes and created.users == 0:
            bpy.data.meshes.remove(created)
    for created in tuple(bpy.data.collections):
        if created.name not in existing_collections:
            bpy.data.collections.remove(created)


def test_the_button_is_available_for_a_selected_mesh(
    loose_object: bpy.types.Object,
) -> None:
    assert SILCAST_OT_separate_loose_parts.poll(bpy.context)


def test_the_button_is_disabled_with_an_empty_selection(
    loose_object: bpy.types.Object,
) -> None:
    loose_object.select_set(False)

    assert not SILCAST_OT_separate_loose_parts.poll(bpy.context)


def test_the_button_is_disabled_when_only_a_non_mesh_is_selected(
    loose_object: bpy.types.Object,
) -> None:
    loose_object.select_set(False)
    empty = bpy.data.objects.new("SelectedEmpty", None)
    bpy.context.scene.collection.objects.link(empty)
    empty.select_set(True)

    assert not SILCAST_OT_separate_loose_parts.poll(bpy.context)


def test_the_button_is_disabled_outside_object_mode(
    loose_object: bpy.types.Object,
) -> None:
    bpy.ops.object.mode_set(mode="EDIT")

    assert not SILCAST_OT_separate_loose_parts.poll(bpy.context)


def test_applied_parts_are_flat_in_source_collections_and_the_source_is_hidden(
    loose_object: bpy.types.Object,
) -> None:
    source_mesh = loose_object.data
    source_collections = set(loose_object.users_collection)
    collection_names = set(bpy.data.collections.keys())
    solidify = loose_object.modifiers.new("Hidden Solidify", "SOLIDIFY")
    solidify.thickness = 0.25
    solidify.show_viewport = False

    result = bpy.ops.silicone_casting.separate_loose_parts()

    assert result == {"FINISHED"}
    assert loose_object.data == source_mesh
    assert len(loose_object.data.vertices) == 6
    assert len(loose_object.data.polygons) == 2
    assert len(loose_object.modifiers) == 1
    assert not solidify.show_viewport
    assert loose_object.hide_get()

    assert set(bpy.data.collections.keys()) == collection_names
    parts = list(bpy.context.selected_objects)
    assert len(parts) == 2
    assert all(set(part.users_collection) == source_collections for part in parts)
    assert all(len(part.modifiers) == 0 for part in parts)
    assert all(len(part.data.vertices) == 6 for part in parts)
    assert all(len(part.data.polygons) == 5 for part in parts)
    assert set(bpy.context.selected_objects) == set(parts)
    assert bpy.context.active_object in parts


def test_selected_meshes_are_processed_in_context_order_while_non_meshes_are_ignored(
    loose_object: bpy.types.Object,
) -> None:
    empty = bpy.data.objects.new("SelectedEmpty", None)
    bpy.context.scene.collection.objects.link(empty)
    empty.select_set(True)

    second_mesh = bpy.data.meshes.new("AlphabeticallyEarlierMesh")
    second_mesh.from_pydata(SECOND_SOURCE_VERTICES, [], SECOND_SOURCE_FACES)
    second_mesh.update()
    second_source = bpy.data.objects.new("AlphabeticallyEarlier", second_mesh)
    bpy.context.scene.collection.objects.link(second_source)
    second_source.select_set(True)

    assert list(bpy.context.selected_objects) == [loose_object, empty, second_source]

    result = bpy.ops.silicone_casting.separate_loose_parts()

    assert result == {"FINISHED"}
    assert loose_object.hide_get()
    assert second_source.hide_get()
    assert not empty.hide_get()
    assert empty.select_get()
    assert bpy.context.active_object is not None
    assert len(bpy.context.active_object.data.vertices) == 3


@pytest.fixture
def materials() -> Iterator[tuple[bpy.types.Material, ...]]:
    created = tuple(
        bpy.data.materials.new(name)
        for name in ("Mesh Color", "Object Color", "Second Face Color")
    )
    yield created
    for material in created:
        bpy.data.materials.remove(material)


def test_separated_parts_keep_object_material_overrides_and_face_assignments(
    loose_object: bpy.types.Object,
    materials: tuple[bpy.types.Material, ...],
) -> None:
    base, override, second = materials
    loose_object.data.materials.append(base)
    loose_object.data.materials.append(second)
    loose_object.material_slots[0].link = "OBJECT"
    loose_object.material_slots[0].material = override
    loose_object.data.polygons[1].material_index = 1

    result = bpy.ops.silicone_casting.separate_loose_parts()

    assert result == {"FINISHED"}
    parts = sorted(
        bpy.context.selected_objects,
        key=lambda part: min(vertex.co.x for vertex in part.data.vertices),
    )
    assert len(parts) == 2
    assert (
        parts[0].material_slots[parts[0].data.polygons[0].material_index].material
        == override
    )
    assert (
        parts[1].material_slots[parts[1].data.polygons[0].material_index].material
        == second
    )
    assert loose_object.material_slots[0].link == "OBJECT"
    assert loose_object.material_slots[0].material == override
    assert list(loose_object.data.materials) == [base, second]


def test_an_empty_object_material_override_stays_empty_on_separated_parts(
    loose_object: bpy.types.Object,
    materials: tuple[bpy.types.Material, ...],
) -> None:
    loose_object.data.materials.append(materials[0])
    loose_object.material_slots[0].link = "OBJECT"
    loose_object.material_slots[0].material = None

    bpy.ops.silicone_casting.separate_loose_parts()

    assert len(bpy.context.selected_objects) == 2
    assert all(
        part.material_slots[0].material is None for part in bpy.context.selected_objects
    )


@pytest.mark.api_contract
def test_the_operator_keeps_its_public_idname(registered: None) -> None:
    assert (
        SILCAST_OT_separate_loose_parts.bl_idname
        == "silicone_casting.separate_loose_parts"
    )
