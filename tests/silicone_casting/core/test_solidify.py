"""Behaviour of the managed Solidify modifier: finding, ensuring, baking.

Every expected number is derived from the 2x2x2 cube in the spec rather
than read off a run. No golden fixture is used here on purpose: the
geometry comes out of Blender's own Solidify modifier, whose vertex
ordering and numerics drift between releases, so pinning it would make CI
fail for reasons unrelated to this add-on. The analytic invariants below
carry the whole load instead.
"""

import bpy
import pytest
from _helpers import MeshInvariants
from conftest import MakeObject

from silicone_casting.core.solidify import (
    MODIFIER_NAME,
    apply_solidify,
    ensure_solidify,
    find_solidify,
)

#: 3 mm in Blender units for a scene with the default scale_length of 1.0.
THICKNESS = 0.003

#: Spec S-2 raises the wall to 5 mm on a second run.
UPDATED_THICKNESS = 0.005

#: An outward wall grows the cube to 2.006 a side and leaves the original
#: 2x2x2 volume as the cavity the master will occupy.
EXPECTED_OUTWARD_VOLUME = (2.0 + 2 * THICKNESS) ** 3 - 2.0**3

#: An inward wall keeps the 2x2x2 outline and hollows 1.994 out of it.
EXPECTED_INWARD_VOLUME = 2.0**3 - (2.0 - 2 * THICKNESS) ** 3

#: Blender stores mesh coordinates as float32, so a 1.003 corner lands
#: ~2e-8 off the analytic value. The volume is a difference between two
#: numbers near 8, which amplifies that to ~5e-7 -- three orders of
#: magnitude looser than the spec's rel=1e-6, hence an absolute bound.
#: 1e-5 still catches a thickness that is wrong by a tenth of a percent.
VOLUME_TOL = 1e-5


class TestFindSolidify:
    def test_an_object_without_modifiers_has_no_managed_solidify(
        self, cube_object: bpy.types.Object
    ) -> None:
        assert find_solidify(cube_object) is None

    def test_the_modifier_ensure_solidify_created_is_the_one_found(
        self, cube_object: bpy.types.Object
    ) -> None:
        created = ensure_solidify(cube_object, THICKNESS)

        assert find_solidify(cube_object) == created

    def test_a_modifier_that_only_borrowed_the_managed_name_is_not_ours(
        self, cube_object: bpy.types.Object
    ) -> None:
        # Spec 8.3: the modifier is identified by name *and* type, so a
        # user-made modifier of another type is never mistaken for ours
        # and never gets baked or overwritten.
        cube_object.modifiers.new(MODIFIER_NAME, "SUBSURF")

        assert find_solidify(cube_object) is None


class TestEnsureSolidify:
    def test_adds_one_solidify_modifier_under_the_managed_name(
        self, cube_object: bpy.types.Object
    ) -> None:
        ensure_solidify(cube_object, THICKNESS)

        assert len(cube_object.modifiers) == 1
        modifier = cube_object.modifiers[0]
        assert modifier.name == MODIFIER_NAME
        assert modifier.type == "SOLIDIFY"
        assert modifier.thickness == pytest.approx(THICKNESS)

    def test_running_again_updates_the_existing_modifier_instead_of_adding_one(
        self, cube_object: bpy.types.Object
    ) -> None:
        # Spec S-2 / FR-11: repeating the operation is idempotent in count.
        ensure_solidify(cube_object, THICKNESS)

        ensure_solidify(cube_object, UPDATED_THICKNESS)

        assert len(cube_object.modifiers) == 1
        assert cube_object.modifiers[0].thickness == pytest.approx(UPDATED_THICKNESS)

    def test_running_again_keeps_the_modifier_where_it_sits_in_the_stack(
        self, cube_object: bpy.types.Object
    ) -> None:
        ensure_solidify(cube_object, THICKNESS)
        cube_object.modifiers.new("Subdivision", "SUBSURF")

        ensure_solidify(cube_object, UPDATED_THICKNESS)

        assert [m.name for m in cube_object.modifiers] == [MODIFIER_NAME, "Subdivision"]

    def test_the_wall_grows_outward_by_default(
        self, cube_object: bpy.types.Object
    ) -> None:
        modifier = ensure_solidify(cube_object, THICKNESS)

        # offset +1 keeps the whole wall outside the source surface, so
        # the original surface becomes the inner face of the wall.
        assert modifier.offset == 1.0

    def test_flipping_puts_the_wall_on_the_inside(
        self, cube_object: bpy.types.Object
    ) -> None:
        modifier = ensure_solidify(cube_object, THICKNESS, flip=True)

        assert modifier.offset == -1.0

    def test_even_thickness_is_on_by_default(
        self, cube_object: bpy.types.Object
    ) -> None:
        modifier = ensure_solidify(cube_object, THICKNESS)

        assert modifier.use_even_offset

    def test_even_thickness_can_be_turned_off_on_an_existing_modifier(
        self, cube_object: bpy.types.Object
    ) -> None:
        ensure_solidify(cube_object, THICKNESS, even_thickness=True)

        modifier = ensure_solidify(cube_object, THICKNESS, even_thickness=False)

        assert not modifier.use_even_offset

    def test_the_remaining_solidify_settings_are_left_at_blender_defaults(
        self, cube_object: bpy.types.Object
    ) -> None:
        # This is a pin, not a behaviour claim: FR-8 sets only thickness,
        # offset and use_even_offset, so these stay at Blender's defaults.
        # The assertion exists to notice if a future Blender moves them.
        modifier = ensure_solidify(cube_object, THICKNESS)

        assert modifier.solidify_mode == "EXTRUDE"
        assert modifier.use_rim


