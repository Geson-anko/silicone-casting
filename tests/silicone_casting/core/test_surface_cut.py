"""Behaviour of the integrated Geometry Nodes Surface Cut modifier."""

from collections.abc import Iterator

import bpy
import pytest
from _helpers import MeshInvariants, make_cube_mesh

from silicone_casting.core.surface_cut import (
    SURFACE_CUT_MODIFIER_NAME,
    create_surface_cut,
)

THICKNESS = 1e-6
EDITABLE_THICKNESS = 0.1
UPDATED_THICKNESS = 0.2
MINIMUM_THICKNESS = 0.001
CORNER_THICKNESS = 0.2
TARGET_VOLUME = 4.0**3
# The bent surface has a constant 2D cross-section over a unit length. Its
# cutter area is t + a + ta, where Extrude Mesh's averaged face normal gives
# a = t / 2 without even thickness and the corner compensation gives a = t.
UNEVEN_CORNER_CUTTER_VOLUME = 0.32
EVEN_CORNER_CUTTER_VOLUME = 0.44
SURFACE_VERTICES = [
    (-2.0, -2.0, 0.0),
    (2.0, -2.0, 0.0),
    (2.0, 2.0, 0.0),
    (-2.0, 2.0, 0.0),
]
SURFACE_FACES = [(0, 1, 2, 3)]
DISTANT_SURFACE_VERTICES = [(x, y, z + 3.0) for x, y, z in SURFACE_VERTICES]
CORNER_SURFACE_VERTICES = [
    (0.0, 0.0, 0.0),
    (1.0, 0.0, 0.0),
    (1.0, 1.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 1.0, 1.0),
    (0.0, 0.0, 1.0),
]
CORNER_SURFACE_FACES = [(0, 1, 2, 3), (0, 3, 4, 5)]


@pytest.fixture
def surface_cut_objects(
    make_object,
) -> Iterator[tuple[bpy.types.Object, bpy.types.Object]]:
    existing_node_groups = set(bpy.data.node_groups.keys())
    target = make_object(make_cube_mesh(2.0, "TargetMesh"), "Target")
    surface_mesh = bpy.data.meshes.new("SurfaceMesh")
    surface_mesh.from_pydata(SURFACE_VERTICES, [], SURFACE_FACES)
    surface_mesh.update()
    surface = make_object(surface_mesh, "Surface")
    yield target, surface
    for node_group in tuple(bpy.data.node_groups):
        if node_group.name not in existing_node_groups:
            bpy.data.node_groups.remove(node_group)


def _evaluated_invariants(target: bpy.types.Object) -> MeshInvariants:
    evaluated = target.evaluated_get(bpy.context.evaluated_depsgraph_get())
    result = bpy.data.meshes.new_from_object(evaluated)
    try:
        return MeshInvariants.from_mesh(result)
    finally:
        bpy.data.meshes.remove(result)


def _thickness_socket(
    modifier: bpy.types.NodesModifier,
) -> bpy.types.NodeTreeInterfaceSocketFloatDistance:
    assert modifier.node_group is not None
    interface = modifier.node_group.interface
    assert interface is not None
    socket = next(item for item in interface.items_tree if item.name == "Thickness")
    assert isinstance(socket, bpy.types.NodeTreeInterfaceSocketFloatDistance)
    return socket


def _object_socket(
    modifier: bpy.types.NodesModifier,
) -> bpy.types.NodeTreeInterfaceSocketObject:
    assert modifier.node_group is not None
    interface = modifier.node_group.interface
    assert interface is not None
    socket = next(
        item for item in interface.items_tree if item.name == "Cutting Surface"
    )
    assert isinstance(socket, bpy.types.NodeTreeInterfaceSocketObject)
    return socket


def _even_thickness_socket(
    modifier: bpy.types.NodesModifier,
) -> bpy.types.NodeTreeInterfaceSocketBool:
    assert modifier.node_group is not None
    interface = modifier.node_group.interface
    assert interface is not None
    socket = next(
        item for item in interface.items_tree if item.name == "Even Thickness"
    )
    assert isinstance(socket, bpy.types.NodeTreeInterfaceSocketBool)
    return socket


