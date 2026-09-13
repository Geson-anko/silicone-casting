"""Executable spec for adding configured Boolean modifiers.

The tests use Blender's real object and modifier data APIs. Nothing in
``bpy`` is mocked.
"""

from collections.abc import Callable, Iterator
from typing import cast

import bpy
import pytest
from _helpers import make_cube_mesh

import silicone_casting
from silicone_casting.core import SURFACE_CUT_MODIFIER_NAME
from silicone_casting.operators import (
    SILCAST_OT_add_boolean,
    SILCAST_OT_add_surface_cut,
)

CUBE_SIZE = 2.0

type AddObject = Callable[..., bpy.types.Object]


@pytest.fixture(scope="module")
def registered() -> Iterator[None]:
    silicone_casting.register()
    yield
    silicone_casting.unregister()


@pytest.fixture
def settings(registered: None) -> Iterator[bpy.types.PropertyGroup]:
    props = bpy.context.scene.silicone_casting
    props.boolean_operand = None
    props.boolean_solver = "EXACT"
    props.surface_cut_thickness_mm = 0.001
    yield props
    props.boolean_operand = None


@pytest.fixture
def add_object(registered: None) -> Iterator[AddObject]:
    for existing in bpy.context.scene.objects:
        existing.select_set(False)
    bpy.context.view_layer.objects.active = None

    created: list[bpy.types.Object] = []
    existing_node_groups = set(bpy.data.node_groups.keys())

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

    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    datablocks = {(type(obj.data).__name__, obj.data.name): obj.data for obj in created}
    for obj in created:
        bpy.data.objects.remove(obj)
    bpy.data.batch_remove([data for data in datablocks.values() if data.users == 0])
    for node_group in tuple(bpy.data.node_groups):
        if node_group.name not in existing_node_groups:
            bpy.data.node_groups.remove(node_group)


def _set_inputs(
    settings: bpy.types.PropertyGroup,
    add_object: AddObject,
    *,
    operand_selected: bool = False,
) -> tuple[bpy.types.Object, bpy.types.Object]:
    target = add_object("Target")
    operand = add_object("Operand", select=operand_selected)
    bpy.context.view_layer.objects.active = target
    settings.boolean_operand = operand
    return target, operand


class TestWhenTheButtonIsClickable:
    def test_a_selected_active_mesh_and_a_different_mesh_operand_are_required(
        self, settings: bpy.types.PropertyGroup, add_object: AddObject
    ) -> None:
        target, _operand = _set_inputs(settings, add_object)

        assert target.select_get()
        assert SILCAST_OT_add_boolean.poll(bpy.context)

    def test_the_button_is_disabled_without_an_operand(
        self, settings: bpy.types.PropertyGroup, add_object: AddObject
    ) -> None:
        target = add_object("Target")
        bpy.context.view_layer.objects.active = target

        assert not SILCAST_OT_add_boolean.poll(bpy.context)

    def test_the_button_is_disabled_when_target_and_operand_are_the_same(
        self, settings: bpy.types.PropertyGroup, add_object: AddObject
    ) -> None:
        target = add_object("Target")
        bpy.context.view_layer.objects.active = target
        settings.boolean_operand = target

        assert not SILCAST_OT_add_boolean.poll(bpy.context)

    def test_the_button_is_disabled_when_the_active_target_is_not_selected(
        self, settings: bpy.types.PropertyGroup, add_object: AddObject
    ) -> None:
        target, _operand = _set_inputs(settings, add_object)
        target.select_set(False)

        assert not SILCAST_OT_add_boolean.poll(bpy.context)

    def test_the_button_is_disabled_for_a_non_mesh_operand(
        self, settings: bpy.types.PropertyGroup, add_object: AddObject
    ) -> None:
        target = add_object("Target")
        camera = add_object("Camera", bpy.data.cameras.new("CameraData"), select=False)
        bpy.context.view_layer.objects.active = target
        settings.boolean_operand = camera

        assert not SILCAST_OT_add_boolean.poll(bpy.context)

    def test_the_button_is_disabled_outside_object_mode(
        self, settings: bpy.types.PropertyGroup, add_object: AddObject
    ) -> None:
        _set_inputs(settings, add_object)
        bpy.ops.object.mode_set(mode="EDIT")

        assert not SILCAST_OT_add_boolean.poll(bpy.context)