class TestApplySolidifyBakesTheSpecifiedShell:
    def test_an_outward_wall_doubles_the_topology_of_a_closed_cube(
        self, cube_object: bpy.types.Object
    ) -> None:
        ensure_solidify(cube_object, THICKNESS)

        apply_solidify(cube_object, bpy.context.evaluated_depsgraph_get())

        # A closed source has no boundary for a rim to bridge, so the
        # result is exactly the cube twice over: 8+8, 12+12, 6+6.
        invariants = MeshInvariants.from_mesh(cube_object.data)
        assert invariants.vertex_count == 16
        assert invariants.edge_count == 24
        assert invariants.face_count == 12

    def test_an_outward_wall_is_watertight_and_falls_into_two_shells(
        self, cube_object: bpy.types.Object
    ) -> None:
        ensure_solidify(cube_object, THICKNESS)

        apply_solidify(cube_object, bpy.context.evaluated_depsgraph_get())

        # Watertight is the precondition for printing at all; the two
        # loose parts are the outer shell and the cavity wall.
        invariants = MeshInvariants.from_mesh(cube_object.data)
        assert invariants.is_watertight
        assert invariants.loose_part_count == 2

    def test_an_outward_wall_holds_the_material_between_the_two_shells(
        self, cube_object: bpy.types.Object
    ) -> None:
        ensure_solidify(cube_object, THICKNESS)

        apply_solidify(cube_object, bpy.context.evaluated_depsgraph_get())

        invariants = MeshInvariants.from_mesh(cube_object.data)
        assert invariants.volume == pytest.approx(
            EXPECTED_OUTWARD_VOLUME, abs=VOLUME_TOL
        )

    def test_an_outward_wall_offsets_every_side_by_the_full_thickness(
        self, cube_object: bpy.types.Object
    ) -> None:
        ensure_solidify(cube_object, THICKNESS)

        apply_solidify(cube_object, bpy.context.evaluated_depsgraph_get())

        # This is what proves Even Thickness is in effect (G-5). Without
        # it the corner vertices would only travel `thickness` along the
        # averaged normal and stop at +-(1 + 0.003 / sqrt(3)) ~ +-1.001732,
        # i.e. a wall thinner than the millimetres the user asked for.
        invariants = MeshInvariants.from_mesh(cube_object.data)
        assert invariants.bbox_min == pytest.approx((-1.003, -1.003, -1.003), abs=1e-6)
        assert invariants.bbox_max == pytest.approx((1.003, 1.003, 1.003), abs=1e-6)

    def test_an_inward_wall_leaves_the_outline_of_the_cube_untouched(
        self, cube_object: bpy.types.Object
    ) -> None:
        ensure_solidify(cube_object, THICKNESS, flip=True)

        apply_solidify(cube_object, bpy.context.evaluated_depsgraph_get())

        # Spec S-3: the source surface becomes the *outer* face, so the
        # silhouette the user modelled is preserved exactly.
        invariants = MeshInvariants.from_mesh(cube_object.data)
        assert invariants.bbox_min == pytest.approx((-1.0, -1.0, -1.0), abs=1e-6)
        assert invariants.bbox_max == pytest.approx((1.0, 1.0, 1.0), abs=1e-6)

    def test_an_inward_wall_is_hollowed_out_of_the_original_cube(
        self, cube_object: bpy.types.Object
    ) -> None:
        ensure_solidify(cube_object, THICKNESS, flip=True)

        apply_solidify(cube_object, bpy.context.evaluated_depsgraph_get())

        invariants = MeshInvariants.from_mesh(cube_object.data)
        assert invariants.volume == pytest.approx(
            EXPECTED_INWARD_VOLUME, abs=VOLUME_TOL
        )