def _solver_socket(
    modifier: bpy.types.NodesModifier,
) -> bpy.types.NodeTreeInterfaceSocketMenu:
    assert modifier.node_group is not None
    interface = modifier.node_group.interface
    assert interface is not None
    socket = next(item for item in interface.items_tree if item.name == "Solver")
    assert isinstance(socket, bpy.types.NodeTreeInterfaceSocketMenu)
    return socket


def _set_modifier_thickness(
    modifier: bpy.types.NodesModifier,
    socket: bpy.types.NodeTreeInterfaceSocketFloatDistance,
    value: float,
) -> None:
    properties = getattr(modifier, "properties", None)
    if properties is None:
        # Blender 5.1 stores Geometry Nodes inputs as modifier ID properties.
        modifier[socket.identifier] = value
    else:
        # Blender 5.2 exposes the same input through structured RNA.
        modifier_input = getattr(properties.inputs, socket.identifier)
        modifier_input.value = value


def _set_modifier_object(
    modifier: bpy.types.NodesModifier,
    socket: bpy.types.NodeTreeInterfaceSocketObject,
    value: bpy.types.Object,
) -> None:
    properties = getattr(modifier, "properties", None)
    if properties is None:
        modifier[socket.identifier] = value
    else:
        modifier_input = getattr(properties.inputs, socket.identifier)
        modifier_input.value = value


def _set_modifier_bool(
    modifier: bpy.types.NodesModifier,
    socket: bpy.types.NodeTreeInterfaceSocketBool,
    value: bool,
) -> None:
    properties = getattr(modifier, "properties", None)
    if properties is None:
        modifier[socket.identifier] = value
    else:
        modifier_input = getattr(properties.inputs, socket.identifier)
        modifier_input.value = value


def _set_modifier_solver_to_exact(
    modifier: bpy.types.NodesModifier,
    socket: bpy.types.NodeTreeInterfaceSocketMenu,
) -> None:
    properties = getattr(modifier, "properties", None)
    if properties is None:
        # Blender 5.1 stores menu items by their stable zero-based enum value.
        modifier[socket.identifier] = 1
    else:
        modifier_input = getattr(properties.inputs, socket.identifier)
        modifier_input.value = "Exact"


def test_one_modifier_performs_the_solidify_and_manifold_difference(
    surface_cut_objects: tuple[bpy.types.Object, bpy.types.Object],
) -> None:
    target, surface = surface_cut_objects

    modifier = create_surface_cut(
        target,
        surface,
        THICKNESS,
        minimum_thickness=THICKNESS,
    )

    assert modifier.name == SURFACE_CUT_MODIFIER_NAME
    assert modifier.type == "NODES"
    assert len(target.modifiers) == 1
    assert len(surface.modifiers) == 0

    invariants = _evaluated_invariants(target)

    assert invariants.vertex_count == 16
    # Internal triangulation may split caps; both components stay genus zero.
    assert invariants.vertex_count - invariants.edge_count + invariants.face_count == 4
    assert invariants.loose_part_count == 2
    assert invariants.is_watertight
    assert invariants.volume == pytest.approx(8.0 - 4.0 * THICKNESS, abs=1e-6)
    assert invariants.bbox_min == pytest.approx((-1.0, -1.0, -1.0))
    assert invariants.bbox_max == pytest.approx((1.0, 1.0, 1.0))


def test_modifier_thickness_is_exposed_and_live(
    surface_cut_objects: tuple[bpy.types.Object, bpy.types.Object],
) -> None:
    target, surface = surface_cut_objects
    modifier = create_surface_cut(
        target,
        surface,
        EDITABLE_THICKNESS,
        minimum_thickness=MINIMUM_THICKNESS,
    )
    socket = _thickness_socket(modifier)
    assert socket.default_value == pytest.approx(EDITABLE_THICKNESS)
    assert socket.min_value == pytest.approx(MINIMUM_THICKNESS)

    before = _evaluated_invariants(target)
    _set_modifier_thickness(modifier, socket, UPDATED_THICKNESS)
    target.update_tag(refresh={"DATA"})
    bpy.context.view_layer.update()
    after = _evaluated_invariants(target)

    assert before.volume == pytest.approx(8.0 - 4.0 * EDITABLE_THICKNESS)
    assert after.volume == pytest.approx(8.0 - 4.0 * UPDATED_THICKNESS)