class TestAddingABooleanModifier:
    @pytest.mark.parametrize("operation", ("DIFFERENCE", "UNION", "INTERSECT"))
    def test_each_operation_reaches_a_new_modifier(
        self,
        operation: str,
        settings: bpy.types.PropertyGroup,
        add_object: AddObject,
    ) -> None:
        target, operand = _set_inputs(settings, add_object)

        result = bpy.ops.silicone_casting.add_boolean(operation=operation)

        assert result == {"FINISHED"}
        assert len(target.modifiers) == 1
        modifier = target.modifiers[0]
        assert modifier.type == "BOOLEAN"
        assert modifier.operation == operation
        assert modifier.operand_type == "OBJECT"
        assert modifier.object == operand

    @pytest.mark.parametrize("solver", ("MANIFOLD", "EXACT", "FLOAT"))
    def test_each_solver_reaches_the_modifier(
        self,
        solver: str,
        settings: bpy.types.PropertyGroup,
        add_object: AddObject,
    ) -> None:
        target, _operand = _set_inputs(settings, add_object)
        settings.boolean_solver = solver

        result = bpy.ops.silicone_casting.add_boolean(operation="DIFFERENCE")

        assert result == {"FINISHED"}
        assert target.modifiers[0].solver == solver

    def test_repeating_the_action_adds_another_modifier(
        self, settings: bpy.types.PropertyGroup, add_object: AddObject
    ) -> None:
        target, _operand = _set_inputs(settings, add_object)

        bpy.ops.silicone_casting.add_boolean(operation="DIFFERENCE")
        bpy.ops.silicone_casting.add_boolean(operation="DIFFERENCE")

        assert [modifier.type for modifier in target.modifiers] == [
            "BOOLEAN",
            "BOOLEAN",
        ]

    def test_only_the_active_target_receives_the_modifier(
        self, settings: bpy.types.PropertyGroup, add_object: AddObject
    ) -> None:
        target, operand = _set_inputs(settings, add_object, operand_selected=True)
        other = add_object("OtherSelected")

        bpy.ops.silicone_casting.add_boolean(operation="UNION")

        assert len(target.modifiers) == 1
        assert len(operand.modifiers) == 0
        assert len(other.modifiers) == 0


class TestAddingASurfaceCut:
    def test_the_target_gets_one_integrated_surface_cut_modifier(
        self, settings: bpy.types.PropertyGroup, add_object: AddObject
    ) -> None:
        target, surface = _set_inputs(settings, add_object)

        result = bpy.ops.silicone_casting.add_surface_cut()

        assert result == {"FINISHED"}
        assert len(target.modifiers) == 1
        modifier = target.modifiers[0]
        assert modifier.name == SURFACE_CUT_MODIFIER_NAME
        assert modifier.type == "NODES"
        assert len(surface.modifiers) == 0
        modifier = cast(bpy.types.NodesModifier, modifier)
        assert modifier.node_group is not None
        interface = modifier.node_group.interface
        assert interface is not None
        cutting_surface = next(
            item for item in interface.items_tree if item.name == "Cutting Surface"
        )
        even_thickness = next(
            item for item in interface.items_tree if item.name == "Even Thickness"
        )
        solver = next(item for item in interface.items_tree if item.name == "Solver")
        assert cutting_surface.default_value == surface
        assert not even_thickness.default_value
        assert solver.default_value == "Manifold"

    def test_configured_thickness_and_minimum_reach_the_modifier_in_scene_units(
        self, settings: bpy.types.PropertyGroup, add_object: AddObject
    ) -> None:
        target, _surface = _set_inputs(settings, add_object)
        settings.surface_cut_thickness_mm = 0.25
        original_scale = bpy.context.scene.unit_settings.scale_length
        bpy.context.scene.unit_settings.scale_length = 0.001
        try:
            result = bpy.ops.silicone_casting.add_surface_cut()
        finally:
            bpy.context.scene.unit_settings.scale_length = original_scale

        assert result == {"FINISHED"}
        modifier = cast(bpy.types.NodesModifier, target.modifiers[0])
        assert modifier.node_group is not None
        interface = modifier.node_group.interface
        assert interface is not None
        thickness = next(
            item for item in interface.items_tree if item.name == "Thickness"
        )
        assert isinstance(thickness, bpy.types.NodeTreeInterfaceSocketFloatDistance)
        # One BU represents one millimetre in this scene.
        assert thickness.default_value == pytest.approx(0.25)
        assert thickness.min_value == pytest.approx(0.001)

    def test_the_integrated_boolean_offers_manifold_and_exact_difference(
        self, settings: bpy.types.PropertyGroup, add_object: AddObject
    ) -> None:
        target, _surface = _set_inputs(settings, add_object)
        settings.boolean_solver = "FLOAT"

        result = bpy.ops.silicone_casting.add_surface_cut()

        assert result == {"FINISHED"}
        modifier = cast(bpy.types.NodesModifier, target.modifiers[0])
        assert modifier.node_group is not None
        booleans = [
            node
            for node in modifier.node_group.nodes
            if isinstance(node, bpy.types.GeometryNodeMeshBoolean)
        ]
        assert len(booleans) == 2
        assert all(node.operation == "DIFFERENCE" for node in booleans)
        assert {node.solver for node in booleans} == {"MANIFOLD", "EXACT"}

    def test_repeating_the_action_adds_another_integrated_modifier(
        self, settings: bpy.types.PropertyGroup, add_object: AddObject
    ) -> None:
        target, surface = _set_inputs(settings, add_object)

        bpy.ops.silicone_casting.add_surface_cut()
        bpy.ops.silicone_casting.add_surface_cut()

        assert len(surface.modifiers) == 0
        assert [modifier.type for modifier in target.modifiers] == ["NODES", "NODES"]


@pytest.mark.api_contract
def test_boolean_operator_keeps_its_public_surface(registered: None) -> None:
    assert SILCAST_OT_add_boolean.bl_idname == "silicone_casting.add_boolean"
    properties = bpy.ops.silicone_casting.add_boolean.get_rna_type().properties
    identifiers = {item.identifier for item in properties["operation"].enum_items}
    assert identifiers == {"DIFFERENCE", "UNION", "INTERSECT"}


@pytest.mark.api_contract
def test_surface_cut_operator_keeps_its_public_idname(registered: None) -> None:
    assert SILCAST_OT_add_surface_cut.bl_idname == "silicone_casting.add_surface_cut"
