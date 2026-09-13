"""Executable spec for the Solidify operators (memory/specs/solidify.md §5.4).

These run against the real ``bpy`` wheel: a real scene, a real selection,
a real modifier stack and a real depsgraph. Nothing here mocks ``bpy``.

The geometry itself is the ``core`` layer's contract and is asserted in
``tests/silicone_casting/core/``; what these tests state is the operator
layer's own job -- which selections make the buttons clickable, which
objects get walked, how the millimetre setting reaches the modifier, and
how a partially failing batch is reported back.
"""

from collections.abc import Callable, Iterator

import bpy
import pytest
from _helpers import make_cube_mesh

import silicone_casting
from silicone_casting.core import MODIFIER_NAME, find_solidify
from silicone_casting.operators import SILCAST_OT_apply_solidify, SILCAST_OT_solidify

#: Edge length of the test cubes: 2x2x2, spanning -1..1 on every axis.
CUBE_SIZE = 2.0

#: Wall thickness the tests ask for, in millimetres (the property's default).
THICKNESS_MM = 3.0

#: THICKNESS_MM in Blender units when 1 BU = 1 m: 3.0 / 1000 / 1.0.
THICKNESS_IN_METRE_SCENE = 0.003

#: A scene where 1 BU = 1 mm, so THICKNESS_MM converts to 3.0 BU unchanged.
MILLIMETRE_SCENE_SCALE = 0.001

#: Vertices of a solidified cube: the original 8 plus 8 on the second shell.
SOLIDIFIED_VERTEX_COUNT = 16

#: Vertices of an untouched cube, i.e. of a mesh the apply left alone.
CUBE_VERTEX_COUNT = 8

#: Signature of the ``add_object`` factory fixture.
type AddObject = Callable[..., bpy.types.Object]


def _leave_edit_mode() -> None:
    """Return to object mode so that fixture teardown can remove objects."""
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


@pytest.fixture(scope="module")
def registered() -> Iterator[None]:
    """The add-on registered, so ``bpy.ops`` and the scene settings exist."""
    silicone_casting.register()
    yield
    silicone_casting.unregister()


@pytest.fixture
def settings(registered: None) -> bpy.types.PropertyGroup:
    """Scene settings reset to the documented defaults (§5.5)."""
    props = bpy.context.scene.silicone_casting
    props.solidify_thickness_mm = THICKNESS_MM
    props.solidify_flip = False
    props.solidify_even_thickness = True
    return props


@pytest.fixture
def add_object(registered: None) -> Iterator[AddObject]:
    """Factory for scene objects, cleaned up when the test ends.

    Everything already in the startup scene is deselected first, so the
    selection the operators see is exactly what the test created. New
    objects are selected unless ``select=False`` is passed, and are given
    a fresh 2x2x2 cube mesh unless a datablock is supplied.

    This is deliberately not ``conftest.make_object``: the operator layer
    reads the *selection*, takes non-mesh objects in its stride, and can
    leave the scene in edit mode, none of which the geometry-level
    factory deals with.
    """
    for existing in bpy.context.scene.objects:
        existing.select_set(False)

    created: list[bpy.types.Object] = []

    def add(
        name: str, data: bpy.types.ID | None = None, *, select: bool = True
    ) -> bpy.types.Object:
        mesh = data if data is not None else make_cube_mesh(CUBE_SIZE, f"{name}Mesh")
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj.select_set(select)
        created.append(obj)
        return obj

    yield add

    _leave_edit_mode()
    # Read the datablocks back only now: an applied object carries a mesh
    # the operator created, not the one the test handed in.
    datablocks = {(type(obj.data).__name__, obj.data.name): obj.data for obj in created}
    for obj in created:
        bpy.data.objects.remove(obj)
    bpy.data.batch_remove([data for data in datablocks.values() if data.users == 0])


@pytest.fixture
def scene_unit_scale() -> Iterator[Callable[[float], None]]:
    """Set ``scene.unit_settings.scale_length``, restoring it afterwards."""
    unit_settings = bpy.context.scene.unit_settings
    original = unit_settings.scale_length

    def set_scale(metres_per_unit: float) -> None:
        unit_settings.scale_length = metres_per_unit

    yield set_scale

    unit_settings.scale_length = original