def test_cutting_surface_object_is_exposed_and_live(
    surface_cut_objects: tuple[bpy.types.Object, bpy.types.Object],
    make_object,
) -> None:
    target, surface = surface_cut_objects
    distant_mesh = bpy.data.meshes.new("DistantSurfaceMesh")
    distant_mesh.from_pydata(DISTANT_SURFACE_VERTICES, [], SURFACE_FACES)
    distant_mesh.update()
    distant_surface = make_object(distant_mesh, "DistantSurface")
    modifier = create_surface_cut(
        target,
        surface,
        EDITABLE_THICKNESS,
        minimum_thickness=MINIMUM_THICKNESS,
    )
    socket = _object_socket(modifier)
    assert socket.default_value == surface

    before = _evaluated_invariants(target)
    _set_modifier_object(modifier, socket, distant_surface)
    target.update_tag(refresh={"DATA"})
    bpy.context.view_layer.update()
    after = _evaluated_invariants(target)

    assert before.volume == pytest.approx(8.0 - 4.0 * EDITABLE_THICKNESS)
    assert after.volume == pytest.approx(8.0)
    assert after.loose_part_count == 1


def test_even_thickness_input_compensates_a_sharp_corner(make_object) -> None:
    target = make_object(make_cube_mesh(4.0, "CornerTargetMesh"), "CornerTarget")
    surface_mesh = bpy.data.meshes.new("CornerSurfaceMesh")
    surface_mesh.from_pydata(
        CORNER_SURFACE_VERTICES,
        [],
        CORNER_SURFACE_FACES,
    )
    surface_mesh.update()
    surface = make_object(surface_mesh, "CornerSurface")
    modifier = create_surface_cut(
        target,
        surface,
        CORNER_THICKNESS,
        minimum_thickness=MINIMUM_THICKNESS,
    )
    socket = _even_thickness_socket(modifier)
    assert not socket.default_value

    uneven = _evaluated_invariants(target)
    _set_modifier_bool(modifier, socket, True)
    target.update_tag(refresh={"DATA"})
    bpy.context.view_layer.update()
    even = _evaluated_invariants(target)

    assert uneven.is_watertight
    assert even.is_watertight
    assert uneven.volume == pytest.approx(
        TARGET_VOLUME - UNEVEN_CORNER_CUTTER_VOLUME,
        abs=1e-6,
    )
    assert even.volume == pytest.approx(
        TARGET_VOLUME - EVEN_CORNER_CUTTER_VOLUME,
        abs=1e-6,
    )


def test_solver_input_offers_manifold_and_exact_and_exact_evaluates(
    surface_cut_objects: tuple[bpy.types.Object, bpy.types.Object],
) -> None:
    target, surface = surface_cut_objects
    modifier = create_surface_cut(
        target,
        surface,
        EDITABLE_THICKNESS,
        minimum_thickness=MINIMUM_THICKNESS,
    )
    socket = _solver_socket(modifier)
    assert socket.default_value == "Manifold"
    assert modifier.node_group is not None
    menu = next(
        node
        for node in modifier.node_group.nodes
        if isinstance(node, bpy.types.GeometryNodeMenuSwitch)
    )
    assert [item.name for item in menu.enum_definition.enum_items] == [
        "Manifold",
        "Exact",
    ]
    booleans = [
        node
        for node in modifier.node_group.nodes
        if isinstance(node, bpy.types.GeometryNodeMeshBoolean)
    ]
    assert {node.solver for node in booleans} == {"MANIFOLD", "EXACT"}

    _set_modifier_solver_to_exact(modifier, socket)
    target.update_tag(refresh={"DATA"})
    bpy.context.view_layer.update()
    exact = _evaluated_invariants(target)

    assert exact.is_watertight
    assert exact.volume == pytest.approx(8.0 - 4.0 * EDITABLE_THICKNESS)
