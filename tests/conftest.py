"""Shared fixtures.

Tests run against the real ``bpy`` wheel from PyPI, so ``bmesh`` and the
data API behave exactly as they do inside Blender. Nothing here mocks
``bpy``. Mesh construction goes through :mod:`tests._helpers`, which owns
the ``bmesh`` import (see the note at the top of that module).
"""

from collections.abc import Callable, Iterator

import bpy
import pytest
from _helpers import make_cube_mesh

#: Edge length of the cube used across the geometry tests.
CUBE_SIZE = 2.0

#: Signature of the :func:`make_object` factory: ``(mesh, name) -> object``.
type MakeObject = Callable[..., bpy.types.Object]


@pytest.fixture
def cube_mesh() -> Iterator[bpy.types.Mesh]:
    """A closed 2x2x2 cube mesh datablock, spanning -1..1 on every axis."""
    mesh = make_cube_mesh(CUBE_SIZE, "TestCube")
    yield mesh
    bpy.data.meshes.remove(mesh)


@pytest.fixture
def empty_mesh() -> Iterator[bpy.types.Mesh]:
    """A mesh datablock with no geometry at all."""
    mesh = bpy.data.meshes.new("TestEmpty")
    yield mesh
    bpy.data.meshes.remove(mesh)


@pytest.fixture
def make_object() -> Iterator[MakeObject]:
    """Factory for mesh objects linked into the scene collection.

    Anything that goes through the depsgraph (``obj.evaluated_get``)
    needs its object to be in the view layer, so these objects are
    linked rather than left floating in ``bpy.data``.

    The factory takes ownership of the mesh it is handed: do not pass a
    datablock that another fixture also removes. Teardown reads
    ``obj.data`` at the end instead of remembering the mesh it started
    with, because baking a modifier swaps in a new datablock and deletes
    the old one.
    """
    created: list[bpy.types.Object] = []

    def make(mesh: bpy.types.Mesh, name: str = "TestObject") -> bpy.types.Object:
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        created.append(obj)
        return obj

    yield make

    for obj in created:
        mesh = obj.data
        bpy.data.objects.remove(obj)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


@pytest.fixture
def cube_object(make_object: MakeObject) -> bpy.types.Object:
    """A scene-linked object holding a closed 2x2x2 cube mesh."""
    return make_object(make_cube_mesh(CUBE_SIZE, "TestCube"), "TestCube")
