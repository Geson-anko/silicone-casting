"""World-space volume of evaluated meshes, and the aggregate over a selection.

Every expected number is derived from the 2x2x2 cube of
``tests/conftest.py`` and from the definitions in the spec (5.2, 9.2,
9.3) rather than read off a run. No golden fixture is used: this feature
emits no geometry, and the one input that comes out of Blender's own
Solidify modifier is pinned by its analytic wall volume instead (see the
spec's 9 preamble).

The degenerate inputs are built face list by face list in this module so
that "open" and "non-manifold" are visible in the test source. Their
boundary and non-manifold edge counts are asserted through
:func:`tests._helpers.mesh_invariants`, which reaches its verdict from
edge/face counts on its own -- the spec (5.2) requires that the test-side
watertight decision stay separate from the implementation's, so neither
can excuse the other.
"""

from collections.abc import Callable, Iterable, Iterator

import bpy
import pytest
from _helpers import make_cube_mesh, mesh_invariants
from conftest import CUBE_SIZE, MakeObject

from silicone_casting.core import (
    VolumeSummary,
    ensure_solidify,
    total_volume,
    world_volume,
)

#: The cube of ``conftest`` spans -1..1 on every axis, so 8 cubic units.
EXPECTED_CUBE_VOLUME = CUBE_SIZE**3

#: 3 mm of wall in Blender units for the default scale_length of 1.0.
WALL_THICKNESS = 0.003

#: An outward wall grows the cube to 2.006 a side and leaves the original
#: 2x2x2 as the cavity, so the material is the difference of the two.
EXPECTED_WALL_VOLUME = (CUBE_SIZE + 2 * WALL_THICKNESS) ** 3 - CUBE_SIZE**3

#: Blender holds mesh coordinates as float32, so a 1.003 corner lands
#: ~2e-8 off the analytic value; the wall volume is a difference between
#: two numbers near 8, which amplifies that to ~5e-7. An absolute bound
#: at this scale still catches a thickness that is wrong by 0.1%.
VOLUME_TOL = 1e-5

#: Doubling every axis of a shared datablock multiplies its volume by 8,
#: so the two users of one cube mesh come to nine cubes of material.
EXPECTED_SHARED_TOTAL = EXPECTED_CUBE_VOLUME * (1 + 2**3)

_HALF = CUBE_SIZE / 2.0

#: Corners of an axis-aligned CUBE_SIZE cube; the face lists index these.
_CORNERS = [
    (-_HALF, -_HALF, -_HALF),
    (_HALF, -_HALF, -_HALF),
    (_HALF, _HALF, -_HALF),
    (-_HALF, _HALF, -_HALF),
    (-_HALF, -_HALF, _HALF),
    (_HALF, -_HALF, _HALF),
    (_HALF, _HALF, _HALF),
    (-_HALF, _HALF, _HALF),
]
_BOTTOM_FACE = (0, 3, 2, 1)
_TOP_FACE = (4, 5, 6, 7)
_SIDE_FACES = [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]

#: A ninth corner, off the -Y/-Z edge, for the extra face below.
_SPUR_CORNER = (0.0, -CUBE_SIZE, -CUBE_SIZE)

#: A triangle hanging off edge 0-1, which already carries two faces.
_SPUR_FACE = (0, 1, 8)


def _mesh_from_faces(
    name: str,
    corners: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
) -> bpy.types.Mesh:
    """Build a mesh datablock from explicit corner and face lists."""
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(corners, [], faces)
    mesh.update()
    return mesh


def _open_cube_mesh(name: str) -> bpy.types.Mesh:
    """A CUBE_SIZE cube with its +Z face left out, so the top is a hole."""
    return _mesh_from_faces(name, _CORNERS, [_BOTTOM_FACE, *_SIDE_FACES])


def _non_manifold_cube_mesh(name: str) -> bpy.types.Mesh:
    """A closed CUBE_SIZE cube with one extra triangle on one of its edges."""
    return _mesh_from_faces(
        name,
        [*_CORNERS, _SPUR_CORNER],
        [_BOTTOM_FACE, _TOP_FACE, *_SIDE_FACES, _SPUR_FACE],
    )


@pytest.fixture
def open_cube_object(make_object: MakeObject) -> bpy.types.Object:
    """A scene-linked object whose mesh has a four-edge boundary."""
    return make_object(_open_cube_mesh("TestOpenCube"), "TestOpenCube")