class TestApplySolidifyLeavesTheObjectConsistent:
    def test_the_baked_modifier_is_gone_from_the_stack(
        self, cube_object: bpy.types.Object
    ) -> None:
        ensure_solidify(cube_object, THICKNESS)

        apply_solidify(cube_object, bpy.context.evaluated_depsgraph_get())

        # Spec S-4: this is also what greys the Apply button out again.
        assert find_solidify(cube_object) is None

    def test_the_baked_mesh_inherits_the_name_of_the_one_it_replaced(
        self, cube_object: bpy.types.Object
    ) -> None:
        original_name = cube_object.data.name

        ensure_solidify(cube_object, THICKNESS)
        apply_solidify(cube_object, bpy.context.evaluated_depsgraph_get())

        # A ".001" suffix here would mean the old datablock was still
        # holding the name when the new one was renamed.
        assert cube_object.data.name == original_name

    def test_the_replaced_mesh_datablock_does_not_survive_as_an_orphan(
        self, cube_object: bpy.types.Object
    ) -> None:
        mesh_count_before = len(bpy.data.meshes)

        ensure_solidify(cube_object, THICKNESS)
        apply_solidify(cube_object, bpy.context.evaluated_depsgraph_get())

        # Baking adds one datablock, so an unchanged total means the one
        # it replaced was removed rather than left behind.
        assert len(bpy.data.meshes) == mesh_count_before


class TestApplySolidifyIgnoresTheRestOfTheStack:
    def test_the_other_modifiers_survive_with_their_visibility_restored(
        self, cube_object: bpy.types.Object
    ) -> None:
        ensure_solidify(cube_object, THICKNESS)
        cube_object.modifiers.new("Subdivision", "SUBSURF")

        apply_solidify(cube_object, bpy.context.evaluated_depsgraph_get())

        assert [m.name for m in cube_object.modifiers] == ["Subdivision"]
        assert cube_object.modifiers["Subdivision"].show_viewport

    def test_a_modifier_the_user_had_already_hidden_stays_hidden(
        self, cube_object: bpy.types.Object
    ) -> None:
        # FR-15: the flag is restored to what it *was*, not to True.
        ensure_solidify(cube_object, THICKNESS)
        subdivision = cube_object.modifiers.new("Subdivision", "SUBSURF")
        subdivision.show_viewport = False

        apply_solidify(cube_object, bpy.context.evaluated_depsgraph_get())

        assert not cube_object.modifiers["Subdivision"].show_viewport

    def test_the_baked_geometry_carries_none_of_their_effects(
        self, cube_object: bpy.types.Object
    ) -> None:
        ensure_solidify(cube_object, THICKNESS)
        cube_object.modifiers.new("Subdivision", "SUBSURF")

        apply_solidify(cube_object, bpy.context.evaluated_depsgraph_get())

        # FR-14: baking means "base mesh plus this one modifier", the same
        # meaning Blender's own modifier_apply has. A subdivision that
        # leaked into the bake would push the count well past 16.
        assert MeshInvariants.from_mesh(cube_object.data).vertex_count == 16


class TestApplySolidifyRefusesUnsafeInput:
    def test_an_object_without_the_managed_modifier_is_refused(
        self, cube_object: bpy.types.Object
    ) -> None:
        with pytest.raises(ValueError):
            apply_solidify(cube_object, bpy.context.evaluated_depsgraph_get())

    def test_a_multi_user_mesh_is_refused_and_left_exactly_as_it_was(
        self, cube_object: bpy.types.Object, make_object: MakeObject
    ) -> None:
        # FR-17: baking a shared datablock would silently reshape every
        # other object using it.
        make_object(cube_object.data, "SecondUser")
        ensure_solidify(cube_object, THICKNESS)

        with pytest.raises(ValueError):
            apply_solidify(cube_object, bpy.context.evaluated_depsgraph_get())

        assert find_solidify(cube_object) is not None
        assert len(cube_object.data.vertices) == 8


class TestApplySolidifyOnDegenerateGeometry:
    def test_a_mesh_without_faces_bakes_to_nothing_rather_than_erroring(
        self, make_object: MakeObject
    ) -> None:
        # Spec 8.2: Blender's Solidify accepts a face-less mesh and yields
        # nothing; the add-on has no reason to invent an error of its own.
        # MeshInvariants cannot describe a mesh with no vertices (there is
        # no bounding box), so the counts are read straight off the mesh.
        obj = make_object(bpy.data.meshes.new("TestEmpty"), "TestEmpty")

        ensure_solidify(obj, THICKNESS)
        apply_solidify(obj, bpy.context.evaluated_depsgraph_get())

        assert len(obj.data.polygons) == 0
        assert len(obj.data.vertices) == 0
