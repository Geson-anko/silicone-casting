"""Executable spec for the volume measurement operator.

Source of truth: ``memory/specs/volume_measurement.md`` §5.4, acceptance
criteria AC-31 -- AC-49.

These run against the real ``bpy`` wheel: a real scene, a real selection, a
real modifier stack and a real depsgraph. Nothing here mocks ``bpy``.

The volume arithmetic is the ``core`` layer's contract and is asserted in
``tests/silicone_casting/core/``. What these tests state is the operator
layer's own job: which selections make the sidebar button clickable, what
ends up in ``Scene.silicone_casting`` after a run, and what happens to an
already stored result when the next run cannot measure the selection.

Expected volumes are spelled as the string the panel displays, i.e. what
``format_ml`` returns, because the display is what the spec fixes; the
float32 arithmetic behind it is not (§9, tolerance policy). Report wording
is never asserted -- the spec deliberately leaves it unfixed (§5.4).
"""

from collections.abc import Callable, Iterator

import bpy
import pytest
from _helpers import make_cube_mesh

import silicone_casting
from silicone_casting.core import MODIFIER_NAME, format_ml
from silicone_casting.operators import SILCAST_OT_measure_volume

#: Edge length of the test cubes in Blender units: a 2 cm cube at 1 BU = 1 m.
CUBE_EDGE_BU = 0.02

#: A 2 cm cube holds 8 mL, so 0.02**3 BU3 * 1e6 mL/BU3 reads as this.
ONE_CUBE_ML = "8.00"

#: Two of those cubes, reported as a single total (N-4: no breakdown).
TWO_CUBES_ML = "16.00"

#: One cube stretched to twice its width: abs(det) of the scale is 2.
STRETCHED_CUBE_ML = "16.00"

#: 1 BU = 1 m, the scene scale every expected value above assumes.
METRE_SCENE_SCALE = 1.0

#: A scene where 1 BU = 1 mm, so a 20 BU cube is the same physical 2 cm cube.
MILLIMETRE_SCENE_SCALE = 0.001
MILLIMETRE_SCENE_CUBE_EDGE = 20.0

#: Wall thickness of the Solidify modifier used to check modifier evaluation.
WALL_THICKNESS_BU = 0.001

#: The wall of that solidified cube, in mL. Offset 1.0 with Even Thickness
#: grows the shell outwards by the full thickness on each side, so the wall is
#: (0.02 + 2 * 0.001)**3 - 0.02**3 = 2.648e-6 BU3, i.e. 2.648 mL. The bare
#: cube would read ONE_CUBE_ML instead.
SOLIDIFIED_WALL_ML = "2.65"

#: Signature of the ``add_object`` factory fixture.
type AddObject = Callable[..., bpy.types.Object]