@pytest.fixture
def non_manifold_cube_object(make_object: MakeObject) -> bpy.types.Object:
    """A scene-linked object whose mesh has an edge shared by three faces."""
    return make_object(_non_manifold_cube_mesh("TestSpurCube"), "TestSpurCube")


@pytest.fixture
def empty_mesh_object(make_object: MakeObject) -> bpy.types.Object:
    """A scene-linked object holding a mesh with no geometry at all.

    The mesh is created here rather than taken from the ``empty_mesh``
    fixture because ``make_object`` takes ownership of what it is handed
    and both would otherwise remove the same datablock.
    """
    return make_object(bpy.data.meshes.new("TestEmpty"), "TestEmpty")


@pytest.fixture
def camera_object() -> Iterator[bpy.types.Object]:
    """A scene-linked camera: something with no geometry to measure."""
    camera = bpy.data.cameras.new("TestCamera")
    obj = bpy.data.objects.new("TestCamera", camera)
    bpy.context.scene.collection.objects.link(obj)
    yield obj
    bpy.data.objects.remove(obj)
    bpy.data.cameras.remove(camera)


class TestTheDegenerateInputsAreWhatTheyClaimToBe:
    """Premise checks, so the ``None`` cases below cannot pass by accident.

    A fixture that was quietly closed would make "returns None for an
    open mesh" green while proving nothing.
    """

    def test_the_open_cube_has_a_four_edge_boundary_and_no_other_defect(
        self, open_cube_object: bpy.types.Object
    ) -> None:
        invariants = mesh_invariants(open_cube_object.data)

        assert invariants.boundary_edge_count == 4
        assert invariants.non_manifold_edge_count == 0

    def test_the_spur_cube_has_exactly_one_edge_shared_by_three_faces(
        self, non_manifold_cube_object: bpy.types.Object
    ) -> None:
        # The added triangle also brings two boundary edges of its own
        # (its two free sides), which is why the spec treats boundary and
        # non-manifold edges as one condition rather than two.
        invariants = mesh_invariants(non_manifold_cube_object.data)

        assert invariants.non_manifold_edge_count == 1
        assert invariants.boundary_edge_count == 2


class TestWorldVolumeOfAClosedMesh:
    def test_an_untransformed_cube_measures_its_analytic_volume(
        self, cube_object: bpy.types.Object
    ) -> None:
        # AC-12.
        volume = world_volume(cube_object, bpy.context.evaluated_depsgraph_get())

        assert volume == pytest.approx(EXPECTED_CUBE_VOLUME, abs=VOLUME_TOL)

    def test_stretching_one_axis_scales_the_volume_by_that_factor(
        self, cube_object: bpy.types.Object
    ) -> None:
        # AC-13 / FR-17: the world volume is the local volume times the
        # determinant of the transform, so 2x on one axis is 2x material.
        cube_object.scale = (2.0, 1.0, 1.0)
        # matrix_world is only recomputed when the depsgraph is flushed,
        # so it must be fetched *after* the transform is set. Reading
        # matrix_world before this line still reports the old determinant.
        depsgraph = bpy.context.evaluated_depsgraph_get()

        volume = world_volume(cube_object, depsgraph)

        assert volume == pytest.approx(2.0 * EXPECTED_CUBE_VOLUME, abs=VOLUME_TOL)

    def test_a_mirrored_scale_measures_the_same_positive_volume(
        self, cube_object: bpy.types.Object
    ) -> None:
        # AC-14 / FR-18: a negative determinant flips the face normals and
        # with them the sign of the signed volume. Material is never
        # negative, so the magnitude is what the caller gets.
        cube_object.scale = (-2.0, 1.0, 1.0)
        depsgraph = bpy.context.evaluated_depsgraph_get()

        volume = world_volume(cube_object, depsgraph)

        assert volume == pytest.approx(2.0 * EXPECTED_CUBE_VOLUME, abs=VOLUME_TOL)

    def test_rotating_and_moving_the_object_leaves_the_volume_alone(
        self, cube_object: bpy.types.Object
    ) -> None:
        # AC-15: a rigid transform has determinant 1.
        cube_object.location = (5.0, -3.0, 2.0)
        cube_object.rotation_euler = (0.3, 0.7, 1.1)
        depsgraph = bpy.context.evaluated_depsgraph_get()

        volume = world_volume(cube_object, depsgraph)

        assert volume == pytest.approx(EXPECTED_CUBE_VOLUME, abs=VOLUME_TOL)