class TestWhenTheButtonsAreClickable:
    """``poll`` decides whether the sidebar buttons are greyed out."""

    @pytest.mark.usefixtures("add_object")
    def test_neither_operator_polls_with_an_empty_selection(self) -> None:
        # Arrange: the fixture deselects the startup scene; nothing is added.
        assert not SILCAST_OT_solidify.poll(bpy.context)
        assert not SILCAST_OT_apply_solidify.poll(bpy.context)

    def test_only_solidify_polls_while_no_mesh_carries_the_modifier(
        self, add_object: AddObject
    ) -> None:
        add_object("Cube")

        assert SILCAST_OT_solidify.poll(bpy.context)
        assert not SILCAST_OT_apply_solidify.poll(bpy.context)

    def test_neither_operator_polls_for_a_selection_without_a_mesh(
        self, add_object: AddObject
    ) -> None:
        add_object("Camera", bpy.data.cameras.new("CameraData"))

        assert not SILCAST_OT_solidify.poll(bpy.context)
        assert not SILCAST_OT_apply_solidify.poll(bpy.context)

    def test_apply_polls_once_the_solidify_operator_has_run(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        add_object("Cube")

        bpy.ops.silicone_casting.solidify()

        assert SILCAST_OT_apply_solidify.poll(bpy.context)

    def test_neither_operator_polls_outside_object_mode(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        # Both operators write to object data, so both require object mode
        # (spec §11 OQ-1). Solidify runs first so that apply's other poll
        # condition -- a mesh carrying the modifier -- is already satisfied
        # and only the mode can turn it false.
        obj = add_object("Cube")
        bpy.context.view_layer.objects.active = obj
        bpy.ops.silicone_casting.solidify()

        bpy.ops.object.mode_set(mode="EDIT")

        assert not SILCAST_OT_solidify.poll(bpy.context)
        assert not SILCAST_OT_apply_solidify.poll(bpy.context)


class TestSolidifyOperator:
    """``silicone_casting.solidify`` walks the selection and sets up walls."""

    def test_every_selected_mesh_gains_the_modifier(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        first = add_object("CubeA")
        second = add_object("CubeB")

        result = bpy.ops.silicone_casting.solidify()

        assert result == {"FINISHED"}
        assert find_solidify(first) is not None
        assert find_solidify(second) is not None

    def test_non_mesh_objects_in_the_selection_are_skipped_silently(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        # Cameras and lights routinely ride along in a selection, so this
        # is not a warning case (§8.1).
        mesh_object = add_object("Cube")
        camera = add_object("Camera", bpy.data.cameras.new("CameraData"))

        result = bpy.ops.silicone_casting.solidify()

        assert result == {"FINISHED"}
        assert find_solidify(mesh_object) is not None
        assert find_solidify(camera) is None

    def test_thickness_is_converted_from_millimetres_to_blender_units(
        self,
        add_object: AddObject,
        settings: bpy.types.PropertyGroup,
        scene_unit_scale: Callable[[float], None],
    ) -> None:
        scene_unit_scale(1.0)
        settings.solidify_thickness_mm = THICKNESS_MM
        obj = add_object("Cube")

        bpy.ops.silicone_casting.solidify()

        modifier = find_solidify(obj)
        assert modifier is not None
        assert modifier.thickness == pytest.approx(THICKNESS_IN_METRE_SCENE, rel=1e-6)

    def test_thickness_follows_the_scene_unit_scale(
        self,
        add_object: AddObject,
        settings: bpy.types.PropertyGroup,
        scene_unit_scale: Callable[[float], None],
    ) -> None:
        # In a 1 BU = 1 mm scene the same 3 mm wall must come out as 3.0 BU,
        # so that the printed wall is the same physical thickness (S-7).
        scene_unit_scale(MILLIMETRE_SCENE_SCALE)
        settings.solidify_thickness_mm = THICKNESS_MM
        obj = add_object("Cube")

        bpy.ops.silicone_casting.solidify()

        modifier = find_solidify(obj)
        assert modifier is not None
        # scale_length is stored as a 32-bit float, hence the loose tolerance.
        assert modifier.thickness == pytest.approx(THICKNESS_MM, rel=1e-5)

    @pytest.mark.parametrize("scale", [1.0, 0.001])
    def test_distance_input_reaches_the_modifier_without_double_conversion(
        self,
        add_object: AddObject,
        settings: bpy.types.PropertyGroup,
        scene_unit_scale: Callable[[float], None],
        scale: float,
    ) -> None:
        scene_unit_scale(scale)
        settings.solidify_thickness = 0.002 / scale
        obj = add_object("Cube")

        bpy.ops.silicone_casting.solidify()

        modifier = find_solidify(obj)
        assert modifier is not None
        assert modifier.thickness == pytest.approx(0.002 / scale)

    def test_the_wall_grows_outwards_by_default(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        settings.solidify_flip = False
        obj = add_object("Cube")

        bpy.ops.silicone_casting.solidify()

        modifier = find_solidify(obj)
        assert modifier is not None
        assert modifier.offset == 1.0

    def test_flipping_the_direction_grows_the_wall_inwards(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        settings.solidify_flip = True
        obj = add_object("Cube")

        bpy.ops.silicone_casting.solidify()

        modifier = find_solidify(obj)
        assert modifier is not None
        assert modifier.offset == -1.0

    def test_even_thickness_setting_reaches_the_modifier(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        settings.solidify_even_thickness = False
        obj = add_object("Cube")

        bpy.ops.silicone_casting.solidify()

        modifier = find_solidify(obj)
        assert modifier is not None
        assert not modifier.use_even_offset


class TestApplySolidifyOperator:
    """``silicone_casting.apply_solidify`` bakes the walls into the meshes."""

    def test_the_modifier_is_baked_into_the_selected_mesh(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        obj = add_object("Cube")
        bpy.ops.silicone_casting.solidify()

        result = bpy.ops.silicone_casting.apply_solidify()

        assert result == {"FINISHED"}
        assert find_solidify(obj) is None
        assert len(obj.data.vertices) == SOLIDIFIED_VERTEX_COUNT

    def test_a_batch_where_every_object_fails_is_cancelled(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        # Two objects sharing one mesh are both multi-user, so neither can
        # be applied without affecting the other (§8.4).
        shared_mesh = make_cube_mesh(CUBE_SIZE, "SharedCube")
        first = add_object("SharingA", shared_mesh)
        second = add_object("SharingB", shared_mesh)
        bpy.ops.silicone_casting.solidify()

        result = bpy.ops.silicone_casting.apply_solidify()

        assert result == {"CANCELLED"}
        assert find_solidify(first) is not None
        assert find_solidify(second) is not None
        assert len(shared_mesh.vertices) == CUBE_VERTEX_COUNT

    def test_a_batch_finishes_when_one_object_succeeds_and_another_fails(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        # S-6: the multi-user object is reported and skipped, the rest of
        # the batch still goes through.
        single_user = add_object("SingleUser")
        shared_mesh = make_cube_mesh(CUBE_SIZE, "SharedCube")
        multi_user = add_object("MultiUser", shared_mesh)
        add_object("UnselectedSharer", shared_mesh, select=False)
        bpy.ops.silicone_casting.solidify()

        result = bpy.ops.silicone_casting.apply_solidify()

        assert result == {"FINISHED"}
        assert find_solidify(single_user) is None
        assert len(single_user.data.vertices) == SOLIDIFIED_VERTEX_COUNT
        assert find_solidify(multi_user) is not None
        assert len(multi_user.data.vertices) == CUBE_VERTEX_COUNT


@pytest.mark.api_contract
class TestPublicSurface:
    """Contract pins, not behaviour tests.

    Blender's UI, keymaps and saved ``.blend`` files address these
    identifiers by name (NFR-4), so they are fixed deliberately here and
    a change to any of them must be a deliberate, documented one.
    """

    def test_solidify_operator_keeps_its_idname(self) -> None:
        assert SILCAST_OT_solidify.bl_idname == "silicone_casting.solidify"

    def test_apply_operator_keeps_its_idname(self) -> None:
        assert SILCAST_OT_apply_solidify.bl_idname == "silicone_casting.apply_solidify"

    def test_managed_modifier_keeps_its_name(self) -> None:
        # A .blend saved by an earlier version identifies the add-on's
        # modifier by this exact name; renaming it orphans those files.
        assert MODIFIER_NAME == "Silicone Casting Solidify"