def _leave_edit_mode() -> None:
    """Return to object mode so that fixture teardown can remove objects."""
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def _make_open_cube_mesh(edge: float, name: str) -> bpy.types.Mesh:
    """Create a cube mesh with its top face missing.

    The four edges around the hole are boundary edges, so this mesh has no
    defined volume (FR-19) and the operator must refuse any selection that
    contains it. Built through ``from_pydata`` rather than ``bmesh``, which
    only ``tests/_helpers.py`` is allowed to import.
    """
    half = edge / 2.0
    vertices = [
        (-half, -half, -half),
        (half, -half, -half),
        (half, half, -half),
        (-half, half, -half),
        (-half, -half, half),
        (half, -half, half),
        (half, half, half),
        (-half, half, half),
    ]
    # Bottom and all four sides; the top face is left off.
    faces = [
        (0, 1, 2, 3),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    return mesh


@pytest.fixture(scope="module")
def registered() -> Iterator[None]:
    """The add-on registered, so ``bpy.ops`` and the scene settings exist."""
    silicone_casting.register()
    yield
    silicone_casting.unregister()


@pytest.fixture
def settings(registered: None) -> Iterator[bpy.types.PropertyGroup]:
    """Scene state each measurement starts from: 1 BU = 1 m, not measured.

    The unit scale is restored afterwards because a test that switches to a
    millimetre scene (AC-39) would otherwise leak that scale into the rest
    of the suite.
    """
    unit_settings = bpy.context.scene.unit_settings
    original_scale = unit_settings.scale_length
    unit_settings.scale_length = METRE_SCENE_SCALE

    props = bpy.context.scene.silicone_casting
    props.volume_ml = 0.0
    props.volume_measured = False

    yield props

    unit_settings.scale_length = original_scale


@pytest.fixture
def add_object(registered: None) -> Iterator[AddObject]:
    """Factory for scene objects, cleaned up when the test ends.

    Everything already in the scene is deselected first. This matters: the
    background startup scene ships a *selected* ``Cube`` (§5.11), so a test
    that expects ``poll`` to be false would pass or fail by accident without
    this. New objects are selected unless ``select=False`` is passed, and are
    given a fresh closed cube mesh unless a datablock is supplied.
    """
    for existing in bpy.context.scene.objects:
        existing.select_set(False)

    created: list[bpy.types.Object] = []

    def add(
        name: str, data: bpy.types.ID | None = None, *, select: bool = True
    ) -> bpy.types.Object:
        mesh = data if data is not None else make_cube_mesh(CUBE_EDGE_BU, f"{name}Mesh")
        obj = bpy.data.objects.new(name, mesh)
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


class TestWhenTheMeasureButtonIsClickable:
    """``poll`` decides whether the sidebar button is greyed out (FR-31)."""

    @pytest.mark.usefixtures("add_object")
    def test_the_button_is_not_clickable_with_an_empty_selection(self) -> None:
        # AC-31. The fixture's deselect pass is what makes this meaningful:
        # the startup scene of a background run has a selected Cube (§5.11).
        assert not SILCAST_OT_measure_volume.poll(bpy.context)

    def test_the_button_is_not_clickable_for_a_selection_without_a_mesh(
        self, add_object: AddObject
    ) -> None:
        # AC-32: only mesh objects have a volume to measure (V-1).
        add_object("Camera", bpy.data.cameras.new("CameraData"))

        assert not SILCAST_OT_measure_volume.poll(bpy.context)

    def test_the_button_becomes_clickable_once_a_mesh_is_selected(
        self, add_object: AddObject
    ) -> None:
        # AC-33
        add_object("Cube")

        assert SILCAST_OT_measure_volume.poll(bpy.context)

    def test_the_button_stays_clickable_in_edit_mode(
        self, add_object: AddObject
    ) -> None:
        # AC-34 / FR-31: measuring only reads geometry, so unlike the two
        # Solidify operators this one must not carry a mode condition.
        obj = add_object("Cube")
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")

        assert SILCAST_OT_measure_volume.poll(bpy.context)


class TestWhatAMeasurementStores:
    """A run writes its snapshot into ``Scene.silicone_casting`` (FR-26)."""

    def test_a_scene_has_no_measurement_until_the_button_is_pressed(
        self, registered: None
    ) -> None:
        # AC-35: the panel's "--" means "nothing measured yet", so the flag
        # has to start out false rather than pointing at a stale volume. Read
        # from the RNA default, which no earlier test in the session can have
        # measured into.
        properties = bpy.context.scene.silicone_casting.bl_rna.properties
        assert properties["volume_measured"].default is False

    def test_one_closed_cube_is_stored_in_cubic_centimetres(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        # AC-36 / S-1
        add_object("Cube")

        result = bpy.ops.silicone_casting.measure_volume()

        assert result == {"FINISHED"}
        assert settings.volume_measured
        assert format_ml(settings.volume_ml) == ONE_CUBE_ML

    def test_two_cubes_are_stored_as_a_single_total(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        # AC-37 / S-3: the sum only, never a per-object breakdown (N-4).
        add_object("CubeA")
        second = add_object("CubeB")
        second.location = (1.0, 0.0, 0.0)

        bpy.ops.silicone_casting.measure_volume()

        assert format_ml(settings.volume_ml) == TWO_CUBES_ML

    def test_non_mesh_objects_in_the_selection_are_skipped_silently(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        # AC-38 / FR-11: cameras and lights routinely ride along in a
        # selection, so their presence must not change the total, and must
        # not produce a warning either.
        add_object("CubeA")
        second = add_object("CubeB")
        second.location = (1.0, 0.0, 0.0)
        add_object("Camera", bpy.data.cameras.new("CameraData"))

        result = bpy.ops.silicone_casting.measure_volume()

        assert result == {"FINISHED"}
        assert format_ml(settings.volume_ml) == TWO_CUBES_ML

    def test_a_millimetre_scene_reports_the_same_physical_amount(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        # AC-39 / S-7: 20 BU in a 1 BU = 1 mm scene is the same 2 cm cube, so
        # the reading must not depend on the scene's unit scale.
        bpy.context.scene.unit_settings.scale_length = MILLIMETRE_SCENE_SCALE
        add_object(
            "Cube", make_cube_mesh(MILLIMETRE_SCENE_CUBE_EDGE, "MillimetreCubeMesh")
        )

        bpy.ops.silicone_casting.measure_volume()

        assert format_ml(settings.volume_ml) == ONE_CUBE_ML

    def test_a_stretched_cube_is_measured_at_its_world_size(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        # AC-40 / S-8 / FR-17: non-uniform scale multiplies the volume by
        # abs(det) of the object's matrix.
        obj = add_object("Cube")
        obj.scale = (2.0, 1.0, 1.0)

        bpy.ops.silicone_casting.measure_volume()

        assert format_ml(settings.volume_ml) == STRETCHED_CUBE_ML

    def test_a_mirrored_cube_is_measured_as_a_positive_volume(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        # AC-40 / S-8 / FR-18: a negative scale flips the face normals and
        # the determinant's sign; neither may reach the stored value.
        obj = add_object("Cube")
        obj.scale = (-2.0, 1.0, 1.0)

        bpy.ops.silicone_casting.measure_volume()

        assert format_ml(settings.volume_ml) == STRETCHED_CUBE_ML

    def test_an_unapplied_modifier_is_included_in_the_measurement(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        # AC-41 / FR-13 / S-4: what is measured is the evaluated mesh, so a
        # cube carrying an unapplied Solidify reads as the volume of its wall
        # (outer shell minus inner shell), not as the cube it was built from.
        obj = add_object("Cube")
        modifier = obj.modifiers.new(MODIFIER_NAME, "SOLIDIFY")
        modifier.thickness = WALL_THICKNESS_BU
        modifier.offset = 1.0
        modifier.use_even_offset = True

        bpy.ops.silicone_casting.measure_volume()

        assert format_ml(settings.volume_ml) == SOLIDIFIED_WALL_ML

    def test_measuring_the_same_selection_twice_stores_the_same_value(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        # AC-42 / §8.4: the operator is idempotent as long as the scene does
        # not change between the two presses.
        add_object("Cube")
        bpy.ops.silicone_casting.measure_volume()
        first_reading = settings.volume_ml

        bpy.ops.silicone_casting.measure_volume()

        assert settings.volume_ml == first_reading

    def test_measuring_leaves_the_selected_geometry_untouched(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        # AC-46 / §6.2: the whole feature is read-only over geometry -- it
        # must neither bake the modifier it evaluates nor leave the temporary
        # mesh behind on the object.
        obj = add_object("Cube")
        modifier = obj.modifiers.new(MODIFIER_NAME, "SOLIDIFY")
        modifier.thickness = WALL_THICKNESS_BU
        vertex_count = len(obj.data.vertices)
        polygon_count = len(obj.data.polygons)
        modifier_count = len(obj.modifiers)

        bpy.ops.silicone_casting.measure_volume()

        assert len(obj.data.vertices) == vertex_count
        assert len(obj.data.polygons) == polygon_count
        assert len(obj.modifiers) == modifier_count


class TestWhenTheSelectionHasNoDefinedVolume:
    """One open mesh anywhere in the selection cancels the whole run.

    The spec asks these runs to return ``{"CANCELLED"}`` (FR-32), but a
    ``self.report({"ERROR"}, ...)`` is converted into a ``RuntimeError`` at
    the ``bpy.ops`` boundary, so from Python the cancelled run surfaces as
    that exception instead of as a return value. Each test therefore states
    the two things that remain observable: the call raises, and no number is
    left behind. The message is not matched -- its wording is not part of the
    spec (§9.4 note), and ``poll`` is asserted first so that a
    ``poll``-failure ``RuntimeError`` cannot be mistaken for the error path.
    """

    def test_an_open_mesh_alone_stores_nothing(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        # AC-43 / FR-32
        add_object("OpenCube", _make_open_cube_mesh(CUBE_EDGE_BU, "OpenCubeMesh"))
        assert SILCAST_OT_measure_volume.poll(bpy.context)

        with pytest.raises(RuntimeError):
            bpy.ops.silicone_casting.measure_volume()

        assert not settings.volume_measured

    def test_one_open_mesh_cancels_an_otherwise_closed_selection(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        # AC-44 / FR-32 / S-5: no partial total. The closed cube's 8.00 must
        # not be stored just because it could be measured on its own.
        add_object("ClosedCube")
        add_object("OpenCube", _make_open_cube_mesh(CUBE_EDGE_BU, "OpenCubeMesh"))
        assert SILCAST_OT_measure_volume.poll(bpy.context)

        with pytest.raises(RuntimeError):
            bpy.ops.silicone_casting.measure_volume()

        assert not settings.volume_measured

    def test_a_failed_measurement_discards_the_previous_result(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        # AC-45 / FR-33 / S-5. The order is the point: measure successfully
        # first, so that the failing run has an old value to clear. A stale
        # number left on screen would be read as the current selection's.
        add_object("ClosedCube")
        open_cube = add_object(
            "OpenCube",
            _make_open_cube_mesh(CUBE_EDGE_BU, "OpenCubeMesh"),
            select=False,
        )
        assert bpy.ops.silicone_casting.measure_volume() == {"FINISHED"}
        assert settings.volume_measured

        open_cube.select_set(True)
        with pytest.raises(RuntimeError):
            bpy.ops.silicone_casting.measure_volume()

        assert not settings.volume_measured

    def test_more_open_meshes_than_the_message_can_list_still_cancels_the_run(
        self, add_object: AddObject, settings: bpy.types.PropertyGroup
    ) -> None:
        # FR-34: the error message lists at most three names and adds a count
        # for the rest, so four open meshes is the smallest selection that
        # takes the truncating branch. AC-79 checks that the resulting line is
        # readable by hand (§9.8) -- what this test states is only that a
        # selection over the cap behaves like any other unmeasurable one.
        #
        # The wording is deliberately not asserted (§9.4 note: message text is
        # not part of the spec). The value of this test is that the truncating
        # path is executed at all: without it, that branch never runs under
        # tier 1 and could break unnoticed until someone opened Blender.
        add_object("OpenCubeA", _make_open_cube_mesh(CUBE_EDGE_BU, "OpenCubeMeshA"))
        add_object("OpenCubeB", _make_open_cube_mesh(CUBE_EDGE_BU, "OpenCubeMeshB"))
        add_object("OpenCubeC", _make_open_cube_mesh(CUBE_EDGE_BU, "OpenCubeMeshC"))
        add_object("OpenCubeD", _make_open_cube_mesh(CUBE_EDGE_BU, "OpenCubeMeshD"))
        assert SILCAST_OT_measure_volume.poll(bpy.context)
        # Seeded true as a second guard on top of the poll assert above: a
        # RuntimeError raised by poll would leave this flag alone, so the flip
        # to false is what proves execute() ran and reached the error branch.
        settings.volume_measured = True

        with pytest.raises(RuntimeError):
            bpy.ops.silicone_casting.measure_volume()

        assert not settings.volume_measured


class TestPublicSurface:
    """How the operator is addressed from outside the add-on."""

    def test_the_operator_pushes_an_undo_step(self) -> None:
        # AC-47 / FR-30: it writes scene properties, so the previous result
        # has to be reachable with Ctrl+Z (S-9). Semantic invariant, not a
        # pin of the literal set.
        assert "UNDO" in SILCAST_OT_measure_volume.bl_options

    @pytest.mark.api_contract
    def test_the_operator_keeps_its_idname(self) -> None:
        # Contract pin, not a behaviour test: AC-48 fixes the name Blender's
        # UI, keymaps and saved .blend files address this operator by (NFR-4).
        assert SILCAST_OT_measure_volume.bl_idname == "silicone_casting.measure_volume"