class TestWorldVolumeOfAMeshWithNoDefinedVolume:
    def test_a_cube_missing_one_face_has_no_volume(
        self, open_cube_object: bpy.types.Object
    ) -> None:
        # AC-16 / FR-19. Blender happily returns a number here (6.67 for
        # this shape), which is why the gate exists: an open surface
        # encloses nothing, so there is no volume to report.
        assert (
            world_volume(open_cube_object, bpy.context.evaluated_depsgraph_get())
            is None
        )

    def test_a_cube_with_a_third_face_on_one_edge_has_no_volume(
        self, non_manifold_cube_object: bpy.types.Object
    ) -> None:
        # AC-17 / FR-19: an internal wall or a doubled face makes "inside"
        # ambiguous, so it is refused the same way an open mesh is.
        assert (
            world_volume(
                non_manifold_cube_object, bpy.context.evaluated_depsgraph_get()
            )
            is None
        )

    def test_a_mesh_with_no_geometry_measures_zero_rather_than_nothing(
        self, empty_mesh_object: bpy.types.Object
    ) -> None:
        # AC-18 / FR-21: "every edge has exactly two faces" is vacuously
        # true of a mesh with no edges, and empty space holds no material.
        # This must be 0.0 and not None -- selecting only such an object
        # is a successful measurement of nothing, not a failure.
        assert (
            world_volume(empty_mesh_object, bpy.context.evaluated_depsgraph_get())
            == 0.0
        )


class TestWorldVolumeMeasuresTheEvaluatedMesh:
    def test_a_solidify_wall_is_measured_instead_of_the_cube_it_wraps(
        self, cube_object: bpy.types.Object
    ) -> None:
        # AC-19 / FR-13 / G-2: this is the number the user actually wants
        # -- how much resin the wall takes, not how much the master
        # displaces. The two shells the modifier leaves behind have
        # opposing normals, so the measurement comes to outer - inner.
        ensure_solidify(cube_object, WALL_THICKNESS)

        volume = world_volume(cube_object, bpy.context.evaluated_depsgraph_get())

        assert volume == pytest.approx(EXPECTED_WALL_VOLUME, abs=VOLUME_TOL)

    def test_a_modifier_hidden_in_the_viewport_is_not_measured(
        self, cube_object: bpy.types.Object
    ) -> None:
        # AC-20 / FR-14: what is measured is what the viewport shows. The
        # cube comes back bare, which is the spec, not a bug.
        modifier = ensure_solidify(cube_object, WALL_THICKNESS)
        modifier.show_viewport = False

        volume = world_volume(cube_object, bpy.context.evaluated_depsgraph_get())

        assert volume == pytest.approx(EXPECTED_CUBE_VOLUME, abs=VOLUME_TOL)


class TestWorldVolumeLeavesNoTemporaryMeshBehind:
    """FR-15/FR-16: the temporary mesh must never become a datablock.

    One leaked mesh per press would accumulate in the ``.blend`` for the
    rest of the session, so both exits from the function are checked.
    """

    def test_measuring_a_closed_mesh_adds_no_mesh_datablock(
        self, cube_object: bpy.types.Object
    ) -> None:
        # AC-21.
        mesh_count_before = len(bpy.data.meshes)

        world_volume(cube_object, bpy.context.evaluated_depsgraph_get())

        assert len(bpy.data.meshes) == mesh_count_before

    def test_refusing_an_open_mesh_adds_no_mesh_datablock(
        self, open_cube_object: bpy.types.Object
    ) -> None:
        # AC-22: the early return for a non-watertight mesh happens before
        # the volume is ever computed, so it is the path most likely to
        # skip the cleanup.
        mesh_count_before = len(bpy.data.meshes)

        world_volume(open_cube_object, bpy.context.evaluated_depsgraph_get())

        assert len(bpy.data.meshes) == mesh_count_before


class TestTotalVolumeOverASelection:
    @pytest.mark.parametrize("objects", [list, iter], ids=["list", "single-pass"])
    def test_two_closed_cubes_come_to_twice_one_cube(
        self,
        cube_object: bpy.types.Object,
        make_object: MakeObject,
        objects: Callable[[list[bpy.types.Object]], Iterable[bpy.types.Object]],
    ) -> None:
        # AC-23 / G-1: the operator reports a single total, so the sum is
        # the contract rather than a per-object breakdown.
        other = make_object(make_cube_mesh(CUBE_SIZE, "OtherCube"), "OtherCube")

        summary = VolumeSummary.from_objects(
            objects([cube_object, other]), bpy.context.evaluated_depsgraph_get()
        )

        assert summary.measured_count == 2
        assert summary.non_watertight_names == ()
        assert summary.volume == pytest.approx(2.0 * EXPECTED_CUBE_VOLUME, abs=1e-9)

    def test_objects_that_are_not_meshes_are_passed_over_in_silence(
        self,
        cube_object: bpy.types.Object,
        make_object: MakeObject,
        camera_object: bpy.types.Object,
    ) -> None:
        # AC-24 / FR-11: a camera or light in the selection is an everyday
        # occurrence. It must neither raise, nor count, nor be reported.
        other = make_object(make_cube_mesh(CUBE_SIZE, "OtherCube"), "OtherCube")

        summary = total_volume(
            [cube_object, camera_object, other], bpy.context.evaluated_depsgraph_get()
        )

        assert summary.measured_count == 2
        assert summary.non_watertight_names == ()
        assert summary.volume == pytest.approx(2.0 * EXPECTED_CUBE_VOLUME, abs=1e-9)

    def test_an_empty_selection_measures_nothing_at_all(self) -> None:
        # AC-25.
        summary = VolumeSummary.from_objects((), bpy.context.evaluated_depsgraph_get())

        assert summary == VolumeSummary(
            volume=0.0, measured_count=0, non_watertight_names=()
        )

    def test_a_selection_of_only_non_meshes_measures_nothing_at_all(
        self, camera_object: bpy.types.Object
    ) -> None:
        # AC-26: indistinguishable from the empty selection, by design.
        summary = VolumeSummary.from_objects(
            [camera_object], bpy.context.evaluated_depsgraph_get()
        )

        assert summary == VolumeSummary(
            volume=0.0, measured_count=0, non_watertight_names=()
        )

    def test_an_open_mesh_is_named_while_the_closed_one_is_still_counted(
        self, cube_object: bpy.types.Object, open_cube_object: bpy.types.Object
    ) -> None:
        # AC-27: the summary carries both halves of the story. Whether a
        # partial total may be shown is the operator's decision (FR-32),
        # and it needs the count and the names to make it.
        summary = VolumeSummary.from_objects(
            [cube_object, open_cube_object], bpy.context.evaluated_depsgraph_get()
        )

        assert summary.measured_count == 1
        assert summary.non_watertight_names == (open_cube_object.name,)
        assert summary.volume == pytest.approx(EXPECTED_CUBE_VOLUME, abs=VOLUME_TOL)

    def test_the_names_of_open_meshes_keep_the_order_they_were_given_in(
        self, make_object: MakeObject
    ) -> None:
        # AC-28 / FR-34: the operator quotes the first three names and
        # counts the rest, so "first" has to mean something stable.
        first = make_object(_open_cube_mesh("OpenFirst"), "OpenFirst")
        second = make_object(_open_cube_mesh("OpenSecond"), "OpenSecond")
        third = make_object(_open_cube_mesh("OpenThird"), "OpenThird")

        summary = VolumeSummary.from_objects(
            [first, second, third], bpy.context.evaluated_depsgraph_get()
        )

        assert summary.measured_count == 0
        assert summary.non_watertight_names == (first.name, second.name, third.name)

    def test_two_objects_sharing_one_mesh_are_measured_once_each(
        self, cube_object: bpy.types.Object, make_object: MakeObject
    ) -> None:
        # AC-29 / FR-12: instances of the same datablock each need their
        # own material, and each carries its own matrix_world, so the
        # scaled copy contributes eight cubes to the original's one.
        scaled = make_object(cube_object.data, "SharedUser")
        scaled.scale = (2.0, 2.0, 2.0)
        depsgraph = bpy.context.evaluated_depsgraph_get()

        summary = VolumeSummary.from_objects([cube_object, scaled], depsgraph)

        assert summary.measured_count == 2
        assert summary.volume == pytest.approx(EXPECTED_SHARED_TOTAL, abs=VOLUME_TOL)

    def test_measuring_changes_none_of_the_meshes_it_reads(
        self, cube_object: bpy.types.Object, open_cube_object: bpy.types.Object
    ) -> None:
        # AC-30: the whole feature is read-only over geometry (6.2). The
        # invariants cover counts, volume and bounding box, so a stray
        # bmesh write-back or a baked modifier would show up here.
        closed_before = mesh_invariants(cube_object.data)
        open_before = mesh_invariants(open_cube_object.data)

        VolumeSummary.from_objects(
            [cube_object, open_cube_object], bpy.context.evaluated_depsgraph_get()
        )

        assert mesh_invariants(cube_object.data) == closed_before
        assert mesh_invariants(open_cube_object.data) == open_before
